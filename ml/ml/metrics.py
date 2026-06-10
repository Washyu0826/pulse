"""
評測指標 —— 分類指標 + 模型對比顯著性檢定（純 Python，無 sklearn）。

Phase 3 訓練（compute_metrics）與 Phase 4 Offline Evaluation 共用。刻意用 stdlib 手刻
（與 sentiment.py 的統計同風格）：可單元測試、無重依賴、可解釋。

- classification_metrics：accuracy / macro-F1 / weighted-F1 / per-class P-R / confusion。
- mcnemar：兩模型在同一 labeled set 的配對比較（Dietterich 1998；Dror et al. 2018）。
  小樣本（discordant < 25）用精確二項；大樣本用連續性校正 χ²（df=1，p 由 erfc 算）。
- f1_macro_delta_ci：macro-F1 差的 paired bootstrap CI（Koehn 2004；reuse annotation.bootstrap_ci）。
"""
from __future__ import annotations

import math

from ml.annotation import bootstrap_ci

__all__ = [
    "confusion_matrix",
    "classification_metrics",
    "mcnemar",
    "f1_macro_delta_ci",
    "expected_calibration_error",
    "brier_score",
    "nll",
    "risk_coverage_curve",
    "accuracy_at_coverage",
    "benjamini_hochberg",
]


def _labels_of(*seqs: list[str]) -> list[str]:
    """所有出現過的標籤（排序，確定性）。"""
    s: set[str] = set()
    for seq in seqs:
        s.update(seq)
    return sorted(s)


def confusion_matrix(
    y_true: list[str], y_pred: list[str], labels: list[str] | None = None
) -> dict:
    """混淆矩陣：rows=true、cols=pred。回傳 {labels, matrix}（matrix[i][j]=true=i 被預測成 j 的數）。"""
    if len(y_true) != len(y_pred):
        raise ValueError("y_true 與 y_pred 長度需相同")
    labels = labels or _labels_of(y_true, y_pred)
    idx = {lbl: i for i, lbl in enumerate(labels)}
    m = [[0] * len(labels) for _ in labels]
    for t, p in zip(y_true, y_pred, strict=True):
        if t in idx and p in idx:
            m[idx[t]][idx[p]] += 1
    return {"labels": labels, "matrix": m}


def classification_metrics(
    y_true: list[str], y_pred: list[str], labels: list[str] | None = None
) -> dict:
    """
    完整分類指標。回傳 dict：accuracy、f1_macro、f1_weighted、
    precision_per_class、recall_per_class、f1_per_class、support、confusion_matrix。
    純函式。空輸入回傳 0 值結構。
    """
    if len(y_true) != len(y_pred):
        raise ValueError("y_true 與 y_pred 長度需相同")
    labels = labels or _labels_of(y_true, y_pred)
    n = len(y_true)
    precision: dict[str, float] = {}
    recall: dict[str, float] = {}
    f1: dict[str, float] = {}
    support: dict[str, int] = {}
    for lbl in labels:
        tp = sum(1 for t, p in zip(y_true, y_pred, strict=True) if t == lbl and p == lbl)
        fp = sum(1 for t, p in zip(y_true, y_pred, strict=True) if t != lbl and p == lbl)
        fn = sum(1 for t, p in zip(y_true, y_pred, strict=True) if t == lbl and p != lbl)
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        precision[lbl] = prec
        recall[lbl] = rec
        f1[lbl] = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        support[lbl] = tp + fn

    accuracy = (
        sum(1 for t, p in zip(y_true, y_pred, strict=True) if t == p) / n if n else 0.0
    )
    f1_macro = sum(f1.values()) / len(labels) if labels else 0.0
    f1_weighted = (sum(f1[lbl] * support[lbl] for lbl in labels) / n) if n else 0.0
    return {
        "accuracy": accuracy,
        "f1_macro": f1_macro,
        "f1_weighted": f1_weighted,
        "precision_per_class": precision,
        "recall_per_class": recall,
        "f1_per_class": f1,
        "support": support,
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels),
    }


def _chi2_df1_sf(stat: float) -> float:
    """χ²（df=1）的存活函數 S(x)=erfc(√(x/2))，給 McNemar 大樣本 p 值用。"""
    if stat <= 0:
        return 1.0
    return math.erfc(math.sqrt(stat / 2.0))


