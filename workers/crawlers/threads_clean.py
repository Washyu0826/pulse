"""
workers/crawlers/threads_clean.py —— 把 Threads 容器 `.text` 夾帶的 UI chrome 剝乾淨。

背景（content-quality backlog #1）：threads.py 用 `el.text` 取整張卡片的可見文字，
會把以下 chrome 一起吞進 content/title：
  - 開頭：作者帳號名（leading handle line）、轉貼/標題式短行、日期行
    （絕對 "2025-7-21" / 相對 "20小時"、"3天"、"剛剛"、"昨天"）。
  - 結尾：分頁指示（"1" / "/" / "2"、"(續)"）、純數字互動計數（讚/留言/轉發，
    含千分位 "3,761"）、"翻譯" 按鈕字樣。

本模組為**純函式**（無 DB / 網路 / selenium 依賴），可單元測試，用真實髒樣本驗證。
策略偏保守：寧可少剝一行（殘留無傷大雅），也不要誤刪真內文。故：
  - 開頭只剝「連續的、明確屬於 chrome」的行（handle → 短標題行 → 日期行），碰到第一個
    看起來像真內文的行就停。
  - 結尾只剝「純 chrome」尾行（純數字 / 分頁符號 / 翻譯），碰到含實質文字的行就停。
"""
from __future__ import annotations

import re

__all__ = ["clean_thread_text"]

# 作者帳號 leading line：Threads handle 允許英數、底線、句點（如 handsome_6_love、yofish.read、
# albert.aka.aba、therealtaipeijay、tsai1519）。整行就是一個 handle（不含空白、不含 CJK）→ chrome。
# Bug #7b 收緊：Threads handle 一律以小寫顯示，故要求**不含大寫字母**。這能把以英文專名開頭的
#   真內文（OpenAI / GPT4 / Claude / Gemini — 皆含大寫）排除在 handle 之外，不被誤剝。
#   仍保留純小寫帳號（someuser / therealtaipeijay）與含底線/數字/句點者。
_HANDLE_RE = re.compile(r"^[a-z0-9._]{2,40}$")

# 常見 AI 專名 allowlist：即使整行恰為純小寫（openai / gpt / claude…）也**不**當 handle，
# 避免以這些字開頭的真內文首行被當作者帳號剝掉（Bug #7b）。
_AI_PROPER_NOUNS = frozenset(
    {
        "ai", "agi", "llm", "llms", "openai", "gpt", "gpt4", "gpt4o", "gpt5",
        "chatgpt", "claude", "gemini", "llama", "deepseek", "grok", "qwen",
        "mistral", "copilot", "cursor", "perplexity", "midjourney", "sora",
        "ollama", "anthropic", "bard", "kimi", "phi",
    }
)


def _is_handle_line(line: str) -> bool:
    """整行是否像作者帳號 handle（Bug #7b 收緊後）：純小寫 handle 字元，且非 AI 專名。"""
    return bool(_HANDLE_RE.match(line)) and line.lower() not in _AI_PROPER_NOUNS


# 絕對日期行：YYYY-M-D / YYYY/M/D（Threads 顯示舊貼用絕對日期）。整行就是日期 → chrome。
_ABS_DATE_RE = re.compile(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}$")

# 相對時間行：N秒/分鐘/分/小時/時/天/週/周/月/年 前(可省略)、剛剛、昨天、前天、今天。
# 整行就是相對時間 → chrome。英文同義（"3h"、"2d"、"now"、"yesterday"、"5 min ago"）。
_REL_TIME_RE = re.compile(
    r"^(?:"
    r"剛剛|刚刚|昨天|前天|今天|"
    r"\d+\s*(?:秒|分鐘|分|分钟|小時|小时|時|时|天|週|周|月|年)(?:前)?|"
    r"\d+\s*(?:s|sec|secs|seconds?|m|min|mins?|minutes?|h|hr|hrs?|hours?|d|days?|w|wk|weeks?|mo|months?|y|yr|years?)"
    r"(?:\s*ago)?|"
    r"now|just\s+now|yesterday|today"
    r")$",
    re.IGNORECASE,
)

# 純數字互動計數行（讚/留言/轉發），含千分位逗號 / K,M 縮寫：15、3,761、1.2K、24M。
_COUNT_RE = re.compile(r"^\d{1,3}(?:,\d{3})*(?:\.\d+)?\s*[KMkm]?$")

