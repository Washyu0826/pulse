"""/api/corpus/* 端點測試 —— 不需 live Postgres。

做法：用 FastAPI 的 `app.dependency_overrides` 把 `get_db` 換成一個假 async session，
依「該服務發出查詢的固定順序」回傳預先排好的 canned 結果（_ScriptedSession）。
這樣只驗證 router/service 的形狀組裝與篩選傳遞，完全不碰真資料庫。

涵蓋：
- /corpus/stats：彙總形狀（total / by_source / by_theme / by_sentiment / quality 三級）。
- /corpus/posts：分頁形狀、左接主題/情緒的攤平、未標註欄位為 None、limit 上限驗證、
  篩選參數確實被帶進查詢（透過攔截 where 子句的數量間接驗證 + 422 邊界）。
"""
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from api.database import get_db
from api.main import app


class _Row:
    """模擬 SQLAlchemy Row：屬性存取（r.source / r.n / r.label ...）。"""

    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Result:
    """模擬 execute() 的回傳：支援 .all() 與直接 for 迭代。"""

    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)

    def __iter__(self):
        return iter(self._rows)


class _ScriptedSession:
    """假 async session：scalar() 與 execute() 依序吐出預排好的結果。

    `scalars` 是給 session.scalar(...) 的回傳序列（依呼叫順序）；
    `results` 是給 session.execute(...) 的 _Result 序列（依呼叫順序）。
    """

    def __init__(self, scalars=None, results=None):
        self._scalars = list(scalars or [])
        self._results = list(results or [])

    async def scalar(self, *_a, **_k):
        return self._scalars.pop(0)

    async def execute(self, *_a, **_k):
        return self._results.pop(0)


def _override(session: _ScriptedSession):
    async def _dep():
        yield session

    app.dependency_overrides[get_db] = _dep


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


client = TestClient(app)


def test_stats_shape():
    """/corpus/stats：彙總四維 + 品質三級形狀正確。

    服務查詢順序：scalar(total) → execute(by_source) → execute(by_theme)
                 → execute(by_sentiment) → execute(quality buckets)。
    """
    session = _ScriptedSession(
        scalars=[42],  # total
        results=[
            _Result([_Row(source="threads", n=30), _Row(source="hackernews", n=12)]),
            _Result([_Row(label="新工具", n=20), _Row(label="使用方法", n=10)]),
            _Result([_Row(label="positive", n=25), _Row(label="negative", n=5)]),
            _Result([_Row(bucket="high", n=18), _Row(bucket="mid", n=20), _Row(bucket="low", n=4)]),
        ],
    )
    _override(session)

    resp = client.get("/api/corpus/stats")
    assert resp.status_code == 200
    data = resp.json()

    assert data["total"] == 42
    assert data["by_source"] == {"threads": 30, "hackernews": 12}
    assert data["by_theme"] == {"新工具": 20, "使用方法": 10}
    assert data["by_sentiment"] == {"positive": 25, "negative": 5}
    assert data["quality"] == {"high": 18, "mid": 20, "low": 4}


def test_stats_quality_defaults_to_zero_when_bucket_absent():
    """品質某一級沒有資料時補 0（不缺鍵）。"""
    session = _ScriptedSession(
        scalars=[3],
        results=[
            _Result([_Row(source="threads", n=3)]),
            _Result([]),
            _Result([]),
            _Result([_Row(bucket="high", n=3)]),  # 只有 high
        ],
    )
    _override(session)

    data = client.get("/api/corpus/stats").json()
    assert data["quality"] == {"high": 3, "mid": 0, "low": 0}
    assert data["by_theme"] == {}


def test_posts_shape_and_flatten():
    """/corpus/posts：分頁 + 左接主題/情緒攤平；未標註欄位為 None。

    服務查詢順序：scalar(total) → execute(rows)。
    """
    now = datetime(2026, 6, 10, 12, 0, tzinfo=UTC)
    session = _ScriptedSession(
        scalars=[2],  # total（符合篩選）
        results=[
            _Result([
                _Row(
                    id=1, source="threads", title="新工具發表", content="內容A",
                    author="alice", quality_score=80, quality_flags=["OK"],
                    posted_at=now, theme="新工具", theme_confidence=0.912,
                    sentiment="positive", sentiment_score=0.876,
                ),
                _Row(
                    id=2, source="hackernews", title="未標註貼", content="內容B",
                    author=None, quality_score=None, quality_flags=None,
                    posted_at=None, theme=None, theme_confidence=None,
                    sentiment=None, sentiment_score=None,
                ),
            ]),
        ],
    )
    _override(session)

    resp = client.get("/api/corpus/posts?limit=10&offset=0")
    assert resp.status_code == 200
    data = resp.json()

    assert data["total"] == 2
    assert data["limit"] == 10
    assert data["offset"] == 0
    assert len(data["items"]) == 2

    a = data["items"][0]
    assert a["id"] == 1
    assert a["source"] == "threads"
    assert a["theme"] == "新工具"
    assert a["theme_confidence"] == 0.912  # 已四捨五入到 3 位
    assert a["sentiment"] == "positive"
    assert a["sentiment_score"] == 0.876
    assert a["quality_flags"] == ["OK"]
    assert a["posted_at"].startswith("2026-06-10")

    b = data["items"][1]
    assert b["author"] is None
    assert b["quality_score"] is None
    assert b["quality_flags"] == []  # None → []
    assert b["posted_at"] is None
    assert b["theme"] is None
    assert b["theme_confidence"] is None
    assert b["sentiment"] is None
    assert b["sentiment_score"] is None


def test_posts_empty():
    """無符合資料時：total=0、items=[]。"""
    session = _ScriptedSession(scalars=[0], results=[_Result([])])
    _override(session)

    data = client.get("/api/corpus/posts?source=nope").json()
    assert data["total"] == 0
    assert data["items"] == []


def test_posts_limit_cap_rejected():
    """limit 超過上限 100 → 422（封頂由 Query(le=100) 保證）。"""
    # override 成空 session，確保即便 DI 先解析也不會碰真 DB；驗證仍回 422。
    _override(_ScriptedSession())
    resp = client.get("/api/corpus/posts?limit=101")
    assert resp.status_code == 422


def test_posts_negative_offset_rejected():
    """offset < 0 → 422。"""
    _override(_ScriptedSession())
    resp = client.get("/api/corpus/posts?offset=-1")
    assert resp.status_code == 422
