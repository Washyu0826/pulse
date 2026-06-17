"""
每日電子報組裝 —— 純函式（精選挑選、口碑統計、封面 prompt、HTML 組版）。

全免費 / 地端（[[prefer-local-llm]]）：摘要走本地 Qwen、寄送走 Gmail SMTP —— 都不打雲端付費 API。
本模組只放**純函式**（無 DB / 網路 / matplotlib / torch 依賴），可單元測試；DB 查詢、SD 生成、
SMTP 寄送在 scripts/send_newsletter.py。

版型：報紙社論版（broadsheet，方向 D1）—— 明體 serif、報頭 masthead、dateline、社論首字下沉、
多欄事件（頭條 / 雙欄 / 三欄短訊）、新聞紙風 HTML 條圖（不用彩色 PNG）、無圓角無方框卡片。
主題對齊 theme.py 5 類 + 其他。每篇貼文以 dict 表示（見 select_highlights 的欄位說明）。
"""
from __future__ import annotations

import html as _html
import re
from datetime import date as _date
from email.header import Header
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid
from statistics import median

from . import hotness as _hot

__all__ = [
    "THEME_ICON",
    "THEME_ORDER",
    "SENTIMENT_ICON",
    "pangu_spacing",
    "select_highlights",
    "sentiment_movers",
    "theme_counts",
    "cover_prompt",
    "render_today_events_section",
    "render_html",
    "html_to_text",
    "build_mime_message",
    "_weather",
    "_pick_lead",
]

# --- 報紙版視覺 token（新聞紙米白 + 墨黑 + 油墨暗紅；720px；CJK 明體棧）---
_PAPER = "#f4f1ea"   # 內頁新聞紙米白
_FRAME = "#d9d4c8"   # 外框較深米
_INK = "#1a1a1a"     # 墨黑（標題 / 主文 / 粗線）
_RED = "#7a1f1f"     # 油墨暗紅（報眉 / 欄目 / 引註 / 數字）
_SUB = "#5a5444"     # 次要灰（byline / 出處）
_RULE = "#c7c0ad"    # 細分隔線
_DOT = "#9a9384"     # 點線分隔
_BODY = "#26241e"    # 主文墨色
_BRIEF = "#3a372e"   # 短訊 / 摘要墨色
_CHIPBG = "#e8e3d6"  # 行內 code 底

_F_DISP = "Georgia,'Times New Roman','Songti TC','Noto Serif TC','Source Han Serif TC',serif"
_F_BODY = "'Songti TC','Noto Serif TC','Source Han Serif TC',Georgia,serif"
_F_LAB = "Georgia,'Songti TC','Noto Serif TC',serif"
_F_PULSE = "Georgia,'Times New Roman',serif"
_F_MONO = "'Courier New',monospace"

_WIDTH = 720
_WK = "一二三四五六日"

# CJK 範圍（pangu 空格用）
_CJK = r"一-鿿㐀-䶿豈-﫿"
_PANGU_A = re.compile(rf"([{_CJK}])([0-9A-Za-z@#$%^&*])")
_PANGU_B = re.compile(rf"([0-9A-Za-z!~&;:,.?$%^*\]\)])([{_CJK}])")


def pangu_spacing(text: str) -> str:
    """
    在中日韓字與相鄰的英數之間插入半形空格（盤古之白）—— 讓「使用GPT-4o」→「使用 GPT-4o」，
    這是混排中英 AI 文案看起來專業的最大單一改善。冪等、純函式。
    """
    if not text:
        return text
    text = _PANGU_A.sub(r"\1 \2", text)
    text = _PANGU_B.sub(r"\1 \2", text)
    return text


# ----------------------- 功能 1：AI 圈今日天氣 -----------------------
def _weather(sentiment_counts: dict | None) -> tuple[str, str]:
    """
    依當日情緒比例，把 AI 圈的「氣氛」映成一句天氣。純函式、確定性。

    回 (emoji, 中文標籤)。門檻（以負/正占比判，總數需 > 0）：
    - 負面占比高（neg/total ≥ 0.30）→ 🌧️ 雷雨（爭議多）：爭議 / 負評壓過大盤。
    - 正面明顯多於負面（pos ≥ 2*neg 且 pos/total ≥ 0.25）→ ☀️ 晴（樂觀）：樂觀情緒主導。
    - 其餘（偏中性 / 正負相當）→ ⛅ 多雲（平穩）。
    - 空資料 / 全 0 → 🌫️ 未明：安全 fallback，不報錯。

    判斷順序：雷雨（負面優先，爭議最該被看見）→ 晴 → 多雲。
    """
    counts = sentiment_counts or {}
    pos = max(0, int(counts.get("positive") or 0))
    neu = max(0, int(counts.get("neutral") or 0))
    neg = max(0, int(counts.get("negative") or 0))
    total = pos + neu + neg
    if total == 0:
        return ("🌫️", "未明")
    if neg / total >= 0.30:
        return ("🌧️", "雷雨（爭議多）")
    if pos >= 2 * neg and pos / total >= 0.25:
        return ("☀️", "晴（樂觀）")
    return ("⛅", "多雲（平穩）")


# 顯示用 icon / 順序（與 theme.py 對齊；使用方法為錨點排前面）。報紙版不顯示 emoji，
# 但常數保留供其他模組 / 向後相容引用。
THEME_ORDER = ("新工具", "模型動態", "使用方法", "風險限制", "倫理法規")
THEME_ICON = {
    "新工具": "🆕",
    "模型動態": "📊",
    "使用方法": "🛠️",
    "風險限制": "🚧",
    "倫理法規": "⚖️",
    "其他": "⚪",
}
SENTIMENT_ICON = {"positive": "🟢", "neutral": "⚪", "negative": "🔴"}


def _engagement(post: dict) -> int:
    """互動分數（讚 + 留言），用於同主題內排序。缺值當 0。

    保留供向後相容；排序已改用 hotness.engagement / per-source 正規化（見 _source_baselines）。
    """
    return int(post.get("score") or 0) + int(post.get("num_comments") or 0)


def _source_of(post: dict) -> str:
    """來源鍵：取 source，缺值歸 'unknown'。同來源才互相比較互動量級。"""
    return str(post.get("source") or "unknown")


