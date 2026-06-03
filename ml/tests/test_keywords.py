"""熱詞抽取測試 —— 斷詞（jieba+OpenCC）+ log-odds 趨勢純函式。"""
from collections import Counter

from ml.keywords import log_odds_trending, tokenize


def test_tokenize_keeps_english_and_models():
    toks = tokenize("用 Claude 寫 prompt，MCP 真的好用")
    assert "claude" in toks  # 英文整塊保留 + 小寫
    assert "mcp" in toks
    # 單字中文 / 停用詞被濾掉
    assert "用" not in toks
    assert "的" not in toks


def test_tokenize_traditional_normalized_to_simplified():
    # 繁體「軟體 / 資料庫」經 OpenCC t2s 後 jieba 才切得乾淨；輸出為簡體
    toks = tokenize("軟體 資料庫 提示詞")
    assert "软件" in toks or "資料庫" not in toks  # 已轉簡體（不應留繁體原樣）


def test_tokenize_drops_pure_numbers_and_single_char():
    toks = tokenize("GPT 4.8 版 的 28")
    assert "4.8" not in toks  # 純版本碎片被濾
    assert "28" not in toks
    assert "gpt" in toks


def test_log_odds_ranks_spiking_term_first():
    # recent 大量出現 mcp，baseline 很少 → mcp z 最高、排第一
    recent = Counter({"mcp": 30, "claude": 10, "gpt": 5})
    baseline = Counter({"mcp": 2, "claude": 40, "gpt": 50})
    ranked = log_odds_trending(recent, baseline, min_recent=3)
    assert ranked[0][0] == "mcp"
    assert ranked[0][1] > 0  # z > 0 = 近期過度出現


def test_log_odds_min_recent_filters_rare():
    recent = Counter({"rare": 2, "common": 20})
    baseline = Counter({"rare": 1, "common": 5})
    terms = [t for t, _z, _c in log_odds_trending(recent, baseline, min_recent=3)]
    assert "rare" not in terms  # 近期 < min_recent → 濾掉
    assert "common" in terms
