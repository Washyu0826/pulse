"""Hugging Face 爬蟲測試 —— 不需網路。"""
from datetime import UTC

import pytest

from crawlers import huggingface
from crawlers.huggingface import normalize_hf_model


def _model(**ov):
    base = dict(
        id="meta-llama/Llama-3.3-70B-Instruct",
        createdAt="2025-04-28T07:16:35.000Z",
        downloads=1234,
        likes=56,
        pipeline_tag="text-generation",
        tags=["llama", "text-generation"],
        gated=False,
    )
    base.update(ov)
    return base


def test_normalize_basic():
    row = normalize_hf_model(_model(), "llama")
    assert row["source"] == "huggingface"
    assert row["external_id"] == "meta-llama/Llama-3.3-70B-Instruct"
    assert row["model"] == "llama"
    assert row["title"] == "Llama-3.3-70B-Instruct"
    assert row["url"] == "https://huggingface.co/meta-llama/Llama-3.3-70B-Instruct"
    assert row["kind"] == "model_upload"
    assert row["version"] is None
    assert row["extra"]["author"] == "meta-llama"
    assert row["extra"]["downloads"] == 1234


def test_normalize_created_at_utc():
    row = normalize_hf_model(_model(), "llama")
    assert row["published_at"].tzinfo == UTC


def test_normalize_missing_optional_fields():
    row = normalize_hf_model(_model(pipeline_tag=None, tags=None), "deepseek")
    assert row["extra"]["pipeline_tag"] is None
    assert row["extra"]["tags"] == []


@pytest.mark.asyncio
async def test_crawl_org_failure_isolation(monkeypatch):
    import httpx

    async def fake(client, org, limit):
        if org == "meta-llama":
            return [_model(id="meta-llama/A"), _model(id="meta-llama/B")]
        if org == "deepseek-ai":
            raise httpx.ConnectError("boom")  # 該 org 失敗，應被隔離
        return []

    monkeypatch.setattr(huggingface, "_fetch_org", fake)
    rows = [
        r async for r in huggingface.crawl_huggingface(orgs=["meta-llama", "deepseek-ai"], limit=5)
    ]
    assert sorted(r["external_id"] for r in rows) == ["meta-llama/A", "meta-llama/B"]


@pytest.mark.asyncio
async def test_crawl_google_gemma_filter(monkeypatch):
    """google org 只保留 id 含 gemma 的 repo。"""

    async def fake(client, org, limit):
        return [_model(id="google/gemma-2-9b"), _model(id="google/vit-base-patch16")]

    monkeypatch.setattr(huggingface, "_fetch_org", fake)
    rows = [r async for r in huggingface.crawl_huggingface(orgs=["google"], limit=5)]
    assert [r["external_id"] for r in rows] == ["google/gemma-2-9b"]
    assert rows[0]["model"] == "gemini"  # google → gemini slug
