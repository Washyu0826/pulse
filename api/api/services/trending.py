"""Trending keywords 服務層 —— 全表替換寫入 + 讀取當前榜單。"""
from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.trending import TrendingKeyword


async def replace_trending(session: AsyncSession, rows: Sequence[dict]) -> int:
    """全表替換熱詞快照（先清空再插入）。rows: [{term, rank, z, recent_count}]。回傳寫入筆數。"""
    await session.execute(delete(TrendingKeyword))
    if rows:
        session.add_all([TrendingKeyword(**r) for r in rows])
    await session.commit()
    return len(rows)


async def get_trending(session: AsyncSession, limit: int = 15) -> list[dict]:
    """讀當前熱詞榜（依 rank）。"""
    rows = (
        await session.execute(
            select(TrendingKeyword).order_by(TrendingKeyword.rank).limit(limit)
        )
    ).scalars().all()
    return [
        {"term": r.term, "rank": r.rank, "z": r.z, "recent_count": r.recent_count}
        for r in rows
    ]
