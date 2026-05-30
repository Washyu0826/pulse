"""情緒分析的純統計邏輯測試 —— 不需模型 / torch。"""
from ml.sentiment import SentimentAnalyzer, SentimentResult, flag_sarcasm


def _r(label: str, score: float = 0.9) -> SentimentResult:
    scores = {"positive": 0.0, "neutral": 0.0, "negative": 0.0}
    scores[label] = score
    return SentimentResult(label=label, score=score, scores=scores)


# ---- signed ----

def test_signed_sign():
    assert _r("positive", 0.8).signed == 0.8
    assert _r("negative", 0.8).signed == -0.8
    assert _r("neutral", 0.8).signed == 0.0


# ---- summarize（信心加權 soft + 收縮）----

def test_summarize_counts_and_weighted_index():
    # 3 正 1 負 1 中、score=0.9；shrink=0 → soft 加權 index = round(0.36*100) = 36
    results = [_r("positive"), _r("positive"), _r("positive"), _r("negative"), _r("neutral")]
    s = SentimentAnalyzer.summarize(results, shrink=0)
    assert (s.total, s.positive, s.negative, s.neutral) == (5, 3, 1, 1)
    assert s.index == 36
    assert s.label == "positive"


def test_summarize_small_sample_shrinks_toward_neutral():
    one_pos = [_r("positive", 1.0)]
    assert SentimentAnalyzer.summarize(one_pos, shrink=0).index == 100  # 無收縮
    assert SentimentAnalyzer.summarize(one_pos, shrink=3).index == 25  # 1/(1+3) 收縮


def test_summarize_empty():
    s = SentimentAnalyzer.summarize([])
    assert s.total == 0 and s.index == 0 and s.label == "neutral"


def test_summarize_neutral_band():
    s = SentimentAnalyzer.summarize([_r("positive"), _r("negative"), _r("neutral")])
    assert s.label == "neutral"


def test_polarization():
    # 50/50 愛恨 → 100；全正 → 0
    half = [_r("positive")] * 5 + [_r("negative")] * 5
    assert SentimentAnalyzer.summarize(half).polarization == 100
    assert SentimentAnalyzer.summarize([_r("positive")] * 5).polarization == 0


# ---- detect_flip（兩比例 z 檢定 + 極性跨越）----

def test_flip_positive_to_negative():
    early = [_r("positive")] * 8 + [_r("negative")]
    later = [_r("negative")] * 8 + [_r("positive")]
    flip = SentimentAnalyzer.detect_flip(early, later)
    assert flip.flipped is True
    assert flip.direction == "to_negative"
    assert flip.p_value < 0.05  # 統計顯著


def test_flip_negative_to_positive():
    flip = SentimentAnalyzer.detect_flip([_r("negative")] * 7, [_r("positive")] * 7)
    assert flip.flipped is True
    assert flip.direction == "to_positive"


def test_no_flip_when_stable():
    early = [_r("positive")] * 7
    later = [_r("positive")] * 6 + [_r("neutral")]
    assert SentimentAnalyzer.detect_flip(early, later).flipped is False


def test_no_flip_when_insufficient_samples():
    flip = SentimentAnalyzer.detect_flip([_r("positive")] * 2, [_r("negative")] * 8)
    assert flip.flipped is False
    assert "樣本不足" in flip.reason


def test_detect_flip_accepts_summary_input():
    """detect_flip 也接受預先算好的 SentimentSummary（生產常見路徑）。"""
    ps = SentimentAnalyzer.summarize([_r("positive")] * 8 + [_r("negative")])
    cs = SentimentAnalyzer.summarize([_r("negative")] * 8 + [_r("positive")])
    flip = SentimentAnalyzer.detect_flip(ps, cs)
    assert flip.flipped is True and flip.direction == "to_negative"


# ---- 反諷標記 ----

def test_flag_sarcasm():
    assert flag_sarcasm("This is totally reliable /s") is True
    assert flag_sarcasm("yeah right, it never crashes") is True
    assert flag_sarcasm("DeepSeek is genuinely fast and reliable") is False
    assert flag_sarcasm("") is False
