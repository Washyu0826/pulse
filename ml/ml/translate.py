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
from typing import Any

from opencc import OpenCC

__all__ = ["needs_translation", "Translator"]

logger = logging.getLogger(__name__)

_s2tw = OpenCC("s2tw")  # 簡→繁（保險）
_CJK = re.compile(r"[一-鿿]")

_OLLAMA = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
_MODEL = os.environ.get("PULSE_TRANSLATE_MODEL", "qwen2.5:7b")

# 實測有效：英文指令 + 保留專名 + 只輸出譯文。
# 強化（content-quality backlog #3）：qwen2.5:7b 會 (a) 音譯專名（Claude→克勞德、
# Fable→寓言）、(b) 漏翻大寫英文（SHIPPING / ISSUE）、(c) 直譯 Show HN/Ask HN、
# (d) 亂加 emoji。逐條用明確指令壓制；無法靠 prompt 完全根治的（音譯）再靠後處理
# 保護詞表 _protect_terms 校正。
_PROMPT = (
    "You are a professional EN->Traditional Chinese (Taiwan) translator for AI tech "
    "news headlines. Translate the text below.\n"
    "STRICT RULES:\n"
    "1. Keep ALL product, model, company, library, and tool names in their original "
    "English spelling. NEVER transliterate or translate them. Examples that MUST stay "
    "verbatim: Claude, Claude Code, Codex, GPT, GPT-5, OpenAI, Anthropic, Gemini, "
    "DeepSeek, MCP, RAG, LLM, SDK, CLI, Fable, Mythos, Conductor, VS Code.\n"
    "2. Keep ALL Latin-script words, acronyms, and ALL-CAPS words in English (do not "
    "leave any English word untranslated by accident, but proper nouns / tech terms "
    "stay English).\n"
    "3. Keep 'Show HN' and 'Ask HN' exactly as-is (do NOT translate to 秀HN/問HN).\n"
    "4. Do NOT add emoji, quotation marks, notes, or explanations.\n"
    "5. Output ONLY the translation on a single line.\n\n"
    "Text:\n{text}"
)

# 後處理保護詞表：模型若把專名音譯/亂翻，這裡用 regex 強制校回英文原名。
# key 為「會出現在模型輸出裡的錯誤寫法」（含常見音譯與被拆開的變體），value 為正名。
# 注意：在 s2tw 轉繁之後比對，故 key 用繁體。順序：長詞先於短詞，避免「Claude Code」
# 被「Claude」先吃掉。
_TERM_FIXES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"克勞德[\s ]*(?:程式)?碼"), "Claude Code"),  # 克勞德碼 / 克勞德程式碼
    (re.compile(r"克勞德"), "Claude"),
    (re.compile(r"(?:Claude|克勞德)[\s ]*寓言"), "Claude Fable"),  # Fable 被翻成「寓言」
    (re.compile(r"(?<![A-Za-z])寓言(?=[\s ]*\d)"), "Fable"),  # 「寓言 5」→ Fable 5
    (re.compile(r"秀[\s ]*HN"), "Show HN"),
    (re.compile(r"問[\s ]*HN"), "Ask HN"),
]
_DUP_PUNCT_RE = re.compile(r"([^\w\s])\1{2,}")  # 連續 3+ 個相同標點/符號（去 ooooo / —— 噪音）


def needs_translation(text: str, *, cjk_threshold: float = 0.15) -> bool:
    """是否需要翻譯：非空、且 CJK 比例低（≈英文）。純函式，可測。"""
    t = (text or "").strip()
    if len(t) < 3:
        return False
    cjk = len(_CJK.findall(t))
    return cjk / max(len(t), 1) < cjk_threshold


def _protect_terms(text: str) -> str:
    """後處理：把被音譯/誤翻的專名校回英文原名，並壓掉重複標點噪音。純函式，可測。

    解掉 qwen 殘留的音譯（克勞德→Claude、寓言→Fable）與 Show HN/Ask HN 直譯。
    在 s2tw 轉繁之後套用（_TERM_FIXES 的 key 用繁體），避免簡繁不一致漏配。
    """
    for pat, repl in _TERM_FIXES:
        text = pat.sub(repl, text)
    return _DUP_PUNCT_RE.sub(r"\1", text)


def _clean(raw: str) -> str:
    """整理模型輸出：去頭尾空白/引號、強制繁體、校正專名、壓重複標點。"""
    s = (raw or "").strip().strip('"「」').strip()
    s = _s2tw.convert(s)
    return _protect_terms(s)


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

    async def translate(self, text: str, client: Any = None) -> str | None:
        # client: httpx.AsyncClient（lazy import，故型別以 Any 標避免模組頂層 import httpx）。
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
