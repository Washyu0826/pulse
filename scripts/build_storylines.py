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
import json
import logging
import sys
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

import storyline_core  # noqa: E402
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


def _prod_state_fn(cells: list[dict]) -> None:
    """正式 producer 的逐日 velocity + 狀態（hotness 全序列前綴），再標全局高峰。就地填入。"""
    daily_volumes = [c["volume"] for c in cells]
    for k, c in enumerate(cells):
        prefix = daily_volumes[: k + 1]
        c["velocity"] = round(hotness.velocity(prefix), 3)
        c["state"] = hotness.storyline_state(prefix)
    storyline_core.mark_peak(cells)


def build_storyline_record(
    s: Storyline,
    rank: int,
    *,
    generate_fn=None,
) -> tuple[dict, float]:
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

    回傳 (record, unrounded_hotness)：unrounded_hotness 供 storyline 間排序（避免 _sl_hotness
    再算一遍 day_volume）；record["hotness"] 為其四捨五入到 3 位的對外值。
    """
    # 1) 逐日合併 + volume + velocity/state + 標高峰（共用 storyline_core.build_timeline）。
    #    production：cell volume = round(hotness.day_volume(members, interaction), 3)；同時把
    #    「未四捨五入」的每日 day_volume 收集起來供 storyline 間排序用（取代原 _sl_hotness：
    #    不再對 day_volume 算第二遍）。排序值與對外 hotness 欄位刻意分開，沿用原行為：
    #    排序用 未捨入聲量總和、對外 hotness = round(已捨入聲量總和, 3)。
    raw_daily_volumes: list[float] = []

    def _volume_fn(members: int, interaction: int) -> float:
        raw = hotness.day_volume(members, interaction)
        raw_daily_volumes.append(raw)
        return round(raw, 3)

    cells = storyline_core.build_timeline(
        s,
        volume_fn=_volume_fn,
        state_fn=_prod_state_fn,
        with_sentiment_citations=True,
    )

    daily_volumes = [c["volume"] for c in cells]
    overall_state = hotness.storyline_state(daily_volumes)
    overall_hotness = round(hotness.storyline_hotness(daily_volumes), 3)
    # 排序用熱度（未捨入），與原 _sl_hotness 等價。
    sort_hotness = hotness.storyline_hotness(raw_daily_volumes)

    # 2) 標題 = 最熱一天的代表標題；主題 = 全鏈最常見主題（兜底「其他」）。
    peak_cell = max(cells, key=lambda c: c["volume"])
    title = peak_cell["headline"]
    all_themes = [t for c in cells for t in c["themes"]]
    theme = _coerce_theme(_most_common(all_themes))

    # 3) 每日一句摘要（選配 qwen；否則用 headline 當摘要）+ 出處 + 當日情緒。
    citations: list[dict] = []
    n = 0
    for c in cells:
        c["sources"] = sorted(c["sources"])
        rep_url = c.pop("_rep_url", None)
        sents = c.pop("_sentiments", [])
        c.pop("themes", None)
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

    record = {
        "id": f"story_{rank:03d}",
        "title": title,
        "state": overall_state,
        "hotness": overall_hotness,
        "span_days": s.span_days,
        "theme": theme,
        "timeline": cells,
        "citations": citations,
    }
    return record, sort_hotness


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
    storyline_core.add_common_args(ap, default_top=12)
    ap.add_argument("--out", type=Path, default=_ROOT / "data" / "storylines.jsonl")
    args = ap.parse_args()

    sources = storyline_core.resolve_sources(args)
    days = storyline_core.compute_window(args.days)

    print(f"⚙️  視窗 {days[0].isoformat()} ~ {days[-1].isoformat()}（{args.days} 天）"
          f"｜來源 {','.join(sources)}｜每日上限 {args.per_day_cap}")
    print(f"⚙️  分群門檻 {args.cluster_threshold}、鏈結門檻 {args.link_threshold}、max_gap {args.max_gap}")

    args.out.parent.mkdir(parents=True, exist_ok=True)

    # --- 撈資料（逐日）---
    print("📂 撈逐日貼文…")
    days_data = storyline_core.fetch_days(
        days, sources, args.min_quality, args.per_day_cap, _fetch_posts_for_day
    )
    total_posts = sum(len(p) for _, p in days_data)
    print(f"📂 共撈 {total_posts} 篇（{args.days} 天）")
    if total_posts < args.min_size * 2:
        args.out.write_text("", encoding="utf-8")
        print(f"⚠️  資料太少，寫空 storylines 檔 → {args.out}")
        return 0

    # --- 建嵌入 callable ---
    embed_fn = storyline_core.build_embedder(
        args.embed_model, build_ollama_embedder=build_ollama_embedder
    )
    if embed_fn is None:
        # 寫空檔不擋每日流程（與「資料不足」一致地以 0 結束）。
        args.out.write_text("", encoding="utf-8")
        return 0

    # --- 逐日分群 + 嵌入 + 跨日鏈結 ---
    print("🧩 逐日分群中（每天各跑一次 cluster_events）…")
    _, storylines = storyline_core.cluster_and_link(
        days_data, embed_fn,
        cluster_threshold=args.cluster_threshold, min_size=args.min_size,
        link_threshold=args.link_threshold, max_gap=args.max_gap,
        build_day_events=build_day_events, link_storylines=link_storylines,
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
    # 先對每條建記錄（不跑 qwen，便宜），用記錄帶回的「未捨入聲量總和」排序 —— 取代原
    # _sl_hotness（不再對 day_volume 算第二遍）。排序鍵與原本相同：(sort_hotness, span_days)。
    built = [build_storyline_record(s, 0) for s in multi_day]  # (record, sort_hotness)
    built.sort(key=lambda rh: (rh[1], rh[0]["span_days"]), reverse=True)
    show = built[: args.top]

    # 取 top N → 補正式 id（依排名）+ 選配每日 qwen 摘要（與原本一樣只對 top N 跑）。
    records = []
    for rank, (record, _sort_h) in enumerate(show, 1):
        record["id"] = f"story_{rank:03d}"
        # qwen 每日摘要只對 top N 跑（與原本相同；citation 標題已用原 headline 固定，
        # 摘要改寫的是 timeline summary，順序與原 build_storyline_record 等價）。
        if generate_fn is not None:
            _attach_daily_summaries(record["timeline"], record["title"], generate_fn)
        records.append(record)

    args.out.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8"
    )
    print(f"💾 寫出 {len(records)} 條 storyline → {args.out}")
    for r in records[:5]:
        print(f"   [{r['state']:<4}] hotness={r['hotness']:>7} 跨{r['span_days']}天  {r['title']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
