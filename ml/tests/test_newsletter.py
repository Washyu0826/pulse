"""電子報純函式測試 —— 精選挑選、口碑、主題計數、封面 prompt、HTML 組版。"""
from datetime import date

from ml.newsletter import (
    THEME_ORDER,
    build_mime_message,
    cover_prompt,
    html_to_text,
    pangu_spacing,
    render_html,
    render_today_events_section,
    select_highlights,
    sentiment_movers,
    theme_counts,
)


def _event(
    title="GPT-5 發表",
    summary="OpenAI 發表 GPT-5[1]，宣稱推理能力提升[2]。",
    *,
    citations=None,
    member_count=3,
    theme="模型動態",
):
    if citations is None:
        citations = [
            {"n": 1, "url": "http://a?x=1&y=2", "source": "threads"},
            {"n": 2, "url": "http://b", "source": "Hacker News"},
        ]
    ev = {"title": title, "summary": summary, "citations": citations}
    if member_count is not None:
        ev["member_count"] = member_count
    if theme is not None:
        ev["theme"] = theme
    return ev


# ---- pangu_spacing ----
def test_pangu_inserts_space_between_cjk_and_latin():
    assert pangu_spacing("使用GPT-4o模型") == "使用 GPT-4o 模型"
    assert pangu_spacing("我愛Claude") == "我愛 Claude"
    assert pangu_spacing("Claude很強") == "Claude 很強"


def test_pangu_is_idempotent_and_safe():
    once = pangu_spacing("用 GPT-4o 寫 code")
    assert pangu_spacing(once) == once  # 已有空格不重複加
    assert pangu_spacing("") == ""
    assert pangu_spacing("全部都是中文沒有英數") == "全部都是中文沒有英數"


def _post(id, theme, *, score=0, comments=0, q=None, senti="neutral", title="t", url="http://x"):
    return {
        "id": id, "theme": theme, "score": score, "num_comments": comments,
        "quality_score": q, "sentiment": senti, "title": title, "url": url,
    }


# ---- select_highlights ----
def test_highlights_groups_and_ranks_by_engagement():
    posts = [
        _post(1, "新工具", score=5),
        _post(2, "新工具", score=50),
        _post(3, "新工具", score=20),
        _post(4, "模型動態", comments=8),
    ]
    h = select_highlights(posts, per_theme=2)
    assert [p["id"] for p in h["新工具"]] == [2, 3]  # 取互動最高的 2 篇、降序
    assert [p["id"] for p in h["模型動態"]] == [4]
    assert "使用方法" not in h  # 無貼文的主題不出現


def test_highlights_filters_low_quality():
    posts = [_post(1, "新工具", score=10, q=10), _post(2, "新工具", score=5, q=80)]
    h = select_highlights(posts, min_quality=30)
    assert [p["id"] for p in h["新工具"]] == [2]  # q=10 被濾，q=80 留


def test_highlights_none_quality_passes():
    h = select_highlights([_post(1, "新工具", q=None)], min_quality=30)
    assert h["新工具"][0]["id"] == 1  # None 視為通過


def test_highlights_is_deterministic_and_pure():
    posts = [_post(1, "新工具", score=10), _post(2, "新工具", score=10)]
    snapshot = [dict(p) for p in posts]
    a = select_highlights(posts)
    b = select_highlights(posts)
    assert [p["id"] for p in a["新工具"]] == [p["id"] for p in b["新工具"]]  # 同分以 id 決勝、可重現
    assert posts == snapshot  # 不改動輸入


def test_highlights_ignores_unknown_theme():
    h = select_highlights([_post(1, "其他"), _post(2, "亂七八糟")])
    assert h == {}  # 非 5 主題不納入精選


# ---- sentiment_movers ----
def test_sentiment_movers_splits_pos_neg():
    posts = [
        _post(1, "新工具", score=9, senti="positive"),
        _post(2, "新工具", score=3, senti="positive"),
        _post(3, "風險限制", score=7, senti="negative"),
        _post(4, "使用方法", score=1, senti="neutral"),
    ]
    m = sentiment_movers(posts, k=1)
    assert [p["id"] for p in m["positive"]] == [1]  # 取互動最高的正評
    assert [p["id"] for p in m["negative"]] == [3]


