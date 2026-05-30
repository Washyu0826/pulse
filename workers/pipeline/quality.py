"""
pipeline.quality —— DQC 編排：算每篇 quality_score/quality_flags + 跨來源去重，寫回 posts。

兩階段（順序重要）：
1. process_quality：對「尚未處理」(dq_processed_at IS NULL) 的貼文逐篇評分（純 ml.data_quality），
   分塊寫回 quality_score / quality_flags / dq_processed_at。可分批、可重跑。
2. detect_duplicates：對**全表**做跨來源近似重複偵測（ml.dedup），在既有 quality_flags 上
   **只**增刪去重標記（DUPLICATE / CANONICAL:<id>），保留品質 flag。冪等、會對帳移除過時標記。

去重不扣 quality_score（兩者正交）；要過濾重複請在查詢層用 flag。重評分：把 dq_processed_at 設回 NULL。
"""
from __future__ import annotations

import logging

from api.database import AsyncSessionLocal
from api.models.models import Model, PostModel
from api.models.posts import Post
from api.services._batch import chunked
from ml.data_quality import score_post
from ml.dedup import build_clusters, reconcile_dedup_flags, select_canonical
from sqlalchemy import Text, bindparam, func, select, update
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_UPDATE_CHUNK = 1000


async def _slugs_by_post(session: AsyncSession, post_ids: list[int]) -> dict[int, list[str]]:
    """一次查出這批貼文各自命中的模型 slug（避免 N+1）。"""
    out: dict[int, list[str]] = {}
    if not post_ids:
        return out
    rows = await session.execute(
        select(PostModel.post_id, Model.slug)
        .join(Model, Model.id == PostModel.model_id)
        .where(PostModel.post_id.in_(post_ids))
    )
    for pid, slug in rows:
        out.setdefault(pid, []).append(slug)
    return out


async def process_quality(limit: int = 500) -> dict[str, int]:
    """評分一批尚未處理的貼文，寫回。回傳 {processed, high, mid, low}。可重跑（只挑 NULL）。"""
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(Post)
                .where(Post.dq_processed_at.is_(None))
                .order_by(Post.fetched_at)  # 走 ix_posts_dq_unprocessed partial index
                .limit(limit)
            )
        ).scalars().all()
        if not rows:
            return {"processed": 0, "high": 0, "mid": 0, "low": 0}

        slugs = await _slugs_by_post(session, [p.id for p in rows])

        updates: list[dict] = []
        high = mid = low = 0
        for p in rows:
            res = score_post(
                {
                    "source": p.source,
                    "title": p.title,
                    "content": p.content,
                    "author": p.author,
                    "url": p.url,
                    "score": p.score,
                    "num_comments": p.num_comments,
                },
                slugs.get(p.id, []),
            )
            updates.append({"b_id": p.id, "b_qs": res.score, "b_qf": res.flags})
            high += res.score >= 60
            mid += 30 <= res.score < 60
            low += res.score < 30

        tbl = Post.__table__
        stmt = (
            update(tbl)
            .where(tbl.c.id == bindparam("b_id"))
            .values(
                quality_score=bindparam("b_qs"),
                quality_flags=bindparam("b_qf", type_=ARRAY(Text)),
                dq_processed_at=func.now(),
            )
        )
        for chunk in chunked(updates, _UPDATE_CHUNK):
            await session.execute(stmt, list(chunk))
        await session.commit()

    result = {"processed": len(rows), "high": high, "mid": mid, "low": low}
    logger.info("DQC 評分：%s", result)
    return result


async def detect_duplicates() -> dict[str, int]:
    """全表跨來源去重，對帳更新 DUPLICATE/CANONICAL flag。回傳 {clusters, duplicates}。"""
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(
                    Post.id,
                    Post.source,
                    Post.url,
                    Post.title,
                    Post.posted_at,
                    Post.score,
                    Post.num_comments,
                    Post.quality_flags,
                )
            )
        ).all()
        posts = [
            {
                "id": r.id, "source": r.source, "url": r.url, "title": r.title,
                "posted_at": r.posted_at, "score": r.score, "num_comments": r.num_comments,
                "quality_flags": list(r.quality_flags or []),
            }
            for r in rows
        ]

        clusters = build_clusters(posts)
        # 算每篇「期望的去重標記」：cluster 內非 canonical → DUPLICATE。
        desired_canonical: dict[int, int | None] = {}
        for cluster in clusters:
            canonical_id = select_canonical(cluster)
            for p in cluster:
                desired_canonical[p["id"]] = None if p["id"] == canonical_id else canonical_id

        # 對帳：對「在 cluster 內」或「目前帶有去重標記」的貼文，重算 flag；變動才寫回。
        flags_now = {p["id"]: p["quality_flags"] for p in posts}
        updates: list[dict] = []
        duplicates = 0
        for pid, cur in flags_now.items():
            has_dedup_tag = any(f == "DUPLICATE" or f.startswith("CANONICAL:") for f in cur)
            if pid not in desired_canonical and not has_dedup_tag:
                continue  # 與去重無關，跳過
            canonical_id = desired_canonical.get(pid)
            is_canonical = pid in desired_canonical and canonical_id is None
            new_flags = reconcile_dedup_flags(cur, is_canonical, canonical_id)
            if not is_canonical and canonical_id is not None:
                duplicates += 1
            if sorted(set(cur)) != new_flags:
                updates.append({"b_id": pid, "b_qf": new_flags})

        if updates:
            tbl = Post.__table__
            stmt = (
                update(tbl)
                .where(tbl.c.id == bindparam("b_id"))
                .values(quality_flags=bindparam("b_qf", type_=ARRAY(Text)))
            )
            for chunk in chunked(updates, _UPDATE_CHUNK):
                await session.execute(stmt, list(chunk))
            await session.commit()

    result = {"clusters": len(clusters), "duplicates": duplicates, "updated": len(updates)}
    logger.info("DQC 去重：%s", result)
    return result


async def run_dqc(batch_limit: int = 500, max_batches: int = 100_000) -> dict[str, int]:
    """
    跑完整 DQC：分批評分**所有**未處理貼文（每批各自 commit、走 partial index，便宜），
    再做一次全表去重對帳。回傳合併統計。

    max_batches 只是防無窮迴圈的上限（極大）；正常會在某批 processed==0 時自然收斂。
    若真的觸到上限仍有殘量 → 記 warning（避免靜默漏處理，code review C1）。
    """
    total = {"processed": 0, "high": 0, "mid": 0, "low": 0}
    drained = False
    for _ in range(max_batches):
        stats = await process_quality(limit=batch_limit)
        for k in total:
            total[k] += stats[k]
        if stats["processed"] == 0:
            drained = True
            break
    if not drained:
        logger.warning("run_dqc 觸到 max_batches 上限仍有未評分貼文；下次執行會接續處理")

    dedup = await detect_duplicates()
    return {**total, **dedup}
