"""DQC 評分純函式測試 —— 不需 DB / 網路。"""
from ml.data_quality import FLAG_DEDUCTIONS, score_post


def _post(**ov) -> dict:
    base = dict(
        source="hackernews",
        title="Claude 3.5 benchmark vs GPT-4: a detailed comparison of coding performance",
        content="I tried Claude on a real refactoring task and compared the results with GPT.",
        author="someuser",
        url="https://news.ycombinator.com/item?id=1",
        score=50,
        num_comments=20,
    )
    base.update(ov)
    return base


def test_clean_relevant_post_scores_high():
    res = score_post(_post(), ["claude", "gpt"])
    assert res.score >= 80
    assert res.flags == []  # 乾淨、相關、無雜訊


def test_deleted_is_hard_zero():
    res = score_post(_post(title="[deleted]", content="[deleted]"), ["claude"])
    assert res.score == 0
    assert res.flags == ["DELETED"]


def test_too_short():
    res = score_post(_post(title="gpt", content=""), ["gpt"])
    assert "TOO_SHORT" in res.flags


def test_link_heavy():
    content = "https://a.com/x https://b.com/y https://c.com/z https://d.com/w " * 3
    res = score_post(_post(content=content), ["claude"])
    assert "LINK_HEAVY" in res.flags


def test_spam_phrase_and_ad():
    res = score_post(
        _post(
            title="Best AI deal: 50% off Claude alternative",
            content="Limited time discount! Sign up now and click here to buy now.",
        ),
        ["claude"],
    )
    assert "SPAM_PHRASE" in res.flags
    assert "AD" in res.flags
    assert res.score < 30  # 推廣垃圾應落到低品質


def test_single_promo_word_not_spam():
    # 單一推廣詞在正當提問裡 → 不該判 SPAM_PHRASE，分數仍高（code review H1）
    res = score_post(_post(title="Does Claude offer a free trial?", content="Thinking of trying Claude."), ["claude"])
    assert "SPAM_PHRASE" not in res.flags
    assert res.score >= 60


def test_hiring_discussion_not_job_posting():
    res = score_post(
        _post(title="Why is OpenAI hiring so aggressively for GPT safety?", content="Curious about the GPT team growth."),
        ["gpt"],
    )
    assert "JOB_POSTING" not in res.flags
    assert res.score >= 60


def test_listicle_title_not_clickbait():
    res = score_post(
        _post(title="5 reasons Claude beats GPT for coding agents", content="A detailed comparison of Claude and GPT."),
        ["claude", "gpt"],
    )
    assert "CLICKBAIT" not in res.flags
    assert res.score >= 60


def test_affiliate():
    res = score_post(
        _post(content="Get the discount here https://x.com/buy?ref=abc123 limited time"),
        ["gpt"],
    )
    assert "AFFILIATE" in res.flags


def test_clickbait_title():
    res = score_post(_post(title="You won't believe what GPT did next"), ["gpt"])
    assert "CLICKBAIT" in res.flags


def test_job_posting():
    res = score_post(
        _post(title="We're hiring: ML engineer to work on LLaMA", content="Apply now, $180k/yr remote role."),
        ["llama"],
    )
    assert "JOB_POSTING" in res.flags


def test_seo_keyword_stuffing_excludes_model_alias():
    # 非主題詞被堆砌 → SEO
    res = score_post(
        _post(
            title="cheap cheap cheap deals",
            content="cheap cheap cheap cheap cheap cheap discount on gemini cheap",
        ),
        ["gemini"],
    )
    assert "SEO" in res.flags


def test_repeating_model_name_is_not_seo():
    # 認真討論某模型、重複其名 7+ 次 → 不該被當成 SEO 堆砌
    res = score_post(
        _post(
            title="Deep dive: Claude for production coding",
            content=("Claude " * 9) + "is great for refactoring; I use Claude daily and review with Claude.",
        ),
        ["claude"],
    )
    assert "SEO" not in res.flags


def test_all_caps_and_excessive_punct():
    res = score_post(_post(title="GPT IS THE BEST MODEL EVER WOW", content="AMAZING INCREDIBLE!!!"), ["gpt"])
    assert "ALL_CAPS" in res.flags
    assert "EXCESSIVE_PUNCT" in res.flags


def test_likely_bot_author():
    res = score_post(_post(author="news_bot42"), ["claude"])
    assert "LIKELY_BOT" in res.flags


def test_keyword_only_in_url_flagged_not_in_body():
    # 模型 slug 只出現在 URL，去雜訊後正文/標題看不到 → KEYWORD_NOT_IN_BODY
    res = score_post(
        _post(title="A neat tool I built", content="Check it out: https://claude.example.com/demo"),
        ["claude"],
    )
    assert "KEYWORD_NOT_IN_BODY" in res.flags


def test_weak_keyword_single_passing_mention():
    res = score_post(
        _post(title="Thoughts on local dev setups", content="By the way I also use gpt sometimes."),
        ["gpt"],
    )
    assert "WEAK_KEYWORD" in res.flags


