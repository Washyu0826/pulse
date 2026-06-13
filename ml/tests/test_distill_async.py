"""
蒸餾 async 路徑測試 —— mock httpx，不打真實 Ollama。

純函式（prompt / parse）測試在 test_distill.py；這裡補 `Distiller.label` 的 async 編排：
注入一個假 client（async post → 假 response），驗證
- 正常回應被正確解析成標籤；
- 單筆服務錯誤（client.post 丟例外）被吞掉回 None（不中斷整批）；
- HTTP 4xx/5xx（raise_for_status 丟）回 None；
- payload 帶 temperature=0（標註要可重現）。

不需 pytest-asyncio：用 asyncio.run 驅動協程（與 scripts/evaluate.py 同套路）。
"""
import asyncio

import pytest

from ml.distill import Distiller


class _FakeResponse:
    """假 httpx.Response：可設 response 文字與是否 raise_for_status 丟錯。"""

    def __init__(self, text: str = "", *, raise_status: bool = False) -> None:
        self._text = text
        self._raise_status = raise_status

    def json(self) -> dict:
        return {"response": self._text}

    def raise_for_status(self) -> None:
        if self._raise_status:
            raise RuntimeError("HTTP 500")


class _FakeClient:
    """假 AsyncClient：記錄送出的 payload，post 依設定回應或丟例外。"""

    def __init__(self, response: _FakeResponse | None = None, *, raise_on_post: bool = False) -> None:
        self._response = response or _FakeResponse("")
        self._raise_on_post = raise_on_post
        self.calls: list[dict] = []

    async def post(self, url: str, json: dict | None = None):  # noqa: A002 - 對齊 httpx 介面
        self.calls.append({"url": url, "json": json})
        if self._raise_on_post:
            raise ConnectionError("connection refused")
        return self._response


def _distiller() -> Distiller:
    # httpx 在 __init__ 才 import；測試環境有裝（ml 依賴），故可建。
    return Distiller(model="qwen2.5:7b", host="http://localhost:11434")


def test_label_parses_valid_sentiment_response():
    d = _distiller()
    client = _FakeClient(_FakeResponse("positive"))
    out = asyncio.run(d.label("Qwen 本地翻譯品質意外地好", "sentiment", client=client))
    assert out == "positive"
    # 打到 Ollama 的 generate 端點，且帶 temperature=0（可重現）。
    assert client.calls[0]["url"].endswith("/api/generate")
    assert client.calls[0]["json"]["options"]["temperature"] == 0


def test_label_parses_theme_english_key():
    d = _distiller()
    client = _FakeClient(_FakeResponse("tool"))
    out = asyncio.run(d.label("Anthropic 發表 Claude Skills", "theme", client=client))
    assert out == "新工具"


def test_label_unparseable_response_returns_none():
    d = _distiller()
    client = _FakeClient(_FakeResponse("完全無法解析的胡言亂語"))
    out = asyncio.run(d.label("隨便", "sentiment", client=client))
    assert out is None


def test_label_connection_error_returns_none_not_raise():
    """單筆連線失敗 → 回 None（呼叫端略過），不該把整批蒸餾炸掉。"""
    d = _distiller()
    client = _FakeClient(raise_on_post=True)
    out = asyncio.run(d.label("文本", "theme", client=client))
    assert out is None


def test_label_http_error_status_returns_none():
    d = _distiller()
    client = _FakeClient(_FakeResponse("positive", raise_status=True))
    out = asyncio.run(d.label("文本", "sentiment", client=client))
    assert out is None


def test_label_rejects_unknown_task():
    d = _distiller()
    client = _FakeClient(_FakeResponse("positive"))
    with pytest.raises(ValueError):
        asyncio.run(d.label("文本", "not_a_task", client=client))
