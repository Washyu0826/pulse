"""標註工具測試 —— 分層抽樣、Cohen's κ、Krippendorff α、bootstrap CI、JSONL I/O 純函式。"""
from ml.annotation import (
    THEME_LABELS,
    GoldLabel,
    bootstrap_ci,
    cohen_kappa,
    krippendorff_alpha,
    labeled_ids,
    load_jsonl,
    parse_quality_key,
    parse_sentiment_key,
    parse_theme_key,
    save_jsonl,
    stratified_sample,
)


# ---- 按鍵解析 ----
def test_parse_keys():
    assert parse_sentiment_key("1") == "negative"
    assert parse_sentiment_key("3") == "positive"
    assert parse_sentiment_key("x") is None
    assert parse_quality_key("H") == "high"  # 大小寫無關
    assert parse_quality_key("z") is None


def test_parse_theme_keys():
    assert parse_theme_key("t") == "新工具"
    assert parse_theme_key("M") == "模型動態"  # 大小寫無關
    assert parse_theme_key("u") == "使用方法"
    assert parse_theme_key("r") == "風險限制"
    assert parse_theme_key("e") == "倫理法規"
    assert parse_theme_key("o") == "其他"
    assert parse_theme_key("x") is None
    # 主題鍵不可與略過/離開鍵衝突
    assert "s" not in set("tmureo") and "q" not in set("tmureo")


def test_theme_labels_and_goldlabel_roundtrip():
    assert THEME_LABELS == ("新工具", "模型動態", "使用方法", "風險限制", "倫理法規", "其他")
    rec = GoldLabel(
        post_id=1, source="threads", sentiment="positive", quality="high",
        text="t", annotated_at="2026-06-05T00:00:00Z", theme="模型動態",
    ).to_json()
    assert rec["theme"] == "模型動態"
    assert rec["note"] == ""  # 預設空


# ---- 分層抽樣 ----
def test_stratified_sample_is_deterministic_and_covers_strata():
    posts = (
        [{"id": i, "source": "threads"} for i in range(10)]
        + [{"id": 100 + i, "source": "hackernews"} for i in range(10)]
    )
    a = stratified_sample(posts, 6, seed=42)
    b = stratified_sample(posts, 6, seed=42)
    assert [p["id"] for p in a] == [p["id"] for p in b]  # 同 seed → 同結果
    assert len(a) == 6
    srcs = {p["source"] for p in a}
    assert srcs == {"threads", "hackernews"}  # 兩層都涵蓋（不 cherry-pick）


def test_stratified_sample_does_not_mutate_input():
    posts = [{"id": 1, "source": "x"}, {"id": 2, "source": "y"}]
    stratified_sample(posts, 2)
    assert [p["id"] for p in posts] == [1, 2]


def test_stratified_sample_edge_cases():
    assert stratified_sample([], 5) == []
    assert stratified_sample([{"id": 1, "source": "a"}], 0) == []


# ---- Cohen's κ ----
def test_cohen_kappa_perfect_and_degenerate():
    assert cohen_kappa(["a", "b", "c"], ["a", "b", "c"]) == 1.0
    # 兩組都壓同一標籤 → pe==1 退化情形視為完全一致
    assert cohen_kappa(["a", "a"], ["a", "a"]) == 1.0
    assert cohen_kappa([], []) == 1.0


def test_cohen_kappa_partial_agreement():
    # Coder1=[a,b,a], Coder2=[a,b,b] → κ=0.4（手算）
    k = cohen_kappa(["a", "b", "a"], ["a", "b", "b"])
    assert abs(k - 0.4) < 1e-9


def test_cohen_kappa_length_mismatch_raises():
    import pytest

    with pytest.raises(ValueError):
        cohen_kappa(["a"], ["a", "b"])


# ---- Krippendorff α ----
def test_krippendorff_perfect_agreement():
    units = [["pos", "pos"], ["neg", "neg"], ["neu", "neu"]]
    assert krippendorff_alpha(units) == 1.0


def test_krippendorff_single_label_is_one():
    # 全部標同一類 → 無從不一致，視為完全一致
    assert krippendorff_alpha([["pos", "pos"], ["pos", "pos"]]) == 1.0


def test_krippendorff_matches_known_value():
    # 與 test_cohen_kappa_partial_agreement 同資料：α≈0.4444（nominal）
    units = [["a", "a"], ["b", "b"], ["a", "b"]]
    a = krippendorff_alpha(units)
    assert abs(a - 0.4444444) < 1e-4


def test_krippendorff_skips_singletons_and_missing():
    # 單一標註的單位（缺值）不貢獻配對，不應讓函式爆掉
    units = [["pos", "pos"], ["neg"], ["neu", None]]
    assert krippendorff_alpha(units) == 1.0  # 唯一可配對的 pos,pos 完全一致


# ---- bootstrap CI ----
def test_bootstrap_ci_is_deterministic_and_brackets_point_estimate():
    pairs = [("a", "a")] * 9 + [("a", "b")]  # κ 高但非完美
    stat = lambda s: cohen_kappa([x for x, _ in s], [y for _, y in s])  # noqa: E731
    lo1, hi1 = bootstrap_ci(pairs, stat, n_boot=500, seed=7)
    lo2, hi2 = bootstrap_ci(pairs, stat, n_boot=500, seed=7)
    assert (lo1, hi1) == (lo2, hi2)  # 固定 seed → 可重現
    assert lo1 <= hi1


def test_bootstrap_ci_empty():
    assert bootstrap_ci([], lambda s: 0.0) == (0.0, 0.0)


# ---- JSONL round-trip ----
def test_jsonl_roundtrip_and_labeled_ids(tmp_path):
    recs = [
        {"post_id": 1, "source": "threads", "sentiment": "positive", "round": 1},
        {"post_id": 2, "source": "threads", "sentiment": "negative", "round": 1},
        {"post_id": 1, "source": "threads", "sentiment": "positive", "round": 2},
    ]
    p = tmp_path / "gold.jsonl"
    save_jsonl(p, recs)
    loaded = load_jsonl(p)
    assert loaded == recs
    assert labeled_ids(loaded, round=1) == {1, 2}
    assert labeled_ids(loaded, round=2) == {1}


def test_load_jsonl_missing_file_returns_empty(tmp_path):
    assert load_jsonl(tmp_path / "nope.jsonl") == []