def test_offtopic_ambiguous_keyword_no_ai_context():
    # llama 指動物/西語、全文無 AI 脈絡（且來自一般社群 threads）→ OFF_TOPIC，分數 <30 被濾
    res = score_post(
        _post(source="threads", title="Mi llama bebé es hermoso",
              content="Es un hermoso machito, se le llama Paco."),
        ["llama"],
    )
    assert "OFF_TOPIC" in res.flags
    assert res.score < 30


def test_offtopic_only_for_general_sources_not_tech():
    # 同樣無脈絡的歧義關鍵字，但來自技術社群（hackernews）→ 信任關鍵字，不判 OFF_TOPIC
    res = score_post(
        _post(source="hackernews", title="Mi llama bebé es hermoso",
              content="Es un hermoso machito, se le llama Paco."),
        ["llama"],
    )
    assert "OFF_TOPIC" not in res.flags


def test_ambiguous_keyword_with_ai_context_passes():
    # 正當的本地 Llama 部署討論：有 70B / local / GPU / inference 脈絡 → 不判 OFF_TOPIC
    res = score_post(
        _post(source="threads", title="Running Llama 70B locally",
              content="Benchmarked Llama on my GPU, great inference speed."),
        ["llama"],
    )
    assert "OFF_TOPIC" not in res.flags
    assert res.score >= 80


def test_gemini_zodiac_is_offtopic():
    # gemini 指星座、無 AI 脈絡（threads）→ OFF_TOPIC
    res = score_post(
        _post(source="threads", title="AIR SIGNS: Gemini Libra Aquarius",
              content="Gemini season energy reading for air signs."),
        ["gemini"],
    )
    assert "OFF_TOPIC" in res.flags


def test_mixed_ambiguous_and_real_model_not_offtopic():
    # 同篇也提到非歧義模型（gpt）→ 明確在談 AI，不該 OFF_TOPIC
    res = score_post(
        _post(source="threads", title="llama vs gpt for my pet project",
              content="Compared llama and gpt on a coding task."),
        ["llama", "gpt"],
    )
    assert "OFF_TOPIC" not in res.flags


def test_model_as_product_not_offtopic():
    # 「模型當產品用」的強訊號（接版本/變體）→ 即使在 threads、無其他脈絡也不該被誤殺
    for title in ("LlaMa.cpp Robot Wars", "Gemini 3.5 Flash beats Opus on bluffbench", "Grok 4 first impressions"):
        slug = "gemini" if "Gemini" in title else "grok" if "Grok" in title else "llama"
        res = score_post(_post(source="threads", title=title, content=title), [slug])
        assert "OFF_TOPIC" not in res.flags, title


def test_generate_in_gemini_not_offtopic():
    # 「generate files in Gemini」→ generat* 脈絡 → 非離題
    res = score_post(
        _post(source="threads", title="You can now generate files in Gemini",
              content="generate files in Gemini"),
        ["gemini"],
    )
    assert "OFF_TOPIC" not in res.flags


def test_company_or_unambiguous_alias_context_not_offtopic():
    # 旁邊出現 AI 公司名 / 非歧義別名（xAI）→ 明確 AI，不該離題（即使在 threads）
    r1 = score_post(_post(source="threads", title="Voice Cloning on xAI", content="Voice Cloning on xAI"), ["grok"])
    assert "OFF_TOPIC" not in r1.flags
    r2 = score_post(
        _post(source="threads", title="Google's Gemini wrote a 5k-word paper",
              content="Google's Gemini wrote a paper"),
        ["gemini"],
    )
    assert "OFF_TOPIC" not in r2.flags


def test_sarcasm_is_flag_only_no_deduction():
    res = score_post(_post(content="Claude broke again, oh great another outage /s"), ["claude"])
    assert "SARCASM_DETECTED" in res.flags
    # flag-only：不在扣分表
    assert "SARCASM_DETECTED" not in FLAG_DEDUCTIONS


def test_non_english_not_penalised_for_language():
    # 中文貼文真的在談 claude → 不應有任何語言 flag，分數仍高
    res = score_post(
        _post(
            title="Claude 表現如何？實測 coding 與 GPT 比較",
            content="我用 Claude 做了重構任務，跟 GPT 比較後覺得品質更好，review 也更準。",
        ),
        ["claude", "gpt"],
    )
    assert all("ENGLISH" not in f and "LANG" not in f for f in res.flags)
    assert res.score >= 80


def test_empty_models_no_relevance_flags():
    res = score_post(_post(), [])
    assert "KEYWORD_NOT_IN_BODY" not in res.flags
    assert "WEAK_KEYWORD" not in res.flags


def test_score_clamped_0_100():
    # 疊一堆扣分也不會 < 0
    res = score_post(
        _post(
            title="HIRING!!! 50% OFF CLICK HERE",
            content="we're hiring apply now buy now discount https://x.com/a?ref=1 " * 5,
            author="spam_bot",
        ),
        ["gpt"],
    )
    assert 0 <= res.score <= 100
