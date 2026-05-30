"""
ml/data_quality.py —— 純函式 DQC 評分器：算 quality_score (0-100) + quality_flags。

依 ADR-009（多層過濾、扣分制：score = clamp(100 + Σ deductions)）。與 ADR 的差異（已和使用者確認）：
- **移除語言層**（NON_ENGLISH）—— 不做語言過濾，非英文貼文照常以相關性/互動評分。
- 著重使用者要的三件事：**垃圾/廣告/SEO**、**模型相關性**、（跨來源去重在 ml/dedup.py + 服務層做）。
- 長度量測用「標題 + 去連結後內文」的實質字數，避免把「有意義標題的連結貼文」誤判為太短。

無 DB / 網路依賴 → 全部純函式、可單元測試（與 sentiment.py / keywords.py 同風格）。
"""
from __future__ import annotations

import html
import re
from collections import Counter
from dataclasses import dataclass

__all__ = ["QualityResult", "score_post", "FLAG_DEDUCTIONS"]

# 模型別名（鏡像 crawlers.keywords.MODEL_KEYWORDS）。ml 套件刻意自包含、可獨立測試，
# 故在此重列；6 個模型別名穩定、極少變動。改別名時兩處要同步。
_MODEL_ALIASES: dict[str, list[str]] = {
    "gpt": ["gpt", "chatgpt", "openai"],
    "claude": ["claude", "anthropic"],
    "gemini": ["gemini", "bard"],
    "grok": ["grok", "xai"],
    "llama": ["llama"],
    "deepseek": ["deepseek"],
}
_MODEL_PAT: dict[str, re.Pattern[str]] = {
    slug: re.compile(r"\b(?:%s)\b" % "|".join(aliases), re.IGNORECASE)
    for slug, aliases in _MODEL_ALIASES.items()
}

# ---- 文字清理 / 偵測用 regex（模組層編譯一次）----
URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
MD_LINK_RE = re.compile(r"\[[^\]]*\]\([^)]*\)")
CODE_FENCE_RE = re.compile(r"```.*?```|`[^`]+`", re.DOTALL)
# 不可吃到 HTML 數字字元參照（&#x27; / &#39;）→ # 前面不能是 \w 或 &。
HASHTAG_RE = re.compile(r"(?<![\w&])#\w+")
HTML_TAG_RE = re.compile(r"<[^>]+>")
DELETED_RE = re.compile(r"^\s*\[(deleted|removed)\]\s*$", re.IGNORECASE)
EMOJI_RE = re.compile(
    "[\U0001f300-\U0001faff\U00002600-\U000027bf\U0001f000-\U0001f0ff\U00002b00-\U00002bff]"
)

# 註：不放 "sign up"——「Claude 的 signup 流程很糟」是正當 UX 討論，太常見不宜當推廣訊號。
PROMO_RE = re.compile(
    r"\b(subscribe\s+now|buy\s+now|order\s+now|shop\s+now|limited\s+time|"
    r"act\s+now|don'?t\s+miss|discount|coupon|promo\s*code|voucher|cashback|"
    r"\d{1,3}\s?%\s?off|save\s+\d{1,3}\s?%|free\s+trial|best\s+price|lowest\s+price|"
    r"money[-\s]?back|guarantee[d]?)\b",
    re.IGNORECASE,
)
CTA_RE = re.compile(
    r"\b(click\s+here|link\s+in\s+bio|dm\s+me|check\s+out\s+my|visit\s+(our|my))\b",
    re.IGNORECASE,
)
AFFILIATE_RE = re.compile(
    r"[?&](ref|aff|affiliate|utm_[a-z]+|tag)=|/aff/|\b(bit\.ly|tinyurl|lnkd\.in|t\.co)\b",
    re.IGNORECASE,
)
# 不含裸 "hiring"（「OpenAI is hiring」是正當討論，非徵才貼文）。
JOB_RE = re.compile(
    r"\b(we'?re\s+hiring|now\s+hiring|apply\s+now|job\s+(opening|posting)|"
    r"open\s+(role|position)|remote\s+(role|position)|send\s+your\s+resume|"
    r"\$\d{2,3}k(/yr|/year)?)\b",
    re.IGNORECASE,
)
# 只抓「好奇心缺口」式標題；不抓裸數字清單（「5 reasons Claude beats GPT」是正當技術文，非 clickbait）。
CLICKBAIT_RE = re.compile(
    r"(you\s+won'?t\s+believe|this\s+one\s+(trick|weird)|will\s+(shock|blow\s+your\s+mind)|"
    r"what\s+happens\s+next|(doctors|experts)\s+hate|\bthe\s+truth\s+about\b)",
    re.IGNORECASE,
)
SEO_LIST_RE = re.compile(r"\b(best|top)\s+\d+\b.*\b20\d\d\b", re.IGNORECASE)
BOT_USER_RE = re.compile(r"(bot[_-]?\d*$|^auto[_-]|[_-]bot$|^ai[_-]?\d+$|[_-]gpt[_-]?\d*$)", re.IGNORECASE)
# 反諷標記（鏡像 ADR-009 Layer 5；flag-only，不扣分）。
SARCASM_RE = re.compile(r"(/s\b|\boh\s+great\s+another\b|\bwow,?\s+just\s+wow\b|\bwhat\s+a\s+surprise\b)", re.IGNORECASE)
# 相關性：模型關鍵字附近是否有「討論詞」（真的在談，不是名字帶過）。
DISCUSSION_RE = re.compile(
    r"\b(review|benchmark|bench|vs|versus|compare|comparison|use[ds]?|using|try|tried|"
    r"api|prompt|prompting|context|token|fine[-\s]?tune|finetune|rag|agent|release[d]?|"
    r"launch|update|version|performance|latency|cost|pricing|hallucinat|reasoning|"
    r"coding|capab|quality|accuracy|fail|broke|slow|fast|better|worse)\b",
    re.IGNORECASE,
)
# SEO 關鍵字堆砌量測用的小型 stopword（非語言偵測，只為避免 the/and 觸發堆砌判定）。
STOPWORDS = frozenset(
    "the a an and or but for to of in on at is are be was were this that with as it "
    "you your we our they i my me he she his her them from by not no so if then than".split()
)