def _source_baselines(posts: list[dict]) -> dict[str, float]:
    """
    算各來源的互動「基準」= 該來源所有貼文 hotness.engagement 的中位數（純函式、確定性）。

    為何用中位數而非平均/最大：HN 偶有爆文（points 上千），平均/最大會被單篇拉高，
    讓正常 HN 貼文反而「相對不熱」；中位數代表該來源的典型量級，最能公平正規化。
    只納入互動 > 0 的貼文算中位數（全 0 或無正互動的來源 → 不給基準，post_hotness
    會退回 log 壓縮）。回傳 {source: baseline>0}。
    """
    by_src: dict[str, list[float]] = {}
    for p in posts:
        e = _hot.engagement(p)
        if e > 0:
            by_src.setdefault(_source_of(p), []).append(e)
    return {src: median(vals) for src, vals in by_src.items() if vals}


def _hotness_key(post: dict, baselines: dict[str, float]):
    """
    排序鍵：per-source 正規化熱度，同分以 id 決勝（確定性）。

    age_hours=0：在 1 天視窗內時間衰減對所有貼文一致（分母同為定值），不影響相對排序；
    重點是用該來源基準正規化互動，讓 Threads 讚數與 HN points 在「同量級尺度」上競爭。
    來源無基準時 source_baseline=None → post_hotness 退回 log 壓縮（仍可比、不爆長尾）。
    """
    baseline = baselines.get(_source_of(post))
    h = _hot.post_hotness(post, age_hours=0, source_baseline=baseline)
    return (h, post.get("id", 0))


def _rank_balanced(posts: list[dict], baselines: dict[str, float], k: int) -> list[dict]:
    """
    取前 k 篇，但做「同來源至少露出」的輕量平衡（純函式、確定性）。

    各來源內先依正規化熱度排序，再以 round-robin 跨來源輪流取（每輪各來源出最熱的一篇），
    來源順序依「該來源當前最熱貼文的熱度」由高到低。效果：高量級來源（HN）不會因
    原始互動大就洗版整個區塊，主力來源 Threads 能穩定露出；同時最熱的仍排前面。
    """
    if k <= 0:
        return []
    by_src: dict[str, list[dict]] = {}
    for p in posts:
        by_src.setdefault(_source_of(p), []).append(p)
    queues = {
        src: sorted(items, key=lambda p: _hotness_key(p, baselines), reverse=True)
        for src, items in by_src.items()
    }
    out: list[dict] = []
    while len(out) < k and any(queues.values()):
        # 每輪：依各來源「下一篇待選」的熱度排來源序，輪流各取一篇（同來源至少露出）。
        ready = [src for src, q in queues.items() if q]
        ready.sort(key=lambda s: _hotness_key(queues[s][0], baselines), reverse=True)
        for src in ready:
            if len(out) >= k:
                break
            out.append(queues[src].pop(0))
    return out


def select_highlights(
    posts: list[dict],
    *,
    per_theme: int = 3,
    min_quality: int = 30,
    themes: tuple[str, ...] = THEME_ORDER,
) -> dict[str, list[dict]]:
    """
    從當日貼文挑各主題精選。純函式 —— 不改動輸入、確定性。

    每篇 post 期望欄位：theme（主題標籤）、score、num_comments、quality_score（可選）、
    title / title_zh / snippet_zh / url / source / sentiment。
    規則：濾掉 quality_score < min_quality（None 視為通過）、依主題分組、組內以
    **per-source 正規化熱度**（hotness.post_hotness + 各來源互動中位數基準）排序，並做
    「同來源至少露出」的輕量平衡後取前 per_theme 篇。這讓 Threads（讚數量級天生低於
    HN points）能在同來源尺度上公平競爭、不被高量級來源擠掉。基準由傳入 posts 內部算，
    無需 DB → 仍是純函式、確定性。回傳 {主題: [post, ...]}，只含有貼文的主題、依 themes 順序。
    """
    baselines = _source_baselines(posts)
    by_theme: dict[str, list[dict]] = {t: [] for t in themes}
    for p in posts:
        q = p.get("quality_score")
        if q is not None and q < min_quality:
            continue
        t = p.get("theme")
        if t in by_theme:
            by_theme[t].append(p)
    out: dict[str, list[dict]] = {}
    for t in themes:
        items = _rank_balanced(by_theme[t], baselines, per_theme)
        if items:
            out[t] = items
    return out


def sentiment_movers(posts: list[dict], *, k: int = 3) -> dict[str, list[dict]]:
    """
    挑當日口碑最鮮明的貼文：最多 k 篇正評、k 篇負評。純函式。

    排序改用 per-source 正規化熱度（同 select_highlights）＋「同來源至少露出」平衡，
    讓主力來源 Threads 不被 HN 量級壓掉；基準由傳入 posts 內部算（無需 DB）。
    """
    baselines = _source_baselines(posts)
    pos = [p for p in posts if p.get("sentiment") == "positive"]
    neg = [p for p in posts if p.get("sentiment") == "negative"]
    return {
        "positive": _rank_balanced(pos, baselines, k),
        "negative": _rank_balanced(neg, baselines, k),
    }


def theme_counts(posts: list[dict], *, themes: tuple[str, ...] = THEME_ORDER) -> dict[str, int]:
    """各主題當日貼文數（給圖表用）。含「其他」。純函式。"""
    counts = dict.fromkeys(themes, 0)
    counts["其他"] = 0
    for p in posts:
        t = p.get("theme")
        if t in counts:
            counts[t] += 1
        else:
            counts["其他"] += 1
    return counts


def cover_prompt(top_terms: list[str], *, lead_theme: str | None = None) -> str:
    """
    組地端 Stable Diffusion 的封面題圖 prompt（英文，SD 對英文較準）。純函式。

    報紙版型預設不放題圖，此函式仍保留供未來 / 其他版型使用。
    """
    terms = ", ".join(t for t in top_terms[:4] if t) or "artificial intelligence"
    mood = {
        "風險限制": "cautious, sparse composition",
        "倫理法規": "thoughtful, balanced composition",
        "新工具": "bold, energetic shapes",
        "模型動態": "data-driven, charts and graph motif",
        "使用方法": "clean, instructional layout",
    }.get(lead_theme or "", "warm, optimistic")
    return (
        f"risograph print illustration, abstract editorial scene about {terms}, "
        f"{mood}, two-color duotone in brick red and warm cream, grainy halftone texture, "
        f"limited spot-color palette, bold simple flat shapes, retro screenprint, "
        f"visible paper grain, slight ink misregistration, no gradients, no text, no words, "
        f"no logo, 16:9"
    )


