"""
摘要品質 bake-off 純統計測試 —— 合成分數串，無模型、無 I/O。

驗證：system_summary 統計值；paired_delta_ci 固定 seed 下確定且 CI 對「明顯分開」的
兩系統會包住真實差且不含 0；win_rate 計數（含 margin / 平手）；decide 在 CI 跨 0 回
no_winner、在明顯分開時點名贏家；compare_systems 正確打包；format_markdown_report
含關鍵數字。
"""
import pytest

from ml.summary_eval import (
    compare_systems,
    decide,
    format_markdown_report,
    paired_delta_ci,
    system_summary,
    win_rate,
)


# ---------------------------------------------------------------- system_summary
def test_system_summary_basic_stats():
    s = system_summary([0.2, 0.4, 0.6, 0.8])
    assert s["mean"] == pytest.approx(0.5)
    assert s["median"] == pytest.approx(0.5)
    assert s["min"] == pytest.approx(0.2)
    assert s["max"] == pytest.approx(0.8)
    assert s["n"] == 4


def test_system_summary_empty():
    s = system_summary([])
    assert s == {"mean": 0.0, "median": 0.0, "min": 0.0, "max": 0.0, "n": 0}


def test_system_summary_single():
    s = system_summary([0.7])
    assert s["mean"] == pytest.approx(0.7)
    assert s["median"] == pytest.approx(0.7)
    assert s["min"] == s["max"] == pytest.approx(0.7)
    assert s["n"] == 1


# ---------------------------------------------------------------- paired_delta_ci
def test_paired_delta_ci_point_estimate():
    a = [0.9, 0.8, 0.95, 0.85]
    b = [0.5, 0.4, 0.55, 0.45]
    out = paired_delta_ci(a, b, n_boot=500, seed=0)
    # delta = mean(a) - mean(b)
    assert out["delta"] == pytest.approx((sum(a) / 4) - (sum(b) / 4))
    assert out["n"] == 4
    assert out["ci_low"] <= out["delta"] <= out["ci_high"]


def test_paired_delta_ci_deterministic_under_seed():
    a = [0.9, 0.7, 0.8, 0.6, 0.85]
    b = [0.4, 0.5, 0.3, 0.45, 0.35]
    out1 = paired_delta_ci(a, b, n_boot=300, seed=7)
    out2 = paired_delta_ci(a, b, n_boot=300, seed=7)
    assert out1 == out2


def test_paired_delta_ci_brackets_true_delta_when_separated():
    # A clearly above B by ~0.4 everywhere → CI should be well above 0.
    a = [0.90, 0.92, 0.88, 0.91, 0.89, 0.93, 0.87, 0.90]
    b = [0.50, 0.52, 0.48, 0.51, 0.49, 0.53, 0.47, 0.50]
    out = paired_delta_ci(a, b, n_boot=1000, seed=0)
    assert out["ci_low"] > 0.0  # 不含 0 → A 顯著較佳
    assert out["ci_low"] <= 0.40 <= out["ci_high"]  # 真實差 ~0.40 落在 CI 內


def test_paired_delta_ci_overlaps_zero_when_near_identical():
    a = [0.50, 0.52, 0.49, 0.51, 0.50, 0.48]
    b = [0.51, 0.49, 0.50, 0.52, 0.49, 0.50]
    out = paired_delta_ci(a, b, n_boot=1000, seed=0)
    assert out["ci_low"] <= 0.0 <= out["ci_high"]


def test_paired_delta_ci_length_mismatch_raises():
    with pytest.raises(ValueError):
        paired_delta_ci([0.1, 0.2], [0.1], n_boot=10)


def test_paired_delta_ci_empty():
    out = paired_delta_ci([], [], n_boot=10)
    assert out == {"delta": 0.0, "ci_low": 0.0, "ci_high": 0.0, "n": 0}


