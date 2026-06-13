"""
語料庫（corpus）服務 —— 把多來源貼文語料 + 標註結果（主題/情緒/品質）對外攤平。

提供作品集 / 研究用的唯讀視角：
- `get_corpus_stats`：全語料的彙總計數（總數、各來源、各主題、各情緒、品質三級）。
- `list_corpus_posts`：可篩選 + 分頁的貼文清單，左接（outer join）主題與情緒。

設計取捨：
- 全部 SELECT，不寫任何資料。
- 統計刻意「不套 DQC 下游門檻」（看的是整個語料庫的全貌，含低品質/重複），
  品質分佈本身就用 `quality` 三級攤開，讓呼叫端自己判讀。
- 主題/情緒以 outer join 帶出，未標註者為 None；不過濾信心（與 feed 服務的取向不同）。
"""
from typing import Any

from sqlalchemy import Case, Select, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.posts import Post
from api.models.sentiment import Sentiment
from api.models.theme import Theme
from api.services._quality import QUALITY_MIN

# 品質三級分界：高 >= QUALITY_MIN(30)，低 < MID_MIN(15)，其餘為中。NULL（尚未檢核）另計為「中」。
_QUALITY_MID_MIN = 15


def _quality_bucket_expr() -> Case:
    """把 quality_score 映射到 'high' / 'mid' / 'low' 的 SQL CASE 運算式。

    - score >= QUALITY_MIN(30)      → high
    - QUALITY_MID_MIN(15) <= score  → mid
    - score < QUALITY_MID_MIN(15)   → low
    - NULL（尚未 DQC）               → mid（保守歸中，避免污染高/低）
    """
    return case(
        (Post.quality_score.is_(None), "mid"),
        (Post.quality_score >= QUALITY_MIN, "high"),
        (Post.quality_score >= _QUALITY_MID_MIN, "mid"),
        else_="low",
    )


async def get_corpus_stats(session: AsyncSession) -> dict[str, Any]:
    """全語料的彙總統計（唯讀）。

    回傳形狀：
        {
          "total": int,
          "by_source": {來源: 數量, ...},
          "by_theme": {主題標籤: 數量, ...},      # 僅統計已標註主題的貼文
          "by_sentiment": {情緒標籤: 數量, ...},  # 僅統計已分析情緒的貼文
          "quality": {"high": int, "mid": int, "low": int},
        }
    """
    total = await session.scalar(select(func.count()).select_from(Post)) or 0

    source_rows = await session.execute(
        select(Post.source, func.count().label("n")).group_by(Post.source)
    )
    by_source = {row.source: row.n for row in source_rows}

    theme_rows = await session.execute(
        select(Theme.label, func.count().label("n")).group_by(Theme.label)
    )
    by_theme = {row.label: row.n for row in theme_rows}

    sentiment_rows = await session.execute(
        select(Sentiment.label, func.count().label("n")).group_by(Sentiment.label)
    )
    by_sentiment = {row.label: row.n for row in sentiment_rows}

    bucket = _quality_bucket_expr()
    quality_rows = await session.execute(
        select(bucket.label("bucket"), func.count().label("n")).group_by(bucket)
    )
    quality = {"high": 0, "mid": 0, "low": 0}
    for row in quality_rows:
        if row.bucket in quality:
            quality[row.bucket] = row.n

    return {
        "total": total,
        "by_source": by_source,
        "by_theme": by_theme,
        "by_sentiment": by_sentiment,
        "quality": quality,
    }


async def list_corpus_posts(
    session: AsyncSession,
    *,
    source: str | None = None,
    theme: str | None = None,
    sentiment: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    """可篩選 + 分頁的貼文清單，左接主題與情緒（唯讀）。

    篩選（皆為等值比對，None = 不限）：
        source     → posts.source
        theme      → themes.label（指定時只回有該主題標註的貼文）
        sentiment  → sentiments.label（指定時只回有該情緒的貼文）

    回傳形狀：
        {"total": <符合篩選的總數>, "limit": int, "offset": int, "items": [貼文, ...]}
    每筆貼文：id/source/title/content/author/quality_score/quality_flags/posted_at
              + theme/theme_confidence + sentiment/sentiment_score（未標註為 None）。
    """
    # 共用 join + 篩選；統計總數與取資料各跑一次，避免 join 放大 count。
    def _apply_filters(stmt: Select) -> Select:
        stmt = stmt.outerjoin(Theme, Theme.post_id == Post.id).outerjoin(
            Sentiment, Sentiment.post_id == Post.id
        )
        if source is not None:
            stmt = stmt.where(Post.source == source)
        if theme is not None:
            stmt = stmt.where(Theme.label == theme)
        if sentiment is not None:
            stmt = stmt.where(Sentiment.label == sentiment)
        return stmt

    total = (
        await session.scalar(_apply_filters(select(func.count()).select_from(Post)))
    ) or 0

    rows = (
        await session.execute(
            _apply_filters(
                select(
                    Post.id,
                    Post.source,
                    Post.title,
                    Post.content,
                    Post.author,
                    Post.quality_score,
                    Post.quality_flags,
                    Post.posted_at,
                    Theme.label.label("theme"),
                    Theme.confidence.label("theme_confidence"),
                    Sentiment.label.label("sentiment"),
                    Sentiment.score.label("sentiment_score"),
                )
            )
            .order_by(Post.posted_at.desc(), Post.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()

    items = [
        {
            "id": r.id,
            "source": r.source,
            "title": r.title,
            "content": r.content,
            "author": r.author,
            "quality_score": r.quality_score,
            "quality_flags": list(r.quality_flags or []),
            "posted_at": r.posted_at.isoformat() if r.posted_at else None,
            "theme": r.theme,
            "theme_confidence": (
                round(r.theme_confidence, 3) if r.theme_confidence is not None else None
            ),
            "sentiment": r.sentiment,
            "sentiment_score": (
                round(r.sentiment_score, 3) if r.sentiment_score is not None else None
            ),
        }
        for r in rows
    ]

    return {"total": total, "limit": limit, "offset": offset, "items": items}
