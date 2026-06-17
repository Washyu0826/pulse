"""
每日電子報組裝 —— 純函式（精選挑選、口碑統計、封面 prompt、HTML 組版）。

全免費 / 地端（[[prefer-local-llm]]）：摘要走本地 Qwen、寄送走 Gmail SMTP —— 都不打雲端付費 API。
本模組只放**純函式**（無 DB / 網路 / matplotlib / torch 依賴），可單元測試；DB 查詢、SD 生成、
SMTP 寄送在 scripts/send_newsletter.py。

版型：瑞士國際主義網格（Swiss / International Typographic Style，方向 D2）—— 無襯線字體、660px 版心、
編號區段（01..05）、左編號鐵軌 + 右內容、純黑 + 暖白 + 單一強調紅、髮絲線分組、6px 粗黑 rule。
**禁止圓角 / 陰影 / 漸層 / 方框卡片**。圖表為純 HTML 水平長條 / 分段條（不用彩色 PNG）。
主題對齊 theme.py 5 類 + 其他。每篇貼文以 dict 表示（見 select_highlights 的欄位說明）。

資料層（精選挑選、口碑、天氣、頭版主秀輪播、引註解析、per-source 排序）與報紙版完全一致，
只在渲染層改寫成 Swiss 視覺。
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

# --- Swiss 視覺 token（暖白紙 + 純黑墨 + 單一強調紅；660px；無襯線棧）---
_PAPER = "#FAFAF8"   # 內頁暖白
_FRAME = "#e8e8e4"   # 外框（body 背景）
_INK = "#111111"     # 純黑（標題 / 主文 / 粗線）
_RED = "#E5322D"     # 單一強調紅（標籤 / 編號 / 引註 / 主類條）
_SUB = "#9a9a92"     # 次要灰（英文小標 / 出處 / metadata）
_RULE = "#e0e0da"    # 髮絲線（事件 / 精選分隔）
_BODY = "#333330"    # 事件內文墨色
_BRIEF = "#555550"   # 精選描述 / 較淡內文
_TRACK = "#d8d8d2"   # 連結底線色
_BARBG = "#ecece6"   # 主題長條底
_NEUBG = "#d4d4ce"   # 中性段 / 口碑中性

# 無襯線字體棧（Helvetica Neue → Arial → Noto Sans TC CJK 後援）。
_F = "'Helvetica Neue',Helvetica,Arial,'Noto Sans TC','PingFang TC','Microsoft JhengHei',sans-serif"

_WIDTH = 660
_WK_EN = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")
_WK_ZH = "一二三四五六日"

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


# 顯示用 icon / 順序（與 theme.py 對齊；使用方法為錨點排前面）。Swiss 版不顯示 emoji，
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

    保留供向後相容；排序已改用 hotness.engagement / per-source 正規化
    （見 hotness.source_baselines / hotness.rank_balanced）。
    """
    return int(post.get("score") or 0) + int(post.get("num_comments") or 0)


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
    baselines = _hot.source_baselines(posts)
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
        items = _hot.rank_balanced(by_theme[t], k=per_theme, baselines=baselines)
        if items:
            out[t] = items
    return out


