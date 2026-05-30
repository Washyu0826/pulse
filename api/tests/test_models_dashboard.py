"""模型看板服務整合測試 —— 真實 Postgres，非破壞性（只動 source='test_dash'）。"""
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import api.models  # noqa: F401
from api.config import settings
from api.database import Base
from api.models.event import Event
from api.models.models import Model
from api.models.posts import Post
from api.models.release import ReleaseEvent
from api.services.events import upsert_events
from api.services.models import get_model_dashboard
from api.services.posts import upsert_posts
from api.services.releases import upsert_release_events

_SOURCE = "test_dash"


def _post(external_id: str, model: str, **ov) -> dict:
    base = dict(
        source=_SOURCE,
        external_id=external_id,
        title="GPT 測試貼文",
        content="",
        author="x",
        subreddit=None,
        url=None,
        permalink=None,
        flair=None,
        over_18=False,
        score=0,
        num_comments=0,
        posted_at=datetime.now(UTC),
        models=[model],
        quality_score=None,
    )
    base.update(ov)
    return base


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(settings.database_url)
    try:
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as e:  # noqa: BLE001
        await eng.dispose()
        pytest.skip(f"無法連線資料庫，跳過：{e}")
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine):
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        await s.execute(
            pg_insert(Model)
            .values([{"slug": "gpt", "name": "GPT", "company": "OpenAI"},
                     {"slug": "claude", "name": "Claude", "company": "Anthropic"}])
            .on_conflict_do_nothing(index_elements=[Model.slug])
        )
        await s.commit()

    async def _cleanup():
        async with maker() as s:
            await s.execute(delete(Post).where(Post.source == _SOURCE))
            await s.execute(delete(ReleaseEvent).where(ReleaseEvent.external_id.like("test_dash%")))
            await s.execute(delete(Event).where(Event.dedup_key.like("test_dash%")))
            await s.execute(delete(Model).where(Model.slug.like("test_dash%")))
            await s.commit()

    await _cleanup()
    async with maker() as s:
        yield s
    await _cleanup()


async def test_dashboard_shape(session):
    """每個模型一筆、欄位齊全、型別正確。"""
    dash = await get_model_dashboard(session)
    by_slug = {d["slug"]: d for d in dash}
    assert {"gpt", "claude"} <= set(by_slug)
    gpt = by_slug["gpt"]
    assert set(gpt) == {
        "slug", "name", "company", "role", "posts_total",
        "posts_recent", "releases_total", "latest_release_at", "spike_severity",
    }
    assert isinstance(gpt["posts_total"], int)
    assert isinstance(gpt["posts_recent"], int)


async def test_dashboard_counts_posts(session):
    """近期 + 舊貼文：posts_total 全算，posts_recent 只算近 7 天。"""
    before = {d["slug"]: d for d in await get_model_dashboard(session)}["gpt"]
    await upsert_posts(session, [
        _post("test_dash_new", "gpt", posted_at=datetime.now(UTC)),
        _post("test_dash_old", "gpt", posted_at=datetime.now(UTC) - timedelta(days=30)),
    ])
    after = {d["slug"]: d for d in await get_model_dashboard(session)}["gpt"]
    assert after["posts_total"] == before["posts_total"] + 2  # 兩篇都算總數
    assert after["posts_recent"] == before["posts_recent"] + 1  # 只有新的算近 7 天


async def _seed_model(session, slug: str):
    await session.execute(
        pg_insert(Model)
        .values({"slug": slug, "name": slug, "company": "X"})
        .on_conflict_do_nothing(index_elements=[Model.slug])
    )
    await session.commit()


async def test_zero_data_model_appears_with_zeros(session):
    """無任何資料的模型也要出現，且全為 0 / None（看板核心不變式）。"""
    await _seed_model(session, "test_dash_empty")
    dash = {d["slug"]: d for d in await get_model_dashboard(session)}
    assert "test_dash_empty" in dash
    e = dash["test_dash_empty"]
    assert e["posts_total"] == 0
    assert e["posts_recent"] == 0
    assert e["releases_total"] == 0
    assert e["latest_release_at"] is None
    assert e["spike_severity"] is None


async def test_releases_and_spike_aggregation(session):
    """release 與 spike 彙總正確（用孤立的測試模型，數值可精確斷言）。"""
    await _seed_model(session, "test_dash_full")
    now = datetime.now(UTC)
    await upsert_release_events(session, [{
        "source": "github", "external_id": "test_dash_rel", "model": "test_dash_full",
        "title": "v1", "url": "http://x", "repo": "o/r", "kind": "github_release",
        "version": "v1", "published_at": now, "extra": {},
    }])
    await upsert_events(session, [{
        "dedup_key": "test_dash_spike", "event_type": "discussion_spike", "model": "test_dash_full",
        "title": "spike", "occurred_at": now, "score": 7.5, "extra": {},
    }])
    full = {d["slug"]: d for d in await get_model_dashboard(session)}["test_dash_full"]
    assert full["releases_total"] == 1
    assert full["latest_release_at"] is not None
    assert full["spike_severity"] == 7.5
