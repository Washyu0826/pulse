"""Lobsters 爬蟲測試 —— 不需網路。"""
from datetime import UTC

import httpx
import pytest

from crawlers import lobsters
from crawlers.lobsters import normalize_lobsters_story


def _story(**ov):
    base = dict(
        short_id="abc123",
        title="DeepSeek vs Llama benchmarks",
        description_plain="My experience running both locally",
        submitter_user="bob",  # 目前 API 是字串
        created_at="2026-05-26T16:41:58.000-05:00",  # 帶 offset
        score=15,
        comment_count=8,
        url="https://example.com/article",
        short_id_url="https://lobste.rs/s/abc123",
        comments_url="https://lobste.rs/s/abc123/deepseek",
        tags=["ai", "ml"],
    )
    base.update(ov)
    return base


def test_normalize_basic():
    row = normalize_lobsters_story(_story())
    assert row["source"] == "lobsters"
    assert row["external_id"] == "abc123"
    assert row["author"] == "bob"
    assert row["score"] == 15
    assert row["num_comments"] == 8
    assert row["permalink"] == "https://lobste.rs/s/abc123/deepseek"
    assert sorted(row["models"]) == ["deepseek", "llama"]


def test_normalize_offset_converted_to_utc():
    row = normalize_lobsters_story(_story())
    assert row["posted_at"].tzinfo == UTC
    assert row["posted_at"].hour == 21  # 16:41 -05:00 → 21:41 UTC


def test_normalize_submitter_user_as_object():
    """跨版本：submitter_user 可能是物件。"""
    row = normalize_lobsters_story(_story(submitter_user={"username": "carol"}))
    assert row["author"] == "carol"


def test_normalize_empty_url_falls_back_to_short_id_url():
    row = normalize_lobsters_story(_story(url=""))
    assert row["url"] == "https://lobste.rs/s/abc123"


@pytest.mark.asyncio
async def test_crawl_dedup_across_pages(monkeypatch):
    async def fake(client, page):
        if page == 1:
            return [_story(short_id="1"), _story(short_id="2")]
        if page == 2:
            return [_story(short_id="2"), _story(short_id="3")]  # 2 重複
        return []

    monkeypatch.setattr(lobsters, "_fetch_page", fake)
    rows = [r async for r in lobsters.crawl_lobsters(pages=2)]
    assert sorted(r["external_id"] for r in rows) == ["1", "2", "3"]


@pytest.mark.asyncio
async def test_crawl_page_failure_isolation(monkeypatch):
    async def fake(client, page):
        if page == 1:
            raise httpx.ConnectError("boom")
        return [_story(short_id="9")]

    monkeypatch.setattr(lobsters, "_fetch_page", fake)
    rows = [r async for r in lobsters.crawl_lobsters(pages=2)]
    assert [r["external_id"] for r in rows] == ["9"]  # page1 失敗，page2 仍產出
