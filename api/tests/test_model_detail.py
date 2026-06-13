"""模型詳情服務整合測試 —— 真實 Postgres，非破壞性（只動 source='test_detail'）。"""
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from fastapi import HTTPException
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
from api.routers.models import model_detail as model_detail_route
from api.services.events import upsert_events
from api.services.model_detail import get_model_detail
from api.services.posts import upsert_posts
from api.services.releases import upsert_release_events

_SOURCE = "test_detail"
_SLUG = "test_detail_model"


def _post(external_id: str, **ov) -> dict:
    base = dict(
        source=_SOURCE,
        external_id=external_id,
        title="趨勢測試貼文",
        content="",
        author="x",
        subreddit=None,
        url="http://example.com/p",
        permalink=None,
        flair=None,
        over_18=False,
        score=10,
        num_comments=0,
        posted_at=datetime.now(UTC),
        models=[_SLUG],
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

    async def _cleanup():
        async with maker() as s:
            await s.execute(delete(Post).where(Post.source == _SOURCE))
            await s.execute(delete(ReleaseEvent).where(ReleaseEvent.external_id.like("test_detail%")))
            await s.execute(delete(Event).where(Event.dedup_key.like("test_detail%")))
            await s.execute(delete(Model).where(Model.slug == _SLUG))
            await s.commit()

    await _cleanup()
    async with maker() as s:
        await s.execute(
            pg_insert(Model)
            .values({"slug": _SLUG, "name": "Detail", "company": "X"})
            .on_conflict_do_nothing(index_elements=[Model.slug])
        )
        await s.commit()
        yield s
    await _cleanup()


async def test_unknown_slug_returns_none(session):
    assert await get_model_detail(session, "no_such_model_slug") is None


async def test_route_unknown_slug_raises_404(session):
    """router 層：查無模型 → HTTPException 404（鎖住 None → 404 的轉換）。"""
    with pytest.raises(HTTPException) as exc:
        await model_detail_route(slug="no_such_model_slug", trend_days=30, db=session)
    assert exc.value.status_code == 404


async def test_detail_shape_and_trend_window(session):
    detail = await get_model_detail(session, _SLUG, trend_days=14)
    assert detail is not None
    assert detail["slug"] == _SLUG
    # trend 補滿每一天（含端點）→ trend_days + 1 筆
    assert len(detail["trend"]) == 15
    assert {"date", "posts", "sentiment_index"} <= set(detail["trend"][0])
    for key in ("events", "top_discussions", "releases"):
        assert isinstance(detail[key], list)


async def test_detail_counts_and_top_discussions(session):
    await upsert_posts(session, [
        _post("d_recent", posted_at=datetime.now(UTC), score=99),
        _post("d_old", posted_at=datetime.now(UTC) - timedelta(days=3), score=5),
    ])
    detail = await get_model_detail(session, _SLUG, trend_days=14)
    assert detail["posts_total"] >= 2
    # 逐日量總和應 >= 2（兩篇都在 14 天窗口內）
    assert sum(p["posts"] for p in detail["trend"]) >= 2
    # 熱門討論依分數排序，高分在前
    assert detail["top_discussions"][0]["score"] == 99


async def test_detail_includes_events_and_releases(session):
    now = datetime.now(UTC)
    await upsert_release_events(session, [{
        "source": "github", "external_id": "test_detail_rel", "model": _SLUG,
        "title": "v9", "url": "http://x", "repo": "o/r", "kind": "github_release",
        "version": "v9", "published_at": now, "extra": {},
    }])
    await upsert_events(session, [{
        "dedup_key": "test_detail_spike", "event_type": "discussion_spike", "model": _SLUG,
        "title": "spike", "occurred_at": now, "score": 6.0, "extra": {},
    }])
    detail = await get_model_detail(session, _SLUG)
    assert any(e["event_type"] == "discussion_spike" for e in detail["events"])
    assert any(r["version"] == "v9" for r in detail["releases"])
