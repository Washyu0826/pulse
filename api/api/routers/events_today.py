"""今日事件 endpoint — 讀 pipeline 產出的忠實摘要 JSONL（DB-optional，不查資料庫）。

前端 `web/lib/api.ts` 的 `getTodayEvents()` 會打 `/api/events/today`，期望拿到一串
`EventSummary`（見 web/lib/types.ts）。後端事件摘要 pipeline 會把每個事件寫成 JSONL 的一行，
本端點直接讀那個檔案並轉成前端要的形狀；檔案不存在或為空時回 `[]`（前端會優雅降級為空狀態）。

設計取捨：刻意不經 DB（不需 Docker/Postgres 也能跑），來源檔路徑由設定
`PULSE_EVENTS_FILE` 控制（見 api/api/config.py）。
"""
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from api.config import settings

router = APIRouter()

# 前端 ThemeLabel 的合法值（與 web/lib/types.ts 對齊）；未知/缺值一律兜底為「其他」。
_VALID_THEMES = {"新工具", "模型動態", "使用方法", "風險限制", "倫理法規", "其他"}


class EventCitation(BaseModel):
    """一筆出處引用：對應摘要中的 [n] 標記，連向原貼文。"""

    n: int
    url: str | None = None
    # 對外用 camelCase（postId）以符合前端型別；同時接受 snake_case 輸入別名。
    post_id: str | None = Field(default=None, serialization_alias="postId")

    model_config = {"populate_by_name": True}


class EventSummary(BaseModel):
    """一則今日事件：多篇相關貼文聚成事件 + 忠實摘要（含行內出處引用）。"""

    id: str
    title: str
    summary: str
    citations: list[EventCitation] = Field(default_factory=list)
    member_count: int = Field(default=0, serialization_alias="memberCount")
    theme: str = "其他"

    model_config = {"populate_by_name": True}


def _coerce_theme(value: Any) -> str:
    """主題兜底：非合法主題（含 None）一律回「其他」，與前端 themeMeta() 行為一致。"""
    return value if value in _VALID_THEMES else "其他"


def _parse_citation(raw: Any, fallback_n: int) -> EventCitation | None:
    """把一筆 raw citation 轉成 EventCitation；無法解析則回 None（略過）。"""
    if not isinstance(raw, dict):
        return None
    n = raw.get("n", fallback_n)
    try:
        n = int(n)
    except (TypeError, ValueError):
        n = fallback_n
    post_id = raw.get("post_id")
    return EventCitation(
        n=n,
        url=raw.get("url"),
        post_id=str(post_id) if post_id is not None else None,
    )


def _map_record(rec: dict[str, Any], fallback_id: int) -> EventSummary | None:
    """把一行 pipeline JSONL 記錄轉成對外的 EventSummary；缺關鍵欄位則回 None。

    欄位對映（pipeline → 前端）：
      event_id     → id
      title        → title
      summary      → summary
      citations[]  → citations[]（n/url/post_id → n/url/postId）
      member_count → memberCount
      theme        → theme（未知值兜底「其他」）
    刻意丟棄後端專用欄位（faithfulness_score / issues）。
    """
    eid = rec.get("event_id")
    if eid is None:
        eid = fallback_id
    summary = rec.get("summary")
    if not isinstance(summary, str):
        # 沒有忠實摘要文字的記錄對前端無意義，略過。
        return None

    raw_citations = rec.get("citations")
    citations: list[EventCitation] = []
    if isinstance(raw_citations, list):
        for i, raw in enumerate(raw_citations, 1):
            cit = _parse_citation(raw, fallback_n=i)
            if cit is not None:
                citations.append(cit)

    member_count = rec.get("member_count")
    if not isinstance(member_count, int):
        member_count = 0

    return EventSummary(
        id=str(eid),
        title=str(rec.get("title", "")),
        summary=summary,
        citations=citations,
        member_count=member_count,
        theme=_coerce_theme(rec.get("theme")),
    )


def _load_events(path: Path, limit: int) -> list[EventSummary]:
    """讀 JSONL（一行一事件），轉成 EventSummary 串列；檔案不存在 / 空 / 壞行都優雅處理。"""
    if not path.exists():
        return []
    out: list[EventSummary] = []
    with path.open(encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                # 單行壞掉不該讓整個 endpoint 失敗 —— 略過該行。
                continue
            if not isinstance(rec, dict):
                continue
            summary = _map_record(rec, fallback_id=i)
            if summary is not None:
                out.append(summary)
            if len(out) >= limit:
                break
    return out


@router.get(
    "/events/today",
    response_model=list[EventSummary],
    response_model_by_alias=True,
)
async def today_events(
    limit: int = Query(8, ge=1, le=100, description="最多回傳幾則事件"),
) -> list[EventSummary]:
    """今日忠實事件摘要（讀 pipeline 產出檔，不查 DB）。

    來源檔由設定 `PULSE_EVENTS_FILE` 指定；檔案不存在或為空時回 `[]`。
    """
    path = Path(settings.events_file)
    return _load_events(path, limit=limit)
