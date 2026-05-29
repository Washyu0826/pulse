"""
ReleaseEvent 服務層 — 把 HF / GitHub 爬蟲產出的發布訊號 UPSERT 進 release_events。

與 posts 不同：release 與 model 是「單一」對應（model_id 欄位），不是多對多。
"""
import logging
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from api.models.models import Model
from api.models.release import ReleaseEvent

logger = logging.getLogger(__name__)

# 寫進 release_events 的欄位（model_id 另由 slug 解析；fetched_at 走 server_default）。
_RE_COLUMNS = ("source", "external_id", "title", "url", "repo", "kind", "version", "published_at", "extra")
_RE_REQUIRED = ("source", "external_id", "title", "url", "repo", "kind", "published_at")
# 重抓同一事件時更新的欄位（版本資訊偶有修訂、downloads/likes 會變）。
_ON_CONFLICT_UPDATE = ("title", "url", "version", "extra")


async def upsert_release_events(session: AsyncSession, rows: Sequence[dict]) -> dict[str, int]:
    """
    批次 UPSERT 發布事件，並把 rows 內的 "model" slug 解析成 model_id。

    回傳統計：{"received", "skipped", "upserted"}。本函式內 commit。
    （與 upsert_posts 相同契約：勿在 get_db() 管理的 request session 內呼叫。）
    """
    stats = {"received": len(rows), "skipped": 0, "upserted": 0}
    if not rows:
        return stats

    valid_rows: list[dict] = []
    for r in rows:
        missing = [k for k in _RE_REQUIRED if r.get(k) is None]
        if missing:
            logger.warning("略過缺必填欄位的 release id=%s：缺 %s", r.get("external_id", "?"), missing)
            stats["skipped"] += 1
            continue
        valid_rows.append(r)

    deduped = {(r["source"], r["external_id"]): r for r in valid_rows}
    unique_rows = list(deduped.values())
    if not unique_rows:
        return stats

    # slug → model_id（對不到的 slug → model_id=None，事件仍保留）
    model_rows = await session.execute(select(Model.id, Model.slug))
    slug_to_id = {row.slug: row.id for row in model_rows}

    values = []
    for r in unique_rows:
        row = {col: r.get(col) for col in _RE_COLUMNS}
        slug = r.get("model")
        if slug is not None and slug not in slug_to_id:
            logger.warning("release %s 對應未知模型 slug=%s（未 seed？）", r["external_id"], slug)
        row["model_id"] = slug_to_id.get(slug)
        values.append(row)

    stmt = pg_insert(ReleaseEvent).values(values)
    stmt = stmt.on_conflict_do_update(
        index_elements=[ReleaseEvent.source, ReleaseEvent.external_id],
        set_={
            **{col: getattr(stmt.excluded, col) for col in _ON_CONFLICT_UPDATE},
            "model_id": stmt.excluded.model_id,
            "updated_at": func.now(),  # UPSERT 不觸發 onupdate，顯式更新
        },
    ).returning(ReleaseEvent.id)

    result = await session.execute(stmt)
    stats["upserted"] = len(result.all())
    await session.commit()
    return stats
