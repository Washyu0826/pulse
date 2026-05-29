"""
workers/crawlers/github.py — 非同步 GitHub Releases 爬蟲（發布訊號）。

偵測「版本釋出」事件：對每個追蹤的 repo 抓最新 releases。
**不需要 token**（未授權 60 req/hr）；若設了 GITHUB_TOKEN 則用之（5000/hr）。
輸出餵 api.services.releases.upsert_release_events。

訊號（見研究）：Llama / DeepSeek 模型 repo；GPT / Claude 多為 SDK proxy 訊號；
Grok 幾乎無 GitHub release。draft 跳過、prerelease 保留並在 extra 標記。
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Mapping
from datetime import UTC, datetime
from typing import Any

import httpx

from crawlers._http import http_retry
from crawlers.keywords import GITHUB_REPO_TO_SLUG

__all__ = ["crawl_github", "normalize_gh_release"]

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
_BASE_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "pulse-crawler/0.1",  # GitHub 強制要 User-Agent，否則 403
}

retry_gh = http_retry()


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def normalize_gh_release(repo: str, release: dict[str, Any], slug: str | None) -> dict:
    """把一筆 GitHub release 物件轉成 release event dict。純函式，可測。"""
    # published_at 在 draft / 剛建立時可能為 null → 退回 created_at
    published = release.get("published_at") or release.get("created_at")
    body = release.get("body") or ""
    return {
        "source": "github",
        "external_id": release.get("node_id") or f"{repo}@{release.get('tag_name')}",
        "model": slug,
        "title": release.get("name") or release.get("tag_name") or "",
        "url": release["html_url"],
        "repo": repo,
        "kind": "github_release",
        "version": release.get("tag_name"),
        "published_at": _parse_iso(published) if published else None,
        "extra": {
            "prerelease": release.get("prerelease", False),
            "draft": release.get("draft", False),
            "author": (release.get("author") or {}).get("login"),
            "body_excerpt": body[:500],
        },
    }


@retry_gh
async def _fetch_releases(client: httpx.AsyncClient, repo: str, per_page: int) -> list[dict]:
    """抓單一 repo 的最新 releases（含重試）。repo 無 releases → 回 []，repo 不存在(404) → 回 []。"""
    resp = await client.get(
        f"{GITHUB_API}/repos/{repo}/releases", params={"per_page": per_page}
    )
    if resp.status_code == 404:
        logger.warning("GitHub repo 不存在或無權限：%s", repo)
        return []
    resp.raise_for_status()
    return resp.json()


async def crawl_github(
    repos: Mapping[str, str] = GITHUB_REPO_TO_SLUG,
    per_page: int = 10,
    token: str | None = None,
    include_prerelease: bool = True,
) -> AsyncIterator[dict]:
    """
    逐 repo 抓最新 releases，yield release event dict。

    - 未授權 60 req/hr → repo 之間「循序」抓並小睡，避免觸發 secondary limit。
    - 單一 repo 失敗只記 log、跳過。
    - draft 一律跳過；prerelease 預設保留（extra 標記）。

    請求預算：每個 repo 1 次請求（不送 conditional request，故每次都計入額度）。
    目前 ~9 個 repo = ~9 req/run，未授權上限 60/hr → **每小時排程安全；勿低於 ~10 分鐘
    一次跑（會超額）**。要更密集就設 GITHUB_TOKEN（5000/hr）。Week 7 Airflow 排程須遵守。
    """
    headers = dict(_BASE_HEADERS)
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async with httpx.AsyncClient(timeout=20.0, headers=headers) as client:
        for repo, slug in repos.items():
            try:
                releases = await _fetch_releases(client, repo, per_page)
            except httpx.HTTPError:
                logger.exception("GitHub 查詢失敗，跳過 repo=%s", repo)
                continue

            kept = 0
            for release in releases:
                if release.get("draft"):
                    continue
                if not include_prerelease and release.get("prerelease"):
                    continue
                try:
                    row = normalize_gh_release(repo, release, slug)
                except Exception:  # noqa: BLE001 — 單筆失敗不該丟掉整個 repo
                    logger.exception("GitHub 正規化失敗，跳過 repo=%s", repo)
                    continue
                kept += 1
                yield row
            logger.info("GitHub repo=%s：取 %d 筆，保留 %d 筆", repo, len(releases), kept)
            await asyncio.sleep(0.5)  # 循序 + 禮貌間隔（GitHub 要求非並發）
