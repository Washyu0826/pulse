"""跨來源去重純函式測試 —— 不需 DB / 網路。"""
from datetime import UTC, datetime

from ml.dedup import (
    build_clusters,
    canonicalize_url,
    hamming,
    jaccard,
    normalize_title,
    reconcile_dedup_flags,
    select_canonical,
    simhash64,
    title_tokens,
)


# ---- canonicalize_url ----
def test_canonicalize_strips_tracking_and_www_and_fragment():
    a = canonicalize_url("https://www.Example.com/Post/?utm_source=hn&id=5#top")
    b = canonicalize_url("http://example.com/Post?id=5")
    assert a == b == "example.com/Post?id=5"


def test_canonicalize_none_for_text_and_junk():
    assert canonicalize_url(None) is None
    assert canonicalize_url("") is None
    assert canonicalize_url("mailto:x@y.com") is None
    assert canonicalize_url("javascript:void(0)") is None


def test_canonicalize_query_order_independent():
    assert canonicalize_url("http://x.com/a?b=2&a=1") == canonicalize_url("http://x.com/a?a=1&b=2")


# ---- normalize_title ----
def test_normalize_strips_show_hn_and_brackets():
    assert normalize_title("Show HN: My Cool Tool [pdf]") == "my cool tool"
    assert normalize_title("Ask HN: How to use Claude?") == "how to use claude"


# ---- simhash / jaccard ----
def test_simhash_identical_titles_zero_hamming():
    t = title_tokens("Claude 3.5 beats GPT-4 on coding benchmarks")
    assert hamming(simhash64(t), simhash64(t)) == 0


def test_jaccard_bounds():
    a = title_tokens("the quick brown fox")
    assert jaccard(a, a) == 1.0
    assert jaccard(a, frozenset()) == 0.0


# ---- build_clusters ----
def _p(pid, **ov):
    base = dict(id=pid, source="hackernews", url=None, title=f"title {pid}",
                posted_at=datetime(2026, 5, 1, tzinfo=UTC), score=0, num_comments=0)
    base.update(ov)
    return base


def test_cluster_by_identical_url_across_sources():
    posts = [
        _p(1, source="hackernews", url="https://blog.com/post?utm_source=hn"),
        _p(2, source="lobsters", url="http://www.blog.com/post"),
        _p(3, source="devto", url="https://other.com/x"),
    ]
    clusters = build_clusters(posts)
    assert len(clusters) == 1
    ids = {p["id"] for p in clusters[0]}
    assert ids == {1, 2}  # 3 不同網址、不合併


def test_cluster_by_similar_title():
    posts = [
        _p(1, url=None, title="DeepSeek V3 released with impressive coding benchmarks today"),
        _p(2, url=None, title="DeepSeek V3 released with impressive coding benchmarks today!!"),
        _p(3, url=None, title="Completely unrelated post about rust async runtimes"),
    ]
    clusters = build_clusters(posts)
    assert len(clusters) == 1
    assert {p["id"] for p in clusters[0]} == {1, 2}


def test_short_generic_titles_not_clustered():
    posts = [_p(1, url=None, title="GPT vs Claude"), _p(2, url=None, title="GPT vs Gemini")]
    assert build_clusters(posts) == []


# ---- select_canonical ----
def test_canonical_is_earliest_posted():
    cluster = [
        _p(1, posted_at=datetime(2026, 5, 3, tzinfo=UTC), score=100),
        _p(2, posted_at=datetime(2026, 5, 1, tzinfo=UTC), score=1),  # 最早 → canonical
        _p(3, posted_at=datetime(2026, 5, 2, tzinfo=UTC), score=50),
    ]
    assert select_canonical(cluster) == 2


def test_canonical_tiebreak_engagement_then_id():
    ts = datetime(2026, 5, 1, tzinfo=UTC)
    cluster = [_p(1, posted_at=ts, score=10), _p(2, posted_at=ts, score=99), _p(3, posted_at=ts, score=99)]
    # 同時間 → 互動高（2,3 同 99）→ 最小 id = 2
    assert select_canonical(cluster) == 2


def test_canonical_tiebreak_source_rank():
    ts = datetime(2026, 5, 1, tzinfo=UTC)
    cluster = [
        _p(1, source="devto", posted_at=ts, score=5),
        _p(2, source="lobsters", posted_at=ts, score=5),  # 同時間同互動 → 來源優先序 lobsters 勝
        _p(3, source="hackernews", posted_at=ts, score=5),
    ]
    assert select_canonical(cluster) == 2


def test_clusters_are_transitive_url_then_title():
    # 1~2 因相同 URL；2~3 因相似標題 → union-find 合成同一群
    posts = [
        _p(1, url="https://blog.com/x", title="DeepSeek V3 released with strong coding benchmarks"),
        _p(2, url="https://www.blog.com/x", title="completely different headline here about cats"),
        _p(3, url="https://other.com/y", title="completely different headline here about cats"),
    ]
    clusters = build_clusters(posts)
    assert len(clusters) == 1
    assert {p["id"] for p in clusters[0]} == {1, 2, 3}


# ---- reconcile_dedup_flags ----
def test_reconcile_adds_for_duplicate_and_is_idempotent():
    once = reconcile_dedup_flags(["LINK_HEAVY"], is_canonical=False, canonical_id=7)
    twice = reconcile_dedup_flags(once, is_canonical=False, canonical_id=7)
    assert once == twice
    assert "DUPLICATE" in once and "CANONICAL:7" in once and "LINK_HEAVY" in once


def test_reconcile_canonical_keeps_quality_flags_only():
    out = reconcile_dedup_flags(["DUPLICATE", "CANONICAL:7", "SEO"], is_canonical=True, canonical_id=None)
    assert out == ["SEO"]  # 去掉去重標記、保留品質 flag


def test_reconcile_removes_stale_dedup_tags():
    # 之前是 dup，現在不再屬於任何 cluster（canonical_id=None, is_canonical=False）→ 清掉
    out = reconcile_dedup_flags(["DUPLICATE", "CANONICAL:7"], is_canonical=False, canonical_id=None)
    assert out == []