# ----------------------- 報紙版渲染小工具 -----------------------
def _u(url) -> str:
    return _html.escape(str(url or "#"), quote=True)


def _cn_date(day: _date) -> str:
    return f"{day.year} 年 {day.month} 月 {day.day} 日 星期{_WK[day.weekday()]}"


def _sup_refs(text: str, valid_ns: set) -> str:
    """把文字中的 `[n]` 轉成小字上標引註（有對應 citation→暗紅，無→灰）。先盤古空格 + HTML 跳脫。"""
    escaped = _html.escape(pangu_spacing(text or ""))

    def _wrap(m: "re.Match[str]") -> str:
        n = m.group(1)
        color = _RED if int(n) in valid_ns else _SUB
        return (
            f'<sup style="font-size:9px;color:{color};font-weight:bold;'
            f'font-family:{_F_LAB}">[{n}]</sup>'
        )

    return re.sub(r"\[(\d+)\]", _wrap, escaped)


def _dropcap_body(text: str, valid_ns: set, *, cap_color: str, cap_size: int, font_size: str) -> str:
    """首字下沉的本文段落：第一個字放大浮左，其餘套盤古空格 + 行內引註。"""
    text = text or ""
    if not text:
        return ""
    first, rest = text[0], text[1:]
    cap = (
        f'<span style="float:left;font-family:{_F_DISP};font-size:{cap_size}px;'
        f'line-height:.78;font-weight:bold;color:{cap_color};padding:5px 9px 0 0">'
        f"{_html.escape(first)}</span>"
    )
    return (
        f'<div style="font-family:{_F_BODY};font-size:{font_size};line-height:1.95;'
        f'color:{_BODY};text-align:justify">{cap}{_sup_refs(rest, valid_ns)}</div>'
    )


def _plain_body(text: str, valid_ns: set, *, font_size: str) -> str:
    return (
        f'<div style="font-family:{_F_BODY};font-size:{font_size};line-height:1.92;'
        f'color:{_BODY};text-align:justify">{_sup_refs(text or "", valid_ns)}</div>'
    )


def _valid_ns(citations: list[dict]) -> set:
    return {c["n"] for c in citations if c.get("n") is not None}


def _byline(event: dict, *, lead: bool = False) -> str:
    """事件 byline：（頭條才有）特派整理 · 綜合 N 則來源 · 忠實度 0.xx。"""
    bits: list[str] = []
    if lead:
        bits.append("特派整理 · Pulse 編輯部")
    mc = event.get("member_count")
    if mc is None:
        mc = event.get("memberCount")
    if mc is not None:
        bits.append(f"綜合 {mc} 則來源")
    f = event.get("faithfulness_score")
    if isinstance(f, (int, float)):
        bits.append(f"忠實度 {f:.2f}")
    return " · ".join(bits)


def _citations_line(citations: list[dict], *, font_size: str = "10.5px") -> str:
    """事件「出處」清單：每筆 [n] 連原貼（無 url 則純文字、不帶連結）。"""
    links: list[str] = []
    for c in citations:
        n = c.get("n")
        if n is None:
            continue
        label = c.get("source") or c.get("post_id") or c.get("postId") or ""
        suffix = f" {pangu_spacing(str(label))}" if label else ""
        body = _html.escape(f"[{n}]{suffix}")
        url = c.get("url")
        if url:
            links.append(
                f'<a href="{_u(url)}" style="color:{_INK};text-decoration:none;'
                f'border-bottom:1px solid {_RULE}">{body}</a>'
            )
        else:
            links.append(f'<span style="color:{_INK}">{body}</span>')
    if not links:
        return ""
    return (
        f'<div style="border-top:1px dotted {_DOT};padding-top:8px;margin-top:10px;'
        f'font-family:{_F_LAB};font-size:{font_size};line-height:1.9;color:{_SUB}">'
        f'<span style="letter-spacing:.18em;text-transform:uppercase;color:{_RED};'
        f'font-weight:bold">出處 — </span>' + " · ".join(links) + "</div>"
    )


def _hr_row(*, thick: bool = False, double: bool = False, pt: str = "24px") -> str:
    if double:
        border = f"border-top:3px double {_INK}"
    elif thick:
        border = f"border-top:1px solid {_INK};border-bottom:1px solid {_INK};height:3px"
    else:
        border = f"border-top:1px solid {_INK}"
    return (
        f'<tr><td style="padding:{pt} 40px 0">'
        f'<div style="{border};font-size:0;line-height:0">&nbsp;</div></td></tr>'
    )


def _band_row(left: str, right: str = "") -> str:
    """欄目名橫幅：左欄目名（tracked-out 大寫）+ 右副註 + 下方粗線。"""
    right_td = (
        f'<td align="right" style="font-family:{_F_PULSE};font-size:11px;letter-spacing:.1em;'
        f'font-style:italic;color:{_SUB}">{_html.escape(right)}</td>'
        if right
        else ""
    )
    return (
        f'<tr><td style="padding:8px 40px 0">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
        f'<td align="left" style="font-family:{_F_PULSE};font-size:13px;letter-spacing:.3em;'
        f'text-transform:uppercase;color:{_INK};font-weight:bold">{_html.escape(left)}</td>'
        f"{right_td}</tr></table></td></tr>" + _hr_row(thick=True, pt="7px")
    )


# ----------------------- 區塊 -----------------------
def _ear_row() -> str:
    cell = (
        "font-family:" + _F_LAB + ";font-size:11px;letter-spacing:.14em;"
        "text-transform:uppercase;color:" + _SUB + ";font-style:italic"
    )
    return (
        f'<tr><td style="padding:22px 40px 0">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
        f'<td align="left" style="{cell}">繁體中文 · 地端產製</td>'
        f'<td align="center" style="font-family:{_F_LAB};font-size:11px;letter-spacing:.22em;'
        f'text-transform:uppercase;color:{_RED};font-weight:bold">每日 AI 情報</td>'
        f'<td align="right" style="{cell}">售價 · 免費</td></tr></table>'
        f'<div style="border-top:1px solid {_INK};margin-top:10px;font-size:0;line-height:0">&nbsp;</div>'
        f"</td></tr>"
    )


