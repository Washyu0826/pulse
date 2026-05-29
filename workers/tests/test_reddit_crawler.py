"""
Reddit 爬蟲純函式測試 — 不需要網路 / Reddit API。

涵蓋 match_models（關鍵字比對）與 normalize_submission（欄位正規化、邊界）。
"""
from datetime import timezone
from types import SimpleNamespace

import pytest

from crawlers.reddit import match_models, normalize_submission


# ---------- match_models ----------

@pytest.mark.parametrize(
    "text,expected",
    [
        ("Claude is great for coding", ["claude"]),
        ("Comparing GPT-4 and Claude", ["gpt", "claude"]),
        ("anthropic released something", ["claude"]),
        ("I love DeepSeek and llama", ["llama", "deepseek"]),
        ("just a random post about cats", []),
    ],
)
def test_match_models(text, expected):
    assert sorted(match_models(text)) == sorted(expected)


def test_match_models_word_boundary():
    """詞界避免誤判：grokking 不該命中 grok。"""
    assert "grok" not in match_models("I am grokking the concept")


def test_match_models_case_insensitive():
    assert match_models("CLAUDE and GpT") == match_models("claude and gpt")


# ---------- normalize_submission ----------

def _fake_submission(**overrides):
    base = dict(
        id="abc123",
        title="Claude vs GPT",
        selftext="Which is better for coding?",
        author=SimpleNamespace(name="alice"),
        subreddit=SimpleNamespace(display_name="ClaudeAI"),
        url="https://example.com",
        permalink="/r/ClaudeAI/comments/abc123/x/",
        link_flair_text="Discussion",
        over_18=False,
        score=42,
        num_comments=7,
        created_utc=1_700_000_000.0,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_normalize_basic_fields():
    row = normalize_submission(_fake_submission())
    assert row["source"] == "reddit"
    assert row["external_id"] == "abc123"
    assert row["author"] == "alice"
    assert row["subreddit"] == "ClaudeAI"
    assert row["permalink"].startswith("https://www.reddit.com/r/ClaudeAI")
    assert row["score"] == 42
    assert row["quality_score"] is None  # 由 DQC 之後填
    assert sorted(row["models"]) == ["claude", "gpt"]


def test_normalize_deleted_author_is_none():
    """帳號被刪 → author=None，不可 crash。"""
    row = normalize_submission(_fake_submission(author=None))
    assert row["author"] is None


def test_normalize_posted_at_is_utc_aware():
    row = normalize_submission(_fake_submission())
    assert row["posted_at"].tzinfo == timezone.utc


def test_normalize_empty_selftext():
    row = normalize_submission(_fake_submission(selftext=None))
    assert row["content"] == ""
