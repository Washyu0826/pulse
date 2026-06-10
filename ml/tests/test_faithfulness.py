"""
忠實度評測測試 —— 全部用確定性的**假 nli_fn**，不需要任何模型。

假 nli_fn 規則（fake_nli）：
- 若 hypothesis 的詞集 ⊆ premise 的詞集（且非空）→ 高蘊含。
- 若 hypothesis 含否定詞（不/沒/非/no/not）而 premise 不含同樣否定 → 高矛盾。
- 否則 → 中性。
這讓我們能在無模型下，確定性地驗證所有純函式與編排邏輯。
"""
import re

from ml.faithfulness import (
    FaithfulnessReport,
    SentenceEntailment,
    build_nli_fn,
    citation_validity,
    entailment_scores,
    faithfulness_report,
    parse_citations,
    source_coverage,
    split_summary_sentences,
    strip_citations,
)

_NEG = ("不", "沒", "非", "no", "not")


def _tokens(text: str) -> set[str]:
    """粗略斷詞：英文按詞、中文按字（夠假 nli 用）。"""
    text = text.lower()
    toks = set(re.findall(r"[a-z0-9]+", text))
    toks.update(ch for ch in text if "一" <= ch <= "鿿")
    return toks


def fake_nli(premise: str, hypothesis: str) -> dict:
    """確定性假 NLI：詞集包含→蘊含；否定不一致→矛盾；否則中性。"""
    p, h = _tokens(premise), _tokens(hypothesis)
    p_neg = any(n in premise.lower() for n in _NEG)
    h_neg = any(n in hypothesis.lower() for n in _NEG)
    if h_neg and not p_neg:
        return {"entailment": 0.05, "neutral": 0.15, "contradiction": 0.80}
    if h and h <= p:
        return {"entailment": 0.90, "neutral": 0.08, "contradiction": 0.02}
    return {"entailment": 0.20, "neutral": 0.70, "contradiction": 0.10}


# ---------------------------------------------------------------------------
# parse_citations
# ---------------------------------------------------------------------------
def test_parse_single_citation():
    assert parse_citations("這是一句 [1]。") == [1]


def test_parse_adjacent_citations():
    assert parse_citations("某主張 [2][3]") == [2, 3]


def test_parse_comma_citations():
    assert parse_citations("某主張 [1,2]") == [1, 2]
    assert parse_citations("某主張 [1, 2]") == [1, 2]


def test_parse_no_citation():
    assert parse_citations("沒有任何引用的句子") == []


def test_parse_dedup_and_order():
    # 去重且保序（依首次出現）。
    assert parse_citations("先 [3] 再 [1] 又 [3]") == [3, 1]


def test_parse_out_of_range_still_parsed():
    # parse 不負責範圍判斷，原樣抽出（範圍交給 validity/coverage）。
    assert parse_citations("越界 [9]") == [9]


# ---------------------------------------------------------------------------
# strip_citations
# ---------------------------------------------------------------------------
def test_strip_removes_markers():
    assert strip_citations("模型發表了新功能 [1][2]。") == "模型發表了新功能 。"


def test_strip_collapses_whitespace():
    assert strip_citations("a [1]  b") == "a b"


def test_strip_no_marker_unchanged():
    assert strip_citations("純文字句子") == "純文字句子"


# ---------------------------------------------------------------------------
# split_summary_sentences
# ---------------------------------------------------------------------------
def test_split_chinese():
    s = split_summary_sentences("第一句。第二句！第三句？")
    assert s == ["第一句", "第二句", "第三句"]


def test_split_english():
    s = split_summary_sentences("First one. Second one! Third?")
    assert s == ["First one", "Second one", "Third"]


def test_split_mixed_and_newlines():
    s = split_summary_sentences("中文句子。\nEnglish line.\n混合 mixed！")
    assert s == ["中文句子", "English line", "混合 mixed"]


def test_split_empty():
    assert split_summary_sentences("") == []
    assert split_summary_sentences("   ") == []


def test_split_keeps_citation_in_sentence():
    s = split_summary_sentences("主張一 [1]。主張二 [2]。")
    assert s == ["主張一 [1]", "主張二 [2]"]


def test_split_does_not_break_decimal():
    # "GPT-4." 的句點不該誤切（其後無空白/結尾的字母數字情境除外）。
    s = split_summary_sentences("價格是 3.5 美元一句話。")
    assert s == ["價格是 3.5 美元一句話"]