def _masthead_row(day: _date, sentiment_counts: dict | None = None) -> str:
    emoji, label = _weather(sentiment_counts)
    # dateline 中欄改成「每日隨情緒變化」的 AI 圈天氣（取代固定刊訓），這是報頭的每日變動性。
    center = pangu_spacing(f"今日 AI 圈天氣：{emoji} {label}")
    return (
        f'<tr><td align="center" style="padding:14px 40px 6px">'
        f'<div style="font-family:{_F_PULSE};font-size:78px;line-height:.92;font-weight:bold;'
        f'letter-spacing:.02em;color:{_INK}">Pulse</div>'
        f'<div style="font-family:{_F_BODY};font-size:19px;letter-spacing:.5em;color:{_INK};'
        f'margin:8px 0 0;padding-left:.5em">每日人工智慧週報</div></td></tr>'
        f'<tr><td style="padding:14px 40px 0">'
        f'<div style="border-top:3px double {_INK};border-bottom:1px solid {_INK};padding:7px 0">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
        f'<td align="left" style="font-family:{_F_LAB};font-size:12px;color:{_INK}">{_cn_date(day)}</td>'
        f'<td align="center" style="font-family:{_F_LAB};font-size:11px;font-style:italic;'
        f'color:{_RED};font-weight:bold">{_html.escape(center)}</td>'
        f'<td align="right" style="font-family:{_F_LAB};font-size:12px;color:{_INK}">地端 · 每日</td>'
        f"</tr></table></div></td></tr>"
    )


def _editorial_row(summary: str) -> str:
    if not summary:
        return ""
    body = _dropcap_body(summary, set(), cap_color=_RED, cap_size=56, font_size="16px")
    return (
        f'<tr><td style="padding:24px 40px 0">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
        f'<td width="118" valign="top" style="padding-right:22px;border-right:1px solid {_RULE}">'
        f'<div style="font-family:{_F_PULSE};font-size:11px;letter-spacing:.22em;'
        f'text-transform:uppercase;color:{_RED};font-weight:bold;line-height:1.5">Editor’s<br>Note</div>'
        f'<div style="font-family:{_F_BODY};font-size:13px;color:{_SUB};letter-spacing:.3em;'
        f'margin-top:6px">今日<br>要事</div></td>'
        f'<td valign="top" style="padding-left:24px">{body}</td>'
        f"</tr></table></td></tr>"
    )


def _split_two(text: str) -> tuple[str, str]:
    """把較長的本文從中段的句號處切兩半（給頭條兩欄）。太短則不切。"""
    text = text or ""
    if len(text) < 70:
        return text, ""
    mid = len(text) // 2
    idx = text.find("。", mid)
    if idx == -1 or idx > len(text) - 6:
        return text, ""
    return text[: idx + 1], text[idx + 1 :]


def _lead_story(event: dict) -> str:
    title = pangu_spacing(str(event.get("title") or "(無標題)"))
    citations = event.get("citations") or []
    vns = _valid_ns(citations)
    left_raw, right_raw = _split_two(str(event.get("summary") or ""))
    left = _dropcap_body(left_raw, vns, cap_color=_INK, cap_size=48, font_size="14.5px")
    if right_raw:
        right = _plain_body(right_raw, vns, font_size="14.5px")
        body = (
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
            f'<td width="316" valign="top" style="padding-right:22px">{left}</td>'
            f'<td width="316" valign="top" style="padding-left:22px;border-left:1px solid {_RULE}">'
            f"{right}</td></tr></table>"
        )
    else:
        body = left
    byline = _byline(event, lead=True)
    byline_row = (
        f'<tr><td style="padding:14px 40px 0">'
        f'<div style="border-top:1px solid {_RULE};border-bottom:1px solid {_RULE};padding:6px 0;'
        f'font-family:{_F_PULSE};font-size:11px;letter-spacing:.12em;text-transform:uppercase;'
        f'color:{_SUB};text-align:center">{_html.escape(byline)}</div></td></tr>'
        if byline
        else ""
    )
    cite = _citations_line(citations)
    cite_row = f'<tr><td style="padding:14px 40px 0">{cite}</td></tr>' if cite else ""
    return (
        f'<tr><td style="padding:20px 40px 0">'
        f'<div style="font-family:{_F_DISP};font-size:32px;line-height:1.18;font-weight:bold;'
        f'letter-spacing:.01em;color:{_INK};text-align:center">{_html.escape(title)}</div></td></tr>'
        f"{byline_row}"
        f'<tr><td style="padding:18px 40px 0">{body}</td></tr>'
        f"{cite_row}"
    )


def _pair_cell(event: dict, *, left_border: bool) -> str:
    title = pangu_spacing(str(event.get("title") or "(無標題)"))
    kicker = str(event.get("theme") or "今日事件")
    citations = event.get("citations") or []
    vns = _valid_ns(citations)
    byline = _byline(event)
    pad = "padding-left:22px" if left_border else "padding-right:22px"
    border = f";border-left:1px solid {_INK}" if left_border else ""
    byline_div = (
        f'<div style="font-family:{_F_PULSE};font-size:10px;letter-spacing:.1em;'
        f'text-transform:uppercase;color:{_SUB};margin:8px 0 10px;border-bottom:1px solid {_RULE};'
        f'padding-bottom:8px">{_html.escape(byline)}</div>'
        if byline
        else ""
    )
    cite = _citations_line(citations, font_size="10px")
    return (
        f'<td width="316" valign="top" style="{pad}{border}">'
        f'<div style="font-family:{_F_PULSE};font-size:10.5px;letter-spacing:.2em;'
        f'text-transform:uppercase;color:{_RED};font-weight:bold">{_html.escape(kicker)}</div>'
        f'<div style="font-family:{_F_DISP};font-size:21px;line-height:1.3;font-weight:bold;'
        f'color:{_INK};margin:7px 0 0">{_html.escape(title)}</div>'
        f"{byline_div}{_plain_body(str(event.get('summary') or ''), vns, font_size='14px')}"
        f"{cite}</td>"
    )


