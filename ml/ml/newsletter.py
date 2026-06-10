"""
每日電子報組裝 —— 純函式（精選挑選、口碑統計、封面 prompt、HTML 組版）。

全免費 / 地端（[[prefer-local-llm]]）：摘要走本地 Qwen、圖表走 matplotlib、題圖走地端 SD、
寄送走 Gmail SMTP —— 都不打雲端付費 API。本模組只放**純函式**（無 DB / 網路 / matplotlib /
torch 依賴），可單元測試；DB 查詢、圖表渲染、SD 生成、SMTP 寄送在 scripts/send_newsletter.py。

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
]

# --- 視覺 token（依電子報設計研究：單一強調色 + 中性灰階；640px；繁中字體棧）---
_FONT = (
    "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,"
    "'PingFang TC','Microsoft JhengHei','Noto Sans TC',sans-serif"
)
_ACCENT = "#2563eb"
_INK = "#111827"      # 標題
_BODY = "#374151"     # 內文
_MUTED = "#6b7280"    # 次要/來源
_BORDER = "#e6e6e6"
_PAGE = "#f4f4f5"     # 外層頁底
_CARD = "#fffffe"     # 內容卡（非純白，避開 Apple 強制反轉）
_SOFT = "#f3f4f6"     # 「今日重點」卡底

# CJK 範圍（pangu 空格用）
_CJK = r"一-鿿㐀-䶿豈-﫿"
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

# 顯示用 icon / 順序（與 theme.py 對齊；使用方法為錨點排前面）。
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
    """互動分數（讚 + 留言），用於同主題內排序。缺值當 0。"""
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
    規則：濾掉 quality_score < min_quality（None 視為通過）、依主題分組、組內以互動分數
    由高到低取前 per_theme 篇。回傳 {主題: [post, ...]}，只含有貼文的主題、依 themes 順序。
    """
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
        items = sorted(by_theme[t], key=lambda p: (_engagement(p), p.get("id", 0)), reverse=True)
        if items:
            out[t] = items[:per_theme]
    return out