# ---------------------------------------------------------------------------
# citation_validity
# ---------------------------------------------------------------------------
def test_citation_validity_fully_cited():
    summary = "主張一 [1]。主張二 [2]。"
    cv = citation_validity(summary, n_sources=2)
    assert cv["rate"] == 1.0
    assert cv["n_sentences"] == 2
    assert cv["uncited"] == []
    assert cv["out_of_range"] == []


def test_citation_validity_partial():
    summary = "有引用 [1]。沒引用。"
    cv = citation_validity(summary, n_sources=2)
    assert cv["rate"] == 0.5
    assert cv["uncited"] == ["沒引用"]


def test_citation_validity_out_of_range():
    summary = "越界引用 [9]。"
    cv = citation_validity(summary, n_sources=2)
    assert cv["rate"] == 0.0
    assert cv["out_of_range"] == ["越界引用 [9]"]
    assert cv["uncited"] == []


def test_citation_validity_empty():
    cv = citation_validity("", n_sources=3)
    assert cv["rate"] == 0.0
    assert cv["n_sentences"] == 0


# ---------------------------------------------------------------------------
# source_coverage
# ---------------------------------------------------------------------------
def test_source_coverage_full():
    summary = "甲 [1]。乙 [2]。丙 [3]。"
    cov = source_coverage(summary, 3)
    assert cov["rate"] == 1.0
    assert cov["cited_sources"] == [1, 2, 3]
    assert cov["uncited_sources"] == []


def test_source_coverage_partial():
    summary = "只引一個來源 [1]，再講一句 [1]。"
    cov = source_coverage(summary, 4)
    assert cov["rate"] == 0.25
    assert cov["cited_sources"] == [1]
    assert cov["uncited_sources"] == [2, 3, 4]


def test_source_coverage_ignores_out_of_range():
    cov = source_coverage("越界 [9]。", 3)
    assert cov["rate"] == 0.0
    assert cov["cited_sources"] == []


def test_source_coverage_zero_sources():
    cov = source_coverage("任意 [1]。", 0)
    assert cov["rate"] == 0.0
    assert cov["n_sources"] == 0


# ---------------------------------------------------------------------------
# entailment_scores（含假 nli）
# ---------------------------------------------------------------------------
def test_entailment_uses_cited_source():
    sources = ["公司今天發表了新模型", "完全無關的內容文字"]
    # 句子引用來源 1，且其詞集 ⊆ 來源 1 → 假 nli 給高蘊含。
    summary = "公司今天發表了新模型 [1]。"
    res = entailment_scores(summary, sources, fake_nli)
    assert len(res) == 1
    se = res[0]
    assert isinstance(se, SentenceEntailment)
    assert se.citations == [1]
    assert se.used_sources == [1]
    assert se.entailment >= 0.5
    assert se.text == "公司今天發表了新模型 。" or "公司" in se.text


def test_entailment_uncited_falls_back_to_all_sources():
    sources = ["甲來源內容", "乙來源內容"]
    summary = "甲來源內容"  # 無引用 → 退回全部來源當 premise
    res = entailment_scores(summary, sources, fake_nli)
    assert res[0].used_sources == [1, 2]
    assert res[0].entailment >= 0.5  # 詞集仍 ⊆ 全部來源串接


def test_entailment_contradiction_signal():
    sources = ["這個工具很穩定可靠"]
    summary = "這個工具不穩定 [1]。"  # 含否定 → 假 nli 給高矛盾
    res = entailment_scores(summary, sources, fake_nli)
    assert res[0].contradiction >= 0.5


def test_entailment_out_of_range_falls_back():
    sources = ["甲", "乙"]
    summary = "某句 [9]。"  # 引用越界 → 退回全部來源
    res = entailment_scores(summary, sources, fake_nli)
    assert res[0].used_sources == [1, 2]


# ---------------------------------------------------------------------------
# faithfulness_report：忠實 vs 幻覺
# ---------------------------------------------------------------------------
def test_report_faithful_summary_scores_high():
    sources = [
        "甲公司今天發表了新的語言模型",
        "新模型在數學測驗上表現更好",
    ]
    summary = "甲公司今天發表了新的語言模型 [1]。新模型在數學測驗上表現更好 [2]。"
    rep = faithfulness_report(summary, sources, fake_nli)
    assert isinstance(rep, FaithfulnessReport)
    assert rep.frac_entailed == 1.0
    assert rep.citation_validity == 1.0
    assert rep.source_coverage == 1.0
    assert rep.frac_contradicted == 0.0
    assert rep.unsupported_sentences == []
    assert rep.faithfulness_score == 1.0