# ---- theme_counts ----
def test_theme_counts_includes_other_and_all_themes():
    c = theme_counts([_post(1, "新工具"), _post(2, "新工具"), _post(3, "怪")])
    assert c["新工具"] == 2
    assert c["其他"] == 1  # 未知主題歸其他
    assert set(c) == set(THEME_ORDER) | {"其他"}


# ---- cover_prompt ----
def test_cover_prompt_is_english_no_text_and_uses_terms():
    p = cover_prompt(["Claude", "MCP", "RAG"], lead_theme="新工具")
    assert "Claude" in p and "MCP" in p
    assert "no text" in p and "no logo" in p  # 避免 SD 畫出亂碼文字
    assert "16:9" in p


def test_cover_prompt_handles_empty_terms():
    p = cover_prompt([])
    assert "artificial intelligence" in p  # fallback 主題


# ---- render_html ----
def test_render_html_contains_sections_and_escapes():
    posts = {
        "新工具": [{"title_zh": "新工具 <X>", "url": "http://a?b=1&c=2", "source": "threads", "sentiment": "positive"}],
    }
    out = render_html(
        day=date(2026, 6, 5),
        summary="今天 AI 圈很熱鬧",
        highlights=posts,
        trending=["MCP", "Claude"],
        cover_cid="cover1",
        chart_cids={"theme": "chart1"},
    )
    assert "Pulse 每日 AI 情報" in out
    assert "2026-06-05" in out
    assert "今天 AI 圈很熱鬧" in out
    assert "新工具 &lt;X&gt;" in out  # HTML 跳脫，防注入
    assert "b=1&amp;c=2" in out  # URL 跳脫
    assert "cid:cover1" in out  # 封面內嵌
    assert "cid:chart1" in out  # 圖表內嵌
    assert "#MCP" in out  # 熱詞 chip


def test_render_html_skips_empty_blocks():
    out = render_html(day=date(2026, 6, 5), summary="", highlights={})
    assert "今日重點" not in out  # 無摘要 → 不出現重點區塊
    assert "cid:" not in out  # 無圖
    assert "Pulse 每日 AI 情報" in out  # 仍有頁首/頁尾


def test_render_html_is_pure():
    args = dict(day=date(2026, 6, 5), summary="s", highlights={"新工具": [{"title": "t", "url": "u"}]})
    assert render_html(**args) == render_html(**args)


# ---- html_to_text ----
def test_html_to_text_strips_tags_and_unescapes():
    t = html_to_text("<h1>標題</h1><p>內文 &amp; 連結</p>")
    assert "標題" in t and "內文 & 連結" in t
    assert "<" not in t and ">" not in t


# ---- render_today_events_section ----
def test_events_section_empty_returns_blank():
    assert render_today_events_section([]) == ""


def test_events_section_renders_title_summary_refs_and_count():
    out = render_today_events_section([_event()])
    assert "今日事件" in out
    assert "GPT-5 發表" in out  # 標題
    assert "OpenAI 發表 GPT-5" in out  # 摘要內文
    assert "[1]" in out and "[2]" in out  # 行內引註標記
    assert "3 篇" in out  # 成員貼文數
    assert "threads" in out and "Hacker News" in out  # 出處清單來源
    assert "出處" in out


def test_events_section_multiple_events_all_present():
    out = render_today_events_section([
        _event(title="事件甲", summary="內容甲[1]。"),
        _event(title="事件乙", summary="內容乙[1]。", theme="新工具"),
    ])
    assert "事件甲" in out and "事件乙" in out
    assert "🆕" in out  # 新工具 icon


def test_events_section_escapes_and_pangu():
    out = render_today_events_section([
        _event(title="風險<X>", summary="模型GPT很強[1]。"),
    ])
    assert "風險&lt;X&gt;" in out  # 標題 HTML 跳脫
    assert "模型 GPT 很強" in out  # 摘要套用盤古空格
    assert "x=1&amp;y=2" in out  # 出處 url 跳脫


def test_events_section_citation_without_url_is_plain():
    out = render_today_events_section([
        _event(summary="僅一句[1]。", citations=[{"n": 1, "source": "threads"}]),
    ])
    assert "[1]" in out and "threads" in out
    assert "href" not in out.split("出處")[1]  # 出處清單中無連結（純文字）


