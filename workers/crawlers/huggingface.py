"""
workers/crawlers/huggingface.py — 非同步 Hugging Face Hub 爬蟲（發布訊號）。

偵測「模型上架」事件：對每個追蹤的 org 查最新建立的 repo（createdAt desc）。
完全免費、**不需要 API key**。輸出餵 api.services.releases.upsert_release_events。

訊號強度（見研究）：Llama / DeepSeek 強；Grok 稀疏；Google 需用 'gemma' 過濾；
GPT / Claude 幾乎無開源權重（近乎無訊號，但仍便宜地查一下以防意外上架）。
"""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Iterable
from datetime import UTC, datetime
from typing import Any

import httpx

from crawlers._http import http_retry
from crawlers.keywords import HF_ORG_TO_SLUG

__all__ = ["crawl_huggingface", "normalize_hf_model"]

logger = logging.getLogger(__name__)

HF_MODELS_URL = "https://huggingface.co/api/models"
_USER_AGENT = "pulse-crawler/0.1 (AI release monitor)"

retry_hf = http_retry()


def _parse_iso(value: str) -> datetime:
    """解析 HF 的 ISO8601（結尾 Z）為 tz-aware UTC。"""
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def normalize_hf_model(model: dict[str, Any], slug: str | None) -> dict:
    """把一筆 HF model 物件轉成 release event dict。純函式，可測。"""
    repo_id = model["id"]  # e.g. "meta-llama/Llama-3.3-70B-Instruct"
    author = repo_id.split("/", 1)[0]
    return {
        "source": "huggingface",
        "external_id": repo_id,  # repo id 即天然去重鍵
        "model": slug,  # 由 org 決定的模型 slug（可能 None）
        "title": repo_id.split("/", 1)[-1],
        "url": f"https://huggingface.co/{repo_id}",
        "repo": repo_id,
        "kind": "model_upload",
        "version": None,
        "published_at": _parse_iso(model["createdAt"]),
        "extra": {
            "author": author,
            "downloads": model.get("downloads", 0),
            "likes": model.get("likes", 0),
            "pipeline_tag": model.get("pipeline_tag"),
            "tags": (model.get("tags") or [])[:20],
            "gated": model.get("gated", False),
        },
    }


@retry_hf
async def _fetch_org(client: httpx.AsyncClient, org: str, limit: int) -> list[dict]:
    """抓單一 org 最新建立的 model（含重試）。"""
    resp = await client.get(
        HF_MODELS_URL,
        params={
            "author": org,
            "sort": "createdAt",
            "direction": -1,
            "limit": limit,
            "full": "true",  # 取得 gated 等欄位
        },
    )
    resp.raise_for_status()
    return resp.json()


async def crawl_huggingface(
    orgs: Iterable[str] = tuple(HF_ORG_TO_SLUG),
    limit: int = 30,
) -> AsyncIterator[dict]:
    """
    逐 org 查最新模型，yield release event dict。

    - 不需 credential。
    - 單一 org 查詢失敗只記 log、跳過。
    - google org 很雜，只保留 repo id 含 'gemma' 的（Gemini 本身閉源）。

    無 high-water mark：每次都重抓各 org 最新 N 筆並 upsert（冪等）。因此
    fetched_at / updated_at 是「抓取時間」非「事件變動」訊號；F8 判斷「新發布」
    請一律用 published_at（= repo createdAt，新 repo 才會變）。
    """
    async with httpx.AsyncClient(timeout=20.0, headers={"User-Agent": _USER_AGENT}) as client:
        for org in orgs:
            slug = HF_ORG_TO_SLUG.get(org)
            try:
                models = await _fetch_org(client, org, limit)
            except httpx.HTTPError:
                logger.exception("HF 查詢失敗，跳過 org=%s", org)
                continue

            kept = 0
            for model in models:
                repo_id = model.get("id", "")
                # google org 充滿非 LLM repo → 只收 gemma
                if org == "google" and "gemma" not in repo_id.lower():
                    continue
                try:
                    row = normalize_hf_model(model, slug)
                except Exception:  # noqa: BLE001 — 單筆失敗不該丟掉整個 org
                    logger.exception("HF 正規化失敗，跳過 id=%s", repo_id)
                    continue
                kept += 1
                yield row
            logger.info("HF org=%s：取 %d 筆，保留 %d 筆", org, len(models), kept)
