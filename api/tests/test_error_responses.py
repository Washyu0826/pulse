"""錯誤回應契約測試 —— 不需 DB（驗證在進 DB 前就觸發）。

鎖住本輪硬化加上的輸入驗證與錯誤封套：
- 422：缺必填 / 超出長度或範圍上限的查詢參數（走全域 RequestValidationError → 自訂封套）。
- 400：商業規則錯誤（collection pack 空清單 / 超量）。
所有 422 都應回統一封套 {"error": "validation_error", "detail": [...], "request_id": ...}。
"""
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def _assert_validation_envelope(resp) -> None:
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"] == "validation_error"
    assert isinstance(body["detail"], list)  # FastAPI 的 errors() 結構
    assert "request_id" in body


def test_decide_requires_models_param():
    """decide 的 models 為必填 → 缺則 422。"""
    _assert_validation_envelope(client.get("/api/decide"))


def test_decide_topic_length_capped():
    """topic 超過 max_length(100) → 422（防止昂貴子字串搜尋）。"""
    _assert_validation_envelope(
        client.get("/api/decide", params={"models": "claude", "topic": "x" * 101})
    )


def test_corpus_posts_limit_capped():
    """corpus limit 超過上限(100) → 422。"""
    _assert_validation_envelope(client.get("/api/corpus/posts", params={"limit": 999}))


def test_corpus_posts_negative_offset_rejected():
    """offset 須 >= 0 → 負值 422。"""
    _assert_validation_envelope(client.get("/api/corpus/posts", params={"offset": -1}))


def test_events_today_limit_capped():
    """events/today limit 超過上限(100) → 422。"""
    _assert_validation_envelope(client.get("/api/events/today", params={"limit": 999}))


def test_model_detail_trend_days_out_of_range():
    """model detail 的 trend_days 須在 7..90 → 超出 422（驗證早於 DB 查詢）。"""
    _assert_validation_envelope(
        client.get("/api/models/anything", params={"trend_days": 999})
    )


def test_collection_pack_empty_is_400():
    """空收藏 → 400（商業規則，非驗證錯誤）。"""
    resp = client.post("/api/collection/pack", json={"posts": [], "distill": False})
    assert resp.status_code == 400


def test_collection_pack_over_cap_is_400():
    """超過單次上限(100 篇) → 400。"""
    posts = [{"title": "t"} for _ in range(101)]
    resp = client.post(
        "/api/collection/pack", json={"posts": posts, "distill": False}
    )
    assert resp.status_code == 400
