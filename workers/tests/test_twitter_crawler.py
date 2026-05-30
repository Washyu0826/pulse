"""X/Twitter 爬蟲純函式測試 —— 不需 twscrape / 網路 / cookie。"""
from datetime import UTC, datetime

from crawlers.twitter import normalize_tweet


def _raw(**ov):
    base = dict(
        id=1799999999999999999,
        id_str="1799999999999999999",
        rawContent="Switched from GPT to Claude for coding, way better at refactoring",
        url="https://x.com/someuser/status/1799999999999999999",
        date=datetime(2026, 5, 20, tzinfo=UTC),
        likeCount=42,
        replyCount=7,
        user={"username": "someuser", "displayname": "Some User"},
    )
    base.update(ov)
    return base


def test_normalize_basic():
    row = normalize_tweet(_raw())
    assert row["source"] == "twitter"
    assert row["external_id"] == "1799999999999999999"
    assert row["author"] == "someuser"
    assert row["score"] == 42
    assert row["num_comments"] == 7
    assert sorted(row["models"]) == ["claude", "gpt"]
    assert row["url"] == row["permalink"]
    assert row["quality_score"] is None


def test_normalize_short_text_is_full_title():
    row = normalize_tweet(_raw())
    assert row["title"] == row["content"]  # <120 → 全文當標題


def test_normalize_truncates_long_title():
    long_text = "Claude " * 50
    row = normalize_tweet(_raw(rawContent=long_text))
    assert len(row["title"]) == 120
    assert row["content"] == long_text.strip()


def test_normalize_empty_text_gets_placeholder_title():
    row = normalize_tweet(_raw(rawContent=""))
    assert row["title"] == "(tweet)"
    assert row["models"] == []


def test_normalize_id_str_fallback_to_int_id():
    row = normalize_tweet(_raw(id_str=None))
    assert row["external_id"] == "1799999999999999999"


def test_normalize_missing_id_is_none():
    row = normalize_tweet(_raw(id=None, id_str=None))
    assert row["external_id"] is None  # upsert 必填防護會略過


def test_normalize_bad_date_becomes_none():
    row = normalize_tweet(_raw(date="not-a-datetime"))
    assert row["posted_at"] is None


def test_normalize_null_counts_default_zero():
    row = normalize_tweet(_raw(likeCount=None, replyCount=None))
    assert row["score"] == 0 and row["num_comments"] == 0


def test_normalize_missing_user_author_none():
    row = normalize_tweet(_raw(user=None))
    assert row["author"] is None
