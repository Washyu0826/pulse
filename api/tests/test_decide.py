"""決策報告純邏輯測試 —— 不需 DB（_recommend / _template_summary 為純函式）。"""
from api.services.decide import _recommend, _template_summary


def _m(slug: str, name: str, idx: int | None, total: int = 100, recent: int = 10) -> dict:
    return {
        "slug": slug,
        "name": name,
        "sentiment_index": idx,
        "posts_total": total,
        "posts_recent": recent,
        "top_discussions": [],
    }


def test_recommend_by_sentiment():
    rec = _recommend([_m("a", "A", 3), _m("b", "B", 13), _m("c", "C", 7)])
    assert rec["winner"] == "b"  # 口碑最高


def test_recommend_tie_breaks_on_volume():
    rec = _recommend([_m("a", "A", 7, total=100), _m("b", "B", 7, total=500)])
    assert rec["winner"] == "b"  # 同口碑時看討論量


def test_recommend_no_sentiment_falls_back_to_volume():
    rec = _recommend([_m("a", "A", None, total=50), _m("b", "B", None, total=200)])
    assert rec["winner"] == "b"


def test_recommend_empty():
    assert _recommend([])["winner"] is None


def test_template_summary_lists_models_and_verdict():
    s = _template_summary("coding", [_m("a", "A", 3), _m("b", "B", 13)], {"winner": "b", "reason": "B 最佳"})
    assert "A" in s and "B" in s and "建議" in s and "coding" in s
