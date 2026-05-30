"""
Events 服務層 — 把偵測到的事件 UPSERT 進 events（以 dedup_key 去重 → 偵測可重跑）。
"""
import logging
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from api.models.event import Event
from api.models.models import Model
from api.services._batch import chunked

logger = logging.getLogger(__name__)

_EVENT_COLUMNS = ("dedup_key", "event_type", "title", "description", "score", "occurred_at", "extra")
_REQUIRED = ("dedup_key", "event_type", "title", "occurred_at")
_ON_CONFLICT_UPDATE = ("title", "description", "score", "occurred_at", "extra")


async def upsert_events(session: AsyncSession, rows: Sequence[dict]) -> dict[str, int]:
    """
    批次 UPSERT 事件，並把 rows 內的 "model" slug 解析成 model_id。
    回傳 {"received", "skipped", "upserted"}。本函式內 commit。
    """
    stats = {"received": len(rows), "skipped": 0, "upserted": 0}
    if not rows:
        return stats

    valid: list[dict] = []
    for r in rows:
        missing = [k for k in _REQUIRED if r.get(k) is None]
        if missing:
            logger.warning("略過缺必填的 event key=%s：缺 %s", r.get("dedup_key", "?"), missing)
            stats["skipped"] += 1
            continue
        valid.append(r)

    deduped = {r["dedup_key"]: r for r in valid}
    unique_rows = list(deduped.values())
    if not unique_rows:
        return stats

    model_rows = await session.execute(select(Model.id, Model.slug))
    slug_to_id = {row.slug: row.id for row in model_rows}

    values = []
    for r in unique_rows:
        row = {col: r.get(col) for col in _EVENT_COLUMNS}
        slug = r.get("model")
        if slug is not None and slug not in slug_to_id:
            logger.warning("event %s 對應未知模型 slug=%s（未 seed？）", r["dedup_key"], slug)
        row["model_id"] = slug_to_id.get(slug)
        values.append(row)

    # 分塊 UPSERT：避免超過 PG 的 32767 bind 參數上限。
    upserted = 0
    for chunk in chunked(values):
        stmt = pg_insert(Event).values(chunk)
        stmt = stmt.on_conflict_do_update(
            index_elements=[Event.dedup_key],
            set_={
                **{col: getattr(stmt.excluded, col) for col in _ON_CONFLICT_UPDATE},
                "model_id": stmt.excluded.model_id,
                "updated_at": func.now(),
            },
        ).returning(Event.id)
        result = await session.execute(stmt)
        upserted += len(result.all())
    stats["upserted"] = upserted
    await session.commit()
    return stats
