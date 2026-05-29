"""GitHub Releases 爬蟲測試 —— 不需網路。"""
from datetime import UTC

import httpx
import pytest

from crawlers import github
from crawlers.github import normalize_gh_release


def _release(**ov):
    base = dict(
        node_id="RE_abc123",
        tag_name="v0.105.2",
        name="v0.105.2",
        html_url="https://github.com/anthropics/anthropic-sdk-python/releases/tag/v0.105.2",
        published_at="2026-05-29T10:00:00Z",
        created_at="2026-05-29T09:00:00Z",
        prerelease=False,
        draft=False,
        author={"login": "octocat"},
        body="release notes " * 100,  # 很長，應被截斷
    )
    base.update(ov)
    return base


def test_normalize_basic():
    row = normalize_gh_release("anthropics/anthropic-sdk-python", _release(), "claude")
    assert row["source"] == "github"
    assert row["external_id"] == "RE_abc123"
    assert row["model"] == "claude"
    assert row["repo"] == "anthropics/anthropic-sdk-python"
    assert row["kind"] == "github_release"
    assert row["version"] == "v0.105.2"
    assert row["extra"]["author"] == "octocat"
    assert len(row["extra"]["body_excerpt"]) <= 500  # body 截斷


def test_normalize_published_at_falls_back_to_created_at():
    row = normalize_gh_release("o/r", _release(published_at=None), "gpt")
    assert row["published_at"].tzinfo == UTC
    assert row["published_at"].hour == 9  # 用了 created_at


def test_normalize_external_id_fallback_without_node_id():
    row = normalize_gh_release("o/r", _release(node_id=None, tag_name="v1.2.3"), "gpt")
    assert row["external_id"] == "o/r@v1.2.3"


def test_normalize_prerelease_flag():
    row = normalize_gh_release("o/r", _release(prerelease=True), "llama")
    assert row["extra"]["prerelease"] is True


@pytest.mark.asyncio
async def test_crawl_skips_draft_and_isolates_failure(monkeypatch):
    async def fake(client, repo, per_page):
        if repo == "a/ok":
            return [_release(node_id="1"), _release(node_id="2", draft=True)]  # draft 應跳過
        if repo == "b/fail":
            raise httpx.ConnectError("boom")  # 該 repo 失敗，應被隔離
        return []

    monkeypatch.setattr(github, "_fetch_releases", fake)
    monkeypatch.setattr(github.asyncio, "sleep", _noop)  # 跳過禮貌 sleep
    rows = [
        r async for r in github.crawl_github(repos={"a/ok": "gpt", "b/fail": "claude"}, per_page=5)
    ]
    assert [r["external_id"] for r in rows] == ["1"]  # draft 與失敗 repo 都被排除


@pytest.mark.asyncio
async def test_crawl_excludes_prerelease_when_disabled(monkeypatch):
    async def fake(client, repo, per_page):
        return [_release(node_id="1", prerelease=True), _release(node_id="2", prerelease=False)]

    monkeypatch.setattr(github, "_fetch_releases", fake)
    monkeypatch.setattr(github.asyncio, "sleep", _noop)
    rows = [
        r async for r in github.crawl_github(
            repos={"a/r": "gpt"}, per_page=5, include_prerelease=False
        )
    ]
    assert [r["external_id"] for r in rows] == ["2"]


async def _noop(*_a, **_k):
    return None