def test_events_section_marker_without_citation_kept_as_plaintext():
    # summary 有 [9] 但 citations 無對應 → 仍保留為上標純文字，不丟字
    out = render_today_events_section([
        _event(summary="講了什麼[9]。", citations=[{"n": 1, "url": "http://a"}]),
    ])
    assert "[9]" in out


def test_events_section_is_pure_no_mutation():
    ev = _event()
    snapshot = {"title": ev["title"], "summary": ev["summary"]}
    a = render_today_events_section([ev])
    b = render_today_events_section([ev])
    assert a == b
    assert ev["title"] == snapshot["title"] and ev["summary"] == snapshot["summary"]


def test_events_section_accepts_camelcase_member_count():
    ev = {"title": "t", "summary": "s[1]。", "citations": [{"n": 1, "url": "http://a"}], "memberCount": 7}
    out = render_today_events_section([ev])
    assert "7 篇" in out


# ---- render_html with events ----
def test_render_html_includes_events_section_when_provided():
    out = render_html(
        day=date(2026, 6, 5),
        summary="今日摘要",
        highlights={"新工具": [{"title_zh": "工具", "url": "http://a"}]},
        events=[_event()],
    )
    assert "今日事件" in out
    assert "GPT-5 發表" in out
    assert "[1]" in out
    assert "3 篇" in out
    # 事件區塊應排在「今日重點」摘要之後、各主題精選（🆕 新工具）之前
    assert out.index("今日重點") < out.index("今日事件") < out.index("🆕 新工具")


def test_render_html_without_events_omits_section_and_is_unchanged():
    args = dict(
        day=date(2026, 6, 5),
        summary="今日摘要",
        highlights={"新工具": [{"title_zh": "工具", "url": "http://a"}]},
    )
    base = render_html(**args)
    assert "今日事件" not in base
    # 顯式 None / 空 list 都應與不傳逐位元組相同（向後相容）
    assert render_html(**args, events=None) == base
    assert render_html(**args, events=[]) == base


def test_render_html_with_events_html_to_text_includes_event_text():
    out = render_html(
        day=date(2026, 6, 5),
        summary="今日摘要",
        highlights={},
        events=[_event(title="事件標題", summary="事件摘要內容[1]。")],
    )
    text = html_to_text(out)
    assert "今日事件" in text
    assert "事件標題" in text
    assert "事件摘要內容" in text
    assert "[1]" in text  # 引註標記在純文字中保留
    assert "<" not in text and ">" not in text


# ---- build_mime_message ----
def test_build_mime_structure_and_cid():
    msg = build_mime_message(
        subject="Pulse 每日 AI 情報 · 2026-06-05",
        sender="me@gmail.com",
        to=["me@gmail.com"],
        html='<img src="cid:cover@pulse">內容',
        images={"cover@pulse": b"\x89PNG\r\n\x1a\n_fakepng"},
    )
    assert msg.get_content_type() == "multipart/related"
    assert msg["Subject"]  # UTF-8 編碼後仍存在
    assert msg["From"] == "me@gmail.com"
    assert msg["To"] == "me@gmail.com"
    assert msg["Message-ID"] and msg["Date"]

    types = [part.get_content_type() for part in msg.walk()]
    assert "multipart/alternative" in types
    assert "text/plain" in types  # 後援純文字
    assert "text/html" in types
    assert "image/png" in types

    # CID header 與 inline disposition
    imgs = [p for p in msg.walk() if p.get_content_type() == "image/png"]
    assert imgs[0]["Content-ID"] == "<cover@pulse>"
    assert "inline" in imgs[0]["Content-Disposition"]


def test_build_mime_text_fallback_autogenerated():
    msg = build_mime_message(
        subject="s", sender="a@b.c", to="a@b.c",
        html="<h1>今日重點</h1><p>有 3 則新工具</p>",
    )
    plain = [p for p in msg.walk() if p.get_content_type() == "text/plain"][0]
    body = plain.get_payload(decode=True).decode("utf-8")
    assert "今日重點" in body and "<" not in body  # 由 HTML 自動轉純文字