def sentiment_movers(posts: list[dict], *, k: int = 3) -> dict[str, list[dict]]:
    """
    挑當日口碑最鮮明的貼文：最多 k 篇正評、k 篇負評。純函式。

    排序改用 per-source 正規化熱度（同 select_highlights）＋「同來源至少露出」平衡，
    讓主力來源 Threads 不被 HN 量級壓掉；基準由傳入 posts 內部算（無需 DB）。
    """
    baselines = _hot.source_baselines(posts)
    pos = [p for p in posts if p.get("sentiment") == "positive"]
    neg = [p for p in posts if p.get("sentiment") == "negative"]
    return {
        "positive": _hot.rank_balanced(pos, k=k, baselines=baselines),
        "negative": _hot.rank_balanced(neg, k=k, baselines=baselines),
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

    Swiss 版型預設不放題圖，此函式仍保留供未來 / 其他版型使用。
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


# ----------------------- Swiss 渲染小工具 -----------------------
def _u(url) -> str:
    return _html.escape(str(url or "#"), quote=True)


def _nbsp(text: str) -> str:
    """把空白換成 &nbsp;（Swiss tracked-out 標籤用，避免折行）。已 escape 過的字串再呼叫。"""
    return text.replace(" ", "&nbsp;")


def _date_dot(day: _date) -> str:
    """masthead 右上主日期：2026 · 06 · 17。"""
    return f"{day.year} · {day.month:02d} · {day.day:02d}"


def _date_meta(day: _date) -> str:
    """masthead 右上副行：WED / 週三。"""
    return f"{_WK_EN[day.weekday()]} / 週{_WK_ZH[day.weekday()]}"


def _cn_date_dot(day: _date) -> str:
    """footer 期數用：2026.06.17。"""
    return f"{day.year}.{day.month:02d}.{day.day:02d}"


def _sup_refs(text: str, valid_ns: set) -> str:
    """把文字中的 `[n]` 轉成小字上標引註（有對應 citation→紅，無→灰）。先盤古空格 + HTML 跳脫。"""
    escaped = _html.escape(pangu_spacing(text or ""))

    def _wrap(m: "re.Match[str]") -> str:
        n = m.group(1)
        color = _RED if int(n) in valid_ns else _SUB
        return (
            f'<sup style="font-size:10px;color:{color};font-weight:700;'
            f'vertical-align:super">[{n}]</sup>'
        )

    return re.sub(r"\[(\d+)\]", _wrap, escaped)


def _valid_ns(citations: list[dict]) -> set:
    return {c["n"] for c in citations if c.get("n") is not None}


def _heavy_rule(pt: str = "34px") -> str:
    """6px 粗黑 rule（區段大分隔）。"""
    return (
        f'<tr><td style="padding:{pt} 44px 0 44px;">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
        f'<td style="height:6px;background:{_INK};font-size:0;line-height:0;">&nbsp;</td>'
        f"</tr></table></td></tr>"
    )


def _hairline(pt: str = "24px") -> str:
    """1px 髮絲線（事件 / 精選之間）。"""
    return (
        f'<tr><td style="padding:{pt} 44px 0 44px;">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
        f'<td style="height:1px;background:{_RULE};font-size:0;line-height:0;">&nbsp;</td>'
        f"</tr></table></td></tr>"
    )


def _section_index(num: str, zh: str, en: str) -> str:
    """編號區段標：左「01 — 今日事件」+ 右英文小標。"""
    return (
        f'<tr><td style="padding:14px 44px 0 44px;">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
        f'<td style="font-size:10px;font-weight:700;letter-spacing:0.2em;text-transform:uppercase;'
        f'color:{_INK};">{num} — {_html.escape(zh)}</td>'
        f'<td align="right" style="font-size:10px;font-weight:400;letter-spacing:0.2em;'
        f'text-transform:uppercase;color:{_SUB};">{_nbsp(_html.escape(en))}</td>'
        f"</tr></table></td></tr>"
    )


def _citations_inline(citations: list[dict]) -> str:
    """事件「SOURCES」行：紅標 + 各筆連結（無 url 則純文字、不帶連結）。"""
    links: list[str] = []
    for c in citations:
        n = c.get("n")
        if n is None:
            continue
        label = c.get("source") or c.get("post_id") or c.get("postId") or ""
        label_html = _html.escape(pangu_spacing(str(label))) if label else ""
        n_html = _html.escape(str(n))
        inner = f"{n_html}&nbsp;{label_html}" if label_html else n_html
        url = c.get("url")
        if url:
            links.append(
                f'<a href="{_u(url)}" style="color:{_INK};text-decoration:none;'
                f'border-bottom:1px solid {_TRACK};">{inner}</a>'
            )
        else:
            links.append(f'<span style="color:{_INK};">{inner}</span>')
    if not links:
        return ""
    sep = "&nbsp;&nbsp;·&nbsp;&nbsp;"
    return (
        f'<div style="padding-top:12px;font-size:11px;line-height:1.9;color:{_SUB};'
        f'letter-spacing:0.02em;">'
        f'<span style="color:{_RED};font-weight:700;letter-spacing:0.14em;">SOURCES&nbsp;&nbsp;</span>'
        + sep.join(links)
        + "</div>"
    )


# ----------------------- MASTHEAD / LEAD -----------------------
def _masthead_row(day: _date, sentiment_counts: dict | None = None) -> str:
    """masthead：紅 tracked-out 刊頭 + 巨大 Pulse + 副標 + 右上日期/星期 + AI 圈天氣。"""
    emoji, label = _weather(sentiment_counts)
    weather = _html.escape(pangu_spacing(f"今日 AI 圈天氣 {emoji} {label}"))
    return (
        # 刊頭列：左 DAILY AI BRIEFING、右 日期 / 星期
        f'<tr><td style="padding:40px 44px 0 44px;">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
        f'<td style="vertical-align:top;">'
        f'<div style="font-size:11px;font-weight:700;letter-spacing:0.34em;text-transform:uppercase;'
        f'color:{_RED};">Daily&nbsp;AI&nbsp;Briefing</div></td>'
        f'<td align="right" style="vertical-align:top;white-space:nowrap;">'
        f'<div style="font-size:11px;font-weight:700;letter-spacing:0.18em;color:{_INK};">'
        f"{_html.escape(_date_dot(day))}</div>"
        f'<div style="font-size:11px;font-weight:400;letter-spacing:0.18em;color:{_SUB};">'
        f"{_nbsp(_html.escape(_date_meta(day)))}</div></td>"
        f"</tr></table></td></tr>"
        # 巨大 Pulse + 副標
        f'<tr><td style="padding:6px 44px 0 44px;">'
        f'<div style="font-size:74px;line-height:0.92;font-weight:800;letter-spacing:-0.03em;'
        f'color:{_INK};">Pulse</div>'
        f'<div style="font-size:22px;line-height:1.1;font-weight:400;letter-spacing:0.02em;'
        f'color:{_INK};padding-top:8px;">每日 AI 情報</div></td></tr>'
        # AI 圈天氣（緊接副標下，每天隨情緒變）
        f'<tr><td style="padding:14px 44px 0 44px;">'
        f'<div style="font-size:11px;font-weight:700;letter-spacing:0.16em;color:{_INK};">'
        f"{weather}</div></td></tr>"
        # 粗黑 rule
        + _heavy_rule(pt="22px")
    )


def _lead_row(summary: str) -> str:
    """今日重點 / Editor's Note：左標籤鐵軌 + 右導言（行內引註）。空摘要回 ""。"""
    if not summary:
        return ""
    body = _sup_refs(summary, set())
    return (
        f'<tr><td style="padding:30px 44px 0 44px;">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
        f'<td width="120" style="vertical-align:top;padding-right:24px;">'
        f'<div style="font-size:10px;font-weight:700;letter-spacing:0.24em;text-transform:uppercase;'
        f'color:{_RED};line-height:1.5;">今日重點</div>'
        f'<div style="font-size:10px;font-weight:400;letter-spacing:0.2em;text-transform:uppercase;'
        f'color:{_SUB};line-height:1.5;">Editor\'s&nbsp;Note</div></td>'
        f'<td style="vertical-align:top;">'
        f'<div style="font-size:21px;line-height:1.5;font-weight:600;letter-spacing:-0.005em;'
        f'color:{_INK};">{body}</div></td>'
        f"</tr></table></td></tr>"
    )


# ----------------------- 今日事件 -----------------------
def _event_row(event: dict, num: int, *, first: bool) -> str:
    """單則事件：左大紅編號 + 右（綜合 N 則 · 主題 / 標題 / 內文 / SOURCES）。"""
    title = _html.escape(pangu_spacing(str(event.get("title") or "(無標題)")))
    citations = event.get("citations") or []
    vns = _valid_ns(citations)
    body = _sup_refs(str(event.get("summary") or ""), vns)

    mc = event.get("member_count")
    if mc is None:
        mc = event.get("memberCount")
    meta_bits: list[str] = []
    if mc is not None:
        meta_bits.append(f"綜合 {mc} 則來源")
    theme = event.get("theme")
    if theme:
        meta_bits.append(str(theme))
    meta = _html.escape(pangu_spacing(" · ".join(meta_bits))) if meta_bits else ""
    meta_div = (
        f'<div style="font-size:10px;font-weight:700;letter-spacing:0.18em;text-transform:uppercase;'
        f'color:{_SUB};">{meta}</div>'
        if meta
        else ""
    )
    cite = _citations_inline(citations)

    pt = "30px" if first else "24px"
    return (
        f'<tr><td style="padding:{pt} 44px 0 44px;">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
        f'<td width="68" style="vertical-align:top;">'
        f'<div style="font-size:32px;font-weight:800;letter-spacing:-0.02em;color:{_RED};'
        f'line-height:1;">{num:02d}</div></td>'
        f'<td style="vertical-align:top;">'
        f"{meta_div}"
        f'<div style="font-size:23px;line-height:1.25;font-weight:700;letter-spacing:-0.01em;'
        f'color:{_INK};padding-top:6px;">{title}</div>'
        f'<div style="font-size:15px;line-height:1.75;font-weight:400;color:{_BODY};'
        f'padding-top:10px;">{body}</div>'
        f"{cite}</td>"
        f"</tr></table></td></tr>"
    )


def render_today_events_section(events: list[dict]) -> str:
    """
    組「今日事件」Swiss 區塊 —— 每則事件編號排列（左大紅編號 + 右內容），事件間用髮絲線分隔。
    每則含「綜合 N 則來源 · 主題」徽章、標題、帶行內 `[n]` 出處引註的忠實摘要、SOURCES 連結行。
    純函式；空 list 回 ""。

    每則 event 期望欄位（對齊摘要管線輸出與前端 EventSummary）：
      - title (str)：事件標題。
      - summary (str)：忠實摘要文字，內含 `[1][2]` 行內引用標記。
      - citations (list[dict])：出處清單，每筆 {n:int, url?:str, source?:str/post_id?:str}。
      - member_count (int，可選；亦接受 memberCount)：成員貼文數。
      - theme (str，可選)：主題標籤，顯示於事件 metadata 列。
    """
    if not events:
        return ""
    parts = [_section_index("01", "今日事件", "Today's Events")]
    for i, ev in enumerate(events):
        if i > 0:
            parts.append(_hairline(pt="24px"))
        parts.append(_event_row(ev, i + 1, first=(i == 0)))
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


def _hero_band(en: str) -> str:
    """hero 區塊頂部：粗黑 rule + 編號式標題「今日主秀」+ 右英文小標。"""
    return (
        _heavy_rule(pt="34px")
        + f'<tr><td style="padding:14px 44px 0 44px;">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
        f'<td style="font-size:10px;font-weight:700;letter-spacing:0.2em;text-transform:uppercase;'
        f'color:{_INK};">今日主秀</td>'
        f'<td align="right" style="font-size:10px;font-weight:400;letter-spacing:0.2em;'
        f'text-transform:uppercase;color:{_SUB};">{_nbsp(_html.escape(en))}</td>'
        f"</tr></table></td></tr>"
    )


def _state_badge(state: str) -> str:
    """議題狀態徽章：升溫/高峰 紅、其餘墨色（與前端徽章語義一致）。Swiss：細框 + tracked-out。"""
    color = _RED if state in (_hot.STATE_RISING, _hot.STATE_PEAK) else _INK
    return (
        f'<span style="font-size:10px;font-weight:700;letter-spacing:0.18em;text-transform:uppercase;'
        f'color:{color};border:1px solid {color};padding:3px 9px;">{_html.escape(state)}</span>'
    )


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
        summ = _html.escape(pangu_spacing(str(t.get("summary") or "")))[:90]
        rows += (
            f'<tr><td style="padding:12px 0 0;">'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
            f'<td width="86" valign="top" style="font-size:10px;letter-spacing:0.06em;color:{_SUB};'
            f'padding-top:1px;">{date_lbl}</td>'
            f'<td valign="top">'
            f'<div style="background:{color};height:8px;width:{w}%;font-size:0;line-height:0;'
            f'min-width:6px;">&nbsp;</div>'
            f'<div style="font-size:12px;line-height:1.6;color:{_BRIEF};margin-top:5px;">'
            f"{summ}</div></td>"
            f"</tr></table></td></tr>"
        )
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="margin-top:6px;">{rows}</table>'
    )


