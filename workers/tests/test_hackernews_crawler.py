"""
HackerNews 爬蟲純函式測試 —— 不需要網路。

涵蓋 normalize_hn_hit 的欄位對應與邊界（缺欄位、None、時間）。
"""
from datetime import UTC

import httpx
import pytest

from crawlers import hackernews
from crawlers.hackernews import normalize_hn_hit


def _hit(**overrides):
    base = dict(
        objectID="40123456",
        title="Claude 3.5 vs GPT-4o for coding",
        story_text="I compared them on real tasks",
        author="pg",
        url="https://example.com/post",
        points=128,
        num_comments=45,
        created_at_i=1_700_000_000,
    )
    base.update(overrides)
    return base


def test_normalize_basic_fields():
    row = normalize_hn_hit(_hit())
    assert row["source"] == "hackernews"
    assert row["external_id"] == "40123456"
    assert row["author"] == "pg"
    assert row["subreddit"] is None
    assert row["score"] == 128
    assert row["num_comments"] == 45
    assert row["permalink"] == "https://news.ycombinator.com/item?id=40123456"
    assert row["quality_score"] is None
    assert sorted(row["models"]) == ["claude", "gpt"]


def test_normalize_posted_at_is_utc():
    row = normalize_hn_hit(_hit())
    assert row["posted_at"].tzinfo == UTC


def test_normalize_missing_created_at_is_none():
    """created_at_i 缺失 → posted_at=None（之後被 upsert 略過）。"""
    row = normalize_hn_hit(_hit(created_at_i=None))
    assert row["posted_at"] is None


def test_normalize_none_points_and_text():
    """連結貼文沒有 story_text、points 可能缺 → 不可炸，給安全預設。"""
    row = normalize_hn_hit(_hit(story_text=None, points=None, num_comments=None))
    assert row["content"] == ""
    assert row["score"] == 0
    assert row["num_comments"] == 0


def test_normalize_objectid_coerced_to_str():
    row = normalize_hn_hit(_hit(objectID=40123456))  # Algolia 偶爾回 int
    assert row["external_id"] == "40123456"


def test_normalize_no_keyword_match():
    row = normalize_hn_hit(_hit(title="A post about gardening", story_text=""))
    assert row["models"] == []


def test_normalize_title_none_kept_none():
    """title 缺失 → 保留 None（之後被 upsert 必填防護略過），不可變成 ""。"""
    row = normalize_hn_hit(_hit(title=None, story_text="some claude discussion"))
    assert row["title"] is None
    assert row["models"] == ["claude"]  # blob 用 (title or '') 不會炸


# ---------- crawl_hackernews（async generator）----------

@pytest.mark.asyncio
async def test_crawl_dedup_and_term_failure_isolation(monkeypatch):
    """跨關鍵字去重 + 單一關鍵字失敗不影響其他關鍵字。"""

    async def fake_search(client, term, hits_per_page):
        if term == "claude":
            return [_hit(objectID="1"), _hit(objectID="2")]
        if term == "gpt":
            raise httpx.ConnectError("boom")  # 該 term 失敗，應被隔離
        if term == "gemini":
            # objectID=2 與 claude 重複（應去重），3 為新
            return [_hit(objectID="2", title="Claude and Gemini"), _hit(objectID="3", title="Gemini")]
        return []

    monkeypatch.setattr(hackernews, "_search_term", fake_search)
    rows = [
        r async for r in hackernews.crawl_hackernews(
            search_terms=["claude", "gpt", "gemini"], hits_per_page=10
        )
    ]
    assert sorted(r["external_id"] for r in rows) == ["1", "2", "3"]  # 去重後 3 筆，gpt 失敗被跳過


@pytest.mark.asyncio
async def test_crawl_keyword_only_filters(monkeypatch):
    """keyword_only=True 時，沒命中任何模型的 hit 要被濾掉。"""

    async def fake_search(client, term, hits_per_page):
        return [_hit(objectID="99", title="gardening tips", story_text="")]

    monkeypatch.setattr(hackernews, "_search_term", fake_search)
    rows = [r async for r in hackernews.crawl_hackernews(search_terms=["claude"], hits_per_page=5)]
    assert rows == []
