"""/api/storylines 端點測試 —— 不需 DB（端點讀檔，不查資料庫）。

驗證：
- 寫一個臨時 JSONL → 端點回傳正確對映的 Storyline 形狀（含 camelCase 別名 spanDays）。
- 來源檔不存在 / 空 → 回 []。
- 狀態/主題兜底、缺 timeline 的記錄略過、壞行略過、limit 生效、參數驗證（422）。
"""
import json

import pytest
from fastapi.testclient import TestClient

from api.config import settings
from api.main import app

client = TestClient(app)


@pytest.fixture
def storylines_file(tmp_path, monkeypatch):
    """寫入並指向設定的 helper；覆寫 settings.storylines_file。"""
    def _write(lines: list[str]) -> str:
        p = tmp_path / "storylines.jsonl"
        p.write_text("\n".join(lines), encoding="utf-8")
        monkeypatch.setattr(settings, "storylines_file", str(p))
        return str(p)

    return _write


def _rec(**ov) -> str:
    base = {
        "id": "story_001",
        "title": "GPT-5 發表後社群討論升溫",
        "state": "升溫",
        "hotness": 42.5,
        "span_days": 3,
        "theme": "模型動態",
        "timeline": [
            {"date": "2026-06-15", "summary": "首日出現", "volume": 5.0, "velocity": 0.0,
             "state": "升溫", "sources": ["hackernews"], "members": 3},
            {"date": "2026-06-16", "summary": "討論擴散", "volume": 9.0, "velocity": 4.0,
             "state": "升溫", "sources": ["hackernews", "devto"], "members": 6},
            {"date": "2026-06-17", "summary": "達到高峰", "volume": 12.0, "velocity": 3.0,
             "state": "高峰", "sources": ["hackernews", "devto"], "members": 8},
        ],
        "citations": [
            {"n": 1, "url": "https://example.com/a", "title": "首日出現"},
            {"n": 2, "title": "討論擴散"},
        ],
    }
    base.update(ov)
    return json.dumps(base, ensure_ascii=False)


def test_maps_record_to_storyline_shape(storylines_file):
    storylines_file([_rec()])
    resp = client.get("/api/storylines")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list) and len(data) == 1
    s = data[0]

    assert s["id"] == "story_001"
    assert s["title"] == "GPT-5 發表後社群討論升溫"
    assert s["state"] == "升溫"
    assert s["hotness"] == 42.5
    assert s["spanDays"] == 3  # camelCase 別名
    assert "span_days" not in s
    assert s["theme"] == "模型動態"

    tl = s["timeline"]
    assert len(tl) == 3
    assert tl[0]["date"] == "2026-06-15"
    assert tl[2]["state"] == "高峰"
    assert tl[1]["sources"] == ["hackernews", "devto"]

    cits = s["citations"]
    assert cits[0] == {"n": 1, "url": "https://example.com/a", "title": "首日出現"}
    assert cits[1]["url"] is None


def test_missing_file_returns_empty(monkeypatch):
    monkeypatch.setattr(settings, "storylines_file", "does/not/exist.jsonl")
    resp = client.get("/api/storylines")
    assert resp.status_code == 200
    assert resp.json() == []


def test_empty_file_returns_empty(storylines_file):
    storylines_file([])
    resp = client.get("/api/storylines")
    assert resp.status_code == 200
    assert resp.json() == []


def test_unknown_state_and_theme_fall_back(storylines_file):
    storylines_file([_rec(state="爆炸", theme="不存在")])
    s = client.get("/api/storylines").json()[0]
    assert s["state"] == "升溫"
    assert s["theme"] == "其他"


def test_records_without_timeline_or_title_dropped(storylines_file):
    storylines_file([
        "{ not json",                                      # 壞 JSON
        json.dumps({"id": "x", "title": "無時間軸", "timeline": []}),  # 空 timeline
        json.dumps({"id": "y", "timeline": [{"date": "2026-06-17"}]}),  # 無 title
        _rec(id="story_ok"),
    ])
    data = client.get("/api/storylines").json()
    assert [s["id"] for s in data] == ["story_ok"]


def test_timeline_point_without_date_dropped(storylines_file):
    rec = json.loads(_rec())
    rec["timeline"].append({"summary": "沒有日期", "volume": 1})  # 無 date → 略過該格
    storylines_file([json.dumps(rec, ensure_ascii=False)])
    s = client.get("/api/storylines").json()[0]
    assert len(s["timeline"]) == 3  # 仍是原 3 格，無日期那格被丟


def test_limit_is_respected(storylines_file):
    storylines_file([_rec(id=f"story_{i}") for i in range(10)])
    data = client.get("/api/storylines?limit=3").json()
    assert len(data) == 3


def test_days_param_validation(storylines_file):
    storylines_file([_rec()])
    assert client.get("/api/storylines?limit=0").status_code == 422
    assert client.get("/api/storylines?limit=101").status_code == 422


def test_id_falls_back_to_line_number(storylines_file):
    storylines_file([_rec(id=None)])
    data = client.get("/api/storylines").json()
    assert data[0]["id"] == "story_001"  # 缺 id → 用行號
