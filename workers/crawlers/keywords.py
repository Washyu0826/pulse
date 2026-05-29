"""
模型關鍵字比對 —— 各爬蟲（Reddit / HackerNews / ...）共用的單一來源。

slug 必須與 models 表、scripts/seed_models.py 一致。
（review 指出 slug/aliases 原本散在多處，這裡收斂成唯一定義。）
"""
from __future__ import annotations

import re

# 6 個監測模型的關鍵字別名。用 \b 詞界避免誤判（grok 不該命中 grokking）。
MODEL_KEYWORDS: dict[str, list[str]] = {
    "gpt": [r"gpt", r"chatgpt", r"openai"],
    "claude": [r"claude", r"anthropic"],
    "gemini": [r"gemini", r"bard"],
    "grok": [r"grok", r"xai"],
    "llama": [r"llama"],
    "deepseek": [r"deepseek"],
}

_PATTERNS: dict[str, re.Pattern[str]] = {
    slug: re.compile(r"\b(?:%s)\b" % "|".join(aliases), re.IGNORECASE)
    for slug, aliases in MODEL_KEYWORDS.items()
}

# 給「以查詢字串抓取」的來源用（如 HN Algolia）：所有別名去重後的扁平清單。
SEARCH_TERMS: list[str] = sorted({alias for aliases in MODEL_KEYWORDS.values() for alias in aliases})


def match_models(text: str) -> list[str]:
    """回傳文字中命中的模型 slug list（可能多個，可能空）。純函式，可測。"""
    return [slug for slug, pat in _PATTERNS.items() if pat.search(text)]


# ---- 發布訊號來源 → 模型 slug 對應（HF / GitHub，依研究實測）----

# Hugging Face org（author）→ slug。
# 注意：GPT/Claude 幾乎不在 HF 放開源權重（訊號弱）；google 需再用 'gemma' 過濾。
HF_ORG_TO_SLUG: dict[str, str] = {
    "meta-llama": "llama",
    "facebook": "llama",
    "deepseek-ai": "deepseek",
    "xai-org": "grok",
    "google": "gemini",  # 只接受 repo id 含 'gemma' 的（Gemini 本身閉源）
    "openai": "gpt",
    "Anthropic": "claude",
}

# GitHub owner/repo → slug（實測有發 Releases 的 repo；GPT/Claude 為 SDK proxy 訊號）。
GITHUB_REPO_TO_SLUG: dict[str, str] = {
    "meta-llama/llama-models": "llama",
    "meta-llama/llama-cookbook": "llama",
    "deepseek-ai/DeepSeek-V3": "deepseek",
    "deepseek-ai/DeepSeek-R1": "deepseek",
    "google-deepmind/gemma": "gemini",
    "openai/openai-python": "gpt",
    "openai/codex": "gpt",
    "anthropics/anthropic-sdk-python": "claude",
    "anthropics/claude-code": "claude",
}
