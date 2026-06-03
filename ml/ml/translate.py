"""
英→繁中翻譯 —— 地端 Ollama（qwen2.5），給 feed 中英並列用。全地端、不打雲端 API（[[prefer-local-llm]]）。

關鍵發現（實測）：qwen2.5 用「中文指令」會變聊天、不肯翻；改用**英文指令** + 只輸出譯文，
才會乖乖翻。輸出可能夾簡體 → 再用 OpenCC s2tw 強制繁體。品質為「看得懂的 gist」，
模型名偶爾音譯（克勞德）——中英並列正好補（原文都在）。

只翻英文貼（CJK 比例低）；中文貼（Threads）本就可讀 → 跳過。
純函式 needs_translation / _clean 可測；translate 需 Ollama 服務。
"""
from __future__ import annotations

import logging
import os
import re

from opencc import OpenCC

__all__ = ["needs_translation", "Translator"]

logger = logging.getLogger(__name__)

_s2tw = OpenCC("s2tw")  # 簡→繁（保險）
_CJK = re.compile(r"[一-鿿]")

_OLLAMA = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
_MODEL = os.environ.get("PULSE_TRANSLATE_MODEL", "qwen2.5:7b")

# 實測有效：英文指令 + 保留專名 + 只輸出譯文。
_PROMPT = (
    "Translate to Traditional Chinese (Taiwan). Keep product, model, and company "
    "names in English (Claude, GPT, OpenAI, MCP, etc.). Reply with ONLY the "
    "translation — no quotes, no explanation:\n\n{text}"
)


def needs_translation(text: str, *, cjk_threshold: float = 0.15) -> bool:
    """是否需要翻譯：非空、且 CJK 比例低（≈英文）。純函式，可測。"""
    t = (text or "").strip()
    if len(t) < 3:
        return False
    cjk = len(_CJK.findall(t))
    return cjk / max(len(t), 1) < cjk_threshold


def _clean(raw: str) -> str:
    """整理模型輸出：去頭尾空白/引號、強制繁體。"""
    s = (raw or "").strip().strip('"「」').strip()
    return _s2tw.convert(s)


class Translator:
    """Ollama 英→繁中翻譯器（httpx 呼叫本機服務）。"""

    def __init__(self, model: str = _MODEL, host: str = _OLLAMA, timeout: float = 120.0) -> None:
        try:
            import httpx
        except ImportError as e:
            raise ImportError("需要 httpx：pip install httpx") from e
        self._httpx = httpx
        self.model = model
        self.host = host
        self.timeout = timeout

    async def translate(self, text: str, client=None) -> str | None:
        """翻一段英文 → 繁中。需要翻才翻；失敗回 None（呼叫端略過、不 crash）。"""
        if not needs_translation(text):
            return None
        payload = {
            "model": self.model,
            "prompt": _PROMPT.format(text=text.strip()),
            "stream": False,
            "options": {"temperature": 0},
        }
        own = client is None
        if own:
            client = self._httpx.AsyncClient(timeout=self.timeout)
        try:
            r = await client.post(f"{self.host}/api/generate", json=payload)
            r.raise_for_status()
            out = _clean(r.json().get("response", ""))
            return out or None
        except Exception:  # noqa: BLE001 — 單筆翻譯失敗不該中斷整批
            logger.exception("翻譯失敗，跳過一筆")
            return None
        finally:
            if own:
                await client.aclose()


if __name__ == "__main__":
    import asyncio
    import sys

    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    async def _demo():
        tr = Translator()
        for t in [
            "Claude Opus 4.8 Released: New Features and Benchmarks",
            "Show HN: I built a self-hosted dashboard to track AI model sentiment",
            "在 Gemini Canvas 做完 App 要怎麼上線",  # 中文 → 應跳過
        ]:
            print(f"\n原: {t}\n譯: {await tr.translate(t)}")

    asyncio.run(_demo())