def _hero_storyline(story: dict) -> str:
    """議題追蹤 hero：標題 + 狀態徽章 + 迷你時間軸（volume 走勢 + 每日 summary）+ 出處。"""
    title = _html.escape(pangu_spacing(str(story.get("title") or "(無標題)")))
    state = str(story.get("state") or "")
    span = story.get("span_days")
    timeline = story.get("timeline") or []
    citations = story.get("citations") or []
    span_note = f"議題演變 · 追蹤 {int(span)} 日" if isinstance(span, (int, float)) else "議題演變"
    head = (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
        f'<td valign="middle" style="font-size:23px;line-height:1.25;font-weight:700;'
        f'letter-spacing:-0.01em;color:{_INK};">{title}</td>'
        f'<td align="right" valign="middle" width="84" style="padding-left:14px;white-space:nowrap;">'
        f"{_state_badge(state)}</td></tr></table>"
    )
    note = (
        f'<div style="font-size:10px;font-weight:700;letter-spacing:0.18em;text-transform:uppercase;'
        f'color:{_SUB};margin:10px 0 2px;">{_nbsp(_html.escape(pangu_spacing(span_note)))}</div>'
    )
    bars = _story_timeline_bars(timeline)
    cite = _citations_inline(citations)
    return (
        _hero_band("Story Tracking · 議題追蹤")
        + f'<tr><td style="padding:18px 44px 0 44px;">{head}{note}{bars}{cite}</td></tr>'
    )