def _pair_block(events: list[dict]) -> str:
    if not events:
        return ""
    if len(events) == 1:
        cells = _pair_cell(events[0], left_border=False).replace('width="316"', 'width="640"', 1)
    else:
        cells = _pair_cell(events[0], left_border=False) + _pair_cell(events[1], left_border=True)
    return (
        _hr_row(pt="26px")
        + f'<tr><td style="padding:18px 40px 0">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
        f"{cells}</tr></table></td></tr>"
    )


def _brief_cell(event: dict, *, position: int) -> str:
    title = pangu_spacing(str(event.get("title") or "(無標題)"))
    citations = event.get("citations") or []
    vns = _valid_ns(citations)
    mc = event.get("member_count")
    if mc is None:
        mc = event.get("memberCount")
    src = ""
    if citations:
        src = str(citations[0].get("source") or "")
    meta_bits = []
    if mc is not None:
        meta_bits.append(f"綜合 {mc} 則")
    if src:
        meta_bits.append(src)
    meta = " · ".join(meta_bits)
    if position == 0:
        style = "padding-right:18px"
    elif position == 1:
        style = f"padding:0 18px;border-left:1px solid {_RULE};border-right:1px solid {_RULE}"
    else:
        style = "padding-left:18px"
    meta_div = (
        f'<div style="font-family:{_F_PULSE};font-size:9.5px;color:{_SUB};margin-top:6px;'
        f'letter-spacing:.05em">{_html.escape(meta)}</div>'
        if meta
        else ""
    )
    return (
        f'<td width="206" valign="top" style="{style}">'
        f'<div style="font-family:{_F_DISP};font-size:16px;line-height:1.32;font-weight:bold;'
        f'color:{_INK}">{_html.escape(title)}</div>'
        f'<div style="font-family:{_F_BODY};font-size:12.5px;line-height:1.78;color:{_BRIEF};'
        f'text-align:justify;margin-top:7px">{_sup_refs(str(event.get("summary") or ""), vns)}</div>'
        f"{meta_div}</td>"
    )


def _briefs_block(events: list[dict]) -> str:
    if not events:
        return ""
    rows: list[str] = []
    for i in range(0, len(events), 3):
        chunk = events[i : i + 3]
        cells = "".join(_brief_cell(e, position=j) for j, e in enumerate(chunk))
        rows.append(
            f'<tr><td style="padding:18px 40px 0">'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
            f"{cells}</tr></table></td></tr>"
        )
    return _band_row("內頁 · 事件短訊") + "".join(rows)


def render_today_events_section(events: list[dict]) -> str:
    """
    組「今日事件」報紙版區塊 —— 把多篇相關貼文聚成的事件，依數量排成頭版版面：
    events[0] 頭條（大標 + byline + 兩欄本文 + 出處）、events[1:3] 雙欄並列、events[3:] 三欄短訊。
    每則含標題、帶行內 `[n]` 出處引註的忠實摘要、底部出處清單。純函式；空 list 回 ""。

    每則 event 期望欄位（對齊摘要管線輸出與前端 EventSummary）：
      - title (str)：事件標題。
      - summary (str)：忠實摘要文字，內含 `[1][2]` 行內引用標記。
      - citations (list[dict])：出處清單，每筆 {n:int, url?:str, source?:str/post_id?:str}。
      - member_count (int，可選；亦接受 memberCount)：成員貼文數。
      - faithfulness_score (float，可選)：忠實度，顯示於 byline。
      - theme (str，可選)：主題標籤，用於雙欄事件的欄目 kicker。
    """
    if not events:
        return ""
    parts = [
        _hr_row(pt="24px"),
        _band_row("頭版 · 今日事件", f"綜合多方來源 · 共 {len(events)} 則"),
        _lead_story(events[0]),
    ]
    parts.append(_pair_block(events[1:3]))
    parts.append(_briefs_block(events[3:]))
    return "".join(parts)


# ----------------------- 功能 2：頭版主秀輪播（資料驅動 hero）-----------------------
def _pick_lead(
    events: list[dict] | None,
    movers: dict | None,
    theme_counts: dict | None,
    sentiment_counts: dict | None,
    storylines: list[dict] | None,
) -> dict | None:
    """
    依當天資料決定頭版「今日主秀」hero 的形態（純函式、確定性）。回 None 表示不出 hero。

    規則（優先序由上到下；越上面越差異化）：
    1. 議題追蹤 hero（最優先）：storylines 有一條 state 為「升溫」或「高峰」且 span_days≥2
       → 取 hotness 最高那條 → {"kind": "storyline", "story": <story dict>}。
    2. 事件日：有 events → 回 None（今日事件頭條本身就是 lead，避免雙頭條）。
    3. 口碑交鋒 hero：無 events 但 movers 正反方都有 → {"kind": "clash", "pos": .., "neg": ..}。
    4. 數據日 hero：都很平淡（無 events 無可用 storyline）但有主題/情緒計數
       → {"kind": "data", "theme_counts": .., "sentiment_counts": ..}。
    5. 其餘 → None。

    缺檔 / 空 storylines / 缺欄位皆優雅退回下一種或 None，絕不報錯。
    """
    stories = storylines or []
    candidates = [
        s
        for s in stories
        if isinstance(s, dict)
        and s.get("state") in (_hot.STATE_RISING, _hot.STATE_PEAK)
        and isinstance(s.get("span_days"), (int, float))
        and s.get("span_days") >= 2
        and s.get("timeline")
    ]
    if candidates:
        best = max(candidates, key=lambda s: (float(s.get("hotness") or 0.0), str(s.get("id") or "")))
        return {"kind": "storyline", "story": best}

    if events:
        return None  # 事件日：頭條即 lead，不出額外 hero。

    movers = movers or {}
    pos = movers.get("positive") or []
    neg = movers.get("negative") or []
    if pos and neg:
        return {"kind": "clash", "pos": pos[0], "neg": neg[0]}

    tc = theme_counts or {}
    sc = sentiment_counts or {}
    if any(v for v in tc.values()) or any(v for v in sc.values()):
        return {"kind": "data", "theme_counts": tc, "sentiment_counts": sc}

    return None


def _hero_band(left: str, right: str = "") -> str:
    """hero 區塊頂部欄目橫幅：🗞 今日主秀 + 副註 + 粗線。沿用 _band_row 視覺語言。"""
    return _band_row(left, right)


