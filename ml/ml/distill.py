"""
LLM 蒸餾 —— 用地端 Qwen2.5（Ollama）把中文貼文預標成 silver labels，供微調小模型。

依據：Wang et al. 2024（用 LLM 產的標籤訓練小分類器，效果可比人工標）、
Distilling Step-by-Step（ACL 2023）。全地端、不打雲端 API（[[prefer-local-llm]]）。

設計（與 translate.py 同風格）：
- 純函式 build_*_prompt / parse_* 不需 Ollama → 可單元測試。
- 英文指令 + few-shot + 只輸出單一標籤（實測 qwen 對英文指令較聽話，見 translate.py）。
- 解析 robust：大小寫無關、容忍多餘字、取最先出現的合法標籤；無法解析回 None（呼叫端略過）。
- silver labels 僅供訓練增強；gold（人工驗證）才進測試集（見 annotation-guidelines.md §7）。
"""
from __future__ import annotations

import logging
import os
from typing import Any

from ml.annotation import SENTIMENT_LABELS
from ml.theme import OTHER_LABEL, THEME_HYPOTHESES

__all__ = [
    "SENTIMENT_LABELS",
    "THEME_LABELS",
    "build_sentiment_prompt",
    "build_theme_prompt",
    "parse_sentiment",
    "parse_theme",
    "Distiller",
]

logger = logging.getLogger(__name__)

# 4 主題（與 theme.py 對齊）：邊界 / 新工具 / 使用方法 / 其他。
THEME_LABELS = (*THEME_HYPOTHESES.keys(), OTHER_LABEL)

# 主題用英文 key 讓 Qwen 輸出更穩，再 map 回中文標籤。
_THEME_KEYS = {
    "tool": "新工具",
    "model": "模型動態",
    "usage": "使用方法",
    "risk": "風險限制",
    "ethics": "倫理法規",
    "other": OTHER_LABEL,
}

_OLLAMA = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
_MODEL = os.environ.get("PULSE_DISTILL_MODEL", "qwen2.5:7b")

_SENTIMENT_PROMPT = (
    "You label the SENTIMENT of a social-media post about AI tools/models.\n"
    "Judge the AUTHOR'S attitude toward the AI tool/model/method they discuss "
    "(not how the post makes you feel).\n"
    "Reply with EXACTLY ONE word: positive, neutral, or negative. No explanation.\n\n"
    "Examples:\n"
    'Post: "DeepSeek 一直 timeout，退回 Claude 了" -> negative\n'
    'Post: "Claude Skills 發表了，提供打包 agent 能力的新方式" -> neutral\n'
    'Post: "Qwen2.5 本地跑翻譯品質意外地好，已取代付費工具" -> positive\n\n'
    'Post: "{text}" ->'
)

_THEME_PROMPT = (
    "You label the TOPIC of a social-media post about AI. Choose ONE:\n"
    "- tool: a new AI tool / app / product / feature being launched or introduced\n"
    "- model: comparison, benchmark, ranking, price, or capability update of AI models\n"
    "- usage: tips, tutorials, prompts, or workflows for using AI\n"
    "- risk: practical limitations, failures, hallucinations, or risks of AI tools\n"
    "- ethics: ethics, regulation, law, policy, or privacy concerns of AI\n"
    "- other: none of the above / off-topic\n"
    "Reply with EXACTLY ONE word: tool, model, usage, risk, ethics, or other. No explanation.\n\n"
    "Examples:\n"
    'Post: "Anthropic just launched Claude Skills" -> tool\n'
    'Post: "GPT-5 vs Claude 在 SWE-bench 誰強？順便比 API 價格" -> model\n'
    'Post: "分享我的 prompt 工作流：先列大綱再逐段展開" -> usage\n'
    'Post: "Claude 有時會編造不存在的 API，重要的事要自己查證" -> risk\n'
    'Post: "歐盟 AI Act 上路，高風險用途要注意資料隱私" -> ethics\n'
    'Post: "今天午餐吃了披薩，天氣很好" -> other\n\n'
    'Post: "{text}" ->'
)


