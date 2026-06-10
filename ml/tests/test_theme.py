"""主題分類純邏輯測試 —— _pick（門檻 + top-2）、ThemeResult.labels、distribution。

不載入模型（torch 只在 ThemeClassifier.__init__ 內 import），純函式可離線測。
"""
from ml.theme import (
    OTHER_LABEL,
    THEME_HYPOTHESES,
    ThemeClassifier,
    ThemeResult,
    _pick,
)

# 5 個主題分數的便利建構（缺的補 0）。
_T = ("新工具", "模型動態", "使用方法", "風險限制", "倫理法規")


def _scores(**kw) -> dict:
    """便利建構 5 主題分數字典（未給的補 0）。"""
    return {t: float(kw.get(t, 0.0)) for t in _T}


def test_taxonomy_is_five_themes():
    assert tuple(THEME_HYPOTHESES) == ("新工具", "模型動態", "使用方法", "風險限制", "倫理法規")
    assert OTHER_LABEL == "其他"


# ---- _pick：信心門檻 ----
def test_pick_below_min_confidence_is_other():
    r = _pick(_scores(新工具=0.30, 模型動態=0.20), min_confidence=0.45)
    assert r.label == OTHER_LABEL
    assert r.confident is False
    assert r.secondary is None
    assert r.labels == [OTHER_LABEL]


def test_pick_above_min_confidence_keeps_top():
    r = _pick(_scores(使用方法=0.80, 新工具=0.10), min_confidence=0.45)
    assert r.label == "使用方法"
    assert r.confident is True
    assert abs(r.confidence - 0.80) < 1e-9


# ---- _pick：top-2 secondary ----
def test_pick_emits_secondary_when_above_secondary_min():
    r = _pick(_scores(新工具=0.80, 使用方法=0.55), min_confidence=0.45, secondary_min=0.40)
    assert r.label == "新工具"
    assert r.secondary == "使用方法"
    assert r.labels == ["新工具", "使用方法"]


def test_pick_no_secondary_when_below_secondary_min():
    r = _pick(_scores(新工具=0.80, 使用方法=0.30), min_confidence=0.45, secondary_min=0.40)
    assert r.secondary is None
    assert r.labels == ["新工具"]


def test_pick_secondary_min_is_inclusive_boundary():
    # 次高剛好等於 secondary_min → 應納入
    r = _pick(_scores(新工具=0.70, 模型動態=0.40), min_confidence=0.45, secondary_min=0.40)
    assert r.secondary == "模型動態"


def test_pick_other_has_no_secondary_even_if_two_low_scores():
    r = _pick(_scores(新工具=0.30, 模型動態=0.25), min_confidence=0.45, secondary_min=0.20)
    assert r.label == OTHER_LABEL
    assert r.secondary is None  # 低信心 fallback 不帶 secondary


def test_pick_is_deterministic_on_ties():
    # 同分時 sorted 穩定 → 結果可重現
    s = _scores(新工具=0.6, 模型動態=0.6, 使用方法=0.6)
    a = _pick(s, min_confidence=0.45)
    b = _pick(s, min_confidence=0.45)
    assert (a.label, a.secondary) == (b.label, b.secondary)


# ---- ThemeResult.labels property ----
def test_labels_property_dedups_and_orders():
    assert ThemeResult("新工具", 0.8, {}, True, secondary=None).labels == ["新工具"]
    assert ThemeResult("新工具", 0.8, {}, True, secondary="模型動態").labels == ["新工具", "模型動態"]
    # 防衛：secondary 與 label 相同時不重複
    assert ThemeResult("新工具", 0.8, {}, True, secondary="新工具").labels == ["新工具"]


# ---- distribution（依主主題彙總，含其他）----
def test_distribution_counts_primary_labels():
    results = [
        ThemeResult("新工具", 0.9, {}, True),
        ThemeResult("新工具", 0.8, {}, True, secondary="使用方法"),
        ThemeResult("模型動態", 0.7, {}, True),
        ThemeResult(OTHER_LABEL, 0.2, {}, False),
    ]
    dist = ThemeClassifier.distribution(results)
    assert dist["新工具"] == 2  # 只算主主題，不算 secondary
    assert dist["模型動態"] == 1
    assert dist["使用方法"] == 0
    assert dist[OTHER_LABEL] == 1
    # 所有 5 主題 + 其他都在
    assert set(dist) == set(THEME_HYPOTHESES) | {OTHER_LABEL}


def test_distribution_empty():
    dist = ThemeClassifier.distribution([])
    assert sum(dist.values()) == 0
    assert dist[OTHER_LABEL] == 0
