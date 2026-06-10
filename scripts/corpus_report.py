"""
語料庫分析報告（唯讀）—— 把 ~6 萬則多來源 AI 貼文語料的全貌彙整成一份 Markdown 報告。

純 SELECT、不寫 DB、不載入任何模型。連線方式比照 scripts/backfill_sentiments.py：
把 api / ml 注入 sys.path，再用 api.database.AsyncSessionLocal 開 session，
所有統計都用 sqlalchemy.text 直接下 SQL 聚合（在 DB 端算，省記憶體）。

用法（production 環境，輸出到檔案）：
    ENVIRONMENT=production python scripts/corpus_report.py --out docs/corpus-report.md
不給 --out 則印到 stdout。

報告內容：
  1. 總量 + 各來源筆數 / 占比
  2. 品質分佈（high>=70 / mid 30-69 / low<30 / null）整體與各來源
  3. DUPLICATE 重複旗標數
  4. 主題分佈（join themes）整體 + 各來源 —— 標出「新工具」嚴重偏斜
  5. 情緒分佈（pos/neu/neg）整體 + 各來源
  6. posted_at 年度覆蓋（注意：created_at 是入庫時間，要用 posted_at 發佈時間）
  7. 各來源前 5 名作者
  8. 自動產生的「觀察 / findings」段（中文來源 PTT/Threads vs 英文來源 HN 的主題差異等）
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "api"))
sys.path.insert(0, str(_ROOT / "ml"))

from api.database import AsyncSessionLocal  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

# 中文來源 vs 英文來源（用於觀察段的對比）。
_ZH_SOURCES = {"ptt", "threads"}
_EN_SOURCES = {"hackernews", "lobsters", "devto"}


def _pct(n: int, total: int) -> str:
    """算占比字串（total=0 時回 0.0%）。"""
    return f"{(100.0 * n / total):.1f}%" if total else "0.0%"


def _bar(frac: float, width: int = 20) -> str:
    """用方塊字元畫一條簡單長條（frac 為 0-1）。"""
    filled = int(round(frac * width))
    return "█" * filled + "·" * (width - filled)


# --------------------------------------------------------------------------- #
# 各區塊查詢（全部 SELECT，DB 端聚合）。回傳乾淨的 Python 結構供 render 使用。
# --------------------------------------------------------------------------- #
async def _q_sources(session: AsyncSession) -> list[tuple[str, int]]:
    rows = (
        await session.execute(
            text("SELECT source, COUNT(*) AS n FROM posts GROUP BY source ORDER BY n DESC")
        )
    ).all()
    return [(r.source, r.n) for r in rows]


async def _q_quality(session: AsyncSession) -> list[tuple[str, int, int, int, int, int]]:
    """各來源（含整體）品質分桶：(source, total, high, mid, low, null)。"""
    rows = (
        await session.execute(
            text(
                """
                SELECT
                    source,
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE quality_score >= 70) AS high,
                    COUNT(*) FILTER (WHERE quality_score >= 30 AND quality_score < 70) AS mid,
                    COUNT(*) FILTER (WHERE quality_score < 30) AS low,
                    COUNT(*) FILTER (WHERE quality_score IS NULL) AS qnull
                FROM posts
                GROUP BY source
                ORDER BY total DESC
                """
            )
        )
    ).all()
    return [(r.source, r.total, r.high, r.mid, r.low, r.qnull) for r in rows]


async def _q_duplicates(session: AsyncSession) -> int:
    """帶 DUPLICATE 旗標的貼文數（精確比對該字串，排除 CANONICAL:* 等其他旗標）。"""
    return (
        await session.execute(
            text("SELECT COUNT(*) FROM posts WHERE quality_flags @> ARRAY['DUPLICATE']")
        )
    ).scalar_one()


async def _q_themes_overall(session: AsyncSession) -> list[tuple[str, int]]:
    rows = (
        await session.execute(
            text("SELECT label, COUNT(*) AS n FROM themes GROUP BY label ORDER BY n DESC")
        )
    ).all()
    return [(r.label, r.n) for r in rows]


async def _q_themes_by_source(session: AsyncSession) -> dict[str, dict[str, int]]:
    """{source: {label: n}}。只含有 theme 的貼文（INNER JOIN）。"""
    rows = (
        await session.execute(
            text(
                """
                SELECT p.source AS source, t.label AS label, COUNT(*) AS n
                FROM themes t
                JOIN posts p ON p.id = t.post_id
                GROUP BY p.source, t.label
                """
            )
        )
    ).all()
    out: dict[str, dict[str, int]] = {}
    for r in rows:
        out.setdefault(r.source, {})[r.label] = r.n
    return out


async def _q_sentiment_overall(session: AsyncSession) -> dict[str, int]:
    rows = (
        await session.execute(
            text("SELECT label, COUNT(*) AS n FROM sentiments GROUP BY label")
        )
    ).all()
    return {r.label: r.n for r in rows}


async def _q_sentiment_by_source(session: AsyncSession) -> dict[str, dict[str, int]]:
    rows = (
        await session.execute(
            text(
                """
                SELECT p.source AS source, s.label AS label, COUNT(*) AS n
                FROM sentiments s
                JOIN posts p ON p.id = s.post_id
                GROUP BY p.source, s.label
                """
            )
        )
    ).all()
    out: dict[str, dict[str, int]] = {}
    for r in rows:
        out.setdefault(r.source, {})[r.label] = r.n
    return out


async def _q_years(session: AsyncSession) -> list[tuple[int | None, int]]:
    """posted_at 年度覆蓋（發佈時間，非入庫 created_at）。posted_at 為 NULL 歸 None。"""
    rows = (
        await session.execute(
            text(
                """
                SELECT EXTRACT(YEAR FROM posted_at)::int AS y, COUNT(*) AS n
                FROM posts
                GROUP BY y
                ORDER BY y NULLS LAST
                """
            )
        )
    ).all()
    return [(r.y, r.n) for r in rows]


async def _q_top_authors(session: AsyncSession, limit: int = 5) -> dict[str, list[tuple[str, int]]]:
    """各來源前 N 名作者（排除 NULL 作者）。用 window function 一次取出。"""
    rows = (
        await session.execute(
            text(
                """
                SELECT source, author, n FROM (
                    SELECT
                        source,
                        author,
                        COUNT(*) AS n,
                        ROW_NUMBER() OVER (PARTITION BY source ORDER BY COUNT(*) DESC) AS rn
                    FROM posts
                    WHERE author IS NOT NULL AND author <> ''
                    GROUP BY source, author
                ) ranked
                WHERE rn <= :limit
                ORDER BY source, n DESC
                """
            ),
            {"limit": limit},
        )
    ).all()
    out: dict[str, list[tuple[str, int]]] = {}
    for r in rows:
        out.setdefault(r.source, []).append((r.author, r.n))
    return out


# --------------------------------------------------------------------------- #
# Render（純函式，把上面結構組成 Markdown 字串）。
# --------------------------------------------------------------------------- #
def _render(
    sources: list[tuple[str, int]],
    quality: list[tuple[str, int, int, int, int, int]],
    dup_count: int,
    themes_overall: list[tuple[str, int]],
    themes_by_source: dict[str, dict[str, int]],
    sent_overall: dict[str, int],
    sent_by_source: dict[str, dict[str, int]],
    years: list[tuple[int | None, int]],
    top_authors: dict[str, list[tuple[str, int]]],
) -> str:
    total = sum(n for _, n in sources)
    src_order = [s for s, _ in sources]  # 依筆數排序的來源清單
    lines: list[str] = []

    lines.append("# 語料庫分析報告（Corpus Analytics Report）")
    lines.append("")
    lines.append(
        f"產生時間：{datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}　"
        f"（唯讀統計，由 `scripts/corpus_report.py` 自動產出）"
    )
    lines.append("")

    # 1. 總量 + 來源占比
    lines.append("## 1. 總量與來源分佈")
    lines.append("")
    lines.append(f"**貼文總數：{total:,}**")
    lines.append("")
    lines.append("| 來源 | 筆數 | 占比 | |")
    lines.append("| --- | ---: | ---: | --- |")
    for src, n in sources:
        lines.append(f"| {src} | {n:,} | {_pct(n, total)} | `{_bar(n / total if total else 0)}` |")
    lines.append("")

    # 2. 品質分佈
    lines.append("## 2. 品質分佈（quality_score）")
    lines.append("")
    lines.append("分桶：**high ≥ 70**、**mid 30–69**、**low < 30**、**null（尚未檢核）**。")
    lines.append("")
    lines.append("| 來源 | 總數 | high | mid | low | null |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: |")
    # 整體列（把各來源加總）
    agg = [0, 0, 0, 0, 0]
    for _src, tot, high, mid, low, qn in quality:
        agg[0] += tot
        agg[1] += high
        agg[2] += mid
        agg[3] += low
        agg[4] += qn
    lines.append(
        f"| **整體** | {agg[0]:,} | {agg[1]:,} ({_pct(agg[1], agg[0])}) | "
        f"{agg[2]:,} ({_pct(agg[2], agg[0])}) | {agg[3]:,} ({_pct(agg[3], agg[0])}) | "
        f"{agg[4]:,} ({_pct(agg[4], agg[0])}) |"
    )
    for src, tot, high, mid, low, qn in quality:
        lines.append(
            f"| {src} | {tot:,} | {high:,} ({_pct(high, tot)}) | {mid:,} ({_pct(mid, tot)}) | "
            f"{low:,} ({_pct(low, tot)}) | {qn:,} ({_pct(qn, tot)}) |"
        )
    lines.append("")

    # 3. DUPLICATE
    lines.append("## 3. 重複旗標（DUPLICATE）")
    lines.append("")
    lines.append(
        f"帶 `DUPLICATE` 旗標的貼文：**{dup_count:,}** 筆"
        f"（占全語料 {_pct(dup_count, total)}）。"
    )
    lines.append("")
    lines.append(
        "> 註：去重 pipeline 另以 `CANONICAL:<id>` 旗標標出每組重複的代表貼文，此處只計 `DUPLICATE`。"
    )
    lines.append("")

    # 4. 主題分佈（標出新工具偏斜）
    lines.append("## 4. 主題分佈（themes）")
    lines.append("")
    theme_total = sum(n for _, n in themes_overall)
    theme_labels = [lab for lab, _ in themes_overall]
    lines.append(f"已分類主題的貼文：{theme_total:,} 筆。")
    lines.append("")
    lines.append("### 4.1 整體")
    lines.append("")
    lines.append("| 主題 | 筆數 | 占比 | |")
    lines.append("| --- | ---: | ---: | --- |")
    for lab, n in themes_overall:
        mark = "  ⚠️ **偏斜**" if (theme_total and n / theme_total >= 0.5) else ""
        lines.append(
            f"| {lab} | {n:,} | {_pct(n, theme_total)} | "
            f"`{_bar(n / theme_total if theme_total else 0)}`{mark} |"
        )
    lines.append("")
    # 偏斜提示
    if themes_overall:
        top_label, top_n = themes_overall[0]
        if theme_total and top_n / theme_total >= 0.5:
            lines.append(
                f"> ⚠️ **主題嚴重偏斜**：「{top_label}」單一主題就占了 {_pct(top_n, theme_total)}"
                f"（{top_n:,} / {theme_total:,}）。zero-shot 假設句把多數「介紹某 AI 工具 / 專案」"
                f"的貼文都吃進「新工具」，類別嚴重不平衡——做訓練 / 評測時需注意（重採樣或調門檻）。"
            )
            lines.append("")

    lines.append("### 4.2 各來源主題占比")
    lines.append("")
    header = "| 來源 | " + " | ".join(theme_labels) + " |"
    sep = "| --- | " + " | ".join(["---:"] * len(theme_labels)) + " |"
    lines.append(header)
    lines.append(sep)
    for src in src_order:
        dist = themes_by_source.get(src, {})
        sub = sum(dist.values())
        cells = [f"{dist.get(lab, 0):,} ({_pct(dist.get(lab, 0), sub)})" for lab in theme_labels]
        lines.append(f"| {src} | " + " | ".join(cells) + " |")
    lines.append("")

    # 5. 情緒分佈
    lines.append("## 5. 情緒分佈（sentiments）")
    lines.append("")
    sent_order = ["positive", "neutral", "negative"]
    zh_sent = {"positive": "正面", "neutral": "中性", "negative": "負面"}
    sent_total = sum(sent_overall.values())
    lines.append(f"已分析情緒的貼文：{sent_total:,} 筆。")
    lines.append("")
    lines.append("| 來源 | 正面 positive | 中性 neutral | 負面 negative |")
    lines.append("| --- | ---: | ---: | ---: |")
    lines.append(
        "| **整體** | "
        + " | ".join(
            f"{sent_overall.get(k, 0):,} ({_pct(sent_overall.get(k, 0), sent_total)})"
            for k in sent_order
        )
        + " |"
    )
    for src in src_order:
        dist = sent_by_source.get(src, {})
        sub = sum(dist.values())
        cells = [f"{dist.get(k, 0):,} ({_pct(dist.get(k, 0), sub)})" for k in sent_order]
        lines.append(f"| {src} | " + " | ".join(cells) + " |")
    lines.append("")
    _ = zh_sent  # 標頭已含中文，保留對照表備用

    # 6. 年度覆蓋
    lines.append("## 6. 發佈時間覆蓋（posted_at 年度）")
    lines.append("")
    lines.append("> 採貼文在來源平台的**發佈時間** `posted_at`；`created_at` 是入庫時間，不採用。")
    lines.append("")
    year_total = sum(n for _, n in years)
    lines.append("| 年份 | 筆數 | 占比 | |")
    lines.append("| --- | ---: | ---: | --- |")
    for y, n in years:
        label = str(y) if y is not None else "（無 posted_at）"
        lines.append(
            f"| {label} | {n:,} | {_pct(n, year_total)} | `{_bar(n / year_total if year_total else 0)}` |"
        )
    lines.append("")

    # 7. 各來源前 5 名作者
    lines.append("## 7. 各來源前 5 名作者")
    lines.append("")
    for src in src_order:
        authors = top_authors.get(src, [])
        if not authors:
            lines.append(f"- **{src}**：（無具名作者）")
            continue
        joined = "、".join(f"{a}（{n:,}）" for a, n in authors)
        lines.append(f"- **{src}**：{joined}")
    lines.append("")

    # 8. 觀察 / findings（自動產生）
    lines.append("## 8. 觀察 / Findings（自動產生）")
    lines.append("")
    lines.extend(
        _findings(
            sources,
            total,
            themes_by_source,
            sent_by_source,
            dup_count,
            agg,
        )
    )
    lines.append("")
    return "\n".join(lines)


def _dominant_theme(dist: dict[str, int]) -> tuple[str, float]:
    """回傳某來源最大主題的 (label, 占比 0-1)。"""
    sub = sum(dist.values())
    if not sub:
        return ("（無）", 0.0)
    lab, n = max(dist.items(), key=lambda kv: kv[1])
    return (lab, n / sub)


def _neg_ratio(dist: dict[str, int]) -> float:
    sub = sum(dist.values())
    return (dist.get("negative", 0) / sub) if sub else 0.0


def _findings(
    sources: list[tuple[str, int]],
    total: int,
    themes_by_source: dict[str, dict[str, int]],
    sent_by_source: dict[str, dict[str, int]],
    dup_count: int,
    quality_agg: list[int],
) -> list[str]:
    """從統計結果自動湊出幾條重點觀察（純函式，不查 DB）。"""
    out: list[str] = []

    # (a) 來源集中度
    if sources:
        top_src, top_n = sources[0]
        out.append(
            f"- **來源高度集中**：`{top_src}` 一家就占 {_pct(top_n, total)}"
            f"（{top_n:,} / {total:,}），其餘來源（含中文 PTT/Threads）為長尾；"
            f"做來源無偏分析時需分層或加權。"
        )

    # (b) 中文 vs 英文來源的主題差異
    zh_present = [s for s in _ZH_SOURCES if themes_by_source.get(s)]
    en_present = [s for s in _EN_SOURCES if themes_by_source.get(s)]
    for grp_name, grp in (("中文來源", zh_present), ("英文來源", en_present)):
        parts = []
        for s in grp:
            lab, frac = _dominant_theme(themes_by_source[s])
            parts.append(f"{s} 以「{lab}」為主（{frac * 100:.0f}%）")
        if parts:
            out.append(f"- **{grp_name}主題傾向**：" + "；".join(parts) + "。")

    # 直接對比 hackernews vs threads/ptt 的「使用方法」「風險限制」占比
    def _theme_share(src: str, label: str) -> float:
        dist = themes_by_source.get(src, {})
        sub = sum(dist.values())
        return (dist.get(label, 0) / sub) if sub else 0.0

    if themes_by_source.get("hackernews") and (
        themes_by_source.get("threads") or themes_by_source.get("ptt")
    ):
        zh_use = max(_theme_share("threads", "使用方法"), _theme_share("ptt", "使用方法"))
        hn_use = _theme_share("hackernews", "使用方法")
        out.append(
            f"- **中英主題差異（使用方法）**：中文社群（Threads/PTT）談「使用方法 / 教學」"
            f"的比例（最高約 {zh_use * 100:.0f}%）明顯高於英文 HackerNews（約 {hn_use * 100:.0f}%）；"
            f"英文來源更偏「新工具 / 專案發表」，符合 HN 的 Show HN 文化。"
        )

    # (c) 情緒：整體中性為主 + 負面占比最高的來源
    if sent_by_source:
        worst = max(sent_by_source.items(), key=lambda kv: _neg_ratio(kv[1]), default=None)
        if worst:
            wsrc, wdist = worst
            out.append(
                f"- **情緒以中性為主**：多數來源中性占絕大宗（資訊 / 公告型貼文）；"
                f"負面占比最高的來源是 `{wsrc}`（{_neg_ratio(wdist) * 100:.0f}%），"
                f"可作為「風險 / 抱怨」訊號的優先挖掘點。"
            )

    # (d) 品質 / 重複
    if quality_agg[0]:
        out.append(
            f"- **品質與重複**：high(≥70) 約占 {_pct(quality_agg[1], quality_agg[0])}、"
            f"null(未檢核) {_pct(quality_agg[4], quality_agg[0])}；"
            f"另有 {dup_count:,} 筆被標 `DUPLICATE`（{_pct(dup_count, total)}），"
            f"訓練 / 評測前應先濾掉重複與低品質。"
        )

    return out


# --------------------------------------------------------------------------- #
async def build_report(limit_authors: int = 5) -> str:
    """開一個唯讀 session，跑完所有查詢並組成 Markdown。"""
    async with AsyncSessionLocal() as session:
        sources = await _q_sources(session)
        quality = await _q_quality(session)
        dup_count = await _q_duplicates(session)
        themes_overall = await _q_themes_overall(session)
        themes_by_source = await _q_themes_by_source(session)
        sent_overall = await _q_sentiment_overall(session)
        sent_by_source = await _q_sentiment_by_source(session)
        years = await _q_years(session)
        top_authors = await _q_top_authors(session, limit_authors)

    return _render(
        sources,
        quality,
        dup_count,
        themes_overall,
        themes_by_source,
        sent_overall,
        sent_by_source,
        years,
        top_authors,
    )


async def main(out: str | None) -> None:
    report = await build_report()
    if out:
        out_path = Path(out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report, encoding="utf-8")
        print(f"✅ 報告已寫入 {out_path}（{len(report):,} 字元）")
    else:
        print(report)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="語料庫唯讀分析報告（Markdown）。")
    parser.add_argument(
        "--out",
        default=None,
        help="輸出 Markdown 檔路徑（預設印到 stdout）。例：docs/corpus-report.md",
    )
    args = parser.parse_args()
    asyncio.run(main(args.out))