def _hero_clash(pos: dict, neg: dict) -> str:
    """口碑交鋒 hero：最強正評 vs 最強負評並列（無 events 時的差異化主秀）。"""
    left = _mover_col([pos], title="最強正評", red=False)
    right = _mover_col([neg], title="最強負評 · 爭議", red=True)
    inner = (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
        f'<td width="280" valign="top" style="padding-right:24px;">{left}</td>'
        f'<td valign="top" style="padding-left:24px;border-left:1px solid {_RULE};">{right}</td>'
        f"</tr></table>"
    )
    return (
        _hero_band("Sentiment Clash · 口碑交鋒")
        + f'<tr><td style="padding:18px 44px 0 44px;">{inner}</td></tr>'
    )


def _big_number(num: str, caption: str) -> str:
    return (
        f'<div style="font-size:64px;line-height:1;font-weight:800;letter-spacing:-0.03em;'
        f'color:{_RED};">{_html.escape(num)}</div>'
        f'<div style="font-size:11px;font-weight:700;letter-spacing:0.14em;text-transform:uppercase;'
        f'color:{_INK};margin-top:10px;">{_nbsp(_html.escape(caption))}</div>'
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
        f'<td width="280" valign="top" style="'
        f'{"padding-left:24px;border-left:1px solid " + _RULE if i else "padding-right:24px"}">'
        f"{c}</td>"
        for i, c in enumerate(cells)
    )
    inner = (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
        f"{tds}</tr></table>"
    )
    return (
        _hero_band("Today by Numbers · 今日數據")
        + f'<tr><td style="padding:18px 44px 0 44px;">{inner}</td></tr>'
    )