@dataclass
class QualityResult:
    """單篇貼文的品質評分結果。"""

    score: int
    flags: list[str]


# 各 flag 的扣分（DELETED 為硬性歸零、SARCASM_DETECTED/去重 flag 為 0 不扣分）。
FLAG_DEDUCTIONS: dict[str, int] = {
    "TOO_SHORT": 50,
    "LINK_HEAVY": 40,
    "EMOJI_SPAM": 30,
    "ALL_CAPS": 15,
    "EXCESSIVE_PUNCT": 15,
    "SPAM_PHRASE": 50,
    "AD": 30,
    "SEO": 40,
    "AFFILIATE": 40,
    "CLICKBAIT": 30,
    "JOB_POSTING": 50,
    "LIKELY_BOT": 60,
    "KEYWORD_NOT_IN_BODY": 30,
    "WEAK_KEYWORD": 10,
    # flag-only（不扣分）：SARCASM_DETECTED；去重的 DUPLICATE / CANONICAL:<id> 由服務層另加。
}


def _strip_noise(text: str) -> str:
    """去掉 code fence / markdown link / URL，留下實質文字（給相關性與長度量測用）。"""
    t = CODE_FENCE_RE.sub(" ", text)
    t = MD_LINK_RE.sub(" ", t)
    t = URL_RE.sub(" ", t)
    return t


def _link_ratio(content: str) -> float:
    if not content:
        return 0.0
    url_chars = sum(len(m.group()) for m in URL_RE.finditer(content))
    return url_chars / max(len(content), 1)


def _caps_ratio(text: str) -> float:
    words = re.findall(r"[A-Za-z]{3,}", text)
    if len(words) < 4:
        return 0.0
    caps = sum(1 for w in words if w.isupper())
    return caps / len(words)


def _emoji_count(text: str) -> int:
    return len(EMOJI_RE.findall(text))


def _keyword_stuffed(text: str, exclude: frozenset[str] = frozenset()) -> bool:
    """
    SEO 關鍵字堆砌偵測：用**密度**而非絕對次數（長文自然會重複詞，絕對次數會誤判）。
    排除 stopword 與 exclude（如模型別名 —— 談主題本就會重複其名）。
    判定：某 token 重複 >= 5 次 **且** 佔非停用詞 token 比例 > 8%。
    """
    toks = [t for t in re.findall(r"[a-z]{4,}", text.lower()) if t not in STOPWORDS and t not in exclude]
    if len(toks) < 5:
        return False
    count = Counter(toks).most_common(1)[0][1]
    return count >= 5 and count / len(toks) > 0.08


