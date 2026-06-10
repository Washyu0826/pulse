"""
摘要品質 bake-off —— 兩套摘要器在同一事件集上的忠實度離線比較（純統計，無模型）。

延續本專案的 Offline Evaluation 哲學（見 ml/ml/metrics.py、ml/ml/annotation.py 與
docs/research/offline-evaluation-literature.md）：報配對 bootstrap CI、不看裸點估計，
且**「落在重疊 / 跨 0 的 CI 內不算贏」**（鏡像 metrics.py 的 f1_macro_delta_ci 決策鐵則）。

本模組刻意做成「對一套系統的結果 = 一串 per-event 指標（list[float]）」的通用形式，
不綁死 faithfulness.py 的 FaithfulnessReport dataclass：呼叫端先把每個事件的某一指標
（通常是 faithfulness_score，也可以是 frac_entailed / source_coverage 等任一面向）抽成
一串分數，本模組只吃這串分數。這樣同一套統計可比較任何 [0,1] 的忠實度面向。

配對性是核心：scores_a[i] 與 scores_b[i] 必須是**同一個事件**在兩套系統下的分數
（同事件集、同順序）。配對比較比獨立比較更敏感（消掉「事件本身好不好摘」的變異）。

設計（與 metrics.py / annotation.py 同風格）：
- 全部純函式 / 純編排，無 DB、無網路、無模型。可單元測試、可重現（固定 seed）。
- 重用 ml.annotation.bootstrap_ci（通用百分位 bootstrap），不重造輪子；配對重抽是對
  「事件索引」重抽，再各自取兩系統的均值差，落在 bootstrap_ci 的 stat_fn 介面內。
"""
from __future__ import annotations

from statistics import mean, median

from ml.annotation import bootstrap_ci

__all__ = [
    "system_summary",
    "paired_delta_ci",
    "win_rate",
    "decide",
    "compare_systems",
    "format_markdown_report",
]


def system_summary(scores: list[float]) -> dict:
    """
    一套系統在事件集上的分數摘要統計：mean / median / min / max / n。

    空輸入回傳全 0、n=0（不丟例外，方便上層先報「無資料」）。純函式。
    """
    n = len(scores)
    if n == 0:
        return {"mean": 0.0, "median": 0.0, "min": 0.0, "max": 0.0, "n": 0}
    return {
        "mean": float(mean(scores)),
        "median": float(median(scores)),
        "min": float(min(scores)),
        "max": float(max(scores)),
        "n": n,
    }


def paired_delta_ci(
    scores_a: list[float],
    scores_b: list[float],
    *,
    n_boot: int = 2000,
    seed: int = 0,
    alpha: float = 0.05,
) -> dict:
    """
    mean(A) − mean(B) 的配對 bootstrap 信賴區間（百分位法；Koehn 2004、
    Berg-Kirkpatrick 2012 建議報 CI 而非裸 p）。

    A、B 必須同長度且**逐位置配對**（a[i]、b[i] 為同一事件在兩系統下的分數）。
    重用 ml.annotation.bootstrap_ci：把「配對」打包成 (a_i, b_i) 的 tuple 清單一起重抽，
    stat_fn 對重抽樣本取 mean(a)-mean(b)——如此事件索引被一致地重抽，保留配對結構，
    也不必另寫一份 bootstrap（沿用同一套已測過、固定 seed 的實作）。

    回傳 {delta, ci_low, ci_high, n}。delta 為點估計（全樣本的均值差）。
    alpha 對應 ci=1-alpha（預設 0.05 → 95% CI）。長度不符丟 ValueError。空輸入回傳 0。
    """
    if len(scores_a) != len(scores_b):
        raise ValueError("scores_a 與 scores_b 長度需相同（配對比較）")
    n = len(scores_a)
    if n == 0:
        return {"delta": 0.0, "ci_low": 0.0, "ci_high": 0.0, "n": 0}

    pairs = list(zip(scores_a, scores_b, strict=True))

    def _delta(sample: list[tuple[float, float]]) -> float:
        return mean(a for a, _ in sample) - mean(b for _, b in sample)

    delta = _delta(pairs)
    lo, hi = bootstrap_ci(pairs, _delta, n_boot=n_boot, ci=1.0 - alpha, seed=seed)
    return {"delta": float(delta), "ci_low": float(lo), "ci_high": float(hi), "n": n}


def win_rate(scores_a: list[float], scores_b: list[float], *, margin: float = 0.0) -> dict:
    """
    逐事件勝負：A 比 B 高出 > margin 算 A 贏、B 高出 > margin 算 B 贏、否則平手。

    margin 是「差多少才算贏」的門檻（避免把噪音等級的微小差距當勝場）。
    回傳 {wins_a, wins_b, ties, n, win_rate_a}（win_rate_a = wins_a / n）。
    A、B 需同長度且配對。空輸入回傳全 0。純函式。
    """
    if len(scores_a) != len(scores_b):
        raise ValueError("scores_a 與 scores_b 長度需相同（配對比較）")
    n = len(scores_a)
    wins_a = wins_b = ties = 0
    for a, b in zip(scores_a, scores_b, strict=True):
        diff = a - b
        if diff > margin:
            wins_a += 1
        elif -diff > margin:
            wins_b += 1
        else:
            ties += 1
    return {
        "wins_a": wins_a,
        "wins_b": wins_b,
        "ties": ties,
        "n": n,
        "win_rate_a": wins_a / n if n else 0.0,
    }