def _hero_row(lead: dict | None) -> str:
    """依 _pick_lead 結果渲染對應 hero；None / 未知種類 → 不出（回 ""）。"""
    if not lead:
        return ""
    kind = lead.get("kind")
    if kind == "storyline":
        return _hero_storyline(lead.get("story") or {})
    if kind == "clash":
        return _hero_clash(lead.get("pos") or {}, lead.get("neg") or {})
    if kind == "data":
        return _hero_data(lead.get("theme_counts") or {}, lead.get("sentiment_counts") or {})
    return ""


# ----------------------- 精選（highlights）-----------------------
def _hl_item(post: dict, theme_label: str, *, first: bool) -> str:
    """單筆精選：左主題標籤（紅）+ 右（標題連結 + 描述）。"""
    title = _html.escape(pangu_spacing(str(post.get("title_zh") or post.get("title") or "(無標題)")))
    snippet = _html.escape(pangu_spacing(str(post.get("snippet_zh") or "")))[:160]
    snip = (
        f'<div style="font-size:13.5px;line-height:1.7;color:{_BRIEF};padding-top:6px;">'
        f"{snippet}</div>"
        if snippet
        else ""
    )
    pt = "20px" if first else "16px"
    return (
        (_hairline(pt="16px") if not first else "")
        + f'<tr><td style="padding:{pt} 44px 0 44px;">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
        f'<td width="68" style="vertical-align:top;font-size:11px;font-weight:700;'
        f'letter-spacing:0.1em;color:{_RED};line-height:1.6;">{_html.escape(theme_label)}</td>'
        f'<td style="vertical-align:top;">'
        f'<a href="{_u(post.get("url"))}" style="font-size:17px;line-height:1.4;font-weight:600;'
        f'color:{_INK};text-decoration:none;letter-spacing:-0.005em;">{title}</a>'
        f"{snip}</td>"
        f"</tr></table></td></tr>"
    )


