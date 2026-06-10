"""蒸餾 prompt / 解析測試 —— 純函式（不需 Ollama）。"""
from ml.distill import (
    THEME_LABELS,
    build_sentiment_prompt,
    build_theme_prompt,
    parse_sentiment,
    parse_theme,
)


def test_theme_labels_match_theme_module():
    assert THEME_LABELS == ("新工具", "模型動態", "使用方法", "風險限制", "倫理法規", "其他")


# ---- prompt 組裝 ----
def test_prompts_embed_text_and_escape_quotes():
    p = build_sentiment_prompt('他說 "Claude 很爛"')
    assert "Claude 很爛" in p
    assert '"Claude 很爛"' not in p  # 雙引號被換成單引號，避免破壞 few-shot 格式
    assert "positive, neutral, or negative" in p


def test_theme_prompt_lists_all_options():
    p = build_theme_prompt("測試")
    for key in ("tool", "model", "usage", "risk", "ethics", "other"):
        assert key in p


# ---- 情緒解析 ----
def test_parse_sentiment_english():
    assert parse_sentiment("positive") == "positive"
    assert parse_sentiment("  Negative.") == "negative"  # 大小寫/標點容忍
    assert parse_sentiment("Neutral") == "neutral"


def test_parse_sentiment_chinese_and_invalid():
    assert parse_sentiment("中性") == "neutral"
    assert parse_sentiment("負面") == "negative"
    assert parse_sentiment("garbage") is None
    assert parse_sentiment("") is None


def test_parse_sentiment_takes_earliest_match():
    # 先出現 negative → 取 negative（容忍模型多話）
    assert parse_sentiment("negative, definitely not positive") == "negative"


# ---- 主題解析 ----
def test_parse_theme_english_keys():
    assert parse_theme("tool") == "新工具"
    assert parse_theme("model comparison") == "模型動態"
    assert parse_theme("usage") == "使用方法"
    assert parse_theme("risk of hallucination") == "風險限制"
    assert parse_theme("ethics") == "倫理法規"
    assert parse_theme("other") == "其他"


def test_parse_theme_accepts_chinese_labels():
    assert parse_theme("使用方法") == "使用方法"
    assert parse_theme("模型動態") == "模型動態"


def test_parse_theme_invalid():
    assert parse_theme("不知道") is None
    assert parse_theme("") is None
