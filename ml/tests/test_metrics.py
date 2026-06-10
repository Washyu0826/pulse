"""評測指標測試 —— 分類指標、McNemar、F1 差 CI 純函式。"""
import math

from ml.metrics import (
    accuracy_at_coverage,
    benjamini_hochberg,
    brier_score,
    classification_metrics,
    confusion_matrix,
    expected_calibration_error,
    f1_macro_delta_ci,
    mcnemar,
    nll,
    risk_coverage_curve,
)


# ---- confusion matrix ----
def test_confusion_matrix_shape_and_counts():
    cm = confusion_matrix(["a", "a", "b"], ["a", "b", "b"])
    assert cm["labels"] == ["a", "b"]
    # true=a: 1 預測 a、1 預測 b；true=b: 1 預測 b
    assert cm["matrix"] == [[1, 1], [0, 1]]


# ---- classification metrics ----
def test_perfect_classification():
    y = ["positive", "neutral", "negative", "positive"]
    m = classification_metrics(y, y)
    assert m["accuracy"] == 1.0
    assert m["f1_macro"] == 1.0
    assert m["f1_weighted"] == 1.0
    assert all(v == 1.0 for v in m["precision_per_class"].values())


def test_metrics_known_values():
    # true: a a a b ; pred: a a b b → a: tp2 fp0 fn1, b: tp1 fp1 fn0
    y_true = ["a", "a", "a", "b"]
    y_pred = ["a", "a", "b", "b"]
    m = classification_metrics(y_true, y_pred)
    assert abs(m["accuracy"] - 0.75) < 1e-9
    # a: P=1.0, R=2/3, F1=0.8 ; b: P=0.5, R=1.0, F1=2/3
    assert abs(m["precision_per_class"]["a"] - 1.0) < 1e-9
    assert abs(m["recall_per_class"]["a"] - 2 / 3) < 1e-9
    assert abs(m["f1_per_class"]["a"] - 0.8) < 1e-9
    assert abs(m["f1_per_class"]["b"] - 2 / 3) < 1e-9
    assert abs(m["f1_macro"] - (0.8 + 2 / 3) / 2) < 1e-9
    assert m["support"] == {"a": 3, "b": 1}


def test_metrics_empty():
    m = classification_metrics([], [])
    assert m["accuracy"] == 0.0
    assert m["f1_macro"] == 0.0


def test_length_mismatch_raises():
    import pytest

    with pytest.raises(ValueError):
        classification_metrics(["a"], ["a", "b"])


# ---- McNemar ----
def test_mcnemar_no_discordant_is_nonsignificant():
    y = ["a", "b", "a", "b"]
    r = mcnemar(y, y, y)
    assert r["n_discordant"] == 0
    assert r["p_value"] == 1.0


def test_mcnemar_counts_b_and_c():
    y_true = ["a", "a", "a", "a"]
    pred_a = ["a", "a", "a", "b"]  # 3 對 1 錯
    pred_b = ["b", "b", "b", "a"]  # 1 對 3 錯
    r = mcnemar(y_true, pred_a, pred_b)
    # A 對 B 錯：前 3 筆（a==a, b!=a）→ b=3；A 錯 B 對：最後一筆 → c=1
    assert r["b"] == 3
    assert r["c"] == 1
    assert r["n_discordant"] == 4
    assert r["exact"] is True  # 小樣本走精確二項
    assert 0.0 <= r["p_value"] <= 1.0


def test_mcnemar_exact_binomial_value():
    # b=4, c=0, n=4 → 雙尾 p = 2 * C(4,0)*0.5^4 = 2/16 = 0.125
    y_true = ["a"] * 4
    pred_a = ["a"] * 4  # 全對
    pred_b = ["b"] * 4  # 全錯 → b=4, c=0
    r = mcnemar(y_true, pred_a, pred_b)
    assert r["b"] == 4 and r["c"] == 0
    assert abs(r["p_value"] - 0.125) < 1e-9


def test_mcnemar_large_sample_uses_chi2():
    # 構造 discordant >= 25：30 筆 A 對 B 錯、5 筆反向
    y_true = ["a"] * 40
    pred_a = ["a"] * 40
    pred_b = ["b"] * 30 + ["a"] * 5 + ["a"] * 5  # b=30, c=... A 全對，B 前30錯
    r = mcnemar(y_true, pred_a, pred_b)
    assert r["exact"] is False
    assert r["n_discordant"] >= 25
    # 連續性校正統計量 = (|30-0|-1)^2/30 = 29^2/30
    assert abs(r["statistic"] - (29**2) / 30) < 1e-9
    assert r["p_value"] < 0.05  # 顯著
    # p 與 erfc 公式一致
    assert abs(r["p_value"] - math.erfc(math.sqrt(r["statistic"] / 2))) < 1e-12