# ---------------------------------------------------------------- win_rate
def test_win_rate_counts():
    a = [0.9, 0.3, 0.5, 0.7]
    b = [0.5, 0.6, 0.5, 0.2]
    # event0 A>B, event1 B>A, event2 tie, event3 A>B
    wr = win_rate(a, b)
    assert wr["wins_a"] == 2
    assert wr["wins_b"] == 1
    assert wr["ties"] == 1
    assert wr["n"] == 4
    assert wr["win_rate_a"] == pytest.approx(0.5)


def test_win_rate_margin_turns_small_wins_into_ties():
    a = [0.55, 0.80]
    b = [0.50, 0.50]
    # margin 0.1: event0 diff 0.05 → tie; event1 diff 0.30 → A win
    wr = win_rate(a, b, margin=0.1)
    assert wr["wins_a"] == 1
    assert wr["wins_b"] == 0
    assert wr["ties"] == 1


def test_win_rate_exact_tie_with_margin_zero():
    wr = win_rate([0.5, 0.5], [0.5, 0.5])
    assert wr["ties"] == 2
    assert wr["wins_a"] == 0
    assert wr["wins_b"] == 0


def test_win_rate_length_mismatch_raises():
    with pytest.raises(ValueError):
        win_rate([0.1], [0.1, 0.2])


# ---------------------------------------------------------------- decide
def test_decide_no_winner_when_ci_straddles_zero():
    assert decide({"ci_low": -0.05, "ci_high": 0.08}) == "no_winner (CI overlaps 0)"


def test_decide_a_wins_when_ci_above_zero():
    msg = decide({"ci_low": 0.10, "ci_high": 0.30}, name_a="lora", name_b="qwen")
    assert "lora wins" in msg


def test_decide_b_wins_when_ci_below_zero():
    msg = decide({"ci_low": -0.30, "ci_high": -0.10}, name_a="lora", name_b="qwen")
    assert "qwen wins" in msg


def test_decide_boundary_zero_in_ci_is_no_winner():
    # CI touching 0 exactly counts as overlap → no winner.
    assert decide({"ci_low": 0.0, "ci_high": 0.2}) == "no_winner (CI overlaps 0)"
    assert decide({"ci_low": -0.2, "ci_high": 0.0}) == "no_winner (CI overlaps 0)"


# ---------------------------------------------------------------- compare_systems
def test_compare_systems_bundles_all_parts():
    a = [0.90, 0.92, 0.88, 0.91, 0.89, 0.93]
    b = [0.50, 0.52, 0.48, 0.51, 0.49, 0.53]
    cmp = compare_systems("lora", a, "qwen", b, n_boot=500, seed=0)
    assert cmp["name_a"] == "lora"
    assert cmp["name_b"] == "qwen"
    assert set(cmp["systems"]) == {"lora", "qwen"}
    assert cmp["systems"]["lora"]["n"] == 6
    assert cmp["delta_ci"]["delta"] > 0
    assert cmp["win_rate"]["wins_a"] == 6
    assert "lora wins" in cmp["decision"]


def test_compare_systems_no_winner_for_near_identical():
    a = [0.50, 0.51, 0.49, 0.50, 0.52, 0.48]
    b = [0.50, 0.49, 0.51, 0.50, 0.48, 0.52]
    cmp = compare_systems("sys_a", a, "sys_b", b, n_boot=500, seed=0)
    assert cmp["decision"] == "no_winner (CI overlaps 0)"


# ---------------------------------------------------------------- format_markdown_report
def test_format_markdown_report_contains_key_numbers():
    a = [0.90, 0.92, 0.88, 0.91]
    b = [0.50, 0.52, 0.48, 0.51]
    cmp = compare_systems("lora", a, "qwen", b, n_boot=300, seed=0)
    md = format_markdown_report(cmp)
    assert "Bake-off" in md
    assert "lora" in md and "qwen" in md
    # 系統均值出現
    assert f"{cmp['systems']['lora']['mean']:.4f}" in md
    # 決策出現
    assert cmp["decision"] in md
    # 勝率章節
    assert "勝率" in md


