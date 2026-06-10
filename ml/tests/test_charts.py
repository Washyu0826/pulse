"""電子報圖表測試 —— 需 matplotlib（未裝則 skip）；驗證產出合法 PNG bytes。"""
import pytest

pytest.importorskip("matplotlib")

from ml.charts import sentiment_bar_png, theme_bar_png  # noqa: E402

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def test_theme_bar_returns_png_bytes():
    data = theme_bar_png({"新工具": 5, "模型動態": 3, "使用方法": 8, "其他": 1})
    assert isinstance(data, bytes) and data.startswith(_PNG_MAGIC)
    assert len(data) > 1000  # 真的有畫東西


def test_theme_bar_handles_empty():
    data = theme_bar_png({})  # 全 0 → 走「今日無資料」分支，不可 crash
    assert data.startswith(_PNG_MAGIC)


def test_sentiment_bar_returns_png_bytes():
    data = sentiment_bar_png({"positive": 7, "neutral": 4, "negative": 2})
    assert data.startswith(_PNG_MAGIC)