# 「明確的互動計數樣態」：含千分位逗號（3,761）或 K/M 縮寫（1.2K、24M）。
# 這類絕不會是內文裡單獨成行的年份/型號/版本 → 即使落單也可放心剝。
_DEFINITE_COUNT_RE = re.compile(r"^(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?\s*[KMkm]?|\d+(?:\.\d+)?\s*[KMkm])$")

# 落單裸數字若 ≥4 位（年份 2025 / 型號 4090 / 12900）或像年份，當內容性數字，不剝。
# （Bug #7a：真內文尾端的年份/型號/版本被當互動計數誤刪。讚/留言計數真要 4 位以上時
#  Threads 一律帶千分位逗號 → 由 _DEFINITE_COUNT_RE 接手，故此處放行裸 4 位數安全。）
_BARE_NUMBER_RE = re.compile(r"^\d+$")

# 分頁指示：單獨的 "/"、"·"、"(續)"、"（續）"、"1/2" 之類。
_PAGINATION_RE = re.compile(r"^(?:/|·|•|\(續\)|（續）|\(续\)|（续）|\d+\s*/\s*\d+)$")

# "翻譯" 按鈕字樣（Threads 內建翻譯入口），含簡體/英文。
_TRANSLATE_RE = re.compile(r"^(?:翻譯|翻译|查看翻譯|查看翻译|Translate|See translation)$", re.IGNORECASE)


# 句末標點（中英）：用來判斷一行是否像「完整句子的內文」而非短標題。
_SENTENCE_PUNCT_RE = re.compile(r"[。！？，、；：…,.!?;]")
# 開頭掃描窗內，超過此長度或含句末標點的行視為「真內文」，停止往下找時間錨點（保護長首句）。
_BODY_LINE_MAXLEN = 20


def _is_long_body_line(line: str) -> bool:
    """一行是否明顯像貼文本體（夠長或含句末標點）—— 用於開頭掃描時不要跨過真內文找時間錨點。"""
    return len(line) > _BODY_LINE_MAXLEN or bool(_SENTENCE_PUNCT_RE.search(line))


def _is_nonnumeric_footer_chrome(line: str) -> bool:
    """整行是否為『非數字類』結尾 chrome（分頁 / 翻譯 / 日期 / 相對時間）。
    這類有明確字面特徵，誤判風險低，落單也可放心剝。"""
    return bool(
        _PAGINATION_RE.match(line)
        or _TRANSLATE_RE.match(line)
        or _ABS_DATE_RE.match(line)
        or _REL_TIME_RE.match(line)
    )


def _is_footer_chrome_line(line: str) -> bool:
    """整行是否為『可剝的結尾 chrome 候選』（純數字計數 / 分頁 / 翻譯 / 日期 / 相對時間）。
    註：此函式僅判斷『字面像 chrome』；落單裸數字（含 ≥4 位的年份/型號樣態）是否真的剝，
    由 clean_thread_text 的結尾掃描依「上下文（是否成群/前有其他 chrome）」再決定（Bug #7a）。
    這裡刻意把『任意長度的純整數』與千分位/K,M 計數都納為候選，讓上下文判斷成為唯一決策點，
    而非依賴 _COUNT_RE 的 3 位上限這種隱性副作用。"""
    return bool(
        _COUNT_RE.match(line)
        or _BARE_NUMBER_RE.match(line)
        or _is_nonnumeric_footer_chrome(line)
    )


