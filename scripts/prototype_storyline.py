"""
議題演變（topic / issue evolution）可行性原型 —— 把每日事件跨日串成 storyline 並判升溫/退燒。

★ 這是 PROTOTYPE（可行性驗證），不碰正式 DB schema / API / 前端，只讀 DB + 印結果評估品質。
★ 只新增本檔與 data/storylines_proto.jsonl，不改既有積木（event_pipeline / 爬蟲 / API…）。

做什麼（對應需求 1~5）：
1. 逐日分群：取近 N 天每天的乾淨貼文（hackernews/devto，可選 --include-threads），對「每一天」各跑
   一次 event_cluster.cluster_events，得到當天的事件群（代表貼文字 / 成員數 / 來源集合）。
   為控時間：每天貼文設上限（--per-day-cap，預設 80）、印進度。
2. 跨日鏈結：每個「日事件群」用 nomic 嵌入其代表文字，跨相鄰日按餘弦相似度（--link-threshold，預設 0.7）
   貪婪連成 storyline（同議題的日事件鏈）。用 union-find 連通分量，原型不最佳化。
3. 演變信號：每條 storyline 產時間軸 [{date, 一句話, volume, sources}]，算 volume 的 velocity(Δ) 與狀態
   標籤（升溫 / 高峰 / 退燒）。
4. （選配 --summarize）對前幾大 storyline 用 qwen 產一段繁中「演變摘要」。
5. 輸出：前 N 條最熱 storyline 時間軸印 console + 寫 data/storylines_proto.jsonl。

複用的既有積木（只讀不改）：
- ml.event_cluster.cluster_events / cosine：逐日分群（沿用 single-link 門檻分群）。
- scripts.run_event_pipeline.build_ollama_embedder：本機 Ollama nomic 嵌入 callable。
- api.database.AsyncSessionLocal：DB 連線（同 build_today_events / backfill_*）。

用法（系統 Python，需 Ollama 開著 + pulse-db healthy）：
    python scripts/prototype_storyline.py
    python scripts/prototype_storyline.py --days 14 --per-day-cap 60 --link-threshold 0.72
    python scripts/prototype_storyline.py --compare-thresholds 0.65 0.7 0.75   # 門檻掃描比較
    python scripts/prototype_storyline.py --summarize --top 5                  # 加演變摘要
    python scripts/prototype_storyline.py --include-threads                    # 試納入 threads
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

# 壓掉 SQLAlchemy echo（config environment=development 會把 engine echo=True，原型輸出才乾淨）。
# engine 的 echo 是透過 logger 寫的，提高該 logger 門檻即可靜音（不改正式 config）。
logging.getLogger("sqlalchemy.engine.Engine").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# TLS 攔截環境（本機 Avast）：Ollama 走本機 http 不需要，但保險與其他腳本一致。
try:
    import truststore

    truststore.inject_into_ssl()
except Exception:  # noqa: BLE001
    pass

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "api"))
sys.path.insert(0, str(_ROOT / "ml"))
sys.path.insert(0, str(_ROOT / "scripts"))

from ml import event_cluster  # noqa: E402
from run_event_pipeline import build_ollama_embedder  # noqa: E402


# ---------------------------------------------------------------------------
# 資料結構
# ---------------------------------------------------------------------------
@dataclass
class DayEvent:
    """某一天的一個事件群（逐日分群的產物）。"""

    day: date
    rep_text: str           # 代表貼文文字（嵌入 + 顯示用）
    rep_title: str          # 代表貼文標題（一句話顯示用）
    member_count: int       # 成員貼文數
    volume: int             # 規模指標（這裡用 成員互動分數總和；退回 member_count）
    sources: list[str]      # 來源集合（hackernews / devto / threads）
    themes: list[str]       # 成員主題集合
    uid: str = ""           # 全域唯一 id（day#idx）
    embedding: list[float] = field(default_factory=list)


@dataclass
class Storyline:
    """一條跨日鏈：同議題的日事件鏈（時間升冪）。"""

    events: list[DayEvent]

    @property
    def total_volume(self) -> int:
        return sum(e.volume for e in self.events)

    @property
    def span_days(self) -> int:
        """這條鏈涵蓋的『相異天數』（非事件數；同日多事件算一天）。"""
        return len({e.day for e in self.events})


# ---------------------------------------------------------------------------
# 1) 從 DB 撈逐日貼文
# ---------------------------------------------------------------------------
async def _fetch_posts_for_day(
    d: date, sources: list[str], min_quality: int, cap: int
) -> list[dict]:
    """撈某一天（posted_at 落在 [d 00:00, d+1 00:00)）達品質門檻的貼文，依互動分數取前 cap 篇。"""
    from datetime import datetime

    from api.database import AsyncSessionLocal
    from sqlalchemy import text

    placeholders = ",".join(f":s{i}" for i in range(len(sources)))
    # posted_at 為 timestamptz → asyncpg 要 datetime 物件（非 ISO 字串）。
    params = {"d0": datetime.combine(d, datetime.min.time()),
              "d1": datetime.combine(d + timedelta(days=1), datetime.min.time()),
              "q": min_quality, "lim": cap}
    params.update({f"s{i}": s for i, s in enumerate(sources)})
    async with AsyncSessionLocal() as s:
        rows = (
            await s.execute(
                text(
                    "select p.id, p.source, p.title, p.content, p.url, "
                    "coalesce(p.score,0)+coalesce(p.num_comments,0) as engagement, "
                    "th.label as theme "
                    "from posts p "
                    "left join themes th on th.post_id=p.id "
                    "where p.posted_at >= :d0 and p.posted_at < :d1 "
                    "and (p.quality_score is null or p.quality_score >= :q) "
                    f"and p.source in ({placeholders}) "
                    "order by engagement desc "
                    "limit :lim"
                ),
                params,
            )
        ).all()
    posts: list[dict] = []
    for r in rows:
        title = (r.title or "").strip()
        body = (r.content or "").strip()
        txt = title if not body else f"{title}. {body[:400]}"
        if len(txt.strip()) < 10:
            continue
        posts.append({
            "post_id": f"p{r.id}", "text": txt, "title": title, "url": r.url,
            "source": r.source, "theme": r.theme, "engagement": int(r.engagement or 0),
        })
    return posts


# ---------------------------------------------------------------------------
# 1) 逐日分群
# ---------------------------------------------------------------------------
def _cluster_one_day(
    d: date, posts: list[dict], embed_fn, *, threshold: float, min_size: int
) -> list[DayEvent]:
    """對一天的貼文跑 event_cluster.cluster_events → 包成 DayEvent 清單。"""
    if len(posts) < min_size:
        return []
    clusters = event_cluster.cluster_events(
        posts, embed_fn, threshold=threshold, min_size=min_size
    )
    day_events: list[DayEvent] = []
    for idx, c in enumerate(clusters):
        rep = posts[c.representative]
        members = [posts[i] for i in c.members]
        vol = sum(m.get("engagement", 0) for m in members) or c.size
        srcs = sorted({m["source"] for m in members})
        themes = sorted({m["theme"] for m in members if m.get("theme")})
        day_events.append(DayEvent(
            day=d,
            rep_text=rep["text"],
            rep_title=(rep["title"] or rep["text"])[:80],
            member_count=c.size,
            volume=int(vol),
            sources=srcs,
            themes=themes,
            uid=f"{d.isoformat()}#{idx}",
        ))
    return day_events


# ---------------------------------------------------------------------------
# 2) 跨日鏈結（union-find 連通分量，僅連相鄰日且餘弦 >= 門檻）
# ---------------------------------------------------------------------------
def link_storylines(
    days_events: list[list[DayEvent]], *, link_threshold: float, max_gap: int = 1
) -> list[Storyline]:
    """
    把逐日事件群跨日連成 storyline。

    - 只比較相隔 <= max_gap 天的兩個日事件（預設 1 = 相鄰日；放寬可容忍中斷一天）。
    - 餘弦相似度 >= link_threshold 視為「同議題延續」→ union。
    - 連通分量即一條 storyline；事件依日期升冪。
    - 簡單貪婪：不做一對一最佳指派，原型只看「能不能合理串起來」。
    """
    flat: list[DayEvent] = [e for de in days_events for e in de]
    n = len(flat)
    parent = list(range(n))

    def find(x: int) -> int:
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            lo, hi = (ra, rb) if ra < rb else (rb, ra)
            parent[hi] = lo

    # 依日期分組索引，方便只比相鄰日。
    by_day: dict[date, list[int]] = defaultdict(list)
    for i, e in enumerate(flat):
        by_day[e.day].append(i)
    sorted_days = sorted(by_day)

    for di, d in enumerate(sorted_days):
        for dj in range(di + 1, len(sorted_days)):
            d2 = sorted_days[dj]
            if (d2 - d).days > max_gap:
                break
            for i in by_day[d]:
                for j in by_day[d2]:
                    sim = event_cluster.cosine(flat[i].embedding, flat[j].embedding)
                    if sim >= link_threshold:
                        union(i, j)

    comps: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        comps[find(i)].append(i)

    storylines: list[Storyline] = []
    for members in comps.values():
        evs = sorted((flat[i] for i in members), key=lambda e: e.day)
        storylines.append(Storyline(events=evs))
    # 最熱在前：先比總 volume，再比跨日數。
    storylines.sort(key=lambda s: (s.total_volume, s.span_days), reverse=True)
    return storylines


# ---------------------------------------------------------------------------
# 3) 演變信號：velocity + 狀態標籤
# ---------------------------------------------------------------------------
def _state_label(prev_vol: int | None, cur_vol: int, next_vol: int | None) -> tuple[int, str]:
    """
    回傳 (velocity, 狀態標籤)。velocity = cur - prev（首日以 0 起算）。

    規則（原型啟發式）：
    - 首日（無 prev）：升溫（議題出現）。
    - velocity > 0：升溫。
    - velocity <= 0 且 prev 為此前最高且 next 也下降/無 → 高峰回落 → 退燒。
    - velocity == 0：高檔持平。
    - velocity < 0：退燒。
    """
    if prev_vol is None:
        return cur_vol, "升溫(出現)"
    vel = cur_vol - prev_vol
    if vel > 0:
        return vel, "升溫"
    if vel == 0:
        return vel, "高檔持平"
    return vel, "退燒"


def build_timeline(s: Storyline) -> list[dict]:
    """
    產 storyline 的演變時間軸（**每天一格**，含 velocity 與狀態）。

    velocity / 升溫退燒是「日對日」訊號，故同一天的多個日事件先合併成一格
    （volume / members 相加、headline 取當天最大規模者、sources/themes 取聯集）→ 再算日對日 Δ。
    """
    # 1) 同日合併
    by_day: dict[date, dict] = {}
    for e in s.events:
        cell = by_day.setdefault(e.day, {
            "date": e.day.isoformat(), "volume": 0, "members": 0,
            "headline": e.rep_title, "_top_vol": -1, "sources": set(), "themes": set(),
        })
        cell["volume"] += e.volume
        cell["members"] += e.member_count
        cell["sources"].update(e.sources)
        cell["themes"].update(e.themes)
        if e.volume > cell["_top_vol"]:
            cell["_top_vol"] = e.volume
            cell["headline"] = e.rep_title

    cells = [by_day[d] for d in sorted(by_day)]
    for c in cells:
        c["sources"] = sorted(c["sources"])
        c["themes"] = sorted(c["themes"])
        c.pop("_top_vol", None)

    # 2) 日對日 velocity + 狀態
    vols = [c["volume"] for c in cells]
    for k, c in enumerate(cells):
        prev_vol = vols[k - 1] if k > 0 else None
        next_vol = vols[k + 1] if k + 1 < len(vols) else None
        c["velocity"], c["state"] = _state_label(prev_vol, c["volume"], next_vol)

    # 3) 標全局高峰（多天才標）
    if len(cells) > 1:
        peak_k = max(range(len(cells)), key=lambda k: cells[k]["volume"])
        cells[peak_k]["state"] = "高峰"
    return cells


# ---------------------------------------------------------------------------
# 4) （選配）演變摘要
# ---------------------------------------------------------------------------
def summarize_evolution(s: Storyline, generate_fn) -> str:
    """用 qwen 產一段「這議題怎麼演變」的繁中摘要（選配；失敗回空字串不致命）。"""
    lines = []
    for e in s.events:
        lines.append(f"- {e.day.isoformat()}（規模 {e.volume}）：{e.rep_title}")
    body = "\n".join(lines)
    prompt = (
        "以下是同一個科技議題在連續幾天的事件紀錄（日期、規模、當日重點）。\n"
        "請用繁體中文寫 2~3 句話，描述這個議題『怎麼隨時間演變』"
        "（何時出現、是升溫還是退燒、高峰在哪天）。只描述資料中的事實，不要臆測。\n\n"
        f"事件紀錄：\n{body}\n\n演變摘要："
    )
    try:
        return generate_fn(prompt).strip()
    except Exception as e:  # noqa: BLE001
        return f"（摘要失敗：{e}）"


# ---------------------------------------------------------------------------
# 逐日分群 + 嵌入代表文字（主流程的重活；快取嵌入避免重算）
# ---------------------------------------------------------------------------
def build_day_events(
    days_data: list[tuple[date, list[dict]]],
    embed_fn,
    *,
    cluster_threshold: float,
    min_size: int,
) -> list[list[DayEvent]]:
    """對每天分群並嵌入每個日事件的代表文字。印進度。"""
    days_events: list[list[DayEvent]] = []
    total_events = 0
    for n, (d, posts) in enumerate(days_data, 1):
        des = _cluster_one_day(d, posts, embed_fn, threshold=cluster_threshold, min_size=min_size)
        # 嵌入代表文字（鏈結用）。cluster_events 內部已對「每篇貼文」嵌過，但代表文字是
        # title+content 拼接、與鏈結語意一致，這裡為清楚起見重新嵌代表文字（量 = 事件數，不大）。
        for de in des:
            de.embedding = list(embed_fn(de.rep_text))
        days_events.append(des)
        total_events += len(des)
        print(f"  [{n}/{len(days_data)}] {d.isoformat()}：{len(posts):>3} 篇 → {len(des):>2} 個日事件",
              flush=True)
    print(f"📊 逐日分群完成：{total_events} 個日事件（{len(days_data)} 天）")
    return days_events


# ---------------------------------------------------------------------------
# 輸出 / 評估
# ---------------------------------------------------------------------------
def print_storyline(rank: int, s: Storyline, timeline: list[dict], evolution: str | None) -> None:
    src = sorted({x for e in s.events for x in e.sources})
    print(f"\n{'='*78}")
    print(f"#{rank}  storyline（跨 {s.span_days} 天，總規模 {s.total_volume}，來源 {','.join(src)}）")
    if evolution:
        print(f"  📝 演變摘要：{evolution}")
    print(f"  {'-'*74}")
    for t in timeline:
        arrow = "▲" if t["velocity"] > 0 else ("▼" if t["velocity"] < 0 else "─")
        print(f"  {t['date']}  [{t['state']:<8}] {arrow} vol={t['volume']:<5} "
              f"(n={t['members']}) {t['headline']}")


def evaluate(storylines: list[Storyline], link_threshold: float) -> dict:
    """印鏈結品質統計（供可行性評估）。"""
    multi = [s for s in storylines if s.span_days >= 2]
    singles = [s for s in storylines if s.span_days == 1]
    spans = [s.span_days for s in multi]
    stats = {
        "link_threshold": link_threshold,
        "total_storylines": len(storylines),
        "multi_day_storylines": len(multi),
        "single_day_events": len(singles),
        "max_span_days": max(spans) if spans else 0,
        "avg_span_of_multi": round(sum(spans) / len(spans), 2) if spans else 0.0,
    }
    print(f"\n🔗 門檻 {link_threshold}: storyline 共 {stats['total_storylines']} 條"
          f"（跨日 {stats['multi_day_storylines']} 條、單日孤立 {stats['single_day_events']} 個）"
          f"｜最長 {stats['max_span_days']} 天、跨日鏈平均 {stats['avg_span_of_multi']} 天")
    return stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="議題演變 storyline 可行性原型（只讀 DB，不改正式系統）")
    ap.add_argument("--days", type=int, default=21, help="回看天數（含今天）")
    ap.add_argument("--per-day-cap", type=int, default=80, help="每天最多納入幾篇（控時間）")
    ap.add_argument("--min-quality", type=int, default=30)
    ap.add_argument("--sources", nargs="+", default=["hackernews", "devto"])
    ap.add_argument("--include-threads", action="store_true", help="額外納入 threads（內文剛清洗）")
    ap.add_argument("--cluster-threshold", type=float, default=0.75, help="逐日分群餘弦門檻（比照 build_today_events）")
    ap.add_argument("--min-size", type=int, default=2, help="日事件最小成員數")
    ap.add_argument("--link-threshold", type=float, default=0.7, help="跨日鏈結餘弦門檻")
    ap.add_argument("--max-gap", type=int, default=1, help="跨日鏈結容忍的最大天數間隔（1=相鄰日）")
    ap.add_argument("--compare-thresholds", nargs="*", type=float, default=None,
                    help="給多個鏈結門檻做掃描比較（如 0.65 0.7 0.75）")
    ap.add_argument("--top", type=int, default=5, help="印出 / 摘要前幾條最熱 storyline")
    ap.add_argument("--summarize", action="store_true", help="對前 top 條用 qwen 產演變摘要（較慢）")
    ap.add_argument("--embed-model", default="nomic-embed-text")
    ap.add_argument("--gen-model", default="qwen2.5:7b")
    ap.add_argument("--out", type=Path, default=_ROOT / "data" / "storylines_proto.jsonl")
    args = ap.parse_args()

    sources = list(args.sources)
    if args.include_threads and "threads" not in sources:
        sources.append("threads")

    today = date.today()
    days = [today - timedelta(days=i) for i in range(args.days - 1, -1, -1)]

    print(f"⚙️  視窗 {days[0].isoformat()} ~ {days[-1].isoformat()}（{args.days} 天）"
          f"｜來源 {','.join(sources)}｜每日上限 {args.per_day_cap}")
    print(f"⚙️  分群門檻 {args.cluster_threshold}、鏈結門檻 {args.link_threshold}、max_gap {args.max_gap}")

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
        print("⚠️  資料太少，無法形成 storyline。", file=sys.stderr)
        return 1

    # --- 建嵌入 callable ---
    try:
        embed_fn = build_ollama_embedder(model=args.embed_model)
    except ImportError as e:
        print(f"❌ 無法建立嵌入器（缺 httpx / Ollama 未開）：{e}", file=sys.stderr)
        return 1

    # --- 逐日分群 + 嵌入 ---
    print("🧩 逐日分群中（每天各跑一次 cluster_events）…")
    days_events = build_day_events(
        days_data, embed_fn, cluster_threshold=args.cluster_threshold, min_size=args.min_size
    )

    # --- 門檻掃描比較（若指定）---
    if args.compare_thresholds:
        print(f"\n{'#'*78}\n# 鏈結門檻掃描比較\n{'#'*78}")
        for th in args.compare_thresholds:
            sl = link_storylines(days_events, link_threshold=th, max_gap=args.max_gap)
            evaluate(sl, th)

    # --- 主鏈結（用 --link-threshold）---
    storylines = link_storylines(days_events, link_threshold=args.link_threshold, max_gap=args.max_gap)
    print(f"\n{'#'*78}\n# 主結果（鏈結門檻 {args.link_threshold}）\n{'#'*78}")
    evaluate(storylines, args.link_threshold)

    # --- 選配演變摘要（只對前 top 跑）---
    generate_fn = None
    if args.summarize:
        try:
            from ml.summarize import build_ollama_generate_fn
            generate_fn = build_ollama_generate_fn(model=args.gen_model)
        except ImportError as e:
            print(f"⚠️  無法建生成器，略過摘要：{e}", file=sys.stderr)

    # --- 印 + 寫檔（前 top 條，且跨日優先）---
    multi_day = [s for s in storylines if s.span_days >= 2]
    show = (multi_day or storylines)[: args.top]
    print(f"\n{'#'*78}\n# 前 {len(show)} 條最熱 storyline 時間軸\n{'#'*78}")

    records: list[dict] = []
    for rank, s in enumerate(show, 1):
        timeline = build_timeline(s)
        evo = summarize_evolution(s, generate_fn) if (args.summarize and generate_fn) else None
        print_storyline(rank, s, timeline, evo)
        records.append({
            "rank": rank,
            "span_days": s.span_days,
            "total_volume": s.total_volume,
            "link_threshold": args.link_threshold,
            "evolution_summary": evo,
            "timeline": timeline,
        })

    # 寫所有跨日 storyline（不只 top），供離線分析
    args.out.parent.mkdir(parents=True, exist_ok=True)
    all_recs = []
    for rank, s in enumerate(multi_day, 1):
        all_recs.append({
            "rank": rank,
            "span_days": s.span_days,
            "total_volume": s.total_volume,
            "link_threshold": args.link_threshold,
            "timeline": build_timeline(s),
        })
    args.out.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in all_recs), encoding="utf-8"
    )
    print(f"\n💾 寫出 {len(all_recs)} 條跨日 storyline → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
