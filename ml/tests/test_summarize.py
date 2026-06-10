"""事件摘要 prompt / 解析 / 驗證 / orchestration 測試 —— 純函式 + 注入 fake generate_fn（不需 Ollama）。"""
from ml.summarize import (
    EventSummary,
    KeySentence,
    build_summary_prompt,
    format_sources,
    parse_summary,
    summarize_event,
    validate_summary,
)

# 範例事件：三句來源關鍵句（編號 1..3）。
KEYS = [
    KeySentence("OpenAI 發表新模型 GPT-5，主打更強的推理能力。", source_id=101, source="Threads"),
    KeySentence("官方表示 GPT-5 的 API 價格與前代相同。", source_id=102),
    KeySentence("有開發者實測指出回應速度略有下降。", source_id=103),
]

# fake：引註完整且合法。
GOOD = "OpenAI 發表 GPT-5，主打更強推理 [1]。API 價格與前代相同 [2]。實測回應速度略降 [3]。"
# fake：第二句缺引註。
MISSING_CITE = "OpenAI 發表 GPT-5 [1]。價格沒有變動。"
# fake：引註超出來源範圍（[5]）。
OUT_OF_RANGE = "OpenAI 發表 GPT-5 [1]。速度下降 [5]。"


def good_fn(_prompt: str) -> str:
    return GOOD


def bad_fn(_prompt: str) -> str:
    return MISSING_CITE


# ---- prompt 組裝 ----
def test_prompt_contains_anti_hallucination_instructions():
    p = build_summary_prompt(KEYS)
    assert "只能使用" in p  # 只准用來源事實
    assert "杜撰" in p  # 禁止杜撰
    assert "[n]" in p  # 引註格式說明
    assert "繁體中文" in p


def test_prompt_embeds_numbered_sources():
    p = build_summary_prompt(KEYS)
    assert "[1] OpenAI 發表新模型 GPT-5" in p
    assert "[2] 官方表示 GPT-5 的 API 價格" in p
    assert "[3] 有開發者實測" in p


def test_prompt_respects_max_sentences():
    p = build_summary_prompt(KEYS, max_sentences=3)
    assert "最多 3 句" in p


def test_prompt_accepts_dicts_and_strings():
    p = build_summary_prompt([{"text": "甲事實", "source_id": 7}, "乙事實"])
    assert "[1] 甲事實" in p
    assert "[2] 乙事實" in p


# ---- format_sources ----
def test_format_sources_numbers_from_one():
    block = format_sources(KEYS)
    lines = block.splitlines()
    assert len(lines) == 3
    assert lines[0].startswith("[1] ")
    assert lines[2].startswith("[3] ")


def test_format_sources_includes_source_tag_when_present():
    block = format_sources(KEYS)
    assert "（來源：Threads）" in block  # 第一句帶 source
    # 第二句沒 source → 不應有空括號
    assert "（來源：）" not in block


def test_format_sources_strips_newlines_in_text():
    block = format_sources([KeySentence("第一行\n第二行")])
    assert block == "[1] 第一行 第二行"


# ---- parse_summary ----
def test_parse_clean_text():
    s = parse_summary(GOOD)
    assert isinstance(s, EventSummary)
    assert s.cited_ids == {1, 2, 3}
    assert len(s.sentences) == 3
    assert "GPT-5" in s.text


def test_parse_strips_code_fence():
    raw = "```\nOpenAI 發表 GPT-5 [1]。價格不變 [2]。\n```"
    s = parse_summary(raw)
    assert "```" not in s.text
    assert s.cited_ids == {1, 2}


def test_parse_strips_code_fence_with_lang():
    raw = "```markdown\n摘要：\nGPT-5 發表 [1]。\n```"
    s = parse_summary(raw)
    assert "```" not in s.text
    assert "摘要：" not in s.text  # 前言行被濾掉
    assert s.cited_ids == {1}


def test_parse_strips_preamble_and_bullets():
    raw = "以下是\n- GPT-5 發表 [1]\n- 價格不變 [2]"
    s = parse_summary(raw)
    assert "以下是" not in s.text
    assert not s.text.lstrip().startswith("-")
    assert s.cited_ids == {1, 2}


def test_parse_extracts_multi_and_fullwidth_citations():
    s = parse_summary("某句 [1][3]。另一句 ［2］。第三句 [4, 5]。")
    assert s.cited_ids == {1, 2, 3, 4, 5}


def test_parse_empty_output():
    s = parse_summary("")
    assert s.text == ""
    assert s.sentences == []
    assert s.cited_ids == set()


# ---- validate_summary ----
def test_validate_good_summary_ok():
    s = parse_summary(GOOD)
    issues = validate_summary(s, n_sources=3)
    assert issues.ok
    assert not issues.empty
    assert issues.uncited_sentences == []
    assert issues.out_of_range_ids == []


def test_validate_flags_missing_citation():
    s = parse_summary(MISSING_CITE)
    issues = validate_summary(s, n_sources=3)
    assert not issues.ok
    assert any("價格沒有變動" in sent for sent in issues.uncited_sentences)


def test_validate_flags_out_of_range():
    s = parse_summary(OUT_OF_RANGE)
    issues = validate_summary(s, n_sources=3)
    assert not issues.ok
    assert issues.out_of_range_ids == [5]


