"""Dev.to 爬蟲測試 —— 不需網路。"""
from datetime import UTC

import httpx
import pytest

from crawlers import devto
from crawlers.devto import normalize_devto_article


def _article(**ov):
    base = dict(
        id=12345,
        title="How I use Claude and GPT-4 daily",
        description="A review of using Claude for coding",
        user={"username": "alice", "name": "Alice"},
        url="https://dev.to/alice/how-i-use-claude",
        published_at="2026-05-27T07:11:18Z",
        positive_reactions_count=42,
        comments_count=5,
        tag_list=["ai", "claude"],
    )
    base.update(ov)
    return base


def test_normalize_basic():
    row = normalize_devto_article(_article())
    assert row["source"] == "devto"
    assert row["external_id"] == "12345"  # int → str
    assert row["author"] == "alice"
    assert row["score"] == 42
    assert row["num_comments"] == 5
    assert row["posted_at"].tzinfo == UTC
    assert sorted(row["models"]) == ["claude", "gpt"]
    assert row["quality_score"] is None


def test_normalize_null_description_and_counts():
    row = normalize_devto_article(_article(description=None, positive_reactions_count=None, comments_count=None))
    assert row["content"] == ""
    assert row["score"] == 0
    assert row["num_comments"] == 0


def test_normalize_bad_published_at():
    row = normalize_devto_article(_article(published_at="not-a-date"))
    assert row["posted_at"] is None  # 之後被 upsert 略過


def test_normalize_missing_id_is_none():
    """缺 id → external_id 保留 None（不可變成字串 "None"）。"""
    row = normalize_devto_article(_article(id=None))
    assert row["external_id"] is None


@pytest.mark.asyncio
async def test_crawl_dedup_and_failure_isolation(monkeypatch):
    async def fake(client, tag, per_page, page=1):
        if tag == "ai":
            return [_article(id=1), _article(id=2)]
        if tag == "llm":
            raise httpx.ConnectError("boom")
        if tag == "claude":
            return [_article(id=2), _article(id=3)]  # id=2 與 ai 重複
        return []

    monkeypatch.setattr(devto, "_fetch_tag", fake)
    rows = [r async for r in devto.crawl_devto(tags=["ai", "llm", "claude"], per_page=10)]
    assert sorted(r["external_id"] for r in rows) == ["1", "2", "3"]


@pytest.mark.asyncio
async def test_crawl_keyword_only_filters(monkeypatch):
    async def fake(client, tag, per_page, page=1):
        return [_article(id=9, title="No-code marketing tips", description="")]

    monkeypatch.setattr(devto, "_fetch_tag", fake)
    rows = [r async for r in devto.crawl_devto(tags=["ai"], per_page=5)]
    assert rows == []


@pytest.mark.asyncio
async def test_crawl_since_early_stop(monkeypatch):
    """整頁都早於 since → 停止翻頁，且只保留 in-range 文章。"""
    from datetime import UTC, datetime

    since = datetime(2026, 4, 1, tzinfo=UTC)
    calls = []

    async def fake(client, tag, per_page, page=1):
        calls.append(page)
        if page == 1:
            return [_article(id=1, published_at="2026-05-01T00:00:00Z")]  # 在範圍內
        if page == 2:
            return [_article(id=2, published_at="2026-03-01T00:00:00Z")]  # 全早於 since
        return [_article(id=3, published_at="2026-05-15T00:00:00Z")]  # 不應被抓到

    monkeypatch.setattr(devto, "_fetch_tag", fake)
    rows = [
        r async for r in devto.crawl_devto(tags=["ai"], per_page=1, since=since, max_pages=5)
    ]
    assert calls == [1, 2]  # page2 全早於 since → 停，不抓 page3
    assert [r["external_id"] for r in rows] == ["1"]  # 只保留 in-range