def _binom_two_sided(b: int, c: int) -> float:
    """精確二項雙尾 p（H0：discordant 對半開，p=0.5）。給小樣本 McNemar 用。"""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) * (0.5**n)
    return min(1.0, 2.0 * tail)


def mcnemar(
    y_true: list[str], pred_a: list[str], pred_b: list[str], *, exact_threshold: int = 25
) -> dict:
    """
    McNemar 配對檢定：A、B 兩模型在同一份 labeled set 上的差異是否統計顯著。

    只看「分歧對」：b = A 對 B 錯、c = A 錯 B 對。discordant = b+c。
    - discordant < exact_threshold → 精確二項雙尾 p（小樣本更穩）。
    - 否則 → 連續性校正 χ² 統計量 (|b-c|-1)²/(b+c)，p 由 χ²(df=1) 存活函數。
    回傳 {b, c, statistic, p_value, n_discordant, exact}。純函式。
    """
    if not (len(y_true) == len(pred_a) == len(pred_b)):
        raise ValueError("三個序列長度需相同")
    b = sum(
        1
        for t, a, bb in zip(y_true, pred_a, pred_b, strict=True)
        if a == t and bb != t
    )
    c = sum(
        1
        for t, a, bb in zip(y_true, pred_a, pred_b, strict=True)
        if a != t and bb == t
    )
    n = b + c
    stat = ((abs(b - c) - 1) ** 2) / n if n > 0 else 0.0
    if n < exact_threshold:
        p = _binom_two_sided(b, c)
        exact = True
    else:
        p = _chi2_df1_sf(stat)
        exact = False
    return {"b": b, "c": c, "statistic": stat, "p_value": p, "n_discordant": n, "exact": exact}


def f1_macro_delta_ci(
    y_true: list[str],
    pred_a: list[str],
    pred_b: list[str],
    *,
    n_boot: int = 1000,
    ci: float = 0.95,
    seed: int = 42,
) -> dict:
    """
    macro-F1 差（A - B）的點估計與 paired bootstrap 95% CI（Koehn 2004；
    Berg-Kirkpatrick 2012 建議報 CI 而非裸 p）。CI 不含 0 ⇒ 差異穩健。純函式。
    """
    data = list(zip(y_true, pred_a, pred_b, strict=True))

    def _delta(sample: list[tuple[str, str, str]]) -> float:
        ts = [x[0] for x in sample]
        ar = [x[1] for x in sample]
        br = [x[2] for x in sample]
        labels = _labels_of(ts, ar, br)
        fa = classification_metrics(ts, ar, labels)["f1_macro"]
        fb = classification_metrics(ts, br, labels)["f1_macro"]
        return fa - fb

    delta = _delta(data)
    lo, hi = bootstrap_ci(data, _delta, n_boot=n_boot, ci=ci, seed=seed)
    return {"f1_delta": delta, "ci_low": lo, "ci_high": hi}


# ---------------------------------------------------------------------------
# 校準與選擇性預測（軸二：Guo 2017、Nixon 2019、Geifman 2019、Geng 2024）。
# 產品在低信心時棄答 → 評測要報校準（ECE/Brier/NLL）與 risk–coverage，不能只看 top-1。
# ---------------------------------------------------------------------------