def clean_thread_text(text: str) -> str:
    """
    剝掉 Threads 卡片 `.text` 夾帶的 UI chrome，回傳乾淨貼文內文。純函式。

    開頭：剝 handle / 日期 / 相對時間 / 翻譯行構成的「開頭 chrome 連續區塊」。
      防誤刪：leading handle 行（如裸 "AI"、"GPT"）與「真的很短的貼文首行」無法純靠
      字面區分，故**只在該開頭區塊同時含有日期/相對時間行**（Threads 卡片必有的發文時間
      訊號）時，才信任整塊是 chrome 並剝除；否則保守不剝（見 test_does_not_strip_real_short_post）。
      刻意**不**剝「短標題式」行（轉貼標題）—— 同樣無法可靠區分真內文，保守保留。
    結尾：連續剝純數字計數 / 分頁 / 翻譯 / 落單日期時間行，直到碰到含實質文字的行為止。
    """
    if not text:
        return ""
    lines = [ln.strip() for ln in text.splitlines()]

    n = len(lines)
    # ---- 剝開頭 chrome ----
    # Threads 卡片開頭 DOM 順序：作者 handle →（可選）轉貼/卡片短標題 → 發文時間（日期或相對）。
    # 策略：在前幾行內找「日期/相對時間」行當錨點；找到 → 連同其前所有開頭行（handle + 短標題）
    # 一起剝到時間行為止。防誤刪：(a) 第一個非空行必須是 handle；(b) 必須真的找到時間錨點，
    # 否則不剝（裸 "AI"/"GPT" 開頭的真內文沒有緊跟的時間行 → 保守保留）。
    start = 0
    # 找第一個非空行
    first = 0
    while first < n and not lines[first]:
        first += 1
    _HEADER_SCAN = 4  # 從第一個非空行起，最多往下看幾行找時間錨點
    if first < n and _is_handle_line(lines[first]):
        time_anchor = -1
        for i in range(first, min(n, first + _HEADER_SCAN)):
            if not lines[i]:
                continue
            if _ABS_DATE_RE.match(lines[i]) or _REL_TIME_RE.match(lines[i]):
                time_anchor = i
                break
            # 開頭區塊只允許「handle / 翻譯 / 短標題式」中間行；碰到看似長內文就放棄找錨點。
            if i > first and _is_long_body_line(lines[i]):
                break
        if time_anchor >= 0:
            start = time_anchor + 1  # 剝到時間行（含）為止

    # ---- 剝結尾 chrome ----
    # 先把尾端「字面像 chrome」的連續區塊（含空行）算出來，再決定真正要剝多少。
    # Bug #7a 防誤刪：落單裸數字（年份 2025 / 型號 4090 / 版本）易被當互動計數誤刪。
    # 規則：尾端 chrome 區塊裡，凡「字面是裸數字、且不符合明確互動計數樣態（無千分位/無 K,M）」
    #   的行，只有在「該數字屬於 2+ 行的 chrome 群（多個計數連在一起）」或「其後仍接著其他
    #   已確認 chrome（分頁/翻譯/時間/千分位計數）」時才剝；若是『單獨一個、且前面就是真內文』
    #   的裸數字，且 ≥4 位（年份/型號樣態）→ 視為內容，停止剝除、保留。
    end = n
    stripped_any = False  # 本輪是否已剝過任何尾端 chrome（提供「往後看」的群組脈絡）。
    while end > start:
        ln = lines[end - 1]
        if not ln:
            end -= 1
            continue
        if not _is_footer_chrome_line(ln):
            break
        # 非數字類 chrome（分頁/翻譯/日期/相對時間）或明確互動計數（千分位/K,M）→ 直接剝。
        if _is_nonnumeric_footer_chrome(ln) or _DEFINITE_COUNT_RE.match(ln):
            end -= 1
            stripped_any = True
            continue
        # 走到這：ln 是裸數字（或非明確計數樣態的數字）。先看「上方相鄰非空行」是否真內文。
        prev = end - 2
        while prev >= start and not lines[prev]:
            prev -= 1
        prev_is_chrome = prev >= start and _is_footer_chrome_line(lines[prev])
        bare = _BARE_NUMBER_RE.match(ln)
        # Bug #7a 反向保護（優先於成群剝除）：與真內文相鄰（上一行就是內文）的純整數，
        # 若 ≥4 位（年份 2025 / 型號 4090 / 12900）→ 視為內容，停止剝除、保留。
        # 不受其後計數群（stripped_any）影響——內容年份後面接讚數很常見。
        if not prev_is_chrome and bare and len(bare.group()) >= 4:
            break
        # 否則：成群（上一行也是 chrome）或其後已剝過 chrome（夾在計數群中）→ 當計數剝。
        if prev_is_chrome or stripped_any:
            end -= 1
            stripped_any = True
            continue
        # 落單、與真內文相鄰、1–3 位裸數字（4 / 15 / 730…）或含小數計數 → 仍當互動計數剝
        # （沿用既有行為，不回歸現有單一尾端計數測試）。
        end -= 1
        stripped_any = True

    body = "\n".join(lines[start:end])
    # 壓掉開頭剝完留下的多餘空行，並 strip。
    return re.sub(r"\n{3,}", "\n\n", body).strip()
