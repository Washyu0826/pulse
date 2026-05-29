"""
upsert_posts 整合測試 —— 針對真實 Postgres（review 指出這是最該補的測試）。

設計成非破壞性：
- 用 create_all(checkfirst) 確保表存在，**不 drop**（不會清掉 dev DB 的資料）。
- 只操作 external_id 以 'test_intg_' 開頭的測試資料，測試前後自行清乾淨。
- 連不到 DB（本機沒起 docker）→ pytest.skip，不讓單元測試紅。

本地執行：
    docker compose up -d db
    cd api && uv run alembic upgrade head   # 或讓 fixture 的 create_all 建表
    DATABASE_URL=postgresql+asyncpg://pulse:pulse@127.0.0.1:5433/pulse uv run pytest tests/test_upsert_integration.py
"""
import asyncio
from datetime import UTC, datetime

import api.models  # noqa: F401 — 註冊所有表
import pytest
import pytest_asyncio
from api.config import settings
from api.database import Base
from api.models.models import Model, PostModel
from api.models.posts import Post
from api.services.posts import upsert_posts
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

_PREFIX = "test_intg_"


def _row(external_id: str, models: list[str], **overrides) -> dict:
    """產一筆爬蟲格式的貼文 dict。"""
    base = dict(
        source="reddit",
        external_id=_PREFIX + external_id,
        title="Claude vs GPT",
        content="body",
        author="alice",
        subreddit="ClaudeAI",
        url=None,
        permalink=None,
        flair=None,
        over_18=False,
        score=1,
        num_comments=0,
        posted_at=datetime(2026, 1, 1, tzinfo=UTC),
        models=models,
        quality_score=None,
    )
    base.update(overrides)
    return base


@pytest_asyncio.fixture
async def engine():
    # function scope：每個 test 在自己的 event loop 跑，engine 必須同 loop 建立，
    # 否則 asyncpg 會報 "another operation is in progress"（跨 loop）。
    eng = create_async_engine(settings.database_url)
    try:
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)  # checkfirst=True，不重建已有表
    except Exception as e:  # noqa: BLE001
        await eng.dispose()
        pytest.skip(f"無法連線資料庫，跳過整合測試：{e}")
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine):
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    # 確保有 gpt / claude 兩個模型可關聯（idempotent）。
    async with maker() as s:
        await s.execute(
            pg_insert(Model)
            .values(
                [
                    {"slug": "gpt", "name": "GPT", "company": "OpenAI"},
                    {"slug": "claude", "name": "Claude", "company": "Anthropic"},
                ]
            )
            .on_conflict_do_nothing(index_elements=[Model.slug])
        )
        await s.commit()

    # 清掉前一輪殘留的測試貼文（cascade 會連帶清 post_models）。
    async def _cleanup():
        async with maker() as s:
            await s.execute(delete(Post).where(Post.external_id.like(f"{_PREFIX}%")))
            await s.commit()

    await _cleanup()
    async with maker() as s:
        yield s
    await _cleanup()


async def _count_assoc(session: AsyncSession, external_id: str) -> int:
    post_id = await session.scalar(
        select(Post.id).where(Post.external_id == _PREFIX + external_id)
    )
    rows = (
        await session.execute(select(PostModel).where(PostModel.post_id == post_id))
    ).all()
    return len(rows)


async def test_insert_and_associate(session):
    stats = await upsert_posts(session, [_row("a", ["gpt", "claude"]), _row("b", ["claude"])])
    assert stats["upserted"] == 2
    assert stats["associations"] == 3  # a→{gpt,claude}, b→{claude}
    assert await _count_assoc(session, "a") == 2
    assert await _count_assoc(session, "b") == 1


async def test_within_batch_dedup(session):
    """同批次重複 (source, external_id) 不可炸，且只算一筆。"""
    stats = await upsert_posts(
        session, [_row("dup", ["gpt"]), _row("dup", ["gpt"], score=999)]
    )
    assert stats["upserted"] == 1
    score = await session.scalar(
        select(Post.score).where(Post.external_id == _PREFIX + "dup")
    )
    assert score == 999  # 留最後一筆


async def test_on_conflict_updates_score_and_updated_at(session):
    await upsert_posts(session, [_row("c", ["gpt"], score=1)])
    first = (
        await session.execute(
            select(Post.score, Post.updated_at).where(Post.external_id == _PREFIX + "c")
        )
    ).one()

    await asyncio.sleep(0.01)  # 確保 now() 推進
    await upsert_posts(session, [_row("c", ["gpt"], score=42)])
    second = (
        await session.execute(
            select(Post.score, Post.updated_at).where(Post.external_id == _PREFIX + "c")
        )
    ).one()

    assert first.score == 1
    assert second.score == 42  # score 被更新
    assert second.updated_at > first.updated_at  # updated_at 有推進（upsert 顯式 set）


async def test_reupsert_does_not_duplicate_associations(session):
    await upsert_posts(session, [_row("d", ["gpt", "claude"])])
    stats = await upsert_posts(session, [_row("d", ["gpt", "claude"])])
    assert stats["associations"] == 0  # 已存在的關聯不再計入
    assert await _count_assoc(session, "d") == 2  # 仍是 2，沒重複


async def test_unknown_slug_is_dropped(session):
    stats = await upsert_posts(session, [_row("e", ["gpt", "nonexistent_model"])])
    assert stats["upserted"] == 1
    assert stats["associations"] == 1  # 只有 gpt 關聯，未知 slug 被略過
    assert await _count_assoc(session, "e") == 1


async def test_missing_required_field_skipped(session):
    """缺 posted_at（NOT NULL）的貼文要被略過，不可炸。"""
    bad = _row("f", ["gpt"], posted_at=None)
    stats = await upsert_posts(session, [bad, _row("g", ["gpt"])])
    assert stats["skipped"] == 1
    assert stats["upserted"] == 1