def sentiment_movers(posts: list[dict], *, k: int = 3) -> dict[str, list[dict]]:
    """挑當日口碑最鮮明的貼文：最多 k 篇正評、k 篇負評（依互動分數）。純函式。"""
    pos = [p for p in posts if p.get("sentiment") == "positive"]
    neg = [p for p in posts if p.get("sentiment") == "negative"]
    key = lambda p: (_engagement(p), p.get("id", 0))  # noqa: E731
    return {
        "positive": sorted(pos, key=key, reverse=True)[:k],
        "negative": sorted(neg, key=key, reverse=True)[:k],
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

    用當日熱詞 + 主導主題拼一句編輯插畫風 prompt（避免文字、避免 logo）。
    """
    terms = ", ".join(t for t in top_terms[:4] if t) or "artificial intelligence"
    mood = {
        "風險限制": "cautious, muted tones",
        "倫理法規": "thoughtful, balanced composition",
        "新工具": "bright, energetic",
        "模型動態": "data-driven, charts motif",
        "使用方法": "clean, instructional",
    }.get(lead_theme or "", "modern, optimistic")
    return (
        f"editorial flat illustration for a daily AI tech newsletter about {terms}, "
        f"{mood}, minimal, vector style, soft gradient background, no text, no words, "
        f"no logo, high quality, 16:9"
    )


def _post_line(p: dict) -> str:
    """單篇貼文的 story block（中文標題優先、pangu 空格、情緒 icon、來源、可選摘要）。"""
    title = pangu_spacing(str(p.get("title_zh") or p.get("title") or "(無標題)"))
    senti = SENTIMENT_ICON.get(p.get("sentiment", ""), "")
    src = _html.escape(str(p.get("source") or ""))
    url = _html.escape(str(p.get("url") or "#"), quote=True)
    safe_title = _html.escape(title)
    snippet = pangu_spacing(str(p.get("snippet_zh") or ""))
    snip = (
        f'<div style="color:{_BODY};font-size:14px;line-height:1.7;margin:4px 0 0">'
        f"{_html.escape(snippet)[:140]}</div>"
        if snippet
        else ""
    )
    return (
        f'<div style="margin:0 0 18px">'
        f'<a href="{url}" style="color:{_INK};text-decoration:none;font-size:17px;'
        f'font-weight:700;line-height:1.5">{safe_title}</a>'
        f'<div style="color:{_MUTED};font-size:13px;margin:3px 0 0">{senti} {src}</div>'
        f"{snip}</div>"
    )


def _section_header(text: str) -> str:
    """主題/區段標題（emoji + 中文 + 細分隔線）。"""
    return (
        f'<div style="margin:28px 0 12px;border-top:1px solid {_BORDER};padding-top:18px">'
        f'<span style="font-size:17px;font-weight:800;color:{_INK}">{text}</span></div>'
    )


def _img(cid: str, alt: str) -> str:
    return (
        f'<img src="cid:{_html.escape(cid, quote=True)}" width="576" alt="{_html.escape(alt, quote=True)}" '
        f'style="display:block;width:100%;max-width:576px;height:auto;border:0;border-radius:8px;background:#ffffff">'
    )


def _event_citations_footer(citations: list[dict]) -> str:
    """事件卡底部的「出處」清單：每筆引註 [n] 連向原貼文（無 url 則純文字）。"""
    chips: list[str] = []
    for c in citations:
        n = c.get("n")
        if n is None:
            continue
        url = c.get("url")
        # 來源標籤：優先 source，否則退回成員貼文 id（對齊前端 postId）。
        label = c.get("source") or c.get("post_id") or c.get("postId")
        suffix = f" {_html.escape(pangu_spacing(str(label)))}" if label else ""
        ref = f"[{_html.escape(str(n))}]"
        if url:
            href = _html.escape(str(url), quote=True)
            chips.append(
                f'<a href="{href}" style="color:{_ACCENT};text-decoration:none;'
                f'font-size:12px;margin:0 10px 0 0;white-space:nowrap">{ref}{suffix}</a>'
            )
        else:
            chips.append(
                f'<span style="color:{_MUTED};font-size:12px;margin:0 10px 0 0;'
                f'white-space:nowrap">{ref}{suffix}</span>'
            )
    if not chips:
        return ""
    return (
        f'<div style="margin:10px 0 0;border-top:1px solid {_BORDER};padding-top:8px">'
        f'<span style="color:{_MUTED};font-size:11px;letter-spacing:0.06em;'
        f'text-transform:uppercase;margin-right:8px">出處</span>'
        f'{"".join(chips)}</div>'
    )


def _summary_with_refs(summary: str, valid_ns: set) -> str:
    """
    把摘要文字中的行內 `[n]` 標記轉成小字上標引註（對齊前端 renderSummary）。
    先做盤古空格 + HTML 跳脫，再以正則把 [n] 包成 <sup>；找不到對應 citation 的標記
    保留為純文字上標（不假裝有連結），避免編號與清單對不齊時誤導。純函式。
    """
    escaped = _html.escape(pangu_spacing(summary or ""))

    def _wrap(m: "re.Match[str]") -> str:
        n = m.group(1)
        color = _ACCENT if int(n) in valid_ns else _MUTED
        return (
            f'<sup style="font-size:10px;color:{color};'
            f'font-family:monospace;margin:0 1px">[{n}]</sup>'
        )

    # escape 後中括號維持原樣（html.escape 不動 []），可安全比對 [數字]。
    return re.sub(r"\[(\d+)\]", _wrap, escaped)


def _event_card(event: dict) -> str:
    """單則「今日事件」卡：主題徽章 + 成員貼文數 + 標題 + 帶行內出處的忠實摘要 + 出處清單。"""
    title = pangu_spacing(str(event.get("title") or "(無標題)"))
    theme = event.get("theme")
    citations = event.get("citations") or []
    valid_ns = {c["n"] for c in citations if c.get("n") is not None}
    member_count = event.get("member_count")
    if member_count is None:
        member_count = event.get("memberCount")

    meta_bits: list[str] = []
    if theme:
        icon = THEME_ICON.get(str(theme), "")
        meta_bits.append(f"{icon} {_html.escape(str(theme))}".strip())
    if member_count is not None:
        meta_bits.append(f"📎 {_html.escape(str(member_count))} 篇")
    meta = (
        f'<div style="color:{_MUTED};font-size:12px;margin:0 0 6px">'
        f'{" · ".join(meta_bits)}</div>'
        if meta_bits
        else ""
    )
    body = _summary_with_refs(str(event.get("summary") or ""), valid_ns)
    return (
        f'<div style="background:{_SOFT};border-radius:12px;padding:16px 18px;margin:0 0 14px">'
        f"{meta}"
        f'<div style="color:{_INK};font-size:16px;font-weight:700;line-height:1.5">'
        f"{_html.escape(title)}</div>"
        f'<div style="color:{_BODY};font-size:14px;line-height:1.8;margin:6px 0 0">'
        f"{body}</div>"
        f"{_event_citations_footer(citations)}"
        f"</div>"
    )


def render_today_events_section(events: list[dict]) -> str:
    """
    組「今日事件」HTML 區塊 —— 把多篇相關貼文聚成的事件，逐則渲染為 story-card：
    主題徽章 + 成員貼文數 + 標題 + 帶行內 `[n]` 出處引註的忠實摘要 + 底部出處清單。
    複用既有視覺 token / 卡片版型（對齊 _post_line / _section_header），與前端 EventSummary 一致。
    純函式 —— 同輸入同輸出、不改動輸入；空 list 回 ""（不出區塊）。

    每則 event 期望欄位（對齊前端 EventSummary 與摘要管線輸出）：
      - title (str)：事件標題。
      - summary (str)：忠實摘要文字，內含 `[1][2]` 行內引用標記。
      - citations (list[dict])：出處清單，每筆 {n:int, url?:str, source?:str/post_id?:str}；
        n 對應 summary 中的 `[n]` 標記，url 為原貼文連結（可無）。
      - member_count (int，可選；亦接受 memberCount)：此事件涵蓋的成員貼文數。
      - theme (str，可選)：主題標籤（對齊 theme.py 5 類），用於徽章 icon。
    """
    if not events:
        return ""
    cards = "".join(_event_card(e) for e in events)
    return _section_header("🗂️ 今日事件") + cards


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
) -> str:
    """
    組電子報 HTML —— 完整文件、640px 表格版型、inline CSS、暗色模式、繁中字體棧（依 email 工程研究）。
    圖以 cid: 內嵌（由寄送端附 MIMEImage）。純函式 —— 同輸入同輸出，可測。

    events（可選）：今日事件清單（見 render_today_events_section 的欄位說明）；提供且非空時，
    在「今日重點」摘要之後、各主題精選之前插入「今日事件」區塊。未提供時輸出與舊版逐位元組相同（向後相容）。
    """
    chart_cids = chart_cids or {}
    inner: list[str] = []

    if cover_cid:
        inner.append(
            f'<tr><td style="padding:0"><img src="cid:{_html.escape(cover_cid, quote=True)}" '
            f'width="640" alt="封面" style="display:block;width:100%;max-width:640px;height:auto;border:0"></td></tr>'
        )
    # 刊頭
    inner.append(
        f'<tr><td style="padding:28px 32px 8px">'
        f'<div style="font-size:22px;font-weight:800;color:{_INK};line-height:1.3">Pulse 每日 AI 情報</div>'
        f'<div style="color:{_MUTED};font-size:13px;margin-top:4px">{day.isoformat()}</div></td></tr>'
    )
    # 今日重點（Qwen 摘要）
    if summary:
        inner.append(
            f'<tr><td style="padding:8px 32px 0"><div style="background:{_SOFT};border-radius:12px;padding:16px 18px">'
            f'<div style="font-size:13px;font-weight:700;letter-spacing:0.04em;color:{_ACCENT}">今日重點</div>'
            f'<div style="font-size:15px;line-height:1.8;color:{_BODY};margin-top:8px;white-space:pre-wrap">'
            f"{_html.escape(pangu_spacing(summary))}</div></div></td></tr>"
        )
    # 今日事件（忠實摘要 + 行內出處）—— 排在摘要之後、各主題精選之前
    body: list[str] = []
    events_section = render_today_events_section(events or [])
    if events_section:
        body.append(events_section)
    # 各主題精選
    for theme, posts in highlights.items():
        if not posts:
            continue
        body.append(_section_header(f"{THEME_ICON.get(theme, '')} {_html.escape(theme)}"))
        body.extend(_post_line(p) for p in posts)
    # 主題分布圖
    if "theme" in chart_cids:
        body.append(_section_header("📊 主題分布"))
        body.append(_img(chart_cids["theme"], "主題分布"))
    # 口碑分布圖
    if "sentiment" in chart_cids:
        body.append(_section_header("🟢 口碑分布"))
        body.append(_img(chart_cids["sentiment"], "口碑分布"))
    # 情緒趨勢圖（未來）
    if "trend" in chart_cids:
        body.append(_section_header("📈 情緒趨勢"))
        body.append(_img(chart_cids["trend"], "情緒趨勢"))
    # 熱詞 chips
    if trending:
        chips = " ".join(
            f'<span style="display:inline-block;background:{_SOFT};color:{_BODY};border-radius:999px;'
            f'padding:4px 12px;margin:3px 3px 0 0;font-size:13px">#{_html.escape(str(t))}</span>'
            for t in trending[:15]
        )
        body.append(_section_header("🔥 熱詞"))
        body.append(f"<div>{chips}</div>")
    # 口碑亮點 / 爭議
    if movers:
        for pol, label in (("positive", "🟢 口碑亮點"), ("negative", "🔴 爭議 / 負評")):
            items = movers.get(pol) or []
            if items:
                body.append(_section_header(label))
                body.extend(_post_line(p) for p in items)
    if body:
        inner.append(f'<tr><td style="padding:8px 32px 0">{"".join(body)}</td></tr>')

    # 頁尾
    inner.append(
        f'<tr><td style="padding:24px 32px 28px"><div style="border-top:1px solid {_BORDER};'
        f'padding-top:16px;color:{_MUTED};font-size:12px;line-height:1.7">'
        "Pulse · 地端 ML 管線自動產生（爬蟲 → DQC → 主題 / 情緒 → 摘要）· 全程免費 / 地端模型</div></td></tr>"
    )

    card = (
        f'<table role="presentation" width="640" cellpadding="0" cellspacing="0" border="0" '
        f'style="width:640px;max-width:640px;background:{_CARD};border-radius:14px;overflow:hidden">'
        f'{"".join(inner)}</table>'
    )
    return (
        '<!DOCTYPE html><html lang="zh-Hant"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="color-scheme" content="light dark">'
        '<meta name="supported-color-schemes" content="light dark">'
        "<title>Pulse 每日 AI 情報</title>"
        "<style>:root{color-scheme:light dark}"
        "@media (prefers-color-scheme:dark){.pg{background:#0b1120!important}"
        ".cd{background:#111827!important}.tk{color:#f3f4f6!important}.tm{color:#9aa4b2!important}}"
        "</style></head>"
        f'<body class="pg" style="margin:0;padding:0;background:{_PAGE};font-family:{_FONT}">'
        '<div style="display:none;max-height:0;overflow:hidden;opacity:0">今日 AI 重點：精選貼文 + 主題分布 + 熱詞</div>'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{_PAGE}">'
        '<tr><td align="center" style="padding:24px 12px">'
        f'<!--[if mso]><table role="presentation" width="640" cellpadding="0" cellspacing="0" border="0"><tr><td><![endif]-->'
        f'{card}'
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
    純函式（不寄送，可測）。`images`：{cid: png_bytes}，cid 需與 render_html 給的 cover_cid/chart_cids 一致。
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