def _relevance_flags(title: str, body_clean: str, models: list[str]) -> set[str]:
    """相關性層：keyword 只在 URL/code → KEYWORD_NOT_IN_BODY；只帶過一次 → WEAK_KEYWORD。"""
    if not models:
        return set()
    in_visible = False  # keyword 出現在標題或去雜訊內文（= 真的在談）
    in_title = False
    max_hits = 0
    visible = f"{title}\n{body_clean}"
    for slug in models:
        pat = _MODEL_PAT.get(slug)
        if pat is None:
            continue
        if pat.search(title):
            in_title = True
            in_visible = True
        if pat.search(body_clean):
            in_visible = True
        max_hits = max(max_hits, len(pat.findall(visible)))

    flags: set[str] = set()
    if not in_visible:
        # 命中模型 slug（crawler 已過濾），但去掉 URL/code 後看不到 → 只在連結/程式碼裡
        flags.add("KEYWORD_NOT_IN_BODY")
    elif max_hits <= 1 and not in_title:
        # 內文只帶過一次、標題也沒提 → 提到但非主題
        flags.add("WEAK_KEYWORD")
    return flags


def score_post(post: dict, models: list[str]) -> QualityResult:
    """
    給一篇貼文 dict（source/title/content/author/url/score/num_comments）+ 命中的模型 slug，
    回傳 (quality_score 0-100, quality_flags)。純函式。

    扣分制：score = clamp(100 + Σ deductions)；DELETED 直接歸零。
    """
    # HN 等來源的文字含 HTML 實體（&#x27;）與標籤（<p>）→ 先解碼 + 去標籤，避免污染各訊號
    # （例如 &#x27; 內的 #x27 被誤判為 hashtag）。
    title = html.unescape((post.get("title") or "").strip())
    content = HTML_TAG_RE.sub(" ", html.unescape(post.get("content") or ""))
    raw = f"{title}\n{content}"
    flags: set[str] = set()

    # 刪除標記 → 硬性歸零（標題或內文任一是 [deleted]/[removed]）
    if DELETED_RE.match(title) or DELETED_RE.match(content.strip()):
        return QualityResult(score=0, flags=["DELETED"])

    body_clean = _strip_noise(content)
    substance = f"{title}\n{body_clean}".strip()

    # ---- 結構 ----
    if len(re.sub(r"\s+", " ", substance)) < 20:
        flags.add("TOO_SHORT")
    if _link_ratio(content) > 0.6:
        flags.add("LINK_HEAVY")

    # ---- 垃圾 / 版面雜訊 ----
    if _emoji_count(raw) > 8:
        flags.add("EMOJI_SPAM")
    if _caps_ratio(raw) > 0.6:
        flags.add("ALL_CAPS")
    if re.search(r"[!?]{3,}|!{5,}", raw):
        flags.add("EXCESSIVE_PUNCT")

    # ---- 推廣 / 廣告 / SEO ----
    # 單一推廣詞（如「Claude 有 free trial 嗎？」）不算垃圾 → 需 >=2 個推廣訊號才判 SPAM_PHRASE，
    # 大幅降低誤判（code review H1）。AD = 至少一個推廣詞 + 明確 CTA。
    promo_hits = len(PROMO_RE.findall(raw))
    has_cta = bool(CTA_RE.search(raw))
    if promo_hits >= 2:
        flags.add("SPAM_PHRASE")
    if promo_hits >= 1 and has_cta:
        flags.add("AD")
    # SEO 堆砌：密度判定 + 排除模型別名（談某模型本就會重複其名，非 stuffing）。
    alias_excl = frozenset(a for slug in models for a in _MODEL_ALIASES.get(slug, []))
    if _keyword_stuffed(raw, alias_excl) or len(HASHTAG_RE.findall(raw)) >= 3 or SEO_LIST_RE.search(title):
        flags.add("SEO")
    if AFFILIATE_RE.search(raw) and promo_hits >= 1:
        flags.add("AFFILIATE")
    if CLICKBAIT_RE.search(title):
        flags.add("CLICKBAIT")
    if JOB_RE.search(raw):
        flags.add("JOB_POSTING")

    author = post.get("author")
    if author and BOT_USER_RE.search(author):
        flags.add("LIKELY_BOT")

    # ---- 相關性 ----
    flags |= _relevance_flags(title, body_clean, models)

    # ---- 情緒可靠性（flag-only）----
    if SARCASM_RE.search(raw):
        flags.add("SARCASM_DETECTED")

    # ---- 分數 ----
    score = 100 - sum(FLAG_DEDUCTIONS.get(f, 0) for f in flags)
    score = max(0, min(100, score))
    return QualityResult(score=score, flags=sorted(flags))