def _highlights_section(highlights: dict[str, list[dict]]) -> str:
    """精選區段：編號標 02 + 各主題精選逐筆（左主題標籤 + 右標題/描述）。"""
    flat: list[tuple[str, dict]] = []
    for theme, posts in highlights.items():
        for p in posts:
            flat.append((theme, p))
    if not flat:
        return ""
    rows = "".join(
        _hl_item(p, theme, first=(i == 0)) for i, (theme, p) in enumerate(flat)
    )
    return _section_index("02", "精選", "Selected") + rows


# ----------------------- 圖表：主題分布 / 口碑分布 -----------------------
def _theme_dist_section(theme_cnts: dict | None) -> str:
    """主題分布：水平長條（紅＝最大類、其餘黑、底灰）+ 右數字。純 HTML。"""
    if not theme_cnts:
        return ""
    items = sorted([(k, int(v)) for k, v in theme_cnts.items() if v > 0],
                   key=lambda x: x[1], reverse=True)
    if not items:
        return ""
    mx = items[0][1] or 1
    top_label = items[0][0]
    rows = ""
    for label, v in items:
        pct = max(2, round(v / mx * 100))
        color = _RED if label == top_label else _INK
        rows += (
            f"<tr>"
            f'<td width="90" style="vertical-align:middle;font-size:13px;font-weight:600;'
            f'color:{_INK};padding:7px 0;">{_html.escape(label)}</td>'
            f'<td style="vertical-align:middle;padding:7px 0;">'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
            f'<td width="{pct}%" style="height:14px;background:{color};font-size:0;line-height:0;">'
            f"&nbsp;</td>"
            f'<td style="height:14px;background:{_BARBG};font-size:0;line-height:0;">&nbsp;</td>'
            f"</tr></table></td>"
            f'<td width="44" align="right" style="vertical-align:middle;font-size:13px;'
            f'font-weight:700;color:{_INK};padding:7px 0;">{v}</td>'
            f"</tr>"
        )
    n = sum(v for _, v in items)
    return (
        _section_index("03", "主題分布", "Theme Distribution")
        + f'<tr><td style="padding:22px 44px 0 44px;">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">'
        f"{rows}</table>"
        f'<div style="font-size:10px;color:{_SUB};letter-spacing:0.1em;padding-top:6px;">'
        f"n = {n} 則 · 紅＝主類{_html.escape(top_label)}</div></td></tr>"
    )


def _sentiment_dist_section(sentiment_cnts: dict | None) -> str:
    """口碑分布：單一分段條（正黑 / 負紅 / 中性灰）+ 圖例。純 HTML。"""
    if not sentiment_cnts:
        return ""
    pos = max(0, int(sentiment_cnts.get("positive") or 0))
    neu = max(0, int(sentiment_cnts.get("neutral") or 0))
    neg = max(0, int(sentiment_cnts.get("negative") or 0))
    total = pos + neu + neg
    if total == 0:
        return ""
    p_pct = round(pos / total * 100)
    n_pct = round(neg / total * 100)
    u_pct = 100 - p_pct - n_pct

    def seg(pct: int, bg: str) -> str:
        if pct <= 0:
            return ""
        return (
            f'<td width="{pct}%" style="height:30px;background:{bg};font-size:0;line-height:0;">'
            f"&nbsp;</td>"
        )

    def legend(pct: int, bg: str, label: str) -> str:
        if pct <= 0:
            return ""
        return (
            f'<td style="font-size:11px;color:{_INK};letter-spacing:0.06em;padding-right:14px;">'
            f'<span style="display:inline-block;width:9px;height:9px;background:{bg};">&nbsp;</span>'
            f"&nbsp;{label} {pct}%</td>"
        )

    bar = seg(p_pct, _INK) + seg(n_pct, _RED) + seg(u_pct, _NEUBG)
    leg = legend(p_pct, _INK, "正面") + legend(n_pct, _RED, "負面") + legend(u_pct, _NEUBG, "中性")
    return (
        _section_index("04", "口碑分布", "Sentiment")
        + f'<tr><td style="padding:22px 44px 0 44px;">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
        f"{bar}</tr></table>"
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="margin-top:10px;"><tr>{leg}</tr></table></td></tr>'
    )