def build_sentiment_prompt(text: str) -> str:
    """組情緒蒸餾 prompt（英文指令 + few-shot）。純函式。"""
    return _SENTIMENT_PROMPT.format(text=(text or "").strip().replace('"', "'"))


def build_theme_prompt(text: str) -> str:
    """組主題蒸餾 prompt（英文指令 + few-shot）。純函式。"""
    return _THEME_PROMPT.format(text=(text or "").strip().replace('"', "'"))


def _first_match(raw: str, candidates: dict[str, str]) -> str | None:
    """回傳在 raw 中最先出現的關鍵字所對應的標籤；都沒中回 None。"""
    low = (raw or "").lower()
    best_pos = len(low) + 1
    best_label: str | None = None
    for key, label in candidates.items():
        pos = low.find(key)
        if pos != -1 and pos < best_pos:
            best_pos = pos
            best_label = label
    return best_label


def parse_sentiment(raw: str) -> str | None:
    """解析 Qwen 情緒輸出 → 'positive'|'neutral'|'negative'；無法解析回 None。"""
    # 同時容忍英文與中文（正/負/中）；取最先出現者。
    cands = {lbl: lbl for lbl in SENTIMENT_LABELS}
    cands.update({"正面": "positive", "負面": "negative", "中性": "neutral"})
    return _first_match(raw, cands)


def parse_theme(raw: str) -> str | None:
    """解析 Qwen 主題輸出 → 4 主題之一；無法解析回 None。"""
    cands = dict(_THEME_KEYS)  # 英文 key → 中文標籤
    cands.update({lbl: lbl for lbl in THEME_LABELS})  # 也接受直接吐中文標籤
    return _first_match(raw, cands)


_PARSERS = {"sentiment": parse_sentiment, "theme": parse_theme}
_BUILDERS = {"sentiment": build_sentiment_prompt, "theme": build_theme_prompt}


class Distiller:
    """Ollama（qwen2.5）蒸餾標註器（httpx 呼叫本機服務）。"""

    def __init__(self, model: str = _MODEL, host: str = _OLLAMA, timeout: float = 120.0) -> None:
        try:
            import httpx
        except ImportError as e:
            raise ImportError("需要 httpx：pip install httpx") from e
        self._httpx = httpx
        self.model = model
        self.host = host
        self.timeout = timeout

    async def _generate(self, prompt: str, client: Any) -> str:
        # client: httpx.AsyncClient（lazy import，故型別以 Any 標避免模組頂層 import httpx）。
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0},  # 標註要可重現
        }
        r = await client.post(f"{self.host}/api/generate", json=payload)
        r.raise_for_status()
        return r.json().get("response", "")

    async def label(self, text: str, task: str, client: Any = None) -> str | None:
        """
        對單則文本產 silver label。task ∈ {'sentiment','theme'}。
        解析失敗 / 服務錯誤回 None（呼叫端略過，不中斷整批）。
        """
        if task not in _PARSERS:
            raise ValueError(f"未知 task：{task}（須為 sentiment/theme）")
        prompt = _BUILDERS[task](text)
        own = client is None
        if own:
            client = self._httpx.AsyncClient(timeout=self.timeout)
        try:
            raw = await self._generate(prompt, client)
            return _PARSERS[task](raw)
        except Exception:  # noqa: BLE001 — 單筆失敗不該中斷整批蒸餾
            logger.exception("蒸餾標註失敗，跳過一筆（task=%s）", task)
            return None
        finally:
            if own:
                await client.aclose()


if __name__ == "__main__":
    import sys

    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    # 純函式 demo（不需 Ollama）：驗證 prompt 與解析。
    print("THEME_LABELS:", THEME_LABELS)
    for r in ["positive", "  Negative.", "中性", "garbage"]:
        print(f"  parse_sentiment({r!r}) = {parse_sentiment(r)}")
    for r in ["tool", "boundary because...", "使用方法", "nope"]:
        print(f"  parse_theme({r!r}) = {parse_theme(r)}")