def test_report_hallucinated_summary_scores_low_and_flags():
    sources = [
        "甲公司今天發表了新的語言模型",
        "新模型在數學測驗上表現更好",
    ]
    # 第一句忠實有引用；第二句憑空捏造、無引用、且與來源詞集不符。
    summary = "甲公司今天發表了新的語言模型 [1]。這個模型其實爛透了完全沒人用。"
    rep = faithfulness_report(summary, sources, fake_nli)
    # 幻覺那句被標為不支持（低蘊含 + 無有效引用）。
    assert "這個模型其實爛透了完全沒人用" in rep.unsupported_sentences
    assert rep.citation_validity == 0.5
    assert rep.frac_entailed < 1.0


def test_report_hallucinated_scores_lower_than_faithful():
    sources = ["甲公司今天發表了新的語言模型", "新模型在數學測驗上表現更好"]
    faithful = "甲公司今天發表了新的語言模型 [1]。新模型在數學測驗上表現更好 [2]。"
    hallucinated = "甲公司今天發表了新的語言模型 [1]。這個模型其實爛透了完全沒人用。"
    s_good = faithfulness_report(faithful, sources, fake_nli).faithfulness_score
    s_bad = faithfulness_report(hallucinated, sources, fake_nli).faithfulness_score
    assert s_bad < s_good


def test_report_contradiction_flagged():
    sources = ["這個工具很穩定可靠且廣受好評"]
    summary = "這個工具不穩定 [1]。"
    rep = faithfulness_report(summary, sources, fake_nli)
    assert rep.frac_contradicted == 1.0
    assert summary.strip().rstrip("。") in [s.rstrip("。") for s in rep.contradicted_sentences] \
        or "這個工具不穩定 [1]" in rep.contradicted_sentences


def test_report_empty_summary_is_safe():
    rep = faithfulness_report("", ["甲", "乙"], fake_nli)
    assert rep.n_sentences == 0
    assert rep.mean_entailment == 0.0
    assert 0.0 <= rep.faithfulness_score <= 1.0


def test_report_score_in_unit_interval():
    sources = ["甲來源", "乙來源", "丙來源"]
    summary = "甲來源 [1]。某段沒引用的話。乙來源 [2] 但又否定不對 [2]。"
    rep = faithfulness_report(summary, sources, fake_nli)
    assert 0.0 <= rep.faithfulness_score <= 1.0


def test_report_custom_thresholds():
    # 把蘊含門檻拉到 0.95，原本 0.90 的句子就不算 entailed。
    sources = ["甲公司發表新模型"]
    summary = "甲公司發表新模型 [1]。"
    strict = faithfulness_report(summary, sources, fake_nli, entail_threshold=0.95)
    loose = faithfulness_report(summary, sources, fake_nli, entail_threshold=0.5)
    assert strict.frac_entailed == 0.0
    assert loose.frac_entailed == 1.0


# ---------------------------------------------------------------------------
# build_nli_fn：只測「沒裝重依賴時給友善錯誤」，不真的載模型
# ---------------------------------------------------------------------------
def test_build_nli_fn_is_callable_factory():
    # 不實際執行（避免下載重模型）；只確認它是可呼叫的工廠。
    assert callable(build_nli_fn)


# ---------------------------------------------------------------------------
# 額外邊界：parse_citations / strip_citations
# ---------------------------------------------------------------------------
def test_parse_citation_with_internal_spaces():
    assert parse_citations("某句 [ 1 , 2 ]") == [1, 2]


def test_parse_citation_fullwidth_brackets_not_supported():
    # faithfulness 的引註正則只認半形 [ ]（與 summarize 不同）；全形 ［］ 不被視為引註。
    # 記錄此行為：pipeline 對齊靠半形 [n]，故全形括號在此模組不算有效引用。
    assert parse_citations("某句 ［1］") == []


def test_parse_empty_brackets_no_digits():
    assert parse_citations("空括號 []") == []


def test_strip_citations_only_citation_leaves_empty():
    assert strip_citations("[1][2]") == ""


def test_strip_citations_multiple_internal_spaces():
    assert strip_citations("a   [1]   b") == "a b"


# ---------------------------------------------------------------------------
# 額外邊界：split_summary_sentences
# ---------------------------------------------------------------------------
def test_split_version_number_with_trailing_space_does_split():
    # 文件已載明：句點後接空白即視為句界，故 "GPT-4. " 會被切（刻意取捨）。
    out = split_summary_sentences("用了 GPT-4. 很強大")
    assert out == ["用了 GPT-4", "很強大"]


