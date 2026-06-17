"""/api/feed* 端點測試 —— 不需 live Postgres（同 test_corpus 的 _ScriptedSession 手法）。

涵蓋 UX P0 修復的兩個契約（docs/ux/research/00-action-plan.md #1 #2）：
- 主題契約：ACTIONABLE_THEMES / Theme Literal 升級為 5 主題（與 ml/ml/theme.py、
  前端 theme-meta.tsx 對齊），DB 殘留的舊「邊界」標籤在查詢層映射到「風險限制」。
- 來源契約：Source Literal 補 `ptt`（前端 SOURCE_ORDER 有，之前選了直接 422）。
"""
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from api.database import get_db
from api.main import app
from api.services.feed import ACTIONABLE_THEMES, _db_labels


class _Row:
    """模擬 SQLAlchemy Row：屬性存取。"""

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
    """假 async session：execute() 依序吐出預排好的結果。"""

    def __init__(self, results=None):
        self._results = list(results or [])

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

EXPECTED_THEMES = ("新工具", "模型動態", "使用方法", "風險限制", "倫理法規")


# ---------- 主題契約（P0 #1） ----------


def test_actionable_themes_match_ml_taxonomy():
    """後端主題集合 = ml/ml/theme.py THEME_HYPOTHESES 的 5 主題（順序＝首頁分區順序）。"""
    assert ACTIONABLE_THEMES == EXPECTED_THEMES


def test_db_labels_maps_legacy_boundary_into_risk():
    """legacy「邊界」併入「風險限制」查詢；其餘主題不受影響。"""
    assert _db_labels("風險限制") == ("風險限制", "邊界")
    assert _db_labels("新工具") == ("新工具",)


def test_feed_returns_all_five_themes():
    """/feed 不指定 theme → 回傳鍵 = 5 主題（前端 THEME_ORDER ⊆ 回傳鍵的 contract test）。"""
    # 每主題各一次 rows 查詢（空 → 不再查 slugs），共 5 次 execute。
    _override(_ScriptedSession(results=[_Result([]) for _ in range(5)]))

    resp = client.get("/api/feed")
    assert resp.status_code == 200
    assert tuple(resp.json().keys()) == EXPECTED_THEMES


def test_feed_single_theme_outputs_canonical_label():
    """指定 theme=風險限制：命中 legacy「邊界」資料列時，輸出 theme 一律為正規標籤。"""
    now = datetime(2026, 6, 11, 12, 0, tzinfo=UTC)
    row = _Row(
        id=7, title="AI 幻覺踩雷", content="內文", source="ptt",
        url="https://example.com", permalink=None, posted_at=now, score=10,
        num_comments=2,
        confidence=0.81, sentiment=None, title_zh=None, snippet_zh=None,
    )
    # 查詢順序：rows → slugs（rows 非空才查）。
    _override(_ScriptedSession(results=[_Result([row]), _Result([])]))

    resp = client.get("/api/feed", params={"theme": "風險限制"})
    assert resp.status_code == 200
    data = resp.json()
    assert list(data.keys()) == ["風險限制"]
    assert data["風險限制"][0]["theme"] == "風險限制"


def _post_row(id, source, score, *, num_comments=0):
    """完整貼文資料列（含 per-source 平衡排序需要的 source/score/num_comments）。"""
    now = datetime(2026, 6, 11, 12, 0, tzinfo=UTC)
    return _Row(
        id=id, title=f"t{id}", content="內文", source=source,
        url=f"https://example.com/{id}", permalink=None, posted_at=now,
        score=score, num_comments=num_comments,
        confidence=0.8, sentiment=None, title_zh=None, snippet_zh=None,
    )


def test_feed_balanced_ranking_mixes_sources_not_all_threads():
    """per-source 平衡排序：候選池中 Threads 數量遠多於 HN，結果仍兩來源都露出、
    不被 Threads 100% 洗版（取代純時間排序）。"""
    # 候選池：5 篇 threads（低互動量級）+ 1 篇 hackernews（高量級）。純時間/數量排序
    # 若 threads 較新會全是 threads；rank_balanced round-robin → 第一輪各來源各取一篇。
    candidate_rows = [
        _post_row(1, "threads", 8),
        _post_row(2, "threads", 6),
        _post_row(3, "threads", 5),
        _post_row(4, "threads", 4),
        _post_row(5, "threads", 3),
        _post_row(6, "hackernews", 500),
    ]
    # 查詢順序：候選池 rows → slugs（rows 非空才查）。
    _override(_ScriptedSession(results=[_Result(candidate_rows), _Result([])]))

    resp = client.get("/api/feed", params={"theme": "新工具", "limit_per_theme": 2})
    assert resp.status_code == 200
    items = resp.json()["新工具"]
    assert len(items) == 2
    srcs = {it["source"] for it in items}
    assert srcs == {"threads", "hackernews"}  # 兩來源都露出，非兩篇全 threads


def test_feed_legacy_boundary_theme_param_rejected():
    """舊「邊界」不再是合法查詢值（前端不會送；legacy 只活在查詢層映射）→ 422。"""
    _override(_ScriptedSession())
    assert client.get("/api/feed", params={"theme": "邊界"}).status_code == 422


def test_feed_summary_merges_legacy_boundary_count():
    """/feed/summary：「邊界」計數併入「風險限制」，不讓資料默默消失；缺鍵補 0。"""
    _override(
        _ScriptedSession(
            results=[_Result([_Row(label="風險限制", n=2), _Row(label="邊界", n=3), _Row(label="新工具", n=4)])]
        )
    )

    resp = client.get("/api/feed/summary")
    assert resp.status_code == 200
    assert resp.json() == {
        "新工具": 4, "模型動態": 0, "使用方法": 0, "風險限制": 5, "倫理法規": 0,
    }


# ---------- 來源契約（P0 #2） ----------


def test_feed_source_ptt_accepted():
    """前端 SOURCE_ORDER 含 ptt → 後端不可再 422。"""
    _override(_ScriptedSession(results=[_Result([]) for _ in range(5)]))
    assert client.get("/api/feed", params={"source": "ptt"}).status_code == 200


def test_feed_summary_source_ptt_accepted():
    _override(_ScriptedSession(results=[_Result([])]))
    assert client.get("/api/feed/summary", params={"source": "ptt"}).status_code == 200


def test_feed_unknown_source_rejected():
    """不在 Literal 的來源仍要擋（422）。"""
    _override(_ScriptedSession())
    assert client.get("/api/feed", params={"source": "facebook"}).status_code == 422