def _story_timeline_bars(timeline: list[dict]) -> str:
    """迷你議題時間軸：各日一條（日期 + volume HTML 條 + 一句 summary），最末日標紅。"""
    days = [t for t in timeline if isinstance(t, dict)]
    if not days:
        return ""
    mx = max((float(t.get("volume") or 0.0) for t in days), default=0.0) or 1.0
    rows = ""
    last_i = len(days) - 1
    for i, t in enumerate(days):
        vol = float(t.get("volume") or 0.0)
        w = max(2, round(vol / mx * 100))
        color = _RED if i == last_i else _INK
        date_lbl = _html.escape(str(t.get("date") or ""))
        summ = pangu_spacing(str(t.get("summary") or ""))
        summ_html = _html.escape(summ)[:90]
        rows += (
            f'<tr><td style="padding:9px 0 0">'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
            f'<td width="86" valign="top" style="font-family:{_F_LAB};font-size:10.5px;'
            f'color:{_SUB};padding-top:1px">{date_lbl}</td>'
            f'<td valign="top">'
            f'<div style="background:{color};height:8px;width:{w}%;font-size:0;line-height:0;'
            f'min-width:6px">&nbsp;</div>'
            f'<div style="font-family:{_F_BODY};font-size:12px;line-height:1.6;color:{_BRIEF};'
            f'margin-top:4px;text-align:justify">{summ_html}</div></td>'
            f"</tr></table></td></tr>"
        )
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">'
        f"{rows}</table>"
    )


def _state_badge(state: str) -> str:
    """議題狀態徽章：升溫/高峰 紅、其餘墨色（與前端徽章語義一致）。"""
    color = _RED if state in (_hot.STATE_RISING, _hot.STATE_PEAK) else _INK
    return (
        f'<span style="font-family:{_F_PULSE};font-size:10.5px;letter-spacing:.18em;'
        f'text-transform:uppercase;color:{color};font-weight:bold;border:1px solid {color};'
        f'padding:2px 8px">{_html.escape(state)}</span>'
    )


def _hero_storyline(story: dict) -> str:
    """議題追蹤 hero：標題 + 狀態徽章 + 迷你時間軸（volume 走勢 + 每日 summary）+ 出處。"""
    title = pangu_spacing(str(story.get("title") or "(無標題)"))
    state = str(story.get("state") or "")
    span = story.get("span_days")
    timeline = story.get("timeline") or []
    citations = story.get("citations") or []
    span_note = f"追蹤 {int(span)} 日" if isinstance(span, (int, float)) else ""
    head = (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
        f'<td valign="middle" style="font-family:{_F_DISP};font-size:22px;line-height:1.3;'
        f'font-weight:bold;color:{_INK}">{_html.escape(title)}</td>'
        f'<td align="right" valign="middle" width="84" style="padding-left:14px">'
        f"{_state_badge(state)}</td></tr></table>"
    )
    note = (
        f'<div style="font-family:{_F_PULSE};font-size:10.5px;letter-spacing:.12em;'
        f'text-transform:uppercase;color:{_SUB};margin:8px 0 4px">議題演變 · {_html.escape(span_note)}'
        f"</div>"
        if span_note
        else ""
    )
    bars = _story_timeline_bars(timeline)
    cite = _citations_line(citations, font_size="10px")
    return (
        _hero_band("頭版 · 今日主秀", "議題追蹤")
        + f'<tr><td style="padding:16px 40px 0">{head}{note}{bars}{cite}</td></tr>'
    )


def _hero_clash(pos: dict, neg: dict) -> str:
    """口碑交鋒 hero：最強正評 vs 最強負評並列（無 events 時的差異化主秀）。"""
    left = _mover_col([pos], title="最強正評", red=False)
    right = _mover_col([neg], title="最強負評 · 爭議", red=True)
    inner = (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
        f'<td width="316" valign="top" style="padding-right:22px">{left}</td>'
        f'<td width="316" valign="top" style="padding-left:22px;border-left:1px solid {_INK}">'
        f"{right}</td></tr></table>"
    )
    return (
        _hero_band("頭版 · 今日主秀", "口碑交鋒")
        + f'<tr><td style="padding:16px 40px 0">{inner}</td></tr>'
    )


def _hero_data(theme_cnts: dict, sentiment_cnts: dict) -> str:
    """數據日 hero：平淡日子用當日主題 / 情緒大數字撐起頭版（避免空版面）。"""
    cells: list[str] = []
    if theme_cnts:
        top = sorted(
            [(k, int(v)) for k, v in theme_cnts.items() if v], key=lambda x: x[1], reverse=True
        )
        if top:
            k, v = top[0]
            cells.append(_big_number(str(v), f"最熱主題 · {k}"))
    if sentiment_cnts:
        total = sum(int(v) for v in sentiment_cnts.values() if v)
        if total:
            emoji, label = _weather(sentiment_cnts)
            cells.append(_big_number(str(total), pangu_spacing(f"今日輿情 · {emoji} {label}")))
    if not cells:
        return ""
    tds = "".join(
        f'<td width="316" valign="top" style="{"padding-left:22px;border-left:1px solid " + _INK if i else "padding-right:22px"}">{c}</td>'
        for i, c in enumerate(cells)
    )
    inner = (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
        f"{tds}</tr></table>"
    )
    return (
        _hero_band("頭版 · 今日主秀", "今日數據")
        + f'<tr><td style="padding:16px 40px 0">{inner}</td></tr>'
    )


def _big_number(num: str, caption: str) -> str:
    return (
        f'<div style="font-family:{_F_PULSE};font-size:64px;line-height:1;font-weight:bold;'
        f'color:{_RED}">{_html.escape(num)}</div>'
        f'<div style="font-family:{_F_LAB};font-size:12px;letter-spacing:.14em;'
        f'text-transform:uppercase;color:{_INK};margin-top:8px">{_html.escape(caption)}</div>'
    )


def _hero_row(lead: dict | None) -> str:
    """依 _pick_lead 結果渲染對應 hero；None / 未知種類 → 不出（回 ""）。"""
    if not lead:
        return ""
    kind = lead.get("kind")
    if kind == "storyline":
        return _hr_row(pt="26px") + _hero_storyline(lead.get("story") or {})
    if kind == "clash":
        return _hr_row(pt="26px") + _hero_clash(lead.get("pos") or {}, lead.get("neg") or {})
    if kind == "data":
        body = _hero_data(lead.get("theme_counts") or {}, lead.get("sentiment_counts") or {})
        return (_hr_row(pt="26px") + body) if body else ""
    return ""