# ----------------------- 熱詞 -----------------------
# 排名 → (font-size px, font-weight, color)：最熱 26px 紅 → 漸小灰。
_HOT_STEPS = [
    (26, 800, _RED),
    (22, 700, _INK),
    (20, 700, _INK),
    (19, 600, _INK),
    (18, 600, _BODY),
    (17, 600, _BODY),
    (16, 500, _BRIEF),
    (16, 500, _BRIEF),
    (15, 500, _BRIEF),
    (15, 500, "#777770"),
    (14, 400, "#777770"),
    (14, 400, "#777770"),
    (13, 400, _SUB),
]


def _keywords_section(trending: list[str] | None) -> str:
    """熱詞：ragged-right、用字級與字重表示排名（最熱大紅 → 漸小灰），無膠囊。"""
    if not trending:
        return ""
    terms = [str(t) for t in trending[:13] if str(t).strip()]
    if not terms:
        return ""
    spans: list[str] = []
    for i, term in enumerate(terms):
        size, weight, color = _HOT_STEPS[min(i, len(_HOT_STEPS) - 1)]
        ls = "letter-spacing:-0.01em;" if i == 0 else ""
        spans.append(
            f'<span style="font-size:{size}px;font-weight:{weight};color:{color};{ls}">'
            f"{_html.escape(term)}</span>"
        )
    body = "&nbsp;&nbsp;&nbsp;\n    ".join(spans)
    return (
        _section_index("05", "熱詞", "Keywords")
        + f'<tr><td style="padding:18px 44px 0 44px;">'
        f'<div style="line-height:2.0;">{body}</div></td></tr>'
    )


# ----------------------- 口碑亮點 / 爭議（movers）-----------------------
def _mover_col(items: list[dict], *, title: str, red: bool) -> str:
    color = _RED if red else _INK
    head = (
        f'<div style="font-size:11px;font-weight:700;letter-spacing:0.18em;text-transform:uppercase;'
        f'color:{color};border-bottom:1px solid {color};padding-bottom:7px;">'
        f"{_nbsp(_html.escape(title))}</div>"
    )
    rows = ""
    for i, p in enumerate(items):
        title_zh = _html.escape(pangu_spacing(str(p.get("title_zh") or p.get("title") or "(無標題)")))
        wrap = (
            "padding:11px 0 0;"
            if i == 0
            else f"padding:11px 0 0;margin-top:11px;border-top:1px solid {_RULE};"
        )
        rows += (
            f'<div style="{wrap}">'
            f'<a href="{_u(p.get("url"))}" style="font-size:15px;line-height:1.4;font-weight:600;'
            f'color:{_INK};text-decoration:none;border-bottom:1px solid {_TRACK};">{title_zh}</a>'
            f"</div>"
        )
    return head + rows


def _movers_section(movers: dict) -> str:
    """口碑亮點 · 爭議：正評 / 負評兩欄（編號區段 06）。"""
    pos = movers.get("positive") or []
    neg = movers.get("negative") or []
    if not pos and not neg:
        return ""
    left = _mover_col(pos, title="口碑亮點", red=False) if pos else ""
    right = _mover_col(neg, title="爭議 · 負評", red=True) if neg else ""
    if left and right:
        inner = (
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
            f'<td width="280" valign="top" style="padding-right:24px;">{left}</td>'
            f'<td valign="top" style="padding-left:24px;border-left:1px solid {_RULE};">{right}</td>'
            f"</tr></table>"
        )
    else:
        inner = left or right
    return (
        _section_index("06", "口碑亮點", "Movers")
        + f'<tr><td style="padding:20px 44px 0 44px;">{inner}</td></tr>'
    )


