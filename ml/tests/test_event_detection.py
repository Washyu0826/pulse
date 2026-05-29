"""事件偵測核心演算法測試 —— 純函式、無 DB / 網路。"""
from datetime import date, timedelta

from ml.event_detection import (
    daily_counts,
    detect_spikes,
    fill_daily_gaps,
    group_launches,
)

_D0 = date(2026, 1, 1)


def _series(counts: list[int]) -> list[tuple[date, int]]:
    return [(_D0 + timedelta(days=i), c) for i, c in enumerate(counts)]


# ---- daily_counts / fill_daily_gaps ----

def test_daily_counts():
    d = _D0
    assert daily_counts([d, d, d + timedelta(days=1)]) == {d: 2, d + timedelta(days=1): 1}


def test_fill_daily_gaps_inserts_zeros():
    sparse = {_D0: 1, _D0 + timedelta(days=2): 3}
    assert fill_daily_gaps(sparse) == [
        (_D0, 1),
        (_D0 + timedelta(days=1), 0),  # 缺的日子補 0
        (_D0 + timedelta(days=2), 3),
    ]


def test_fill_daily_gaps_empty():
    assert fill_daily_gaps({}) == []


# ---- detect_spikes ----

def test_detect_basic_spike():
    counts = [1, 0, 1, 0, 2, 1, 0, 1, 0, 1, 1, 0, 1, 0, 12]  # 14 平日 + 突增 12
    spikes = detect_spikes(_series(counts))
    assert len(spikes) == 1
    assert spikes[0].count == 12
    assert spikes[0].day == _D0 + timedelta(days=14)


def test_min_count_gate_blocks_small_numbers():
    """0,0,...,2 不算事件（低於 min_count），也避免除以零。"""
    counts = [0] * 10 + [2]
    assert detect_spikes(_series(counts)) == []


def test_all_zero_baseline_then_spike():
    """全 0 baseline → MAD=0 用 floor，明顯突增仍偵測得到。"""
    counts = [0] * 10 + [8]
    spikes = detect_spikes(_series(counts))
    assert len(spikes) == 1
    assert spikes[0].count == 8
    assert spikes[0].severity > 0


def test_robust_to_prior_spike_masking():
    """baseline 含過去的大突增（20），不應遮蔽後來的突增（median/MAD 抗離群）。"""
    counts = [1, 0, 2, 20, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 18]
    spikes = detect_spikes(_series(counts))
    assert any(s.count == 18 for s in spikes)


def test_warmup_period_no_events():
    """baseline 不足 min_baseline 天 → 不發事件，即使數字大。"""
    assert detect_spikes(_series([10, 10])) == []


def test_steady_high_not_flagged():
    """穩定的高量（非突增）不該被標記。"""
    spikes = detect_spikes(_series([10] * 20))
    assert spikes == []


def test_down_spike_not_flagged():
    """突然變低（x < median）不該被當成事件。"""
    assert detect_spikes(_series([10] * 14 + [0])) == []


def test_severity_is_capped():
    """全 0 baseline + 巨大突增 → severity 封頂 10，但 modified_z 遠大於 10。"""
    spikes = detect_spikes(_series([0] * 14 + [100]))
    assert len(spikes) == 1
    assert spikes[0].severity == 10.0
    assert spikes[0].modified_z > 10.0


def test_window_must_be_ge_min_baseline():
    import pytest
    with pytest.raises(ValueError):
        detect_spikes(_series([1, 2, 3]), window=3, min_baseline=5)


# ---- group_launches ----

def test_group_launches_by_model_and_day():
    d = _D0
    releases = [
        {"model": "gpt", "day": d, "title": "a"},
        {"model": "gpt", "day": d, "title": "b"},
        {"model": "claude", "day": d, "title": "c"},
    ]
    launches = {(lc.model_slug, lc.count) for lc in group_launches(releases)}
    assert ("gpt", 2) in launches
    assert ("claude", 1) in launches


def test_group_launches_handles_none_model():
    out = group_launches([{"model": None, "day": _D0, "title": "x"}])
    assert out[0].model_slug is None
    assert out[0].count == 1


def test_group_launches_collects_kinds():
    d = _D0
    out = group_launches([
        {"model": "llama", "day": d, "title": "a", "kind": "model_upload"},
        {"model": "llama", "day": d, "title": "b", "kind": "github_release"},
    ])
    assert out[0].kinds == ["github_release", "model_upload"]  # sorted, deduped