def test_validate_flags_zero_and_negative_handled():
    # [0] 不合法（<1）；應被列為超範圍。
    s = parse_summary("某事件 [0]。")
    issues = validate_summary(s, n_sources=3)
    assert 0 in issues.out_of_range_ids


def test_validate_empty_summary():
    issues = validate_summary(parse_summary(""), n_sources=3)
    assert issues.empty
    assert not issues.ok


def test_validate_pure_citation_line_not_uncited():
    # 只有引註、沒有實質內容的句子不該被當成「缺引註的論述句」。
    s = parse_summary("實質內容 [1]。 [2] ")
    issues = validate_summary(s, n_sources=2)
    assert issues.uncited_sentences == []


def test_validate_no_duplicate_out_of_range():
    s = parse_summary("句一 [9]。句二 [9]。")
    issues = validate_summary(s, n_sources=3)
    assert issues.out_of_range_ids == [9]  # 去重


# ---- summarize_event（注入 fake，端到端）----
def test_summarize_event_good_end_to_end():
    summary, issues = summarize_event(KEYS, good_fn)
    assert summary.cited_ids == {1, 2, 3}
    assert issues.ok


def test_summarize_event_bad_reports_issues():
    summary, issues = summarize_event(KEYS, bad_fn)
    assert not issues.ok
    assert issues.uncited_sentences


def test_summarize_event_passes_prompt_to_generate_fn():
    captured = {}

    def capture_fn(prompt: str) -> str:
        captured["prompt"] = prompt
        return GOOD

    summarize_event(KEYS, capture_fn, max_sentences=4)
    assert "最多 4 句" in captured["prompt"]
    assert "[1] OpenAI" in captured["prompt"]


def test_summarize_event_n_sources_from_keys():
    # 只給 2 句來源，但模型引了 [3] → 應判超範圍。
    two = KEYS[:2]
    summary, issues = summarize_event(two, good_fn)  # GOOD 引到 [3]
    assert 3 in issues.out_of_range_ids
    assert summary.cited_ids == {1, 2, 3}


def test_to_json_roundtrip_shapes():
    summary, issues = summarize_event(KEYS, good_fn)
    sj = summary.to_json()
    assert sj["cited_ids"] == [1, 2, 3]
    assert set(issues.to_json()) == {"ok", "empty", "uncited_sentences", "out_of_range_ids"}


# ---------------------------------------------------------------------------
# 額外邊界：format_sources / _coerce
# ---------------------------------------------------------------------------
def test_format_sources_empty_returns_empty_string():
    assert format_sources([]) == ""


def test_format_sources_coerces_dict_post_id_fallback():
    # dict 無 source_id 但有 post_id → 以 post_id 填 source_id（顯示編號仍 1..N）。
    block = format_sources([{"text": "甲", "post_id": 42}])
    assert block == "[1] 甲"


def test_build_summary_prompt_empty_keys_has_empty_source_block():
    # 無關鍵句仍能組出 prompt（來源區塊為空），不丟例外。
    p = build_summary_prompt([])
    assert "來源：" in p
    assert "事件摘要：" in p


# ---------------------------------------------------------------------------
# 額外邊界：parse_summary robust 解析
# ---------------------------------------------------------------------------
def test_parse_fullwidth_comma_in_citation():
    # 全形逗號 / 頓號分隔的引註也要抽得到。
    s = parse_summary("某句 [1，2、3]。")
    assert s.cited_ids == {1, 2, 3}


def test_parse_ignores_non_numeric_brackets():
    # [a]、[] 不是有效引註，不該被當成編號。
    s = parse_summary("有 [1] 與 [a] 還有 [] 與 [ 2 ]。")
    assert s.cited_ids == {1, 2}


def test_parse_code_fence_only_is_empty():
    s = parse_summary("```\n```")
    assert s.text == ""
    assert s.sentences == []
    assert s.cited_ids == set()


def test_parse_semicolon_splits_sentences():
    # 中英文分號也是句界。
    s = parse_summary("甲事實 [1]；乙事實 [2]")
    assert len(s.sentences) == 2


def test_parse_numbered_list_prefix_stripped_keeps_citation():
    # 行首 "1." 編號被去掉，但句中引註 [n] 保留。
    s = parse_summary("1. 甲事件 [1]\n2) 乙事件 [2]")
    assert s.cited_ids == {1, 2}
    assert not s.text.lstrip().startswith("1.")


# ---------------------------------------------------------------------------
# 額外邊界：validate_summary
# ---------------------------------------------------------------------------
def test_validate_all_out_of_range_when_zero_sources():
    s = parse_summary("某句 [1]。")
    issues = validate_summary(s, n_sources=0)
    assert issues.out_of_range_ids == [1]
    assert not issues.ok


def test_validate_multiple_distinct_out_of_range_sorted():
    s = parse_summary("甲 [9]。乙 [7]。丙 [9]。")
    issues = validate_summary(s, n_sources=3)
    # 去重且排序（cited_ids 為 set，validate 依排序輸出）。
    assert issues.out_of_range_ids == [7, 9]


def test_validate_pure_citation_then_empty_not_flagged_uncited():
    s = parse_summary("實質內容 [1]。[2]。")
    issues = validate_summary(s, n_sources=2)
    assert issues.uncited_sentences == []


def test_summarize_event_empty_generation_is_empty_and_safe():
    summary, issues = summarize_event(KEYS, lambda _p: "")
    assert summary.text == ""
    assert issues.empty
    assert not issues.ok
