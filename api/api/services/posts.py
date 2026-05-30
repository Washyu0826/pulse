"""
Posts 服務層 — 把爬蟲產出的 raw 貼文 UPSERT 進 DB，並建立模型關聯。

放在 services 層而非爬蟲內，讓爬蟲保持「純粹輸出 dict、可單元測試」，
而 DB 寫入邏輯（UPSERT、關聯）由 test 腳本與 Airflow DAG 共用。
"""
import logging
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from api.models.models import Model, PostModel
from api.models.posts import Post
from api.services._batch import chunked

logger = logging.getLogger(__name__)

# DB NOT NULL 的必填欄位 —— 缺任一就跳過該筆（這是 DAG / HN 共用的寫入路徑）。
_REQUIRED_FIELDS = ("source", "external_id", "title", "posted_at")

# 會寫進 posts 表的欄位（其餘如 fetched_at 走 server_default；models 另存關聯表）。
_POST_COLUMNS = (
    "source",
    "external_id",
    "title",
    "content",
    "author",
    "subreddit",
    "url",
    "permalink",
    "flair",
    "over_18",
    "score",
    "num_comments",
    "posted_at",
)

# 重抓同一篇時要更新的欄位（互動指標會變；內容 / 標題偶爾會被編輯）。
# 不更新 external_id / source / created_at / fetched_at / quality_*（保留首次值與 DQC 結果）。
_ON_CONFLICT_UPDATE = ("title", "content", "score", "num_comments", "flair", "over_18")

# 分塊大小：PG 單一語句 bind 參數上限 32767。posts 13 欄、post_models 2 欄。
_POST_CHUNK = 1000
_ASSOC_CHUNK = 5000


async def upsert_posts(session: AsyncSession, rows: Sequence[dict]) -> dict[str, int]:
    """
    批次 UPSERT 貼文 + 建立 post↔model 關聯。

    回傳統計：{"received", "skipped", "upserted", "associations"}。
    呼叫端負責提供 session；本函式內 commit。

    注意：本函式自行 commit、自行掌控交易，**不要** 在 FastAPI `get_db()` 依賴
    管理的 request session 內呼叫（會與其 commit 行為衝突）。
    """
    stats = {"received": len(rows), "skipped": 0, "upserted": 0, "associations": 0}
    if not rows:
        return stats

    # 過濾掉缺必填欄位的貼文（否則 INSERT 會踩 NOT NULL 違規）。
    valid_rows: list[dict] = []
    for r in rows:
        missing = [k for k in _REQUIRED_FIELDS if r.get(k) is None]
        if missing:
            logger.warning("略過缺必填欄位的貼文 id=%s：缺 %s", r.get("external_id", "?"), missing)
            stats["skipped"] += 1
            continue
        valid_rows.append(r)

    # 同一批次內可能有重複 (source, external_id)（例如關鍵字命中多次），
    # 必須先去重，否則 PG 會報 "ON CONFLICT ... cannot affect row a second time"。
    deduped = {(r["source"], r["external_id"]): r for r in valid_rows}
    unique_rows = list(deduped.values())
    if not unique_rows:
        return stats

    post_values = [{col: r.get(col) for col in _POST_COLUMNS} for r in unique_rows]

    # 分塊 UPSERT：避免超過 PG 的 32767 bind 參數上限（回填可能上千列）。
    id_map: dict[tuple[str, str], int] = {}
    for chunk in chunked(post_values, _POST_CHUNK):
        stmt = pg_insert(Post).values(chunk)
        stmt = stmt.on_conflict_do_update(
            index_elements=[Post.source, Post.external_id],
            set_={
                **{col: getattr(stmt.excluded, col) for col in _ON_CONFLICT_UPDATE},
                # UPSERT 不會觸發 onupdate，要顯式更新（見 mixins.py 說明）。
                "updated_at": func.now(),
            },
        ).returning(Post.id, Post.source, Post.external_id)
        result = await session.execute(stmt)
        for row in result:
            id_map[(row.source, row.external_id)] = row.id
    stats["upserted"] = len(id_map)

    # 建立 post ↔ model 關聯（rows 內 models 是 slug list）。
    model_rows = await session.execute(select(Model.id, Model.slug))
    slug_to_id = {row.slug: row.id for row in model_rows}
    assoc: list[dict] = []
    for r in unique_rows:
        post_id = id_map.get((r["source"], r["external_id"]))
        if post_id is None:
            continue
        for slug in r.get("models", []):
            model_id = slug_to_id.get(slug)
            if model_id is None:
                # MODEL_KEYWORDS 有但 models 表沒 seed → 記 log 以便發現漂移
                logger.warning("貼文 %s 命中未知模型 slug=%s（未 seed？）", r["external_id"], slug)
                continue
            assoc.append({"post_id": post_id, "model_id": model_id})

    inserted = 0
    for chunk in chunked(assoc, _ASSOC_CHUNK):
        assoc_stmt = (
            pg_insert(PostModel)
            .values(chunk)
            .on_conflict_do_nothing(index_elements=[PostModel.post_id, PostModel.model_id])
            .returning(PostModel.post_id)
        )
        result = await session.execute(assoc_stmt)
        inserted += len(result.all())  # 實際新增的關聯數（已存在的不計）
    stats["associations"] = inserted

    await session.commit()
    return stats