# ----------------------- 數據側欄 / 精選 / 口碑 -----------------------
def _bar_block(title: str, items: list[tuple[str, int]], *, red_labels=(), first: bool = False) -> str:
    if not items:
        return ""
    mx = max(v for _, v in items) or 1
    rows = ""
    for label, v in items:
        w = max(2, round(v / mx * 100))
        color = _RED if label in red_labels else _INK
        rows += (
            f'<tr><td style="font-family:{_F_BODY};font-size:12px;color:{_INK};padding-bottom:2px">'
            f'{_html.escape(label)} <span style="font-family:{_F_PULSE};color:{_RED};'
            f'font-weight:bold">{v}</span></td></tr>'
            f'<tr><td style="padding-bottom:9px"><div style="background:{color};height:9px;'
            f'width:{w}%;font-size:0;line-height:0">&nbsp;</div></td></tr>'
        )
    mt = "0" if first else "22px"
    return (
        f'<div style="font-family:{_F_LAB};font-size:11px;letter-spacing:.2em;text-transform:uppercase;'
        f'color:{_RED};font-weight:bold;border-bottom:3px double {_INK};padding-bottom:6px;'
        f'margin-top:{mt}">{_html.escape(title)}</div>'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="margin-top:12px">{rows}</table>'
    )


def _sidebar(theme_cnts, sentiment_cnts, trending) -> str:
    blocks: list[str] = []
    if theme_cnts:
        items = sorted(
            [(k, v) for k, v in theme_cnts.items() if v > 0], key=lambda x: x[1], reverse=True
        )
        blocks.append(_bar_block("今日數據 · 主題分布", items, first=True))
    if sentiment_cnts:
        zh = {"positive": "正面", "neutral": "中性", "negative": "負面"}
        items = sorted(
            [(zh[k], v) for k, v in sentiment_cnts.items() if k in zh and v > 0],
            key=lambda x: x[1],
            reverse=True,
        )
        blocks.append(
            _bar_block("輿情 · 口碑分布", items, red_labels={"負面"}, first=not blocks)
        )
    if trending:
        chips = " · ".join(_html.escape(str(t)) for t in trending[:14])
        blocks.append(
            f'<div style="font-family:{_F_LAB};font-size:11px;letter-spacing:.2em;'
            f'text-transform:uppercase;color:{_RED};font-weight:bold;border-bottom:3px double {_INK};'
            f'padding-bottom:6px;margin-top:{"0" if not blocks else "22px"}">今日熱詞索引</div>'
            f'<div style="font-family:{_F_BODY};font-size:12.5px;line-height:2;color:{_INK};'
            f'margin-top:10px">{chips}</div>'
        )
    return "".join(blocks)


def _hl_item(post: dict, *, first: bool) -> str:
    title = pangu_spacing(str(post.get("title_zh") or post.get("title") or "(無標題)"))
    snippet = pangu_spacing(str(post.get("snippet_zh") or ""))
    snip = (
        f'<div style="font-family:{_F_BODY};font-size:13px;line-height:1.8;color:{_BRIEF};'
        f'text-align:justify;margin-top:6px">{_html.escape(snippet)[:160]}</div>'
        if snippet
        else ""
    )
    wrap = (
        "padding:14px 0 0"
        if first
        else f"border-top:1px dotted {_DOT};margin:14px 0 0;padding:14px 0 0"
    )
    return (
        f'<div style="{wrap}">'
        f'<a href="{_u(post.get("url"))}" style="text-decoration:none;color:{_INK}">'
        f'<span style="font-family:{_F_DISP};font-size:16.5px;font-weight:bold;line-height:1.35;'
        f'border-bottom:1px solid {_INK}">{_html.escape(title)}</span></a>{snip}</div>'
    )


def _highlights_col(highlights: dict[str, list[dict]]) -> str:
    items = [p for posts in highlights.values() for p in posts]
    if not items:
        return ""
    body = "".join(_hl_item(p, first=(i == 0)) for i, p in enumerate(items))
    return (
        f'<div style="font-family:{_F_PULSE};font-size:13px;letter-spacing:.3em;'
        f'text-transform:uppercase;color:{_INK};font-weight:bold;border-bottom:1px solid {_INK};'
        f'padding-bottom:7px">新工具 · 使用方法</div>{body}'
    )


def _tools_and_data_row(highlights, theme_cnts, sentiment_cnts, trending) -> str:
    main = _highlights_col(highlights)
    side = _sidebar(theme_cnts, sentiment_cnts, trending)
    if not main and not side:
        return ""
    if main and side:
        inner = (
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
            f'<td width="430" valign="top" style="padding-right:26px;border-right:1px solid {_INK}">'
            f"{main}</td>"
            f'<td width="204" valign="top" style="padding-left:26px">{side}</td>'
            f"</tr></table>"
        )
    else:
        inner = main or side
    return _hr_row(pt="26px") + f'<tr><td style="padding:18px 40px 0">{inner}</td></tr>'


def _mover_col(items: list[dict], *, title: str, red: bool) -> str:
    color = _RED if red else _INK
    head = (
        f'<div style="font-family:{_F_PULSE};font-size:12px;letter-spacing:.24em;'
        f'text-transform:uppercase;color:{color};font-weight:bold;border-bottom:1px solid {color};'
        f'padding-bottom:6px">{_html.escape(title)}</div>'
    )
    rows = ""
    for i, p in enumerate(items):
        title_zh = pangu_spacing(str(p.get("title_zh") or p.get("title") or "(無標題)"))
        wrap = (
            "padding:11px 0 0"
            if i == 0
            else f"padding:11px 0 0;margin-top:11px;border-top:1px dotted {_DOT}"
        )
        rows += (
            f'<div style="{wrap};font-family:{_F_DISP};font-size:14.5px;font-weight:bold;'
            f'line-height:1.4"><a href="{_u(p.get("url"))}" style="color:{_INK};'
            f'text-decoration:none;border-bottom:1px solid {_RULE}">{_html.escape(title_zh)}</a></div>'
        )
    return head + rows