def test_format_markdown_report_extra_metrics_table():
    a = [0.9, 0.8]
    b = [0.5, 0.4]
    cmp = compare_systems("lora", a, "qwen", b, n_boot=100, seed=0)
    extra = {
        "frac_entailed": {"lora": 0.95, "qwen": 0.60},
        "source_coverage": {"lora": 0.80, "qwen": 0.50},
    }
    md = format_markdown_report(cmp, extra_metrics=extra)
    assert "frac_entailed" in md
    assert "source_coverage" in md
    assert "0.9500" in md  # lora frac_entailed
    assert "0.5000" in md  # qwen source_coverage


def test_format_markdown_report_decision_rule_text_present():
    cmp = compare_systems("a", [0.5, 0.5], "b", [0.5, 0.5], n_boot=50, seed=0)
    md = format_markdown_report(cmp)
    assert "一場勝利" in md  # 決策鐵則「跨 0 ≠ 一場勝利」


# ---------------------------------------------------------------- 額外邊界
def test_paired_delta_ci_single_pair_degenerate_ci():
    # n=1：唯一可重抽的就是該對 → CI 退化成點（low == high == delta）。
    out = paired_delta_ci([0.9], [0.4], n_boot=100, seed=0)
    assert out["n"] == 1
    assert out["delta"] == pytest.approx(0.5)
    assert out["ci_low"] == pytest.approx(0.5)
    assert out["ci_high"] == pytest.approx(0.5)


def test_paired_delta_ci_identical_scores_zero_delta():
    a = [0.5, 0.6, 0.7]
    out = paired_delta_ci(a, a, n_boot=200, seed=3)
    assert out["delta"] == pytest.approx(0.0)
    assert out["ci_low"] == pytest.approx(0.0)
    assert out["ci_high"] == pytest.approx(0.0)


def test_system_summary_negative_and_mixed_scores():
    # 模組吃任意 float（不限 [0,1]）；統計仍正確。
    s = system_summary([-0.2, 0.0, 0.4])
    assert s["min"] == pytest.approx(-0.2)
    assert s["max"] == pytest.approx(0.4)
    assert s["mean"] == pytest.approx(0.2 / 3)
    assert s["n"] == 3


def test_win_rate_empty_inputs():
    wr = win_rate([], [])
    assert wr == {"wins_a": 0, "wins_b": 0, "ties": 0, "n": 0, "win_rate_a": 0.0}


def test_win_rate_all_a_wins():
    wr = win_rate([0.9, 0.8, 0.7], [0.1, 0.2, 0.3])
    assert wr["wins_a"] == 3
    assert wr["win_rate_a"] == pytest.approx(1.0)


def test_win_rate_margin_exactly_equal_to_diff_is_tie():
    # diff 恰等於 margin → 不算贏（需 > margin），列為平手。
    wr = win_rate([0.6], [0.5], margin=0.1)
    assert wr["ties"] == 1
    assert wr["wins_a"] == 0


def test_decide_ci_low_zero_is_no_winner():
    # ci_low 恰為 0（含 0）→ 不宣稱勝利。
    assert decide({"ci_low": 0.0, "ci_high": 0.3}) == "no_winner (CI overlaps 0)"


def test_decide_ci_high_zero_is_no_winner():
    assert decide({"ci_low": -0.3, "ci_high": 0.0}) == "no_winner (CI overlaps 0)"


def test_decide_uses_custom_names_for_b_wins():
    msg = decide({"ci_low": -0.4, "ci_high": -0.2}, name_a="X", name_b="Y")
    assert "Y wins" in msg
    assert "X" not in msg.split("wins")[0]  # 贏家是 Y，不是 X


def test_compare_systems_length_mismatch_propagates_valueerror():
    with pytest.raises(ValueError):
        compare_systems("a", [0.1, 0.2], "b", [0.1], n_boot=10)


def test_format_markdown_report_no_extra_metrics_section_when_absent():
    cmp = compare_systems("a", [0.5, 0.6], "b", [0.4, 0.5], n_boot=50, seed=0)
    md = format_markdown_report(cmp)
    # 沒傳 extra_metrics → 不應出現「其他忠實度面向」章節。
    assert "其他忠實度面向" not in md