def expected_calibration_error(
    confidences: list[float], correct: list[bool], *, n_bins: int = 15, adaptive: bool = False
) -> float:
    """
    ECE：Σ_bin (n_bin/N)·|acc_bin − conf_bin|（Guo 2017）。
    adaptive=True 用等量分箱（每箱樣本數相同，Nixon 2019），小樣本較不受 bin 數影響。
    confidences=每筆 top-1 機率；correct=該筆是否預測正確。純函式。
    """
    if len(confidences) != len(correct):
        raise ValueError("confidences 與 correct 長度需相同")
    n = len(confidences)
    if n == 0:
        return 0.0
    if adaptive:
        order = sorted(range(n), key=lambda i: confidences[i])
        bins = [
            [(confidences[i], correct[i]) for i in order[k * n // n_bins : (k + 1) * n // n_bins]]
            for k in range(n_bins)
        ]
    else:
        bins = [[] for _ in range(n_bins)]
        for conf, ok in zip(confidences, correct, strict=True):
            idx = min(int(conf * n_bins), n_bins - 1)
            bins[idx].append((conf, ok))
    ece = 0.0
    for b in bins:
        if not b:
            continue
        conf_mean = sum(c for c, _ in b) / len(b)
        acc = sum(1 for _, ok in b if ok) / len(b)
        ece += (len(b) / n) * abs(acc - conf_mean)
    return ece


def brier_score(probs: list[dict[str, float]], y_true: list[str], labels: list[str]) -> float:
    """多類 Brier 分數：平均 Σ_k (p_k − 1[y=k])²（proper scoring rule，越低越好）。純函式。"""
    n = len(y_true)
    if n == 0:
        return 0.0
    total = 0.0
    for p, t in zip(probs, y_true, strict=True):
        for lbl in labels:
            y = 1.0 if t == lbl else 0.0
            total += (p.get(lbl, 0.0) - y) ** 2
    return total / n


def nll(
    probs: list[dict[str, float]], y_true: list[str], *, eps: float = 1e-12
) -> float:
    """平均負對數似然（= 溫度縮放擬合的目標；越低越好）。純函式。"""
    n = len(y_true)
    if n == 0:
        return 0.0
    s = 0.0
    for p, t in zip(probs, y_true, strict=True):
        s += -math.log(max(p.get(t, 0.0), eps))
    return s / n


def risk_coverage_curve(confidences: list[float], correct: list[bool]) -> dict:
    """
    risk–coverage 曲線（Geifman & El-Yaniv 2019）：按信心由高到低納入，
    coverage=已答比例、risk=已答中的錯誤率。AURC = 各 coverage 的選擇性風險平均（越低越好）。
    回傳 {coverage:[...], risk:[...], aurc}。純函式。
    """
    n = len(confidences)
    if n == 0:
        return {"coverage": [], "risk": [], "aurc": 0.0}
    order = sorted(range(n), key=lambda i: confidences[i], reverse=True)
    coverage: list[float] = []
    risk: list[float] = []
    errors = 0
    aurc_sum = 0.0
    for k, i in enumerate(order, 1):
        if not correct[i]:
            errors += 1
        r = errors / k
        coverage.append(k / n)
        risk.append(r)
        aurc_sum += r
    return {"coverage": coverage, "risk": risk, "aurc": aurc_sum / n}


def accuracy_at_coverage(
    confidences: list[float], correct: list[bool], coverages: tuple[float, ...] = (1.0, 0.9, 0.8, 0.7)
) -> dict[float, float]:
    """各 coverage 下（取信心最高的前 c 比例）的 accuracy。比較新舊模型應在相同 coverage 下比。純函式。"""
    n = len(confidences)
    if n == 0:
        return {c: 0.0 for c in coverages}
    order = sorted(range(n), key=lambda i: confidences[i], reverse=True)
    out: dict[float, float] = {}
    for c in coverages:
        k = max(1, round(c * n))
        sel = order[:k]
        out[c] = sum(1 for i in sel if correct[i]) / k
    return out


def benjamini_hochberg(p_values: dict[str, float], q: float = 0.05) -> dict[str, dict]:
    """
    BH-FDR 多重比較校正（Benjamini-Hochberg 1995）：多個 per-class/per-task 檢定一起校正，
    比 Bonferroni 有檢定力。回傳每個 key 的 {p, p_adj, reject}。純函式。
    """
    if not p_values:
        return {}
    items = sorted(p_values.items(), key=lambda kv: kv[1])
    m = len(items)
    # BH 調整 p：從大到小取累積最小（保證單調）。
    adj: list[float] = [0.0] * m
    prev = 1.0
    for rank in range(m, 0, -1):
        _, p = items[rank - 1]
        val = min(prev, p * m / rank)
        adj[rank - 1] = val
        prev = val
    out: dict[str, dict] = {}
    for (key, p), p_adj in zip(items, adj, strict=True):
        out[key] = {"p": p, "p_adj": p_adj, "reject": p_adj <= q}
    return out
