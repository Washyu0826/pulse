"""Translations 服務層 —— 批次 UPSERT 譯文。"""
from collections.abc import Sequence

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from api.models.translation import Translation
from api.services._batch import chunked

_COLUMNS = ("post_id", "title_zh", "snippet_zh")


async def upsert_translations(session: AsyncSession, rows: Sequence[dict]) -> dict[str, int]:
    """批次 UPSERT 譯文（post_id 衝突則更新）。回傳 {"upserted"}。本函式內 commit。"""
    stats = {"upserted": 0}
    if not rows:
        return stats
    values = [{c: r.get(c) for c in _COLUMNS} for r in rows]
    upserted = 0
    for chunk in chunked(values):
        stmt = pg_insert(Translation).values(chunk)
        stmt = stmt.on_conflict_do_update(
            index_elements=[Translation.post_id],
            set_={
                "title_zh": stmt.excluded.title_zh,
                "snippet_zh": stmt.excluded.snippet_zh,
                "translated_at": func.now(),
            },
        ).returning(Translation.post_id)
        result = await session.execute(stmt)
        upserted += len(result.all())
    stats["upserted"] = upserted
    await session.commit()
    return stats
