"""
翻譯模組測試 —— 純函式 needs_translation/_clean + async translate（mock httpx，不打 Ollama）。

驗證：
- needs_translation：英文要翻、中文跳過、太短跳過；
- _clean：去引號 + 強制繁體（s2tw）；
- Translator.translate：英文 → 注入假 client 回譯文；中文 → 不打 client 直接回 None；
- 單筆服務錯誤 → 回 None（不中斷整批）。

不需 pytest-asyncio：用 asyncio.run 驅動協程。
"""
import asyncio

from ml.translate import Translator, needs_translation


# ---- 純函式：needs_translation ----
def test_needs_translation_english_yes_chinese_no():
    assert needs_translation("Claude Opus released with new benchmarks") is True
    assert needs_translation("在 Gemini Canvas 做完 App 要怎麼上線") is False


def test_needs_translation_too_short_is_false():
    assert needs_translation("") is False
    assert needs_translation("hi") is False  # < 3 字元


def test_needs_translation_threshold_boundary():
    # 高 CJK 比例（超過門檻）→ 不需翻。
    assert needs_translation("AI 模型 很強 厲害 不錯 讚") is False


# ---- 純函式：_clean（透過 translate 間接驗，也直接測 _clean）----
def test_clean_strips_quotes_and_forces_traditional():
    from ml.translate import _clean

    # 簡體 + 引號 → 去引號 + 繁體化。
    out = _clean('"这是测试"')
    assert '"' not in out
    assert "這" in out  # s2tw：这→這
    assert "测" not in out  # 测→測


# ---- 純函式：_protect_terms（後處理保護詞表）----
def test_protect_terms_restores_product_names():
    from ml.translate import _protect_terms

    # 音譯 / 誤翻校回英文原名（content-quality backlog #3）。
    assert _protect_terms("克勞德碼很好用") == "Claude Code很好用"
    assert _protect_terms("克勞德程式碼") == "Claude Code"
    assert _protect_terms("用克勞德寫程式") == "用Claude寫程式"
    assert _protect_terms("Claude寓言 5 上線") == "Claude Fable 5 上線"


def test_protect_terms_keeps_show_ask_hn_english():
    from ml.translate import _protect_terms

    assert _protect_terms("秀 HN：開源工具") == "Show HN：開源工具"
    assert _protect_terms("問HN：有人試過嗎") == "Ask HN：有人試過嗎"


def test_protect_terms_collapses_repeated_punct_noise():
    from ml.translate import _protect_terms

    # qwen 偶吐連續破折號 / 標點雜訊 → 壓成單一。
    assert _protect_terms("標題————副標") == "標題—副標"
    assert _protect_terms("結尾。。。。") == "結尾。"


def test_clean_applies_term_protection_after_traditional():
    from ml.translate import _clean

    # s2tw 後再校專名：簡體「克劳德」→繁「克勞德」→「Claude」。
    assert _clean("克劳德 发布新版") .startswith("Claude")


# ---- async：translate（mock httpx client）----
class _FakeResponse:
    def __init__(self, text: str = "", *, raise_status: bool = False) -> None:
        self._text = text
        self._raise_status = raise_status

    def json(self) -> dict:
        return {"response": self._text}

    def raise_for_status(self) -> None:
        if self._raise_status:
            raise RuntimeError("HTTP 503")


class _FakeClient:
    def __init__(self, response: _FakeResponse | None = None, *, raise_on_post: bool = False) -> None:
        self._response = response or _FakeResponse("")
        self._raise_on_post = raise_on_post
        self.calls: list[dict] = []

    async def post(self, url: str, json: dict | None = None):  # noqa: A002 - 對齊 httpx 介面
        self.calls.append({"url": url, "json": json})
        if self._raise_on_post:
            raise ConnectionError("connection refused")
        return self._response


def _translator() -> Translator:
    return Translator(model="qwen2.5:7b", host="http://localhost:11434")


def test_translate_english_returns_cleaned_traditional():
    tr = _translator()
    client = _FakeClient(_FakeResponse("克劳德 发布新版本"))  # 模型可能吐簡體
    out = asyncio.run(tr.translate("Claude released a new version", client=client))
    assert out is not None
    # s2tw 強制繁體：发→發、布→佈、劳→勞；簡體字應已消失。
    assert "發" in out and "佈" in out
    assert "发" not in out and "劳" not in out
    # 有打到 Ollama generate 端點、溫度 0。
    assert client.calls[0]["url"].endswith("/api/generate")
    assert client.calls[0]["json"]["options"]["temperature"] == 0


def test_translate_chinese_skips_without_calling_ollama():
    tr = _translator()
    client = _FakeClient(_FakeResponse("不應該被用到"))
    out = asyncio.run(tr.translate("在 Gemini Canvas 做完 App 要怎麼上線", client=client))
    assert out is None
    assert client.calls == []  # needs_translation=False → 根本不打 client


def test_translate_connection_error_returns_none():
    tr = _translator()
    client = _FakeClient(raise_on_post=True)
    out = asyncio.run(tr.translate("Some English text to translate", client=client))
    assert out is None


def test_translate_http_error_returns_none():
    tr = _translator()
    client = _FakeClient(_FakeResponse("whatever", raise_status=True))
    out = asyncio.run(tr.translate("Some English text to translate", client=client))
    assert out is None


def test_translate_empty_model_output_returns_none():
    tr = _translator()
    client = _FakeClient(_FakeResponse("   "))  # 清理後空字串
    out = asyncio.run(tr.translate("Some English text to translate", client=client))
    assert out is None
