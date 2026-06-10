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


# ---------------------------------------------------------------------------
# 廣義 AI 相關判定 —— 給「主題廣、不一定點名模型」的來源（Threads 為主力）用。
# 不能只用 match_models（會丟掉「提示詞 / AI工具 / 變現 / AI繪圖」這類不點名模型的台灣 AI 討論）。
# ---------------------------------------------------------------------------

# 短/易誤判詞 → 嚴格邊界（兩側非英文字母，但允許與中文相鄰，故用 [a-z] lookaround 而非 \b）。
_AI_STRICT = ("ai", "agi", "llm", "llms", "rag", "mcp", "gpt", "grok", "sora", "xai")
# 具辨識度的長詞 → 只要前邊界（容許 prompts / agents / fine-tuning 等字尾）。
_AI_LOOSE = (
    "chatgpt", "openai", "anthropic", "claude", "gemini", "bard", "llama", "deepseek",
    "copilot", "cursor", "perplexity", "midjourney", "stable diffusion", "notebooklm",
    "qwen", "ollama", "prompt", "agent", "chatbot", "genai", "generative ai",
    "machine learning", "deep learning", "neural net", "transformer", "fine-tun", "diffusion",
)
_AI_LATIN_RE = re.compile(
    r"(?<![a-z])(?:" + "|".join(_AI_STRICT) + r")(?![a-z])"
    r"|(?<![a-z])(?:" + "|".join(_AI_LOOSE) + r")",
    re.IGNORECASE,
)
# 中文 AI 關鍵字（子字串比對；中文無詞界、也無 'ai' in 'email' 的假命中問題）。
_AI_ZH_KEYWORDS = (
    "人工智慧", "人工智能", "生成式", "提示詞", "提示工程", "大語言模型", "大型語言模型",
    "語言模型", "大模型", "機器學習", "深度學習", "神經網路", "神經網絡", "微調",
    "智能體", "智慧體", "聊天機器人", "對話機器人", "文生圖", "生成圖片", "生圖",
    "向量資料庫", "嵌入向量", "演算法",
)


def is_ai_related(text: str) -> bool:
    """文字是否與 AI 相關（廣義：模型 / 工具 / 提示 / 生成 / 變現 等）。純函式，可測。"""
    if not text:
        return False
    if _AI_LATIN_RE.search(text):
        return True
    return any(kw in text for kw in _AI_ZH_KEYWORDS)


# 高頻「簡體獨有」字（繁體寫法不同）—— 用來偵測中國簡體內容並過濾，保留台灣繁中訊號。
_SIMPLIFIED_MARKERS = frozenset(
    "这个们时软网务实习边龙应经见觉单题类样优关处还发区图说话语让对没来国师业东车书长门问间风马"
    "鱼爱万与专写号体术认识记设计编辑视频频导"
)


def looks_simplified(text: str, *, min_markers: int = 2) -> bool:
    """
    是否像簡體中文（中國內容）—— 出現 >= min_markers 個簡體獨有字則判為簡體。純函式，可測。

    保守門檻（預設 2）：繁中貼文偶爾引用一個簡體字不會誤殺；簡體貼文通常一句就有多個 marker。
    """
    if not text:
        return False
    return sum(text.count(c) for c in _SIMPLIFIED_MARKERS) >= min_markers


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