# ---- F1 delta CI ----
def test_f1_delta_ci_positive_when_a_better():
    y_true = ["a", "a", "b", "b", "a", "b"]
    pred_a = ["a", "a", "b", "b", "a", "b"]  # 全對 → F1=1
    pred_b = ["b", "b", "a", "a", "b", "a"]  # 全錯
    r = f1_macro_delta_ci(y_true, pred_a, pred_b, n_boot=300, seed=1)
    assert r["f1_delta"] > 0
    assert r["ci_low"] <= r["f1_delta"] <= r["ci_high"]


def test_f1_delta_ci_is_deterministic():
    y_true = ["a", "a", "b", "b"]
    pa = ["a", "b", "b", "b"]
    pb = ["a", "a", "a", "b"]
    r1 = f1_macro_delta_ci(y_true, pa, pb, n_boot=200, seed=7)
    r2 = f1_macro_delta_ci(y_true, pa, pb, n_boot=200, seed=7)
    assert r1 == r2


# ---- ECE ----
def test_ece_perfectly_calibrated_is_zero():
    # 信心 0.6、剛好 60% 正確 → 該箱 acc==conf → ECE=0
    confidences = [0.6] * 10
    correct = [True] * 6 + [False] * 4
    assert expected_calibration_error(confidences, correct, n_bins=10) < 1e-9


def test_ece_overconfident_is_positive():
    # 信心全 0.9 但只有一半對 → |0.5-0.9|=0.4
    ece = expected_calibration_error([0.9] * 10, [True] * 5 + [False] * 5, n_bins=10)
    assert abs(ece - 0.4) < 1e-9


def test_ece_adaptive_runs_and_bounded():
    import random

    rng = random.Random(0)
    conf = [rng.random() for _ in range(50)]
    corr = [rng.random() < c for c in conf]
    e = expected_calibration_error(conf, corr, n_bins=5, adaptive=True)
    assert 0.0 <= e <= 1.0


# ---- Brier / NLL ----
def test_brier_and_nll_perfect():
    probs = [{"a": 1.0, "b": 0.0}, {"a": 0.0, "b": 1.0}]
    y = ["a", "b"]
    assert brier_score(probs, y, ["a", "b"]) == 0.0
    assert abs(nll(probs, y)) < 1e-9


def test_brier_worst_case():
    # 機率全押錯類 → 每筆 (1-0)^2 + (0-1)^2 = 2
    probs = [{"a": 0.0, "b": 1.0}]
    assert abs(brier_score(probs, ["a"], ["a", "b"]) - 2.0) < 1e-9


def test_nll_penalizes_confident_wrong():
    probs = [{"a": 0.01, "b": 0.99}]
    assert nll(probs, ["a"]) > 4.0  # -log(0.01) ≈ 4.6


# ---- risk-coverage ----
def test_risk_coverage_all_correct_is_zero_risk():
    rc = risk_coverage_curve([0.9, 0.8, 0.7], [True, True, True])
    assert rc["aurc"] == 0.0
    assert rc["risk"] == [0.0, 0.0, 0.0]


def test_risk_coverage_confident_wrong_hurts_early():
    # 最高信心那筆就錯 → 低 coverage 風險高
    rc = risk_coverage_curve([0.9, 0.5, 0.4], [False, True, True])
    assert rc["risk"][0] == 1.0  # coverage=1/3 全錯
    assert rc["aurc"] > 0


def test_accuracy_at_coverage_improves_when_abstaining():
    # 信心高的對、信心低的錯 → 降 coverage 應提升 accuracy
    conf = [0.9, 0.8, 0.2, 0.1]
    correct = [True, True, False, False]
    acc = accuracy_at_coverage(conf, correct, coverages=(1.0, 0.5))
    assert acc[1.0] == 0.5
    assert acc[0.5] == 1.0  # 只留信心最高的一半 → 全對


# ---- BH-FDR ----
def test_benjamini_hochberg_rejects_and_is_monotone():
    pvals = {"x": 0.001, "y": 0.01, "z": 0.5, "w": 0.04}
    out = benjamini_hochberg(pvals, q=0.05)
    assert out["x"]["reject"] is True
    assert out["z"]["reject"] is False
    # 調整後 p 不小於原始 p
    assert all(out[k]["p_adj"] >= out[k]["p"] - 1e-12 for k in pvals)


def test_benjamini_hochberg_empty():
    assert benjamini_hochberg({}) == {}
