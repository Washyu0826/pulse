"""議題時間軸（storylines）endpoint — 讀 build_storylines.py 產出的跨日議題鏈 JSONL（DB-optional）。

前端 `web/lib/api.ts` 的 `getStorylines()` 會打 `/api/storylines`，期望拿到一串 `Storyline`
（見 web/lib/types.ts）。產製器把每條議題鏈寫成 JSONL 的一行，本端點直接讀那個檔案並轉成
前端要的形狀；檔案不存在或為空時回 `[]`（前端優雅降級為空狀態）。

設計取捨（比照 routers/events_today.py）：刻意不經 DB（不需 Docker/Postgres 也能跑），
來源檔路徑由設定 `PULSE_STORYLINES_FILE` 控制（見 api/api/config.py）。
"""
import logging
import sys
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from api.config import settings

# 重用 monorepo 的 ml 純函式（共用 JSONL 讀檔；與 routers/collection.py 同作法：
# 把 D:\pulse\ml 加進 path）。read_jsonl 無重依賴，import 安全。
_ML = Path(__file__).resolve().parents[3] / "ml"
if str(_ML) not in sys.path:
    sys.path.insert(0, str(_ML))

from ml.jsonlio import read_jsonl  # noqa: E402

logger = logging.getLogger("pulse.api")

router = APIRouter()

# 來源檔新鮮度上限：產製器每日重產，超過此時長未更新視為「陳舊」（記 warning）。
_STALE_AFTER_S = 36 * 3600

# 合法狀態（與 ml/ml/hotness.py 狀態字串對齊）；未知值兜底為「升溫」。
_VALID_STATES = {"升溫", "高峰", "退燒", "持平"}
_VALID_THEMES = {"新工具", "模型動態", "使用方法", "風險限制", "倫理法規", "其他"}


class StorylineCitation(BaseModel):
    """一筆出處引用：對應時間軸某日的代表貼文。"""

    n: int
    url: str | None = None
    title: str | None = None


class TimelinePoint(BaseModel):
    """議題鏈某一天的一格：聲量 / 速度 / 狀態 / 一句重點 / 來源。"""

    date: str
    summary: str = ""
    volume: float = 0.0
    velocity: float = 0.0
    state: str = "升溫"
    sentiment: str | None = None
    sources: list[str] = Field(default_factory=list)
    members: int = 0


class Storyline(BaseModel):
    """一條議題時間軸：同議題的跨日事件鏈，含每日聲量走勢與升溫/退燒狀態。"""

    id: str
    title: str
    state: str = "升溫"
    hotness: float = 0.0
    span_days: int = Field(default=0, serialization_alias="spanDays")
    theme: str = "其他"
    timeline: list[TimelinePoint] = Field(default_factory=list)
    citations: list[StorylineCitation] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


def _coerce_state(value: Any) -> str:
    return value if value in _VALID_STATES else "升溫"


def _coerce_theme(value: Any) -> str:
    return value if value in _VALID_THEMES else "其他"


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_timeline(raw: Any) -> list[TimelinePoint]:
    points: list[TimelinePoint] = []
    if not isinstance(raw, list):
        return points
    for item in raw:
        if not isinstance(item, dict):
            continue
        d = item.get("date")
        if not isinstance(d, str):
            continue  # 沒有日期的格對前端無意義
        srcs = item.get("sources")
        members = item.get("members")
        points.append(
            TimelinePoint(
                date=d,
                summary=str(item.get("summary", "")),
                volume=_num(item.get("volume")),
                velocity=_num(item.get("velocity")),
                state=_coerce_state(item.get("state")),
                sentiment=item.get("sentiment") if isinstance(item.get("sentiment"), str) else None,
                sources=[str(s) for s in srcs] if isinstance(srcs, list) else [],
                members=int(members) if isinstance(members, int) else 0,
            )
        )
    return points


def _parse_citations(raw: Any) -> list[StorylineCitation]:
    cits: list[StorylineCitation] = []
    if not isinstance(raw, list):
        return cits
    for i, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            continue
        n = item.get("n", i)
        try:
            n = int(n)
        except (TypeError, ValueError):
            n = i
        cits.append(
            StorylineCitation(
                n=n,
                url=item.get("url") if isinstance(item.get("url"), str) else None,
                title=item.get("title") if isinstance(item.get("title"), str) else None,
            )
        )
    return cits


def _map_record(rec: dict[str, Any], fallback_id: int) -> Storyline | None:
    """把一行 JSONL 記錄轉成對外 Storyline；缺關鍵欄位（title / timeline）則回 None。"""
    title = rec.get("title")
    if not isinstance(title, str) or not title.strip():
        return None
    timeline = _parse_timeline(rec.get("timeline"))
    if not timeline:
        return None  # 沒有時間軸的議題鏈對前端無意義
    sid = rec.get("id")
    span = rec.get("span_days")
    return Storyline(
        id=str(sid) if sid is not None else f"story_{fallback_id:03d}",
        title=title,
        state=_coerce_state(rec.get("state")),
        hotness=_num(rec.get("hotness")),
        span_days=int(span) if isinstance(span, int) else len(timeline),
        theme=_coerce_theme(rec.get("theme")),
        timeline=timeline,
        citations=_parse_citations(rec.get("citations")),
    )


def _load_storylines(path: Path, limit: int) -> list[Storyline]:
    """讀 JSONL（一行一議題鏈）→ Storyline 串列；檔案不存在 / 空 / 壞行都優雅處理。"""
    if not path.exists():
        logger.warning(
            "storylines 來源檔不存在：%s（回空清單；檢查 build_storylines 是否有產出）", path
        )
        return []
    age_s = time.time() - path.stat().st_mtime
    if age_s > _STALE_AFTER_S:
        logger.warning(
            "storylines 來源檔陳舊：%s（已 %.1fh 未更新，上限 %.0fh）—— 上游可能斷流",
            path, age_s / 3600, _STALE_AFTER_S / 3600,
        )
    out: list[Storyline] = []
    for i, rec in enumerate(read_jsonl(path), 1):
        story = _map_record(rec, fallback_id=i)
        if story is not None:
            out.append(story)
        if len(out) >= limit:
            break
    return out


@router.get(
    "/storylines",
    response_model=list[Storyline],
    response_model_by_alias=True,
)
async def storylines(
    limit: int = Query(12, ge=1, le=100, description="最多回傳幾條議題鏈"),
) -> list[Storyline]:
    """議題時間軸（跨日議題鏈 + 每日聲量走勢 + 升溫/退燒狀態），讀產製檔，不查 DB。

    來源檔由設定 `PULSE_STORYLINES_FILE` 指定；檔案不存在或為空時回 `[]`。
    """
    path = Path(settings.storylines_file)
    return _load_storylines(path, limit=limit)
