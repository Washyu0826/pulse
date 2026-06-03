"""
每日實用情報 feed 服務 —— 定位 C 的核心：以「主題」為主軸（新工具/使用方法/邊界），
模型 / 情緒 / 來源 / 時間為篩選維度。供首頁三主題分區與主題列表頁共用。

只看高品質、非重複貼文（沿用 DQC 下游門檻 quality_post_filter），且只取「高信心」主題
（themes.confident），「其他」不在實用情報內。
"""
import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.models import Model, PostModel
from api.models.posts import Post
from api.models.sentiment import Sentiment
from api.models.theme import Theme
from api.models.translation import Translation
from api.services._quality import quality_post_filter

# 實用情報的三大主題（不含「其他」）。順序＝首頁分區順序（新工具量最大擺第一）。
ACTIONABLE_THEMES: tuple[str, ...] = ("新工具", "使用方法", "邊界")

_WS_RE = re.compile(r"\s+")


def _clean(text: str | None, limit: int) -> str:
    """收合換行/多餘空白並截斷（Threads 內文常夾多重換行）。"""
    return _WS_RE.sub(" ", (text or "").strip())[:limit]


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


def _base_filters(stmt, *, source: str | None, sentiment: str | None, cutoff: datetime, model: str | None):
    """套用共用篩選：品質門檻 + 時間窗 + 來源 + 情緒 + 模型。"""
    stmt = stmt.where(*quality_post_filter()).where(Post.posted_at >= cutoff)
    if source:
        stmt = stmt.where(Post.source == source)
    if sentiment:
        stmt = stmt.where(Sentiment.label == sentiment)  # 指定情緒 → 只取已分析且相符
    if model:
        stmt = stmt.where(
            Post.id.in_(
                select(PostModel.post_id)
                .join(Model, Model.id == PostModel.model_id)
                .where(Model.slug == model)
            )
        )
    return stmt


async def _query_theme(
    session: AsyncSession, label: str, *, model, sentiment, source, cutoff, limit
) -> list[dict]:
    """取單一主題、套篩選後的 top N 貼文（最新優先）。"""
    stmt = (
        select(
            Post.id, Post.title, Post.content, Post.source,
            Post.url, Post.permalink, Post.posted_at, Post.score,
            Theme.confidence, Sentiment.label.label("sentiment"),
            Translation.title_zh, Translation.snippet_zh,
        )
        .join(Theme, Theme.post_id == Post.id)
        .outerjoin(Sentiment, Sentiment.post_id == Post.id)
        .outerjoin(Translation, Translation.post_id == Post.id)
        .where(Theme.confident.is_(True), Theme.label == label)
        .order_by(Post.posted_at.desc(), Post.id.desc())
        .limit(limit)
    )
    stmt = _base_filters(stmt, source=source, sentiment=sentiment, cutoff=cutoff, model=model)
    rows = (await session.execute(stmt)).all()

    slugs = await _slugs_by_post(session, [r.id for r in rows])
    return [
        {
            "id": r.id,
            "title": _clean(r.title, 120),
            "title_zh": _clean(r.title_zh, 120) or None,  # 繁中譯文（英文貼才有）
            "snippet": _clean(r.content, 160),
            "snippet_zh": _clean(r.snippet_zh, 200) or None,
            "source": r.source,
            "url": r.permalink or r.url,
            "models": slugs.get(r.id, []),
            "sentiment": r.sentiment,  # None = 未分析
            "theme": label,
            "theme_confidence": round(r.confidence, 3),
            "score": r.score,
            "posted_at": r.posted_at.isoformat() if r.posted_at else None,
        }
        for r in rows
    ]


async def get_feed(
    session: AsyncSession,
    *,
    model: str | None = None,
    sentiment: str | None = None,
    source: str | None = None,
    days: int = 7,
    limit_per_theme: int = 6,
    theme: str | None = None,
) -> dict[str, list[dict]]:
    """
    回傳各實用主題的 top N 貼文。`theme` 指定 → 只回該主題（量加大，給主題列表頁）。
    回傳 {主題: [貼文卡, ...]}（順序同 ACTIONABLE_THEMES）。
    """
    cutoff = datetime.now(UTC) - timedelta(days=days)
    labels = (theme,) if theme in ACTIONABLE_THEMES else ACTIONABLE_THEMES
    out: dict[str, list[dict]] = {}
    for label in labels:
        out[label] = await _query_theme(
            session, label, model=model, sentiment=sentiment, source=source,
            cutoff=cutoff, limit=limit_per_theme,
        )
    return out


async def get_feed_summary(
    session: AsyncSession,
    *,
    model: str | None = None,
    sentiment: str | None = None,
    source: str | None = None,
    days: int = 7,
) -> dict[str, int]:
    """各實用主題在篩選條件下的貼文數（給首頁今日摘要列）。"""
    cutoff = datetime.now(UTC) - timedelta(days=days)
    stmt = (
        select(Theme.label, func.count().label("n"))
        .join(Post, Post.id == Theme.post_id)
        .outerjoin(Sentiment, Sentiment.post_id == Post.id)
        .where(Theme.confident.is_(True), Theme.label.in_(ACTIONABLE_THEMES))
        .group_by(Theme.label)
    )
    stmt = _base_filters(stmt, source=source, sentiment=sentiment, cutoff=cutoff, model=model)
    rows = (await session.execute(stmt)).all()
    counts = {r.label: r.n for r in rows}
    return {label: counts.get(label, 0) for label in ACTIONABLE_THEMES}
