"""
共用熱度（hotness）純函式測試 —— 互動加權 / 時間衰減 / per-source 正規化 /
事件廣度 / storyline 聲量・velocity・狀態。

全部離線、無依賴、確定性（hotness.py 為純算術）。
"""
import math

from ml.hotness import (
    STATE_COOLING,
    STATE_FLAT,
    STATE_PEAK,
    STATE_RISING,
    breadth_factor,
    day_volume,
    engagement,
    event_hotness,
    post_hotness,
    storyline_hotness,
    storyline_state,
    velocity,
)


# ---------------------------------------------------------------------------
# engagement 互動加權
# ---------------------------------------------------------------------------
def test_engagement_weighting():
    """like + 2*comment + 3*repost。"""
    p = {"likes": 10, "comments": 5, "reposts": 2}
    assert engagement(p) == 10 + 2 * 5 + 3 * 2  # 26


def test_engagement_missing_fields_are_zero():
    assert engagement({}) == 0.0
    assert engagement({"likes": 4}) == 4.0


def test_engagement_field_aliases():
    """容忍不同來源欄位命名（score/num_comments/shares）。"""
    p = {"score": 100, "num_comments": 3, "shares": 1}
    assert engagement(p) == 100 + 2 * 3 + 3 * 1  # 109


def test_engagement_non_numeric_ignored():
    p = {"likes": "oops", "comments": 2}
    assert engagement(p) == 4.0  # likes 略過、comments 算到


# ---------------------------------------------------------------------------
# post_hotness 時間衰減 + 正規化
# ---------------------------------------------------------------------------
def test_post_hotness_decays_with_age():
    """同互動下，越舊熱度越低（單調遞減）。"""
    p = {"likes": 50}
    fresh = post_hotness(p, age_hours=0)
    mid = post_hotness(p, age_hours=24)
    old = post_hotness(p, age_hours=168)
    assert fresh > mid > old > 0


def test_post_hotness_more_engagement_hotter():
    """同年齡下，互動越多越熱。"""
    low = post_hotness({"likes": 1}, age_hours=10)
    high = post_hotness({"likes": 1000}, age_hours=10)
    assert high > low


def test_post_hotness_zero_engagement_still_positive():
    """零互動仍有微小新鮮度分（+1 in numerator），不為 0。"""
    assert post_hotness({}, age_hours=1) > 0


def test_post_hotness_negative_age_clamped():
    """未來時間/時鐘誤差 → age 夾 0，不爆值。"""
    a = post_hotness({"likes": 10}, age_hours=-5)
    b = post_hotness({"likes": 10}, age_hours=0)
    assert a == b


def test_post_hotness_source_baseline_normalizes():
    """給 baseline 時，高基準來源的同互動熱度較低（被正規化壓下）。"""
    p = {"likes": 100}
    low_base = post_hotness(p, age_hours=5, source_baseline=10)
    high_base = post_hotness(p, age_hours=5, source_baseline=100)
    assert low_base > high_base


def test_post_hotness_deterministic():
    p = {"likes": 33, "comments": 2}
    assert post_hotness(p, age_hours=12) == post_hotness(p, age_hours=12)


# ---------------------------------------------------------------------------
# 廣度 + 事件熱度
# ---------------------------------------------------------------------------
def test_breadth_factor():
    assert breadth_factor(1) == 1.0
    assert breadth_factor(0) == 1.0  # 夾為 1
    assert breadth_factor(2) == 1.0 + math.log(2)
    assert breadth_factor(3) > breadth_factor(2)


def test_event_hotness_sum_times_breadth():
    members = [1.0, 2.0, 3.0]
    single = event_hotness(members, num_sources=1)
    assert single == 6.0  # breadth=1
    multi = event_hotness(members, num_sources=3)
    assert multi == 6.0 * (1.0 + math.log(3))
    assert multi > single  # 跨來源更熱


def test_event_hotness_empty():
    assert event_hotness([], num_sources=2) == 0.0


# ---------------------------------------------------------------------------
# storyline 聲量 / velocity / 狀態
# ---------------------------------------------------------------------------
def test_day_volume_members_plus_log_interaction():
    assert day_volume(0, 0) == 0.0
    assert day_volume(3, 0) == 3.0
    assert day_volume(3, math.e - 1) == 3.0 + 1.0  # log1p(e-1)=1


def test_day_volume_stable_vs_pure_interaction():
    """十篇穩定討論的聲量勝過一篇爆文（聲量設計目的）。"""
    ten_posts = day_volume(10, 200)
    one_viral = day_volume(1, 5000)
    assert ten_posts > one_viral


def test_storyline_hotness_is_sum():
    assert storyline_hotness([1.0, 2.0, 3.0]) == 6.0
    assert storyline_hotness([]) == 0.0


def test_velocity():
    assert velocity([]) == 0.0
    assert velocity([5.0]) == 0.0
    assert velocity([2.0, 5.0]) == 3.0
    assert velocity([5.0, 2.0]) == -3.0


def test_state_single_day_is_rising():
    assert storyline_state([]) == STATE_RISING
    assert storyline_state([3.0]) == STATE_RISING


def test_state_peak_when_last_is_max_and_rising():
    """末日最高且上升 → 高峰。"""
    assert storyline_state([1.0, 3.0, 7.0]) == STATE_PEAK


def test_state_rising_when_last_below_earlier_peak_but_up():
    """末日上升但仍低於先前高峰 → 升溫（非高峰）。"""
    assert storyline_state([2.0, 10.0, 3.0, 5.0]) == STATE_RISING


def test_state_cooling_when_declining():
    assert storyline_state([10.0, 6.0, 2.0]) == STATE_COOLING


def test_state_flat_when_unchanged_and_not_peak():
    """末日與前日相等、且非全局高峰 → 持平。"""
    assert storyline_state([10.0, 5.0, 5.0]) == STATE_FLAT


def test_state_peak_on_plateau_at_top():
    """末日與前日相等、且就是全局最高 → 高峰（vel>=0 且 last>=peak）。"""
    assert storyline_state([3.0, 7.0, 7.0]) == STATE_PEAK
