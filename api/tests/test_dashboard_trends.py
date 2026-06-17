"""
dashboard 趨勢端點測試。

兩層（對齊既有慣例，避免本機比 CI 寬鬆而假綠）：
1. 純函式 / 不需 DB：_fill_trend 的補零、升冪、鍵完整性；端點參數驗證封套（422）。
2. 真實 Postgres 整合：插入跨日測試貼文 → 驗逐日計數正確。連不到 DB → skip。
"""
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import api.models  # noqa: F401
from api.config import settings
from api.database import Base
from api.main import app
from api.models.posts import Post
from api.models.sentiment import Sentiment
from api.models.theme import Theme
from api.services.dashboard import (
    SENTIMENT_ORDER,
    THEME_ORDER,
    _fill_trend,
    get_dashboard_trends,
)

client = TestClient(app)


# ---------------------------------------------------------------------------
# 純函式 / 不需 DB
# ---------------------------------------------------------------------------
def test_fill_trend_length_order_and_zero_fill():
    """_fill_trend：剛好 days 筆、日期升冪、缺日補 0、鍵齊全。"""
    today = datetime.now(UTC).date()
    counts = {today: {"新工具": 5, "其他": 1}}  # 只有今天有資料
    trend = _fill_trend(7, THEME_ORDER, counts)

    assert len(trend) == 7
    dates = [row["date"] for row in trend]
    assert dates == sorted(dates)  # 升冪
    assert dates[-1] == today.isoformat()  # 最後一筆 = 今天

    # 每一筆都含全部主題鍵（缺資料的日子補 0）。
    for row in trend:
        assert set(row) == {"date", *THEME_ORDER}
    assert trend[-1]["新工具"] == 5
    assert trend[-1]["其他"] == 1
    assert trend[0]["新工具"] == 0  # 起日無資料 → 0


def test_fill_trend_single_day():
    """days=1 → 只回今天一筆。"""
    trend = _fill_trend(1, SENTIMENT_ORDER, {})
    assert len(trend) == 1
    assert trend[0]["date"] == datetime.now(UTC).date().isoformat()
    assert all(trend[0][k] == 0 for k in SENTIMENT_ORDER)


def test_theme_order_matches_contract():
    """合約規定的 6 主題鍵與順序。"""
    assert THEME_ORDER == ("新工具", "模型動態", "使用方法", "風險限制", "倫理法規", "其他")
    assert SENTIMENT_ORDER == ("positive", "neutral", "negative")


def _assert_validation_envelope(resp) -> None:
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"] == "validation_error"
    assert "request_id" in body


def test_days_out_of_range_rejected():
    """days 須在 1..90 → 超出 422（驗證早於 DB 查詢）。"""
    _assert_validation_envelope(client.get("/api/dashboard/trends", params={"days": 0}))
    _assert_validation_envelope(client.get("/api/dashboard/trends", params={"days": 91}))


# ---------------------------------------------------------------------------
# 真實 Postgres 整合（連不到 → skip；非破壞性，external_id 前綴 test_dash_）
# ---------------------------------------------------------------------------
_PREFIX = "test_dash_"


@pytest_asyncio.fixture
async def session():
    eng = create_async_engine(settings.database_url)
    try:
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as e:  # noqa: BLE001
        await eng.dispose()
        pytest.skip(f"無法連線資料庫，跳過：{e}")
    maker = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)

    async def _cleanup():
        async with maker() as s:
            ids = (
                await s.execute(select(Post.id).where(Post.external_id.like(f"{_PREFIX}%")))
            ).scalars().all()
            if ids:
                await s.execute(delete(Theme).where(Theme.post_id.in_(ids)))
                await s.execute(delete(Sentiment).where(Sentiment.post_id.in_(ids)))
                await s.execute(delete(Post).where(Post.id.in_(ids)))
            await s.commit()

    await _cleanup()
    async with maker() as s:
        yield s
    await _cleanup()
    await eng.dispose()


async def _add_post(
    session: AsyncSession, ext: str, posted_at: datetime, theme: str, sentiment: str
) -> None:
    post = Post(
        source="threads",
        external_id=_PREFIX + ext,
        title="t",
        content="c",
        posted_at=posted_at,
        quality_score=80,
    )
    session.add(post)
    await session.flush()  # 取得 post.id
    session.add(Theme(post_id=post.id, label=theme, confidence=0.9, confident=True))
    session.add(
        Sentiment(
            post_id=post.id,
            label=sentiment,
            score=0.9,
            p_positive=0.8,
            p_neutral=0.1,
            p_negative=0.1,
            confident=True,
        )
    )
    await session.commit()


def _theme_on(trends: dict, day: datetime, key: str) -> int:
    row = next(r for r in trends["theme_trend"] if r["date"] == day.date().isoformat())
    return row[key]


def _sent_on(trends: dict, day: datetime, key: str) -> int:
    row = next(r for r in trends["sentiment_trend"] if r["date"] == day.date().isoformat())
    return row[key]


async def test_trends_counts_by_day(session):
    """跨兩天插入測試貼文 → 逐日主題 / 情緒計數的增量正確。

    共享 dev DB 已有大量真實貼文，故比對「插入前後的差值」而非絕對值（隔離法，
    不靠放寬斷言）。差值精確等於我們插入的筆數即證明 group by date / 分桶正確。
    """
    today = datetime.now(UTC)
    yday = today - timedelta(days=1)

    before = await get_dashboard_trends(session, days=3)
    base_new = _theme_on(before, today, "新工具")
    base_other = _theme_on(before, today, "其他")
    base_model_yday = _theme_on(before, yday, "模型動態")
    base_pos = _sent_on(before, today, "positive")
    base_neg = _sent_on(before, today, "negative")

    # 今天：2 新工具 / 1 其他；情緒 2 positive / 1 negative
    await _add_post(session, "t1", today, "新工具", "positive")
    await _add_post(session, "t2", today, "新工具", "positive")
    await _add_post(session, "t3", today, "其他", "negative")
    # 昨天：1 模型動態 / neutral
    await _add_post(session, "y1", yday, "模型動態", "neutral")

    after = await get_dashboard_trends(session, days=3)
    assert len(after["theme_trend"]) == 3  # 補滿 3 天
    assert len(after["sentiment_trend"]) == 3

    assert _theme_on(after, today, "新工具") - base_new == 2
    assert _theme_on(after, today, "其他") - base_other == 1
    assert _theme_on(after, yday, "模型動態") - base_model_yday == 1
    assert _sent_on(after, today, "positive") - base_pos == 2
    assert _sent_on(after, today, "negative") - base_neg == 1


async def test_trends_endpoint_shape(session):
    """端點實打：回應結構符合合約（鍵齊全、日期升冪）。"""
    await _add_post(session, "e1", datetime.now(UTC), "使用方法", "neutral")
    resp = client.get("/api/dashboard/trends", params={"days": 5})
    assert resp.status_code == 200
    body = resp.json()
    assert {"theme_trend", "sentiment_trend"} == set(body)
    assert len(body["theme_trend"]) == 5
    for row in body["theme_trend"]:
        assert set(row) == {"date", *THEME_ORDER}
    dates = [r["date"] for r in body["theme_trend"]]
    assert dates == sorted(dates)