def test_split_domain_or_decimal_not_broken():
    # 句點後緊接非空白（小數 / 網域）不切。
    assert split_summary_sentences("造訪 openai.com 看看") == ["造訪 openai.com 看看"]
    assert split_summary_sentences("價格 3.5 元") == ["價格 3.5 元"]


def test_split_only_punctuation_is_empty():
    assert split_summary_sentences("。！？") == []


# ---------------------------------------------------------------------------
# 額外邊界：citation_validity / source_coverage
# ---------------------------------------------------------------------------
def test_citation_validity_mixed_valid_and_out_of_range_in_one_sentence():
    # 一句同時帶有效 [1] 與越界 [9] → 視為有效（有任一有效引用即可）。
    cv = citation_validity("某主張 [1][9]。", n_sources=3)
    assert cv["rate"] == 1.0
    assert cv["out_of_range"] == []


def test_citation_validity_zero_id_is_out_of_range():
    cv = citation_validity("某句 [0]。", n_sources=3)
    assert cv["rate"] == 0.0
    assert cv["out_of_range"] == ["某句 [0]"]


def test_source_coverage_negative_n_sources_safe():
    cov = source_coverage("某句 [1]。", -5)
    assert cov == {"rate": 0.0, "n_sources": 0, "cited_sources": [], "uncited_sources": []}


def test_source_coverage_dedups_repeated_citation():
    cov = source_coverage("甲 [1]。乙 [1]。丙 [2]。", 3)
    assert cov["cited_sources"] == [1, 2]
    assert abs(cov["rate"] - 2 / 3) < 1e-9


# ---------------------------------------------------------------------------
# 額外邊界：entailment_scores / faithfulness_report 對 nli_fn 回傳的容錯
# ---------------------------------------------------------------------------
def test_entailment_handles_partial_nli_keys():
    # nli_fn 只回 entailment → 缺的鍵以 0 補，不丟例外。
    def partial_nli(_p, _h):
        return {"entailment": 0.9}

    res = entailment_scores("某句 [1]。", ["來源"], partial_nli)
    assert res[0].entailment == 0.9
    assert res[0].neutral == 0.0
    assert res[0].contradiction == 0.0


def test_entailment_handles_extra_nli_keys():
    # nli_fn 多回無關鍵 → 被忽略。
    def extra_nli(_p, _h):
        return {"entailment": 0.7, "neutral": 0.2, "contradiction": 0.1, "garbage": 9.9}

    res = entailment_scores("某句 [1]。", ["來源"], extra_nli)
    assert res[0].entailment == 0.7


def test_report_nli_tie_at_threshold_counts_both():
    # entailment 與 contradiction 同為門檻值（0.5）→ 兩個 >= 判定皆成立。
    def tie_nli(_p, _h):
        return {"entailment": 0.5, "neutral": 0.0, "contradiction": 0.5}

    rep = faithfulness_report("某句 [1]。", ["來源"], tie_nli)
    assert rep.frac_entailed == 1.0  # 0.5 >= 0.5
    assert rep.frac_contradicted == 1.0  # 0.5 >= 0.5


def test_report_no_sources_all_citations_out_of_range():
    # 沒有任何來源 → 任何引用都越界 → 退回「全部來源」(空字串) 當 premise。
    def neutral_nli(_p, _h):
        return {"entailment": 0.2, "neutral": 0.7, "contradiction": 0.1}

    rep = faithfulness_report("某句 [1]。", [], neutral_nli)
    assert rep.source_coverage == 0.0
    assert rep.citation_validity == 0.0  # 無來源 → 引用全越界 → 無有效引用
    assert 0.0 <= rep.faithfulness_score <= 1.0


def test_report_score_clamped_to_unit_interval_extremes():
    # 全忠實 → 1.0；全不支持 + 矛盾 → 不低於 0、亦在 [0,1]。
    def all_contra(_p, _h):
        return {"entailment": 0.0, "neutral": 0.0, "contradiction": 1.0}

    rep = faithfulness_report("亂講的句子。又一句亂講。", ["來源甲"], all_contra)
    assert 0.0 <= rep.faithfulness_score <= 1.0


def test_entailment_empty_summary_returns_empty_list():
    assert entailment_scores("", ["甲", "乙"], fake_nli) == []
