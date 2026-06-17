"""storyline 共用核心 —— prototype_storyline 與 build_storylines 的去重底層。

兩支腳本（原型 / 正式 producer）的「逐日合併成時間軸 + 算 velocity/狀態 + 標高峰」與
「argparse / 時間窗 / 逐日 fetch 迴圈 / 資料不足 bail / 嵌入 / 逐日分群 / 跨日鏈結」原本各寫
一遍。本模組把這兩段共用骨架抽出，**行為與原本兩支腳本完全等價**：

- build_timeline(...)：逐日合併 + 逐格 velocity/state + 標全局高峰的單一實作；
  volume 與 velocity/state 演算法由呼叫端以 callable 注入（prototype 用原始加總 + 啟發式
  _state_label；production 用 hotness.day_volume + hotness.velocity/storyline_state），
  另以 with_sentiment_citations 開關決定要不要帶 sentiment/citations/url（production 才要）。

- add_common_args(...) / compute_window(...) / fetch_days(...) / cluster_and_link(...)：
  CLI 參數、時間窗、逐日撈文、嵌入分群與跨日鏈結的共用骨架。

全程沿用既有積木（event_cluster / ollama embedder / hotness / AsyncSessionLocal），純函式優先、
不碰 DB schema / API / 前端。
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date, timedelta
from typing import Callable, Optional


# ---------------------------------------------------------------------------
# 共用：逐日合併 + 時間軸建構
# ---------------------------------------------------------------------------
def build_timeline(
    storyline,
    *,
    volume_fn: Callable[[int, int], float],
    state_fn: Callable[[list[float]], None],
    with_sentiment_citations: bool = False,
) -> list[dict]:
    """把一條跨日 Storyline 攤平成「每天一格」的時間軸（日期升冪）。

    同一天可能有多個日事件 → 先合併成一格：members / interaction 相加、headline 取當天最大
    規模（volume）者、sources/themes 取聯集；再算各日 volume、velocity 與狀態，最後標全局高峰。

    呼叫端注入策略以保留各自原本語意：
    - volume_fn(members, interaction) -> float：把合併後的（成員數、互動總和）換算成當日聲量。
      * prototype：lambda members, interaction: interaction（純原始互動加總）。
      * production：lambda members, interaction: round(hotness.day_volume(members, interaction), 3)。
    - state_fn(cells) -> None：就地填入每格的 "velocity" 與 "state"，並標全局高峰。
      （velocity/state 演算法 prototype 與 production 不同，整段邏輯各自封裝注入。）

    with_sentiment_citations=True（production）時，額外保留 _rep_url / _sentiments，供呼叫端
    產 citations / sentiment 與 summary 欄位；False（prototype）時保留 headline/themes 原樣。
    """
    by_day: dict[date, dict] = {}
    for e in storyline.events:
        cell = by_day.get(e.day)
        if cell is None:
            cell = {
                "date": e.day.isoformat(),
                "members": 0,
                "_interaction": 0,
                "headline": e.rep_title,
                "_top_vol": -1,
                "sources": set(),
                "themes": set(),
            }
            if with_sentiment_citations:
                cell["_rep_url"] = e.rep_url
                cell["_sentiments"] = []
            by_day[e.day] = cell
        cell["members"] += e.member_count
        cell["_interaction"] += e.volume
        cell["sources"].update(e.sources)
        cell["themes"].update(e.themes)
        if with_sentiment_citations:
            cell["_sentiments"].extend(e.sentiments)
        if e.volume > cell["_top_vol"]:
            cell["_top_vol"] = e.volume
            cell["headline"] = e.rep_title
            if with_sentiment_citations:
                cell["_rep_url"] = e.rep_url

    cells = [by_day[d] for d in sorted(by_day)]

    # 每日聲量（策略注入）。
    for c in cells:
        c["volume"] = volume_fn(c["members"], c["_interaction"])

    # velocity / state（+ 標全局高峰；策略注入）。
    state_fn(cells)

    # 清掉內部暫存欄位。
    for c in cells:
        c.pop("_top_vol", None)
        c.pop("_interaction", None)

    return cells


def mark_peak(cells: list[dict]) -> None:
    """多天才標：全局聲量最高那天蓋成「高峰」（單日不蓋）。兩支腳本共用。"""
    if len(cells) > 1:
        peak_k = max(range(len(cells)), key=lambda i: cells[i]["volume"])
        cells[peak_k]["state"] = "高峰"


# ---------------------------------------------------------------------------
# 共用：CLI / 時間窗 / 撈文 / 分群鏈結 骨架
# ---------------------------------------------------------------------------
def add_common_args(ap: argparse.ArgumentParser, *, default_top: int) -> None:
    """加兩支腳本共用的 CLI 參數（top 預設不同 → 由呼叫端給）。"""
    ap.add_argument("--days", type=int, default=21, help="回看天數（含今天）")
    ap.add_argument("--per-day-cap", type=int, default=80, help="每天最多納入幾篇（控時間）")
    ap.add_argument("--min-quality", type=int, default=30)
    ap.add_argument("--sources", nargs="+", default=["hackernews", "devto"])
    ap.add_argument("--include-threads", action="store_true",
                    help="額外納入 threads（內文剛清洗）")
    ap.add_argument("--cluster-threshold", type=float, default=0.75, help="逐日分群餘弦門檻")
    ap.add_argument("--min-size", type=int, default=2, help="日事件最小成員數")
    ap.add_argument("--link-threshold", type=float, default=0.7, help="跨日鏈結餘弦門檻（甜蜜點）")
    ap.add_argument("--max-gap", type=int, default=1, help="跨日鏈結容忍最大天數間隔（1=相鄰日）")
    ap.add_argument("--top", type=int, default=default_top, help="處理前幾條最熱 storyline")
    ap.add_argument("--summarize", action="store_true", help="用 qwen 產摘要（較慢）")
    ap.add_argument("--embed-model", default="nomic-embed-text")
    ap.add_argument("--gen-model", default="qwen2.5:7b")


def resolve_sources(args) -> list[str]:
    """合併 --sources 與 --include-threads。"""
    sources = list(args.sources)
    if args.include_threads and "threads" not in sources:
        sources.append("threads")
    return sources


def compute_window(days_back: int) -> list[date]:
    """回傳含今天、升冪排列的 days_back 天日期清單。"""
    today = date.today()
    return [today - timedelta(days=i) for i in range(days_back - 1, -1, -1)]


def fetch_days(days: list[date], sources: list[str], min_quality: int, cap: int,
               fetch_one) -> list[tuple[date, list[dict]]]:
    """逐日撈貼文（共用 _fetch_all 迴圈）。fetch_one 為 async 撈單日的 callable。"""
    async def _fetch_all():
        out = []
        for d in days:
            out.append((d, await fetch_one(d, sources, min_quality, cap)))
        return out

    return asyncio.run(_fetch_all())


def cluster_and_link(days_data, embed_fn, *, cluster_threshold, min_size,
                     link_threshold, max_gap, build_day_events, link_storylines):
    """逐日分群 + 嵌入 + 跨日鏈結（共用骨架）。回傳 (days_events, storylines)。"""
    days_events = build_day_events(
        days_data, embed_fn, cluster_threshold=cluster_threshold, min_size=min_size
    )
    storylines = link_storylines(
        days_events, link_threshold=link_threshold, max_gap=max_gap
    )
    return days_events, storylines


def build_embedder(embed_model: str, *, build_ollama_embedder) -> Optional[Callable]:
    """建嵌入 callable；Ollama 未開 / 缺 httpx 回 None（呼叫端決定如何 bail）。"""
    try:
        return build_ollama_embedder(model=embed_model)
    except ImportError as e:
        print(f"❌ 無法建立嵌入器（缺 httpx / Ollama 未開）：{e}", file=sys.stderr)
        return None
