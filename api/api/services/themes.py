"""Themes 服務層 —— 批次 UPSERT 主題分類結果（分塊避開 PG 參數上限）。"""
import logging
from collections.abc import Sequence

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from api.models.theme import Theme
from api.services._batch import chunked

logger = logging.getLogger(__name__)

_COLUMNS = ("post_id", "label", "confidence", "confident")
_ON_CONFLICT_UPDATE = ("label", "confidence", "confident")


async def upsert_themes(session: AsyncSession, rows: Sequence[dict]) -> dict[str, int]:
    """批次 UPSERT 主題（post_id 衝突則更新）。回傳 {"upserted"}。本函式內 commit。"""
    stats = {"upserted": 0}
    if not rows:
        return stats
    values = [{c: r[c] for c in _COLUMNS} for r in rows]
    upserted = 0
    for chunk in chunked(values):
        stmt = pg_insert(Theme).values(chunk)
        stmt = stmt.on_conflict_do_update(
            index_elements=[Theme.post_id],
            set_={
                **{c: getattr(stmt.excluded, c) for c in _ON_CONFLICT_UPDATE},
                "classified_at": func.now(),
                "updated_at": func.now(),
            },
        ).returning(Theme.post_id)
        result = await session.execute(stmt)
        upserted += len(result.all())
    stats["upserted"] = upserted
    await session.commit()
    return stats
