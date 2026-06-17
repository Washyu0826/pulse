"""
scripts/ 的純 helper 測試 —— 用 importlib 載入腳本（重依賴 torch/transformers 只在 main 內 import，
模組層只有輕量 import），驗證 evaluate.py 與 train_classifier.py 不需 GPU/DB 的核心邏輯。
"""
import importlib.util
import os
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]  # D:\pulse
sys.path.insert(0, str(_ROOT / "ml"))


def _load(mod_name: str, rel: str):
    spec = importlib.util.spec_from_file_location(mod_name, _ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def ev():
    return _load("pulse_evaluate", "scripts/evaluate.py")


@pytest.fixture(scope="module")
def tr():
    return _load("pulse_train", "scripts/train_classifier.py")


@pytest.fixture(scope="module")
def nl():
    return _load("pulse_send_newsletter", "scripts/send_newsletter.py")


# ---------------- evaluate.py ----------------
def test_evaluate_confidence(ev):
    assert ev._confidence("a", {"a": 0.7, "b": 0.3}) == 0.7
    assert ev._confidence("a", None) == 1.0  # 無機率（Qwen 硬標）→ 1.0
    assert ev._confidence("c", {"a": 0.7, "b": 0.3}) == 0.7  # pred 不在 dict → 取 max


def test_evaluate_calibration_proper_probs(ev):
    labels = ["a", "b"]
    preds = [("a", {"a": 0.9, "b": 0.1}), ("b", {"a": 0.2, "b": 0.8}), ("a", {"a": 0.6, "b": 0.4})]
    y_true = ["a", "b", "b"]  # 第三筆錯
    c = ev._calibration(preds, y_true, labels)
    assert c["available"] is True
    assert c["proper_probs"] is True
    assert c["brier"] is not None and c["nll"] is not None
    assert 0.0 <= c["ece_15bin"] <= 1.0
    assert "1.0" in c["acc_at_coverage"]  # coverage 鍵以字串存


def test_evaluate_calibration_unavailable_without_probs(ev):
    preds = [("a", None), ("b", None)]
    c = ev._calibration(preds, ["a", "b"], ["a", "b"])
    assert c["available"] is False


def test_evaluate_load_gold_filters(ev, tmp_path):
    from ml.annotation import save_jsonl

    p = tmp_path / "gold.jsonl"
    save_jsonl(p, [
        {"post_id": 1, "sentiment": "positive", "text": "好", "round": 1},
        {"post_id": 2, "sentiment": "bogus", "text": "x", "round": 1},   # 非法標籤 → 濾
        {"post_id": 3, "sentiment": "negative", "text": "", "round": 1},  # 空文字 → 濾
        {"post_id": 4, "sentiment": "neutral", "text": "中", "round": 2},  # round=2 → 濾
        {"post_id": 5, "sentiment": "neutral", "text": "中性", "round": 1},
    ])
    gold = ev._load_gold(p, "sentiment")
    assert gold == [("好", "positive"), ("中性", "neutral")]


def test_evaluate_theme_labels_in_sync(ev):
    from ml.annotation import THEME_LABELS

    assert tuple(ev.LABELS["theme"]) == THEME_LABELS  # 與標註器同一套主題


# ---------------- train_classifier.py ----------------
def test_train_load_examples_sentiment_round1_only(tr, tmp_path):
    from ml.annotation import save_jsonl

    p = tmp_path / "gold.jsonl"
    save_jsonl(p, [
        {"post_id": 1, "sentiment": "positive", "text": "a", "round": 1},
        {"post_id": 2, "sentiment": "negative", "text": "b", "round": 2},  # round=2 跳過
    ])
    ex = tr._load_examples(p, "sentiment", round1_only=True)
    assert ex == [("a", "positive")]


def test_train_load_examples_theme_uses_label_fallback(tr, tmp_path):
    from ml.annotation import save_jsonl

    # silver 記錄用 'label' 欄；gold 用任務欄（這裡測 silver 的 label fallback）
    p = tmp_path / "silver.jsonl"
    save_jsonl(p, [
        {"post_id": 1, "label": "模型動態", "text": "比較", "task": "theme"},
        {"post_id": 2, "label": "不存在", "text": "x", "task": "theme"},  # 非法 → 濾
    ])
    ex = tr._load_examples(p, "theme", round1_only=False)
    assert ex == [("比較", "模型動態")]


def test_train_theme_labels_in_sync(tr):
    from ml.annotation import THEME_LABELS

    assert tuple(tr.LABELS["theme"]) == THEME_LABELS


# ---------------- send_newsletter.py 編排（dry-run，monkeypatch DB/摘要/題圖）----------------
def test_load_dotenv_does_not_override(nl, tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("PULSE_X=fromfile\nPULSE_Y=y  # 註解\n# 整行註解\n", encoding="utf-8")
    monkeypatch.setenv("PULSE_X", "fromenv")  # 已存在 → 不覆蓋
    monkeypatch.delenv("PULSE_Y", raising=False)
    nl._load_dotenv(env)
    assert os.environ["PULSE_X"] == "fromenv"
    assert os.environ["PULSE_Y"] == "y"  # 行內註解被去掉


def test_newsletter_dry_run_writes_html(nl, tmp_path, monkeypatch):
    import argparse
    import asyncio

    posts = [
        {"id": 1, "theme": "新工具", "sentiment": "positive", "score": 30,
         "title": "Claude Skills 發表", "title_zh": "Claude Skills 發表", "url": "http://x", "source": "threads"},
        {"id": 2, "theme": "使用方法", "sentiment": "neutral", "score": 10,
         "title": "我的 prompt 工作流", "url": "http://y", "source": "threads"},
    ]

    async def fake_fetch(days, min_quality):
        return posts, ["MCP", "Claude"]

    async def fake_summarize(titles):
        return "今日 AI 圈聚焦新工具與使用方法。"

    monkeypatch.setattr(nl, "_fetch", fake_fetch)
    monkeypatch.setattr(nl, "_summarize", fake_summarize)
    monkeypatch.setattr(nl, "_generate_cover", lambda *a, **k: None)  # 跳過 SD

    args = argparse.Namespace(
        to=None, days=1, min_quality=30, per_theme=3, no_cover=True,
        seed=1, dry_run=True, out=tmp_path / "nl",
    )
    asyncio.run(nl.main_async(args))

    html = (tmp_path / "nl" / "newsletter.html").read_text(encoding="utf-8")
    assert "Pulse 每日 AI 情報" in html
    assert "Claude Skills 發表" in html        # 精選貼文進了信
    assert "今日 AI 圈聚焦新工具與使用方法" in html  # 摘要進了信（Swiss 行內、完整保留）
    assert "MCP" in html                       # 熱詞（Swiss 熱詞無 #）
