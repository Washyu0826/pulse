"""Threads 爬蟲純函式測試 —— 不需瀏覽器 / 網路。"""
from datetime import UTC, datetime

from crawlers.threads import normalize_thread_post


def _raw(**ov):
    base = dict(
        id="threads_abc123",
        text="Claude is way better than GPT for refactoring",
        author="someuser",
        url="https://www.threads.net/@someuser/post/abc123",
        likes=42,
        replies=7,
        posted_at=datetime(2026, 5, 20, tzinfo=UTC),
    )
    base.update(ov)
    return base


def test_normalize_basic():
    row = normalize_thread_post(_raw())
    assert row["source"] == "threads"
    assert row["external_id"] == "threads_abc123"
    assert row["author"] == "someuser"
    assert row["score"] == 42
    assert row["num_comments"] == 7
    assert sorted(row["models"]) == ["claude", "gpt"]
    assert row["title"] == "Claude is way better than GPT for refactoring"  # <120 → 全文當標題


def test_normalize_truncates_long_title():
    long_text = "Claude " * 50
    row = normalize_thread_post(_raw(text=long_text))
    assert len(row["title"]) == 120
    assert row["content"] == long_text.strip()


def test_normalize_empty_text_gets_placeholder_title():
    row = normalize_thread_post(_raw(text=""))
    assert row["title"] == "(Threads 貼文)"
    assert row["models"] == []


def test_normalize_missing_id_is_none():
    row = normalize_thread_post(_raw(id=None))
    assert row["external_id"] is None  # upsert 必填防護會略過


def test_normalize_bad_posted_at_becomes_none():
    row = normalize_thread_post(_raw(posted_at="not-a-datetime"))
    assert row["posted_at"] is None


def test_normalize_null_counts_default_zero():
    row = normalize_thread_post(_raw(likes=None, replies=None))
    assert row["score"] == 0 and row["num_comments"] == 0
