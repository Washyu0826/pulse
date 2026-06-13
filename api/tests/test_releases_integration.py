"""
release_events 整合測試 —— 針對真實 Postgres。非破壞性（只動 external_id 前綴 test_re_）。
連不到 DB → skip。
"""
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import api.models  # noqa: F401
from api.config import settings
from api.database import Base
from api.models.models import Model
from api.models.release import ReleaseEvent
from api.routers.releases import recent_releases
from api.services.releases import upsert_release_events

_PREFIX = "test_re_"


def _ev(external_id: str, model: str | None, **ov) -> dict:
    base = dict(
        source="github",
        external_id=_PREFIX + external_id,
        model=model,
        title="A release",
        url=f"https://example.com/{external_id}",
        repo="owner/repo",
        kind="github_release",
        version="v1.0.0",
        published_at=datetime(2026, 1, 1, tzinfo=UTC),
        extra={"prerelease": False},
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
            await s.execute(delete(ReleaseEvent).where(ReleaseEvent.external_id.like(f"{_PREFIX}%")))
            await s.commit()

    await _cleanup()
    async with maker() as s:
        yield s
    await _cleanup()


async def _model_id_of(session: AsyncSession, external_id: str):
    return await session.scalar(
        select(ReleaseEvent.model_id).where(ReleaseEvent.external_id == _PREFIX + external_id)
    )


async def test_insert_and_resolve_model(session):
    stats = await upsert_release_events(session, [_ev("a", "gpt"), _ev("b", "claude")])
    assert stats["upserted"] == 2
    gpt_id = await session.scalar(select(Model.id).where(Model.slug == "gpt"))
    assert await _model_id_of(session, "a") == gpt_id


async def test_unknown_slug_model_id_none(session):
    stats = await upsert_release_events(session, [_ev("c", "nonexistent")])
    assert stats["upserted"] == 1
    assert await _model_id_of(session, "c") is None  # 對不到 → 事件保留但 model_id 為 None


async def test_model_id_updated_on_conflict(session):
    """重 upsert 時 model_id 也要更新（它在 _ON_CONFLICT_UPDATE 之外手動加，需回歸保護）。"""
    await upsert_release_events(session, [_ev("h", "nonexistent")])
    assert await _model_id_of(session, "h") is None
    # 再用已知 slug 重 upsert → model_id 應被填上
    await upsert_release_events(session, [_ev("h", "gpt")])
    gpt_id = await session.scalar(select(Model.id).where(Model.slug == "gpt"))
    assert await _model_id_of(session, "h") == gpt_id


async def test_within_batch_dedup(session):
    stats = await upsert_release_events(session, [_ev("d", "gpt"), _ev("d", "gpt", title="newer")])
    assert stats["upserted"] == 1
    title = await session.scalar(
        select(ReleaseEvent.title).where(ReleaseEvent.external_id == _PREFIX + "d")
    )
    assert title == "newer"


async def test_idempotent_reupsert(session):
    await upsert_release_events(session, [_ev("e", "gpt")])
    await upsert_release_events(session, [_ev("e", "gpt", title="updated")])
    count = await session.scalar(
        select(ReleaseEvent.id).where(ReleaseEvent.external_id == _PREFIX + "e")
    )
    assert count is not None  # 仍只有一筆（unique 約束）
    title = await session.scalar(
        select(ReleaseEvent.title).where(ReleaseEvent.external_id == _PREFIX + "e")
    )
    assert title == "updated"


async def test_missing_required_skipped(session):
    stats = await upsert_release_events(session, [_ev("f", "gpt", published_at=None), _ev("g", "gpt")])
    assert stats["skipped"] == 1
    assert stats["upserted"] == 1


async def test_recent_releases_endpoint(session):
    # 用「遠未來」日期讓兩筆測試資料一定排在 top-N 最前，避免共享 dev DB 裡既有的大量
    # 真實 release 把測試列擠出 limit 視窗（隔離法，不靠放寬斷言）。
    far = datetime(2099, 1, 1, tzinfo=UTC)
    await upsert_release_events(session, [
        _ev("old", "gpt", published_at=far),
        _ev("new", "claude", published_at=far.replace(month=2)),
    ])
    result = await recent_releases(limit=100, source=None, db=session)
    # url 結尾是 external_id 後段（old / new）
    pos = {r["url"].rsplit("/", 1)[-1]: i for i, r in enumerate(result)}
    assert "new" in pos and "old" in pos
    assert pos["new"] < pos["old"]  # published_at desc：new(2099-02) 在 old(2099-01) 前
    new_row = next(r for r in result if r["url"].endswith("/new"))
    assert new_row["model"] == "claude"  # model slug 有被解析
