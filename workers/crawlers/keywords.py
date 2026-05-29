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
