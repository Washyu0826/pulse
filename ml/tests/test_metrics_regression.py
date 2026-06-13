"""
統計實作回歸鎖定 —— McNemar / ECE / Brier / BH-FDR 的硬編期望值。

這些是 Offline Evaluation 的統計命脈（選型結論直接依賴它們）。公式經查正確（見 metrics.py
docstring 引用），本檔用**手算的黃金數值**鎖住輸出，讓日後任何重構若改了數值會立刻紅燈，
而不是靜默退化。每個數值都附「怎麼算出來的」以便人工複核。純函式，不需重依賴。
"""
import math

from ml.metrics import (
    benjamini_hochberg,
    brier_score,
    expected_calibration_error,
    mcnemar,
)


# ---------------------------------------------------------------------------
# McNemar：小樣本精確二項、大樣本連續性校正 χ²(df=1)。
# ---------------------------------------------------------------------------
def test_mcnemar_exact_binomial_golden():
    # b=3, c=1, n=4 < 25 → 精確二項雙尾。
    # 雙尾 p = 2·Σ_{i=0}^{min(b,c)} C(4,i)·0.5^4 = 2·(C(4,0)+C(4,1))·0.0625
    #        = 2·(1+4)·0.0625 = 2·5·0.0625 = 0.625
    y_true = ["a", "a", "a", "a"]
    pred_a = ["a", "a", "a", "b"]  # 前3對、末1錯 → b=3
    pred_b = ["b", "b", "b", "a"]  # 前3錯、末1對 → c=1
    r = mcnemar(y_true, pred_a, pred_b)
    assert r["b"] == 3 and r["c"] == 1
    assert r["exact"] is True
    assert abs(r["p_value"] - 0.625) < 1e-12


def test_mcnemar_exact_extreme_golden():
    # b=5, c=0, n=5 → 雙尾 p = 2·C(5,0)·0.5^5 = 2/32 = 0.0625
    y_true = ["a"] * 5
    pred_a = ["a"] * 5
    pred_b = ["b"] * 5
    r = mcnemar(y_true, pred_a, pred_b)
    assert r["b"] == 5 and r["c"] == 0
    assert abs(r["p_value"] - 0.0625) < 1e-12


def test_mcnemar_chi2_continuity_golden():
    # discordant=26 >= 25 → 連續性校正 χ²。b=20, c=6。
    # stat = (|20-6|-1)^2 / 26 = 13^2/26 = 169/26 = 6.5
    # p = erfc(sqrt(6.5/2)) = erfc(sqrt(3.25))
    y_true = ["a"] * 26
    pred_a = ["a"] * 20 + ["b"] * 6  # 前20對、後6錯 → b=20
    pred_b = ["b"] * 20 + ["a"] * 6  # 前20錯、後6對 → c=6
    r = mcnemar(y_true, pred_a, pred_b)
    assert r["b"] == 20 and r["c"] == 6
    assert r["exact"] is False
    assert abs(r["statistic"] - 6.5) < 1e-12
    assert abs(r["p_value"] - math.erfc(math.sqrt(3.25))) < 1e-12


# ---------------------------------------------------------------------------
# ECE：Σ_bin (n_bin/N)·|acc_bin − conf_bin|。
# ---------------------------------------------------------------------------
def test_ece_two_bins_golden():
    # 10 筆，兩個有資料的箱（n_bins=10）：
    #   conf=0.15 ×4（落 bin1=[0.1,0.2)），其中 1 對 → acc=0.25，|0.25-0.15|=0.10，權重 4/10
    #   conf=0.85 ×6（落 bin8=[0.8,0.9)），其中 6 對 → acc=1.0，|1.0-0.85|=0.15，權重 6/10
    # ECE = 0.4·0.10 + 0.6·0.15 = 0.04 + 0.09 = 0.13
    confidences = [0.15] * 4 + [0.85] * 6
    correct = [True] + [False] * 3 + [True] * 6
    ece = expected_calibration_error(confidences, correct, n_bins=10)
    assert abs(ece - 0.13) < 1e-12


def test_ece_perfect_is_zero_golden():
    # conf=0.6 ×10，剛好 6 對 → acc=0.6=conf → ECE=0。
    ece = expected_calibration_error([0.6] * 10, [True] * 6 + [False] * 4, n_bins=10)
    assert abs(ece) < 1e-12


# ---------------------------------------------------------------------------
# Brier：平均 Σ_k (p_k − 1[y=k])²。
# ---------------------------------------------------------------------------
def test_brier_golden_value():
    # 兩筆、labels=[a,b]：
    #   筆1 y=a, p={a:0.7,b:0.3} → (0.7-1)²+(0.3-0)² = 0.09+0.09 = 0.18
    #   筆2 y=b, p={a:0.2,b:0.8} → (0.2-0)²+(0.8-1)² = 0.04+0.04 = 0.08
    # 平均 = (0.18+0.08)/2 = 0.13
    probs = [{"a": 0.7, "b": 0.3}, {"a": 0.2, "b": 0.8}]
    y_true = ["a", "b"]
    assert abs(brier_score(probs, y_true, ["a", "b"]) - 0.13) < 1e-12


def test_brier_perfect_and_worst_golden():
    # 完美：0；最差（全押反）：每筆 2，平均 2。
    assert brier_score([{"a": 1.0, "b": 0.0}], ["a"], ["a", "b"]) == 0.0
    assert abs(brier_score([{"a": 0.0, "b": 1.0}], ["a"], ["a", "b"]) - 2.0) < 1e-12


# ---------------------------------------------------------------------------
# BH-FDR：排序後 p_adj = min(右側累積最小, p·m/rank)，單調。
# ---------------------------------------------------------------------------
def test_bh_fdr_golden_adjusted_values():
    # m=4，排序 p = [0.001(x), 0.01(y), 0.04(w), 0.5(z)]
    # 原始 BH：p·m/rank → x:0.001·4/1=0.004; y:0.01·4/2=0.02; w:0.04·4/3≈0.05333; z:0.5·4/4=0.5
    # 從大到小取累積最小（保單調）：z=0.5; w=min(0.5,0.05333)=0.05333; y=min(0.05333,0.02)=0.02;
    #   x=min(0.02,0.004)=0.004
    out = benjamini_hochberg({"x": 0.001, "y": 0.01, "w": 0.04, "z": 0.5}, q=0.05)
    assert abs(out["x"]["p_adj"] - 0.004) < 1e-12
    assert abs(out["y"]["p_adj"] - 0.02) < 1e-12
    assert abs(out["w"]["p_adj"] - 0.04 * 4 / 3) < 1e-12
    assert abs(out["z"]["p_adj"] - 0.5) < 1e-12
    # q=0.05：x,y 拒絕（p_adj<=0.05）；w 的 p_adj≈0.0533>0.05 不拒；z 不拒。
    assert out["x"]["reject"] is True
    assert out["y"]["reject"] is True
    assert out["w"]["reject"] is False
    assert out["z"]["reject"] is False


def test_bh_fdr_is_monotone_nondecreasing():
    # 調整後 p 隨原始 p 單調不減（BH 的不變量）。
    pvals = {"a": 0.001, "b": 0.008, "c": 0.02, "d": 0.03, "e": 0.2}
    out = benjamini_hochberg(pvals, q=0.05)
    ordered = sorted(pvals, key=lambda k: pvals[k])
    adj = [out[k]["p_adj"] for k in ordered]
    assert all(adj[i] <= adj[i + 1] + 1e-12 for i in range(len(adj) - 1))
