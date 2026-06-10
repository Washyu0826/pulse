"""/api/events/today 端點測試 —— 不需 DB（端點讀檔，不查資料庫）。

驗證：
- 寫一個臨時 JSONL → 端點回傳正確對映的 EventSummary 形狀（含 camelCase 別名）。
- 來源檔不存在 → 回 []。
- 主題兜底（未知/缺值 → 「其他」）、壞行略過、limit 生效。
"""
import json

import pytest
from fastapi.testclient import TestClient

from api.config import settings
from api.main import app

client = TestClient(app)


@pytest.fixture
def events_file(tmp_path, monkeypatch):
    """回傳一個「寫入並指向設定」的 helper；每次呼叫覆寫 settings.events_file。"""
    def _write(lines: list[str]) -> str:
        p = tmp_path / "events_today.jsonl"
        p.write_text("\n".join(lines), encoding="utf-8")
        monkeypatch.setattr(settings, "events_file", str(p))
        return str(p)

    return _write


def _rec(**ov) -> str:
    base = {
        "event_id": "evt_001",
        "title": "OpenAI 發表 GPT-5",
        "summary": "OpenAI 發表 GPT-5[1]，價格維持不變[2]。",
        "citations": [
            {"n": 1, "url": "https://example.com/a", "post_id": "9001"},
            {"n": 2, "source": "Threads"},
        ],
        "member_count": 4,
        "theme": "模型動態",
        "faithfulness_score": 0.97,
        "issues": {"unsupported": []},
    }
    base.update(ov)
    return json.dumps(base, ensure_ascii=False)


def test_maps_record_to_event_summary_shape(events_file):
    events_file([_rec()])
    resp = client.get("/api/events/today")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list) and len(data) == 1
    ev = data[0]

    # 前端必填欄位（camelCase）全部存在且對映正確。
    assert ev["id"] == "evt_001"
    assert ev["title"] == "OpenAI 發表 GPT-5"
    assert "[1]" in ev["summary"]
    assert ev["memberCount"] == 4
    assert ev["theme"] == "模型動態"

    # 後端專用欄位不外洩。
    assert "faithfulness_score" not in ev
    assert "issues" not in ev
    assert "member_count" not in ev  # 只用 camelCase 別名

    # citations：n/url/postId 對映；缺 url/post_id 時為 None。
    cits = ev["citations"]
    assert cits[0] == {"n": 1, "url": "https://example.com/a", "postId": "9001"}
    assert cits[1]["n"] == 2
    assert cits[1]["url"] is None
    assert cits[1]["postId"] is None


def test_missing_file_returns_empty(monkeypatch):
    monkeypatch.setattr(settings, "events_file", "does/not/exist.jsonl")
    resp = client.get("/api/events/today")
    assert resp.status_code == 200
    assert resp.json() == []


def test_empty_file_returns_empty(events_file):
    events_file([])
    resp = client.get("/api/events/today")
    assert resp.status_code == 200
    assert resp.json() == []


def test_unknown_or_missing_theme_falls_back_to_other(events_file):
    events_file([_rec(theme="不存在的主題"), _rec(event_id="evt_002", theme=None)])
    data = client.get("/api/events/today").json()
    assert [e["theme"] for e in data] == ["其他", "其他"]


def test_bad_lines_skipped_and_record_without_summary_dropped(events_file):
    events_file([
        "{ not json",                       # 壞 JSON → 略過
        json.dumps({"event_id": "x", "title": "無摘要"}),  # 缺 summary → 略過
        _rec(event_id="evt_ok"),
    ])
    data = client.get("/api/events/today").json()
    assert [e["id"] for e in data] == ["evt_ok"]


def test_limit_is_respected(events_file):
    events_file([_rec(event_id=f"evt_{i}") for i in range(10)])
    data = client.get("/api/events/today?limit=3").json()
    assert len(data) == 3


def test_event_id_falls_back_to_line_number(events_file):
    events_file([_rec(event_id=None)])
    data = client.get("/api/events/today").json()
    assert data[0]["id"] == "1"  # 缺 event_id → 用行號
