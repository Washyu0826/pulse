"""storyline_core 純函式測試 —— 共用時間軸建構（build_timeline / mark_peak）。

不需 DB / Ollama / 網路：直接用假的 DayEvent 序列驗證「同日合併 + 逐日 volume + velocity/state
+ 標全局高峰」的行為，覆蓋 prototype（原始加總 volume + 啟發式 state）與 production
（hotness.day_volume + hotness.velocity/state）兩種注入策略。
"""
import math
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]  # D:\pulse
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "ml"))

import storyline_core  # noqa: E402
from ml import hotness  # noqa: E402


@dataclass
class _FakeEvent:
    """build_timeline 只用到 DayEvent 的這些欄位。"""
    day: date
    rep_title: str
    member_count: int
    volume: int
    sources: list
    themes: list
    rep_url: str | None = None
    sentiments: list = field(default_factory=list)


@dataclass
class _FakeStoryline:
    events: list


def _d(n: int) -> date:
    return date(2026, 6, n)


# ---------------------------------------------------------------------------
# prototype 策略：volume = 原始互動加總；state = _state_label 啟發式
# ---------------------------------------------------------------------------
def _proto_state(cells):
    """重現 prototype _state_label + mark_peak（不 import 重依賴的 prototype_storyline）。"""
    vols = [c["volume"] for c in cells]
    for k, c in enumerate(cells):
        prev = vols[k - 1] if k > 0 else None
        if prev is None:
            c["velocity"], c["state"] = c["volume"], "升溫(出現)"
        else:
            vel = c["volume"] - prev
            c["velocity"] = vel
            c["state"] = "升溫" if vel > 0 else ("高檔持平" if vel == 0 else "退燒")
    storyline_core.mark_peak(cells)


def test_prototype_timeline_merges_same_day_and_marks_peak():
    s = _FakeStoryline([
        # day 1: 兩個日事件 → 合併成一格（volume 10+5=15、members 3+2=5、headline 取 volume 大者）
        _FakeEvent(_d(1), "小事件", 2, 5, ["devto"], ["新工具"]),
        _FakeEvent(_d(1), "大事件", 3, 10, ["hackernews"], ["模型動態"]),
        # day 2: 升到 30（全局高峰）
        _FakeEvent(_d(2), "高峰日", 6, 30, ["hackernews"], ["模型動態"]),
        # day 3: 退到 8
        _FakeEvent(_d(3), "退燒日", 2, 8, ["devto"], ["新工具"]),
    ])
    cells = storyline_core.build_timeline(
        s, volume_fn=lambda m, i: i, state_fn=_proto_state, with_sentiment_citations=False,
    )
    assert [c["date"] for c in cells] == ["2026-06-01", "2026-06-02", "2026-06-03"]
    # 同日合併
    assert cells[0]["volume"] == 15 and cells[0]["members"] == 5
    assert cells[0]["headline"] == "大事件"  # volume 大者
    # velocity / state（日對日）
    assert cells[0]["state"] == "升溫(出現)"
    assert cells[1]["velocity"] == 15 and cells[1]["state"] == "高峰"  # 升溫但被標高峰
    assert cells[2]["velocity"] == -22 and cells[2]["state"] == "退燒"
    # sources/themes 仍是集合（呼叫端負責排序）；內部暫存欄位已清掉
    assert isinstance(cells[0]["sources"], set)
    assert "_top_vol" not in cells[0] and "_interaction" not in cells[0]
    # prototype 不帶 sentiment/citations 欄位
    assert "_rep_url" not in cells[0] and "_sentiments" not in cells[0]


# ---------------------------------------------------------------------------
# production 策略：volume = hotness.day_volume；state = hotness.velocity/state
# ---------------------------------------------------------------------------
def _prod_state(cells):
    daily = [c["volume"] for c in cells]
    for k, c in enumerate(cells):
        prefix = daily[: k + 1]
        c["velocity"] = round(hotness.velocity(prefix), 3)
        c["state"] = hotness.storyline_state(prefix)
    storyline_core.mark_peak(cells)


def test_production_timeline_uses_hotness_and_keeps_sentiment_citations():
    s = _FakeStoryline([
        _FakeEvent(_d(1), "首日", 3, 10, ["hackernews"], ["模型動態"],
                   rep_url="https://example.com/1", sentiments=["positive", "neutral"]),
        _FakeEvent(_d(2), "次日", 6, 40, ["devto"], ["新工具"],
                   rep_url="https://example.com/2", sentiments=["negative"]),
    ])
    cells = storyline_core.build_timeline(
        s,
        volume_fn=lambda m, i: round(hotness.day_volume(m, i), 3),
        state_fn=_prod_state,
        with_sentiment_citations=True,
    )
    assert len(cells) == 2
    assert cells[0]["volume"] == round(hotness.day_volume(3, 10), 3)
    assert cells[1]["volume"] == round(hotness.day_volume(6, 40), 3)
    # velocity = 末日 - 前日（已四捨五入）
    assert cells[1]["velocity"] == round(cells[1]["volume"] - cells[0]["volume"], 3)
    # day2 為全局高峰
    assert cells[1]["state"] == "高峰"
    # production 保留 sentiment/citations 暫存欄位供呼叫端用
    assert cells[0]["_rep_url"] == "https://example.com/1"
    assert cells[0]["_sentiments"] == ["positive", "neutral"]
    assert cells[1]["_rep_url"] == "https://example.com/2"


def test_single_day_no_peak_marking():
    s = _FakeStoryline([_FakeEvent(_d(5), "只有一天", 2, 7, ["devto"], [])])
    cells = storyline_core.build_timeline(
        s, volume_fn=lambda m, i: i, state_fn=_proto_state, with_sentiment_citations=False,
    )
    assert len(cells) == 1
    # 單日不標高峰（mark_peak 對 1 格不動作）→ 維持 state_fn 給的「升溫(出現)」
    assert cells[0]["state"] == "升溫(出現)"


def test_mark_peak_picks_global_max():
    cells = [{"volume": 3, "state": "x"}, {"volume": 9, "state": "y"}, {"volume": 5, "state": "z"}]
    storyline_core.mark_peak(cells)
    assert cells[1]["state"] == "高峰"
    assert cells[0]["state"] == "x" and cells[2]["state"] == "z"


def test_day_volume_formula_sanity():
    # day_volume = members + log1p(interaction)
    assert hotness.day_volume(3, 10) == 3 + math.log1p(10)