def decide(delta_ci: dict, *, name_a: str = "A", name_b: str = "B") -> str:
    """
    決策鐵則（鏡像本專案「落在重疊 CI 內不算贏」）：

    - delta = mean(A) − mean(B)。若 (ci_low, ci_high) **跨 0**（ci_low <= 0 <= ci_high）
      → 「no_winner (CI overlaps 0)」：差異與 0 不可區分，不宣稱任何一方贏。
    - 否則 CI 整段在 0 之上 → A 顯著較佳；整段在 0 之下 → B 顯著較佳。

    吃 paired_delta_ci 的輸出 dict。回傳人類可讀字串。純函式。
    """
    lo, hi = delta_ci["ci_low"], delta_ci["ci_high"]
    if lo <= 0.0 <= hi:
        return "no_winner (CI overlaps 0)"
    if lo > 0.0:
        return f"{name_a} wins (CI excludes 0)"
    return f"{name_b} wins (CI excludes 0)"


def compare_systems(
    name_a: str,
    scores_a: list[float],
    name_b: str,
    scores_b: list[float],
    *,
    n_boot: int = 2000,
    seed: int = 0,
    alpha: float = 0.05,
    margin: float = 0.0,
) -> dict:
    """
    把兩套系統的比較打包成一份報告 dict（純編排）：

    - systems: {name_a: system_summary, name_b: system_summary}
    - delta_ci: paired_delta_ci(A, B)（mean(A)-mean(B) 的配對 bootstrap CI）
    - win_rate: 逐事件勝負（含 margin）
    - decision: decide(delta_ci)（含系統名）

    metric 名稱由呼叫端決定（這裡只吃分數串）。長度不符會由下游函式丟 ValueError。
    """
    delta = paired_delta_ci(scores_a, scores_b, n_boot=n_boot, seed=seed, alpha=alpha)
    return {
        "name_a": name_a,
        "name_b": name_b,
        "systems": {
            name_a: system_summary(scores_a),
            name_b: system_summary(scores_b),
        },
        "delta_ci": delta,
        "win_rate": win_rate(scores_a, scores_b, margin=margin),
        "decision": decide(delta, name_a=name_a, name_b=name_b),
    }


def format_markdown_report(comparison: dict, *, extra_metrics: dict | None = None) -> str:
    """
    把 compare_systems 的輸出 render 成 markdown bake-off 報告。

    版面對齊 docs/evaluation-report-template.md（系統均值表 → 配對差 CI → 勝率 → 決策），
    並把決策鐵則寫進報告（CI 跨 0 ≠ 一場勝利）。

    extra_metrics（可選）：{指標名: {name_a: 數值, name_b: 數值}} ——
    額外面向（如 frac_entailed / source_coverage / frac_contradicted）的兩系統均值對照表，
    對應範本「§7 忠實度指標」。純函式（只組字串，不算統計）。
    """
    a, b = comparison["name_a"], comparison["name_b"]
    sa = comparison["systems"][a]
    sb = comparison["systems"][b]
    dci = comparison["delta_ci"]
    wr = comparison["win_rate"]
    n = dci["n"]

    lines: list[str] = []
    lines.append("# 摘要品質 Bake-off 報告")
    lines.append("")
    lines.append(
        "> 兩套摘要器在同一事件集上的忠實度配對比較（Offline Evaluation；非線上 A/B）。"
    )
    lines.append(f"> 事件數（配對）：{n}")
    lines.append("")

    # 1. 系統均值表
    lines.append("## 1. 系統分數摘要")
    lines.append("")
    lines.append("| 系統 | mean | median | min | max | n |")
    lines.append("|------|------|--------|-----|-----|---|")
    lines.append(
        f"| {a} | {sa['mean']:.4f} | {sa['median']:.4f} | "
        f"{sa['min']:.4f} | {sa['max']:.4f} | {sa['n']} |"
    )
    lines.append(
        f"| {b} | {sb['mean']:.4f} | {sb['median']:.4f} | "
        f"{sb['min']:.4f} | {sb['max']:.4f} | {sb['n']} |"
    )
    lines.append("")

    # 2. 配對差 CI
    lines.append("## 2. 配對均值差與 bootstrap 95% CI")
    lines.append("")
    lines.append(f"Δ = mean({a}) − mean({b}) = **{dci['delta']:+.4f}**")
    lines.append("")
    lines.append(f"配對 bootstrap 95% CI：[{dci['ci_low']:+.4f}, {dci['ci_high']:+.4f}]")
    lines.append("")

    # 3. 勝率
    lines.append("## 3. 逐事件勝率")
    lines.append("")
    lines.append("| 結果 | 場數 |")
    lines.append("|------|------|")
    lines.append(f"| {a} 勝 | {wr['wins_a']} |")
    lines.append(f"| {b} 勝 | {wr['wins_b']} |")
    lines.append(f"| 平手 | {wr['ties']} |")
    lines.append(f"| 合計 | {wr['n']} |")
    lines.append("")
    lines.append(f"{a} 勝率：{wr['win_rate_a']:.2%}")
    lines.append("")

    # 4. 額外面向（對齊範本 §7 忠實度指標）
    if extra_metrics:
        lines.append("## 4. 其他忠實度面向（均值對照）")
        lines.append("")
        lines.append(f"| 指標 | {a} | {b} |")
        lines.append("|------|------|------|")
        for metric_name, vals in extra_metrics.items():
            va = vals.get(a, 0.0)
            vb = vals.get(b, 0.0)
            lines.append(f"| {metric_name} | {va:.4f} | {vb:.4f} |")
        lines.append("")

    # 5. 決策
    lines.append("## 5. 決策")
    lines.append("")
    lines.append(
        "**決策鐵則：配對差的 bootstrap CI 跨 0（含 0）≠ 一場勝利。** "
        "只有 CI 整段不含 0 才宣稱該系統顯著較佳；否則視為「打平 / 證據不足」。"
    )
    lines.append("")
    lines.append(f"決策：**{comparison['decision']}**")
    lines.append("")
    return "\n".join(lines)
