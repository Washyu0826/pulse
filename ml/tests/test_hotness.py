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
    rank_balanced,
    source_baselines,
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
# source_baselines（各來源互動中位數基準）
# ---------------------------------------------------------------------------
def test_source_baselines_median_per_source():
    posts = [
        {"source": "hn", "likes": 10},
        {"source": "hn", "likes": 20},
        {"source": "hn", "likes": 30},
        {"source": "threads", "likes": 4},
    ]
    bl = source_baselines(posts)
    assert bl["hn"] == 20  # 中位數
    assert bl["threads"] == 4


def test_source_baselines_excludes_zero_engagement():
    """互動 == 0 的貼文不計入；全 0 的來源不給基準。"""
    posts = [
        {"source": "a", "likes": 0},
        {"source": "a", "likes": 0},
        {"source": "b", "likes": 5},
    ]
    bl = source_baselines(posts)
    assert "a" not in bl  # 全 0 → 無基準
    assert bl["b"] == 5


def test_source_baselines_missing_source_is_unknown():
    bl = source_baselines([{"likes": 8}])
    assert bl == {"unknown": 8}


def test_source_baselines_custom_source_key():
    bl = source_baselines([{"src": "x", "likes": 6}], source_key="src")
    assert bl == {"x": 6}


def test_source_baselines_empty():
    assert source_baselines([]) == {}


# ---------------------------------------------------------------------------
# rank_balanced（per-source 正規化 + round-robin 平衡）
# ---------------------------------------------------------------------------
def _p(id, source, score):
    return {"id": id, "source": source, "score": score}


def test_rank_balanced_round_robin_across_sources():
    """高量級來源不洗版：低量級主力來源也穩定露出。"""
    posts = [
        _p(1, "hn", 1000),
        _p(2, "hn", 800),
        _p(3, "hn", 600),
        _p(4, "threads", 10),
        _p(5, "threads", 5),
    ]
    out = rank_balanced(posts, k=2)
    srcs = {p["source"] for p in out}
    assert srcs == {"hn", "threads"}  # 兩來源各露出，而非兩篇全 HN


def test_rank_balanced_first_round_picks_hottest_per_source():
    """第一輪各來源出最熱的一篇，來源序依該篇熱度由高到低。"""
    posts = [
        _p(1, "hn", 1000),
        _p(2, "hn", 800),
        _p(3, "threads", 10),
    ]
    out = rank_balanced(posts, k=2)
    # HN 最熱 → 先 HN 最熱(id=1)，再 threads 最熱(id=3)；不是兩篇 HN。
    assert [p["id"] for p in out] == [1, 3]


def test_rank_balanced_k_zero_or_negative():
    assert rank_balanced([_p(1, "hn", 5)], k=0) == []
    assert rank_balanced([_p(1, "hn", 5)], k=-3) == []


def test_rank_balanced_k_larger_than_pool_returns_all():
    posts = [_p(1, "hn", 5), _p(2, "threads", 3)]
    out = rank_balanced(posts, k=10)
    assert {p["id"] for p in out} == {1, 2}


def test_rank_balanced_deterministic_tiebreak_by_id():
    """同來源同熱度 → 以 id 決勝（穩定可重現）。排序鍵 (hotness, id) + reverse → 大 id 先。"""
    posts = [_p(1, "hn", 10), _p(2, "hn", 10)]
    out = rank_balanced(posts, k=2)
    assert [p["id"] for p in out] == [2, 1]  # 同熱度，較大 id 先（與 newsletter 既有行為一致）
    # 與輸入順序無關（確定性）
    assert [p["id"] for p in rank_balanced([_p(2, "hn", 10), _p(1, "hn", 10)], k=2)] == [2, 1]


def test_rank_balanced_within_source_sorted_by_hotness():
    posts = [_p(1, "hn", 5), _p(2, "hn", 500), _p(3, "hn", 50)]
    out = rank_balanced(posts, k=3)
    assert [p["id"] for p in out] == [2, 3, 1]  # 單來源 → 純熱度降序


def test_rank_balanced_accepts_external_baselines():
    """傳入預算 baselines 時應採用之（共用同一組基準）。"""
    posts = [_p(1, "hn", 100), _p(2, "threads", 100)]
    bl = source_baselines(posts)
    out = rank_balanced(posts, k=2, baselines=bl)
    assert {p["id"] for p in out} == {1, 2}


def test_rank_balanced_custom_keys():
    posts = [
        {"pid": 1, "src": "a", "likes": 100},
        {"pid": 2, "src": "b", "likes": 5},
    ]
    out = rank_balanced(posts, k=2, source_key="src", id_key="pid")
    assert {p["pid"] for p in out} == {1, 2}


def test_rank_balanced_pure_no_mutation():
    posts = [_p(1, "hn", 10), _p(2, "threads", 5)]
    snapshot = [dict(p) for p in posts]
    rank_balanced(posts, k=2)
    assert posts == snapshot


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
