"""events 整合測試 —— 真實 Postgres，非破壞性（只動 dedup_key 前綴 test_ev:）。"""
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import api.models  # noqa: F401
from api.config import settings
from api.database import Base
from api.models.event import Event
from api.models.models import Model
from api.routers.events import list_events
from api.services.events import upsert_events

_PREFIX = "test_ev:"


def _ev(key: str, model: str | None, event_type="discussion_spike", **ov) -> dict:
    base = dict(
        dedup_key=_PREFIX + key,
        event_type=event_type,
        model=model,
        title="某事件",
        description="desc",
        score=3.5,
        occurred_at=datetime(2026, 3, 1, tzinfo=UTC),
        extra={"count": 10},
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
            await s.execute(delete(Event).where(Event.dedup_key.like(f"{_PREFIX}%")))
            await s.commit()

    await _cleanup()
    async with maker() as s:
        yield s
    await _cleanup()


async def _get(session, key):
    return await session.scalar(select(Event).where(Event.dedup_key == _PREFIX + key))


async def test_insert_and_resolve_model(session):
    stats = await upsert_events(session, [_ev("a", "gpt"), _ev("b", "claude", event_type="launch")])
    assert stats["upserted"] == 2
    gpt_id = await session.scalar(select(Model.id).where(Model.slug == "gpt"))
    ev = await _get(session, "a")
    assert ev.model_id == gpt_id


async def test_unknown_slug_model_id_none(session):
    await upsert_events(session, [_ev("c", "nonexistent")])
    ev = await _get(session, "c")
    assert ev.model_id is None


async def test_dedup_key_conflict_updates(session):
    await upsert_events(session, [_ev("d", "gpt", score=3.5)])
    await upsert_events(session, [_ev("d", "gpt", score=9.9, title="更嚴重")])
    ev = await _get(session, "d")
    assert ev.score == 9.9
    assert ev.title == "更嚴重"


async def test_missing_required_skipped(session):
    stats = await upsert_events(session, [_ev("e", "gpt", occurred_at=None), _ev("f", "gpt")])
    assert stats["skipped"] == 1
    assert stats["upserted"] == 1


async def test_endpoint_orders_and_filters(session):
    await upsert_events(session, [
        _ev("old", "gpt", event_type="launch", occurred_at=datetime(2026, 1, 1, tzinfo=UTC)),
        _ev("new", "claude", event_type="discussion_spike", occurred_at=datetime(2026, 5, 1, tzinfo=UTC)),
    ])
    # 全部：new 在 old 前（occurred_at desc）
    allr = await list_events(limit=200, event_type=None, model=None, db=session)
    titles_order = [r["occurred_at"] for r in allr]
    assert titles_order == sorted(titles_order, reverse=True)
    # 依 type 篩選
    spikes = await list_events(limit=200, event_type="discussion_spike", model=None, db=session)
    assert all(r["event_type"] == "discussion_spike" for r in spikes)
    # 依 model 篩選
    claude_only = await list_events(limit=200, event_type=None, model="claude", db=session)
    assert all(r["model"] == "claude" for r in claude_only)