def _movers_row(movers: dict) -> str:
    pos = movers.get("positive") or []
    neg = movers.get("negative") or []
    if not pos and not neg:
        return ""
    left = _mover_col(pos, title="口碑亮點", red=False) if pos else ""
    right = _mover_col(neg, title="爭議 · 負評", red=True) if neg else ""
    if left and right:
        inner = (
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
            f'<td width="316" valign="top" style="padding-right:22px">{left}</td>'
            f'<td width="316" valign="top" style="padding-left:22px;border-left:1px solid {_INK}">'
            f"{right}</td></tr></table>"
        )
    else:
        inner = left or right
    return _hr_row(pt="26px") + f'<tr><td style="padding:18px 40px 0">{inner}</td></tr>'


def _colophon_row(day: _date) -> str:
    return (
        _hr_row(double=True, pt="30px")
        + f'<tr><td align="center" style="padding:16px 40px 34px">'
        f'<div style="font-family:{_F_PULSE};font-size:24px;font-weight:bold;letter-spacing:.04em;'
        f'color:{_INK}">Pulse</div>'
        f'<div style="font-family:{_F_BODY};font-size:11.5px;line-height:1.9;color:{_SUB};'
        f'margin-top:8px">本報由地端 ML 管線自動產製 · 爬蟲 → 資料品管 → 主題／情緒 → 忠實摘要<br>'
        f"全程免費、全程地端模型 · 繁體中文 · {_cn_date(day)}</div></td></tr>"
    )


def render_html(
    *,
    day: _date,
    summary: str,
    highlights: dict[str, list[dict]],
    movers: dict[str, list[dict]] | None = None,
    trending: list[str] | None = None,
    cover_cid: str | None = None,
    chart_cids: dict[str, str] | None = None,
    events: list[dict] | None = None,
    theme_counts: dict[str, int] | None = None,
    sentiment_counts: dict[str, int] | None = None,
    storylines: list[dict] | None = None,
) -> str:
    """
    組電子報 HTML —— 報紙社論版（broadsheet）、720px 表格版型、inline CSS、CJK 明體棧、light only。

    區塊順序：報眉 → 報頭 masthead/dateline（含今日 AI 圈天氣）→ 社論導言（summary，首字下沉）→
    今日主秀 hero（資料驅動、可選）→ 今日事件（events，頭條/雙欄/三欄短訊）→ 新工具·使用方法 +
    今日數據側欄（highlights / theme_counts / sentiment_counts / trending）→ 口碑亮點·爭議（movers）
    → 報尾 colophon。純函式，可測。

    theme_counts / sentiment_counts：原始計數，用於側欄的新聞紙風 HTML 條圖（取代彩色 PNG）；
    sentiment_counts 另驅動報頭天氣。storylines：議題演變（state/span_days/timeline/citations），
    驅動「今日主秀」hero 的議題追蹤形態；缺 / 空 → hero 自動退回其他形態或不出。
    cover_cid / chart_cids：報紙版型不使用（保留參數向後相容），不渲染。
    """
    lead = _pick_lead(events, movers, theme_counts, sentiment_counts, storylines)
    rows = [
        _ear_row(),
        _masthead_row(day, sentiment_counts),
        _editorial_row(summary),
        _hero_row(lead),
        render_today_events_section(events or []),
        _tools_and_data_row(highlights, theme_counts, sentiment_counts, trending),
        _movers_row(movers or {}),
        _colophon_row(day),
    ]
    inner = "".join(r for r in rows if r)
    return (
        '<!DOCTYPE html><html lang="zh-Hant"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="color-scheme" content="light">'
        '<meta name="supported-color-schemes" content="light">'
        "<title>Pulse 每日 AI 情報</title></head>"
        f'<body style="margin:0;padding:0;background:{_FRAME};font-family:{_F_DISP};color:{_INK}">'
        '<div style="display:none;max-height:0;overflow:hidden;opacity:0">'
        "今日 AI 要事：頭版事件 + 工具方法 + 主題口碑數據</div>"
        '<center><table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="background:{_FRAME}"><tr><td align="center" style="padding:28px 12px">'
        f'<!--[if mso]><table role="presentation" width="{_WIDTH}" cellpadding="0" cellspacing="0" '
        'border="0"><tr><td><![endif]-->'
        f'<table role="presentation" width="{_WIDTH}" cellpadding="0" cellspacing="0" border="0" '
        f'style="width:{_WIDTH}px;max-width:{_WIDTH}px;background:{_PAPER}">{inner}</table>'
        "<!--[if mso]></td></tr></table><![endif]-->"
        "</td></tr></table></center></body></html>"
    )


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\n{3,}")


def html_to_text(html: str) -> str:
    """把 HTML 粗略轉純文字（給 multipart/alternative 的 text 後援；spam/可及性需要）。純函式。"""
    text = re.sub(r"(?i)</(p|div|tr|h1|h2|li)>", "\n", html)
    text = _TAG_RE.sub("", text)
    text = _html.unescape(text)
    text = _WS_RE.sub("\n\n", text)
    return text.strip()


def build_mime_message(
    *,
    subject: str,
    sender: str,
    to: list[str] | str,
    html: str,
    text: str | None = None,
    images: dict[str, bytes] | None = None,
) -> MIMEMultipart:
    """
    組 email：multipart/related →（multipart/alternative → text + html）+ 內嵌 PNG（CID）。
    依 email 工程研究：alternative 在最前、related 包圖；CID header `<cid>` 對 HTML 的 src="cid:cid"。
    純函式（不寄送，可測）。`images`：{cid: png_bytes}，cid 需與 render_html 給的 cid 一致。
    """
    images = images or {}
    root = MIMEMultipart("related")
    root["Subject"] = Header(subject, "utf-8")
    root["From"] = sender
    root["To"] = ", ".join(to) if isinstance(to, (list, tuple)) else to
    root["Date"] = formatdate(localtime=True)
    root["Message-ID"] = make_msgid(domain="pulse.local")

    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(text or html_to_text(html), "plain", "utf-8"))
    alt.attach(MIMEText(html, "html", "utf-8"))
    root.attach(alt)

    for cid, data in images.items():
        img = MIMEImage(data, _subtype="png")  # 圖表/題圖皆 PNG
        img.add_header("Content-ID", f"<{cid}>")
        img.add_header("Content-Disposition", "inline", filename=f"{cid.split('@')[0]}.png")
        root.attach(img)
    return root
