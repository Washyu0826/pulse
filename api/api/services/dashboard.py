"""
產品洞察 dashboard 時序服務 —— 主題分布 / 情緒分布隨時間的趨勢。

供前端「產品洞察 dashboard」的趨勢圖用：逐日各主題貼文數、逐日各情緒貼文數。
依 posts.posted_at 的日期分組（純 SQL group by date，不在 Python 端掃全表），
缺資料的日子補 0（前端不必自己補洞，趨勢線連續）。

設計沿用既有約定：
- 日期分桶用 func.date(Post.posted_at)，與 services/model_detail.py 的逐日彙總一致。
- 主題 6 鍵對齊 ml/ml/theme.py THEME_HYPOTHESES（5 實用主題）+「其他」。
- legacy「邊界」標籤映射到「風險限制」（與 services/feed.py 同一套別名規則）。
"""
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.posts import Post
from api.models.sentiment import Sentiment
from api.models.theme import Theme
from api.services.feed import ACTIONABLE_THEMES, LEGACY_THEME_ALIASES

# dashboard 主題分布的 6 個鍵（5 實用主題 + 其他），順序對齊 THEME_HYPOTHESES + 「其他」。
# 與合約 / 前端 THEME_ORDER 一致。
OTHER_LABEL = "其他"
THEME_ORDER: tuple[str, ...] = (*ACTIONABLE_THEMES, OTHER_LABEL)

# 情緒分布的 3 個鍵（對齊 sentiments.label）。
SENTIMENT_ORDER: tuple[str, ...] = ("positive", "neutral", "negative")

# 反向別名表：DB themes.label → dashboard 顯示鍵。非實用主題 / 非別名一律歸「其他」。
_DB_THEME_TO_KEY: dict[str, str] = {
    **{label: label for label in ACTIONABLE_THEMES},
    **{alias: canonical for canonical, aliases in LEGACY_THEME_ALIASES.items() for alias in aliases},
}


async def _theme_counts_by_day(
    session: AsyncSession, start: datetime
) -> dict[date, dict[str, int]]:
    """逐日 × 各 DB 主題標籤的貼文數（純 SQL group by date, label）。"""
    rows = (
        await session.execute(
            select(
                func.date(Post.posted_at).label("day"),
                Theme.label.label("label"),
                func.count().label("n"),
            )
            .join(Theme, Theme.post_id == Post.id)
            .where(Post.posted_at >= start)
            .group_by(func.date(Post.posted_at), Theme.label)
        )
    ).all()
    out: dict[date, dict[str, int]] = {}
    for r in rows:
        # DB 標籤 → 顯示鍵：實用主題保留、legacy 別名映射、其餘（含非信心『其他』）歸「其他」。
        key = _DB_THEME_TO_KEY.get(r.label, OTHER_LABEL)
        day_bucket = out.setdefault(r.day, {})
        day_bucket[key] = day_bucket.get(key, 0) + r.n
    return out


async def _sentiment_counts_by_day(
    session: AsyncSession, start: datetime
) -> dict[date, dict[str, int]]:
    """逐日 × 各情緒標籤的貼文數（純 SQL group by date, label）。"""
    rows = (
        await session.execute(
            select(
                func.date(Post.posted_at).label("day"),
                Sentiment.label.label("label"),
                func.count().label("n"),
            )
            .join(Sentiment, Sentiment.post_id == Post.id)
            .where(Post.posted_at >= start)
            .group_by(func.date(Post.posted_at), Sentiment.label)
        )
    ).all()
    out: dict[date, dict[str, int]] = {}
    for r in rows:
        if r.label in SENTIMENT_ORDER:  # 只收三類正規標籤，忽略非預期值
            out.setdefault(r.day, {})[r.label] = r.n
    return out


def _fill_trend(
    days: int,
    keys: tuple[str, ...],
    counts_by_day: dict[date, dict[str, int]],
) -> list[dict]:
    """補滿最近 days 天（日期升冪、缺資料補 0），每天一筆 {date, key1: n, ...}。"""
    today = datetime.now(UTC).date()
    # 最近 days 天：含今天，往回推 days-1 天 → 共 days 筆。
    start_day = today - timedelta(days=days - 1)
    trend: list[dict] = []
    for i in range(days):
        d = start_day + timedelta(days=i)
        bucket = counts_by_day.get(d, {})
        row: dict = {"date": d.isoformat()}
        for k in keys:
            row[k] = bucket.get(k, 0)
        trend.append(row)
    return trend


async def get_dashboard_trends(session: AsyncSession, *, days: int = 14) -> dict:
    """
    回傳主題分布 / 情緒分布的逐日時序（最近 days 天，日期升冪、缺日補 0）。

    {
        "theme_trend": [{"date": ..., "新工具": n, ..., "其他": n}, ...],
        "sentiment_trend": [{"date": ..., "positive": n, "neutral": n, "negative": n}, ...],
    }
    """
    # 從「最近 days 天的起日凌晨」起算，避免漏掉起日當天較早的貼文。
    start = datetime.combine(
        datetime.now(UTC).date() - timedelta(days=days - 1),
        datetime.min.time(),
        tzinfo=UTC,
    )
    theme_by_day = await _theme_counts_by_day(session, start)
    sentiment_by_day = await _sentiment_counts_by_day(session, start)
    return {
        "theme_trend": _fill_trend(days, THEME_ORDER, theme_by_day),
        "sentiment_trend": _fill_trend(days, SENTIMENT_ORDER, sentiment_by_day),
    }