# ----------------------- FOOTER -----------------------
def _footer_row(day: _date) -> str:
    """footer：大 Pulse + 產製說明 + 右下刊頭 / 期數。"""
    return (
        _heavy_rule(pt="34px")
        + f'<tr><td style="padding:20px 44px 44px 44px;">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
        f'<td style="vertical-align:top;">'
        f'<div style="font-size:30px;font-weight:800;letter-spacing:-0.02em;color:{_INK};'
        f'line-height:1;">Pulse</div>'
        f'<div style="font-size:11px;line-height:1.8;color:{_SUB};letter-spacing:0.02em;'
        f'padding-top:8px;max-width:380px;">'
        f"地端 ML 管線自動產製：爬蟲 → 資料品管 → 主題／情緒 → 忠實摘要。<br>"
        f"全程免費、地端模型，不打雲端付費 API。</div></td>"
        f'<td align="right" style="vertical-align:bottom;white-space:nowrap;">'
        f'<div style="font-size:10px;font-weight:700;letter-spacing:0.2em;text-transform:uppercase;'
        f'color:{_RED};">Daily&nbsp;AI&nbsp;Briefing</div>'
        f'<div style="font-size:10px;letter-spacing:0.2em;color:{_SUB};padding-top:4px;">'
        f"{_html.escape(_cn_date_dot(day))}</div></td>"
        f"</tr></table></td></tr>"
    )


# ----------------------- 主組裝 -----------------------
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
    組電子報 HTML —— 瑞士國際主義網格（Swiss）、660px 表格版型、inline CSS、無襯線棧、light only。

    區塊順序：masthead（巨大 Pulse + 右上日期/星期 + 今日 AI 圈天氣）→ 今日重點 / Editor's Note
    （summary，行內引註）→ 今日主秀 hero（資料驅動、可選）→ 01 今日事件 → 02 精選 →
    03 主題分布 → 04 口碑分布 → 05 熱詞 →（06 口碑亮點 · 爭議，有 movers 才出）→ footer。
    純函式，可測。

    視覺：禁止圓角 / 陰影 / 漸層 / 方框卡片；分組僅用留白 + 髮絲線 + 對齊 + 6px 粗黑 rule。
    theme_counts / sentiment_counts：原始計數，驅動 03/04 的純 HTML 條圖（取代彩色 PNG）；
    sentiment_counts 另驅動 masthead 天氣。storylines：議題演變（state/span_days/timeline/citations），
    驅動「今日主秀」hero 的議題追蹤形態；缺 / 空 → hero 自動退回其他形態或不出。
    cover_cid / chart_cids：Swiss 版型不使用（保留參數向後相容），不渲染。
    """
    lead = _pick_lead(events, movers, theme_counts, sentiment_counts, storylines)
    rows = [
        _masthead_row(day, sentiment_counts),
        _lead_row(summary),
        _hero_row(lead),
        render_today_events_section(events or []),
        _highlights_section(highlights),
        _theme_dist_section(theme_counts),
        _sentiment_dist_section(sentiment_counts),
        _keywords_section(trending),
        _movers_section(movers or {}),
        _footer_row(day),
    ]
    inner = "".join(r for r in rows if r)
    return (
        '<!DOCTYPE html><html lang="zh-Hant"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="color-scheme" content="light only">'
        '<meta name="supported-color-schemes" content="light">'
        "<title>Pulse 每日 AI 情報</title></head>"
        f'<body style="margin:0;padding:0;background:{_FRAME};font-family:{_F};color:{_INK};'
        '-webkit-font-smoothing:antialiased;">'
        '<div style="display:none;max-height:0;overflow:hidden;opacity:0;">'
        "今日 AI 要事：頭版事件 + 工具方法 + 主題口碑數據</div>"
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="background:{_FRAME};"><tr><td align="center" style="padding:36px 14px;">'
        f'<!--[if mso]><table role="presentation" width="{_WIDTH}" cellpadding="0" cellspacing="0" '
        'border="0"><tr><td><![endif]-->'
        f'<table role="presentation" width="{_WIDTH}" cellpadding="0" cellspacing="0" border="0" '
        f'style="width:{_WIDTH}px;max-width:{_WIDTH}px;background:{_PAPER};">{inner}</table>'
        "<!--[if mso]></td></tr></table><![endif]-->"
        "</td></tr></table></body></html>"
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
