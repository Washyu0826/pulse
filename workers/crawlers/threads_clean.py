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
# albert.aka.aba）。整行就是一個 handle（不含空白、不含 CJK）→ 視為 chrome。
_HANDLE_RE = re.compile(r"^[A-Za-z0-9._]{2,40}$")

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


def _is_footer_chrome_line(line: str) -> bool:
    """整行是否為『可剝的結尾 chrome』（純數字計數 / 分頁 / 翻譯 / 日期 / 相對時間）。"""
    return bool(
        _COUNT_RE.match(line)
        or _PAGINATION_RE.match(line)
        or _TRANSLATE_RE.match(line)
        or _ABS_DATE_RE.match(line)
        or _REL_TIME_RE.match(line)
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
    if first < n and _HANDLE_RE.match(lines[first]):
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
    end = n
    while end > start:
        ln = lines[end - 1]
        if not ln:
            end -= 1
            continue
        if _is_footer_chrome_line(ln):
            end -= 1
            continue
        break

    body = "\n".join(lines[start:end])
    # 壓掉開頭剝完留下的多餘空行，並 strip。
    return re.sub(r"\n{3,}", "\n\n", body).strip()
