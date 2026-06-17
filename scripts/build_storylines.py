"""
每日「議題時間軸（storylines）」產製器 —— DB 撈近 N 天貼文 → 逐日分群 → 跨日鏈結 →
用 hotness 算每日聲量 / velocity / 升溫退燒狀態 → 寫 data/storylines.jsonl。

把 scripts/prototype_storyline.py（已驗證可行的跨日鏈結原型）產品化，**比照
scripts/build_today_events.py 的模式**：DB → JSONL 產出檔，由 API（/api/storylines）直接讀，
不查 DB、不改 schema。給 daily_refresh.ps1 在寄電子報前跑（與 build_today_events 並列）。

設計取捨（沿用原型驗證結論）：
- 來源預設乾淨來源（hackernews / devto）；分群門檻 0.75、跨日鏈結門檻 0.7（原型甜蜜點）。
- 每日聲量改用 ml.hotness.day_volume（成員數 + log(1+互動)），比原型純互動總和穩。
- 狀態（升溫/高峰/退燒）由 ml.hotness.storyline_state 對「每日聲量序列」判定。
- storyline 排序用 ml.hotness.storyline_hotness（各日聲量總和）。
- 資料不足 / 分不出跨日鏈 → 寫空檔、以 0 結束（不擋每日流程）。

全地端模型（[[prefer-local-llm]]）：Ollama nomic 嵌入（逐日分群 + 跨日鏈結都用同一 embedder）。
可選 --summarize 用 Ollama qwen 對前幾大 storyline 產繁中一句「當日重點」摘要（較慢，預設關）。

用法（系統 Python，需 Ollama 開著 + pulse-db healthy）：
    python scripts/build_storylines.py
    python scripts/build_storylines.py --days 14 --per-day-cap 60 --top 8
    python scripts/build_storylines.py --summarize         # 加當日一句摘要（較慢）
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

# 壓掉 SQLAlchemy echo（與原型一致，輸出乾淨）。
logging.getLogger("sqlalchemy.engine.Engine").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# TLS 攔截環境（本機 Avast）：Ollama 走本機 http 不需要，但與其他腳本一致、保險。
try:
    import truststore

    truststore.inject_into_ssl()
except Exception:  # noqa: BLE001
    pass

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "api"))
sys.path.insert(0, str(_ROOT / "ml"))
sys.path.insert(0, str(_ROOT / "scripts"))

from ml import hotness  # noqa: E402

# 複用原型已驗證的逐日分群 / 跨日鏈結 / DB 撈資料（純藍本，不重寫）。
from prototype_storyline import (  # noqa: E402
    Storyline,
    _fetch_posts_for_day,
    build_day_events,
    link_storylines,
)
from run_event_pipeline import build_ollama_embedder  # noqa: E402

# 前端 ThemeLabel 合法值（與 web/lib/types.ts / events_today router 對齊）；未知一律「其他」。
_VALID_THEMES = {"新工具", "模型動態", "使用方法", "風險限制", "倫理法規", "其他"}


def _coerce_theme(value: str | None) -> str:
    return value if value in _VALID_THEMES else "其他"


def build_storyline_record(
    s: Storyline,
    rank: int,
    *,
    generate_fn=None,
) -> dict:
    """
    把一條跨日 Storyline 轉成對外 JSONL 記錄（比照 events_today 的扁平、DB-optional 形狀）。

    形狀（與 API / 前端契約對齊）：
    {
      "id": "story_001",
      "title": "...",                 # 最熱一天的代表標題
      "state": "升溫" | "高峰" | "退燒" | "持平",
      "hotness": float,               # 各日聲量總和（storyline 間排序用）
      "span_days": int,
      "timeline": [                   # 每天一格，日期升冪
        {"date", "summary", "volume", "velocity", "state", "sentiment", "sources", "members"}
      ],
      "citations": [{"n", "url", "title"}]   # 每日代表貼文出處
    }

    每日聲量 / velocity / 狀態用 ml.hotness（成員數 + log(1+互動)；末日相對前日 + 全局高峰）。
    """
    # 1) 同日合併成一格（同一天可能有多個日事件）。
    by_day: dict[date, dict] = {}
    for e in s.events:
        cell = by_day.setdefault(e.day, {
            "date": e.day.isoformat(),
            "members": 0,
            "interaction": 0,      # 原型 DayEvent.volume = 成員互動分數總和 → 當互動量
            "headline": e.rep_title,
            "_top": -1,
            "_rep_url": e.rep_url,  # 最熱日事件的代表 URL（出處用）
            "sources": set(),
            "themes": set(),
            "_sentiments": [],      # 當日所有成員的情緒標籤（多數情緒用）
        })
        cell["members"] += e.member_count
        cell["interaction"] += e.volume
        cell["sources"].update(e.sources)
        cell["themes"].update(e.themes)
        cell["_sentiments"].extend(e.sentiments)
        if e.volume > cell["_top"]:
            cell["_top"] = e.volume
            cell["headline"] = e.rep_title
            cell["_rep_url"] = e.rep_url

    cells = [by_day[d] for d in sorted(by_day)]

    # 2) 每日聲量（hotness.day_volume）。
    for c in cells:
        c["volume"] = round(hotness.day_volume(c["members"], c["interaction"]), 3)

    daily_volumes = [c["volume"] for c in cells]

    # 3) 逐日 velocity + 狀態（日對日）；整條的狀態用全序列判。
    for k, c in enumerate(cells):
        prefix = daily_volumes[: k + 1]
        c["velocity"] = round(hotness.velocity(prefix), 3)
        c["state"] = hotness.storyline_state(prefix)
    # 全局高峰那天標「高峰」（多天才標；單日不蓋）。
    if len(cells) > 1:
        peak_k = max(range(len(cells)), key=lambda i: cells[i]["volume"])
        cells[peak_k]["state"] = hotness.STATE_PEAK

    overall_state = hotness.storyline_state(daily_volumes)
    overall_hotness = round(hotness.storyline_hotness(daily_volumes), 3)

    # 4) 標題 = 最熱一天的代表標題；主題 = 全鏈最常見主題（兜底「其他」）。
    peak_cell = max(cells, key=lambda c: c["volume"])
    title = peak_cell["headline"]
    all_themes = [t for c in cells for t in c["themes"]]
    theme = _coerce_theme(_most_common(all_themes))

    # 5) 每日一句摘要（選配 qwen；否則用 headline 當摘要）。
    citations: list[dict] = []
    n = 0
    for c in cells:
        c["sources"] = sorted(c["sources"])
        rep_url = c.pop("_rep_url", None)
        sents = c.pop("_sentiments", [])
        c.pop("themes", None)
        c.pop("_top", None)
        c.pop("interaction", None)
        c["summary"] = c.pop("headline")
        # 出處：每日代表事件的代表貼文 URL（前端用 citation.n 對齊時間軸第 n 天 → 渲染 [n] 連結）。
        # 取不到 url 時留 None，前端條件式渲染會自動略過連結。
        n += 1
        citations.append({"n": n, "url": rep_url, "title": c["summary"][:80]})
        # 當日情緒 = 當日所有成員貼文的多數情緒（positive/neutral/negative 字串；
        # API/前端 sentiment 欄位接受字串，非字串會被當 None）。無情緒資料則 None。
        c["sentiment"] = _majority_sentiment(sents)

    if generate_fn is not None:
        _attach_daily_summaries(cells, title, generate_fn)

    return {
        "id": f"story_{rank:03d}",
        "title": title,
        "state": overall_state,
        "hotness": overall_hotness,
        "span_days": s.span_days,
        "theme": theme,
        "timeline": cells,
        "citations": citations,
    }


_VALID_SENTIMENTS = {"positive", "neutral", "negative"}


def _majority_sentiment(labels: list[str]) -> str | None:
    """當日成員情緒的多數標籤（positive/neutral/negative）。無有效標籤回 None。

    平手取出現次數最多者，再以固定優先序（negative > positive > neutral）破平，確保確定性
    且傾向凸顯負面討論（風險議題更該被看見）。
    """
    valid = [x for x in labels if x in _VALID_SENTIMENTS]
    if not valid:
        return None
    counts: dict[str, int] = {}
    for x in valid:
        counts[x] = counts.get(x, 0) + 1
    priority = {"negative": 0, "positive": 1, "neutral": 2}
    return min(counts, key=lambda k: (-counts[k], priority[k]))


def _most_common(items: list[str]) -> str | None:
    if not items:
        return None
    counts: dict[str, int] = {}
    for it in items:
        counts[it] = counts.get(it, 0) + 1
    # tie：取字典序最小（確定性）。
    return min(sorted(counts), key=lambda k: (-counts[k], k))


def _attach_daily_summaries(cells: list[dict], title: str, generate_fn) -> None:
    """選配：用 qwen 把每日 headline 潤成繁中一句「當日重點」。失敗則保留原 headline。"""
    for c in cells:
        prompt = (
            f"議題：「{title}」。以下是某一天關於此議題的重點貼文標題，請用繁體中文改寫成"
            f"一句不超過 30 字、客觀陳述事實的當日重點（不要臆測、不加形容詞）：\n"
            f"{c['summary']}\n\n當日重點："
        )
        try:
            out = generate_fn(prompt).strip().split("\n")[0]
            if out:
                c["summary"] = out[:60]
        except Exception:  # noqa: BLE001 — 摘要失敗不致命，保留原 headline
            pass


def main() -> int:
    ap = argparse.ArgumentParser(description="每日議題時間軸 storylines 產製（DB → JSONL）")
    ap.add_argument("--days", type=int, default=21, help="回看天數（含今天）")
    ap.add_argument("--per-day-cap", type=int, default=80, help="每天最多納入幾篇（控時間）")
    ap.add_argument("--min-quality", type=int, default=30)
    ap.add_argument("--sources", nargs="+", default=["hackernews", "devto"])
    ap.add_argument("--include-threads", action="store_true")
    ap.add_argument("--cluster-threshold", type=float, default=0.75, help="逐日分群餘弦門檻")
    ap.add_argument("--min-size", type=int, default=2, help="日事件最小成員數")
    ap.add_argument("--link-threshold", type=float, default=0.7, help="跨日鏈結餘弦門檻（甜蜜點）")
    ap.add_argument("--max-gap", type=int, default=1, help="跨日鏈結容忍最大天數間隔（1=相鄰日）")
    ap.add_argument("--top", type=int, default=12, help="最多寫出幾條最熱跨日 storyline")
    ap.add_argument("--summarize", action="store_true", help="用 qwen 產每日一句重點（較慢）")
    ap.add_argument("--embed-model", default="nomic-embed-text")
    ap.add_argument("--gen-model", default="qwen2.5:7b")
    ap.add_argument("--out", type=Path, default=_ROOT / "data" / "storylines.jsonl")
    args = ap.parse_args()

    sources = list(args.sources)
    if args.include_threads and "threads" not in sources:
        sources.append("threads")

    today = date.today()
    days = [today - timedelta(days=i) for i in range(args.days - 1, -1, -1)]

    print(f"⚙️  視窗 {days[0].isoformat()} ~ {days[-1].isoformat()}（{args.days} 天）"
          f"｜來源 {','.join(sources)}｜每日上限 {args.per_day_cap}")
    print(f"⚙️  分群門檻 {args.cluster_threshold}、鏈結門檻 {args.link_threshold}、max_gap {args.max_gap}")

    args.out.parent.mkdir(parents=True, exist_ok=True)

    # --- 撈資料（逐日）---
    print("📂 撈逐日貼文…")

    async def _fetch_all():
        out = []
        for d in days:
            posts = await _fetch_posts_for_day(d, sources, args.min_quality, args.per_day_cap)
            out.append((d, posts))
        return out

    days_data = asyncio.run(_fetch_all())
    total_posts = sum(len(p) for _, p in days_data)
    print(f"📂 共撈 {total_posts} 篇（{args.days} 天）")
    if total_posts < args.min_size * 2:
        args.out.write_text("", encoding="utf-8")
        print(f"⚠️  資料太少，寫空 storylines 檔 → {args.out}")
        return 0

    # --- 建嵌入 callable ---
    try:
        embed_fn = build_ollama_embedder(model=args.embed_model)
    except ImportError as e:
        print(f"❌ 無法建立嵌入器（缺 httpx / Ollama 未開）：{e}", file=sys.stderr)
        # 寫空檔不擋每日流程（與「資料不足」一致地以 0 結束）。
        args.out.write_text("", encoding="utf-8")
        return 0

    # --- 逐日分群 + 嵌入代表文字 ---
    print("🧩 逐日分群中（每天各跑一次 cluster_events）…")
    days_events = build_day_events(
        days_data, embed_fn, cluster_threshold=args.cluster_threshold, min_size=args.min_size
    )

    # --- 跨日鏈結 ---
    storylines = link_storylines(
        days_events, link_threshold=args.link_threshold, max_gap=args.max_gap
    )
    multi_day = [s for s in storylines if s.span_days >= 2]
    print(f"🔗 鏈結完成：{len(storylines)} 條（跨日 {len(multi_day)} 條）")

    if not multi_day:
        args.out.write_text("", encoding="utf-8")
        print(f"⚠️  沒有形成跨日議題鏈（資料太分散）→ 空檔 {args.out}")
        return 0

    # --- 選配生成器 ---
    generate_fn = None
    if args.summarize:
        try:
            from ml.summarize import build_ollama_generate_fn
            generate_fn = build_ollama_generate_fn(model=args.gen_model)
        except ImportError as e:
            print(f"⚠️  無法建生成器，略過每日摘要：{e}", file=sys.stderr)

    # --- 依 storyline_hotness 排序（最熱在前），取 top ---
    def _sl_hotness(s: Storyline) -> float:
        by_day: dict[date, list] = {}
        for e in s.events:
            by_day.setdefault(e.day, []).append(e)
        vols = [
            hotness.day_volume(
                sum(ev.member_count for ev in evs),
                sum(ev.volume for ev in evs),
            )
            for evs in (by_day[d] for d in sorted(by_day))
        ]
        return hotness.storyline_hotness(vols)

    multi_day.sort(key=lambda s: (_sl_hotness(s), s.span_days), reverse=True)
    show = multi_day[: args.top]

    records = [
        build_storyline_record(s, rank, generate_fn=generate_fn)
        for rank, s in enumerate(show, 1)
    ]

    args.out.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8"
    )
    print(f"💾 寫出 {len(records)} 條 storyline → {args.out}")
    for r in records[:5]:
        print(f"   [{r['state']:<4}] hotness={r['hotness']:>7} 跨{r['span_days']}天  {r['title']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
