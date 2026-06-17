"""
忠實事件摘要 —— 產生帶來源引註（inline `[n]`）的繁體中文事件摘要（Qwen-only baseline，Step 1）。

一個「事件」= 一群來源貼文聚成的群集，事先抽好若干「關鍵句」（key sentences），每句帶來源 id。
本模組把這些關鍵句組成 prompt，請地端 Qwen2.5（Ollama）用「抽取 → 改寫」兩段式做忠實摘要：

抗幻覺設計（為何這樣組 prompt）：
- 只准用編號關鍵句裡出現的事實，不得自行補充常識或臆測。
- 每個論述句結尾須附支持該句的來源編號 `[n]`（可多個 `[1][3]`），逼模型把每句對齊到證據。
- 不確定就略過，寧缺勿造；輸出純摘要、不要前言或結語。
- 全程地端、不打雲端 API（[[prefer-local-llm]]）。

設計（與 distill.py 同風格）：
- 純函式 build_summary_prompt / format_sources / parse_summary / validate_summary 不需 Ollama → 可單元測試。
- LLM 呼叫以 generate_fn 注入（summarize_event 接 `generate_fn(prompt)->str`），測試用 fake，不打 Ollama。
- 解析 robust：容忍 code fence、前言雜訊、條列符號；引註用正則抽取，超範圍/缺漏交給 validate 檢查（不丟例外）。
- validate_summary 只回報 issues（不 raise），與另一支 faithfulness 模組保持獨立（不互相 import）。
- build_ollama_generate_fn 為工廠：lazy 建 Ollama-backed generate_fn（try/except ImportError），測試不會跑到。
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Callable, Sequence

__all__ = [
    "GenerateFn",
    "KeySentence",
    "EventSummary",
    "SummaryIssues",
    "build_summary_prompt",
    "format_sources",
    "parse_summary",
    "validate_summary",
    "summarize_event",
    "build_ollama_generate_fn",
]

logger = logging.getLogger(__name__)

# 簡→繁（台灣）：qwen2.5 摘要輸出常夾簡體（「面临」「网络」）。OpenCC 為純地端、無網路，
# 與 keywords.py / translate.py 同一套依賴。lazy 載入：缺 opencc 時退化為 identity（不致命）。
try:
    from opencc import OpenCC

    _s2tw = OpenCC("s2tw")

    def _to_traditional(text: str) -> str:
        return _s2tw.convert(text)
except Exception:  # noqa: BLE001 — 無 opencc 時不轉（純函式仍可測）
    def _to_traditional(text: str) -> str:
        return text

# generate_fn 型別：吃組好的 prompt（str）→ 回 LLM 文字（str）。生產為 Ollama，測試注入 fake。
GenerateFn = Callable[[str], str]

_OLLAMA = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
_MODEL = os.environ.get("PULSE_SUMMARIZE_MODEL", "qwen2.5:7b")

# 從文字抽取 inline 引註：[1]、[12]、[1][3]、[1, 3]、全形［1］皆可。只抓數字。
_CITATION_RE = re.compile(r"[\[［]\s*(\d+(?:\s*[,，、]\s*\d+)*)\s*[\]］]")
# 拆句（中英標點）：。！？!?；; 與換行皆視為句界。保留非空片段。
_SENT_SPLIT_RE = re.compile(r"[。！？!?；;\n]+")
# 常見前言雜訊（模型有時會加），整行濾掉。
_PREAMBLE_RE = re.compile(
    r"^\s*(?:摘要|事件摘要|以下是?|這是?|here(?:'s| is)|summary)\s*[：:]?\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class KeySentence:
    """單則來源關鍵句（事件群集裡抽出的證據）。source_id 供引註對齊（顯示為 [n]）。"""

    text: str
    source_id: int = 0  # 來源貼文 id（顯示用編號另由 1..N 給，見 _enumerate）
    source: str = ""  # 來源平台 / 作者（可選，僅供 prompt 脈絡）


def _coerce(key_sentences: Sequence[KeySentence | dict | str]) -> list[KeySentence]:
    """把混合輸入（KeySentence / dict / 純字串）正規化成 KeySentence 清單。純函式。"""
    out: list[KeySentence] = []
    for item in key_sentences:
        if isinstance(item, KeySentence):
            out.append(item)
        elif isinstance(item, dict):
            out.append(
                KeySentence(
                    text=str(item.get("text", "")),
                    source_id=int(item.get("source_id", item.get("post_id", 0)) or 0),
                    source=str(item.get("source", "")),
                )
            )
        else:
            out.append(KeySentence(text=str(item)))
    return out


def _enumerate(items: Sequence[KeySentence]) -> list[tuple[int, KeySentence]]:
    """給關鍵句 1..N 的顯示編號（引註 [n] 對齊此編號，與來源 id 解耦）。"""
    return list(enumerate(items, start=1))


@dataclass
class EventSummary:
    """解析後的事件摘要結果（純資料）。"""

    text: str  # 清理後的完整摘要文字
    sentences: list[str] = field(default_factory=list)  # 拆句後的論述句（不含空白）
    cited_ids: set[int] = field(default_factory=set)  # 全文出現過的引註編號集合
    raw: str = ""  # 模型原始輸出（除錯用）

    def to_json(self) -> dict:
        return {
            "text": self.text,
            "sentences": self.sentences,
            "cited_ids": sorted(self.cited_ids),
        }


@dataclass
class SummaryIssues:
    """validate_summary 的檢查結果（只回報、不 raise）。ok 為 True 表示無問題。"""

    empty: bool = False  # 摘要為空
    uncited_sentences: list[str] = field(default_factory=list)  # 沒有任何引註的論述句
    out_of_range_ids: list[int] = field(default_factory=list)  # 落在 [1, n_sources] 外的引註

    @property
    def ok(self) -> bool:
        return not (self.empty or self.uncited_sentences or self.out_of_range_ids)

    def to_json(self) -> dict:
        return {
            "ok": self.ok,
            "empty": self.empty,
            "uncited_sentences": self.uncited_sentences,
            "out_of_range_ids": self.out_of_range_ids,
        }


def format_sources(key_sentences: Sequence[KeySentence | dict | str]) -> str:
    """
    把關鍵句渲染成編號來源區塊：`[1] ...\n[2] ...`。純函式。

    編號為 1..N（即模型該引用的 `[n]`）；若關鍵句帶 source，附在行尾括號中供脈絡。
    """
    items = _coerce(key_sentences)
    lines: list[str] = []
    for n, ks in _enumerate(items):
        text = (ks.text or "").strip().replace("\n", " ")
        tag = f"（來源：{ks.source}）" if ks.source else ""
        lines.append(f"[{n}] {text}{tag}")
    return "\n".join(lines)


def build_summary_prompt(
    key_sentences: Sequence[KeySentence | dict | str],
    *,
    max_sentences: int = 8,
    lang: str = "zh-Hant",
) -> str:
    """
    組事件摘要 prompt（抽取 → 改寫，帶 inline 引註）。純函式，回傳 prompt 字串。

    指令（抗幻覺，全部明確寫進 prompt）：
    (a) 用繁體中文寫一段精簡的事件摘要；
    (b) 只能使用下方編號來源句裡出現的事實，不得加入任何來源沒有的資訊；
    (c) 每個論述句結尾標上支持它的來源編號，格式為 `[n]`（多來源寫成 `[1][3]`）；
    (d) 不得杜撰；無法被來源支持的內容寧可略過。

    max_sentences 控制輸出句數上限；lang 預留多語（目前固定繁中指令）。
    """
    sources = format_sources(key_sentences)
    lang_name = "繁體中文（台灣用語）" if str(lang).lower().startswith("zh") else lang
    return (
        "你是一位嚴謹的新聞編輯，負責把多則來源整理成一段忠實的事件摘要。\n"
        f"請用{lang_name}寫摘要，並嚴格遵守下列規則：\n"
        "1. 只能使用「來源」區塊中編號句子裡出現的事實；不得加入任何來源沒有寫到的資訊。\n"
        "2. 每個論述句的結尾，必須標註支持該句的來源編號，格式為 [n]（多個來源寫成 [1][3]）。\n"
        "3. 嚴禁杜撰、臆測或加入常識補充；若某項說法無法由來源支持，寧可不寫。\n"
        f"4. 摘要要精簡、客觀，最多 {max_sentences} 句，聚焦這個事件的核心進展。\n"
        "5. 只陳述事實，不要加入評論、推論、感想或總結句（例如「這反映出…」「顯示…挑戰」）。\n"
        "6. 產品 / 模型 / 公司名一律保留英文原文（如 Claude、Claude Code、GPT、Anthropic），"
        "不要音譯或意譯；jailbreak 等技術術語照英文或慣用譯法，不要直譯成字面意思。\n"
        "7. 直接輸出摘要本文即可，不要前言、不要結語、不要重複來源清單。\n\n"
        "（做法建議：先在心中挑出可用的來源句，再把它們改寫成連貫的中文，並逐句附上 [n]。）\n\n"
        "來源：\n"
        f"{sources}\n\n"
        "事件摘要："
    )


def _strip_code_fences(raw: str) -> str:
    """移除 markdown code fence（```lang ... ```）外殼，保留內容。純函式。"""
    text = (raw or "").strip()
    if text.startswith("```"):
        # 去掉開頭 ``` 與可選的語言標記那一行
        text = re.sub(r"^```[^\n]*\n?", "", text)
        # 去掉結尾的 ```
        text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


def _extract_ids(text: str) -> list[int]:
    """抽出文字中所有 inline 引註編號（依出現順序，可能重複）。純函式。"""
    ids: list[int] = []
    for m in _CITATION_RE.finditer(text or ""):
        for part in re.split(r"[,，、]", m.group(1)):
            part = part.strip()
            if part.isdigit():
                ids.append(int(part))
    return ids


def parse_summary(raw_output: str) -> EventSummary:
    """
    把模型原始輸出 robust 解析成 EventSummary。純函式（不 raise）。

    處理：去 code fence、濾掉「摘要：」之類前言行、去條列符號 / 行首編號、拆句、抽引註編號。
    cleaned text 保留 inline `[n]` 引註（驗證與下游展示都需要）。
    """
    text = _to_traditional(_strip_code_fences(raw_output))
    # 逐行清理前言雜訊與條列符號
    cleaned_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or _PREAMBLE_RE.match(stripped):
            continue
        # 去掉行首條列符號 / 編號（- * • 1. 2)）但保留引註 [n]
        stripped = re.sub(r"^\s*(?:[-*•‧]|\d+[.)、])\s+", "", stripped)
        cleaned_lines.append(stripped)
    cleaned = "\n".join(cleaned_lines).strip()

    sentences = [s.strip() for s in _SENT_SPLIT_RE.split(cleaned) if s.strip()]
    cited_ids = set(_extract_ids(cleaned))
    return EventSummary(text=cleaned, sentences=sentences, cited_ids=cited_ids, raw=raw_output or "")


def _strip_citations(sentence: str) -> str:
    """移除句中的 inline 引註，看剩下是否還有實質內容（判定空句用）。"""
    return _CITATION_RE.sub("", sentence).strip()


def validate_summary(summary: EventSummary, *, n_sources: int) -> SummaryIssues:
    """
    檢查摘要的忠實性形式條件（不 raise，回 SummaryIssues）：純函式。

    - empty：摘要文字（去引註後）為空。
    - uncited_sentences：有實質內容卻沒有任何 [n] 引註的論述句。
    - out_of_range_ids：出現落在 [1, n_sources] 範圍外的引註編號（含 0 或負數）。

    與 faithfulness 模組刻意保持獨立：這裡只看「形式」（有沒有引、引得合不合法），
    不判斷引註內容是否真的支持該句（那是 faithfulness 的事）。
    """
    issues = SummaryIssues()
    if not summary.text or not _strip_citations(summary.text):
        issues.empty = True

    for sent in summary.sentences:
        if not _strip_citations(sent):
            continue  # 純引註 / 空句不算論述句
        if not _extract_ids(sent):
            issues.uncited_sentences.append(sent)

    seen: set[int] = set()
    for cid in sorted(summary.cited_ids):
        if (cid < 1 or cid > n_sources) and cid not in seen:
            issues.out_of_range_ids.append(cid)
            seen.add(cid)
    return issues


def summarize_event(
    key_sentences: Sequence[KeySentence | dict | str],
    generate_fn: GenerateFn,
    *,
    max_sentences: int = 8,
    lang: str = "zh-Hant",
) -> tuple[EventSummary, SummaryIssues]:
    """
    事件摘要 orchestration（對注入的 generate_fn 為純函式）：
    build prompt → 呼叫 generate_fn(prompt)->str → parse → validate → 回 (EventSummary, SummaryIssues)。

    generate_fn 由呼叫端注入（測試傳 fake、正式傳 build_ollama_generate_fn 的結果），
    本函式不碰任何網路 / Ollama。n_sources 由關鍵句數推得（即引註合法範圍 [1, n_sources]）。
    """
    items = _coerce(key_sentences)
    prompt = build_summary_prompt(items, max_sentences=max_sentences, lang=lang)
    raw = generate_fn(prompt)
    summary = parse_summary(raw)
    issues = validate_summary(summary, n_sources=len(items))
    return summary, issues


def build_ollama_generate_fn(
    model: str = _MODEL,
    host: str = _OLLAMA,
    *,
    timeout: float = 180.0,
    temperature: float = 0.2,
) -> Callable[[str], str]:
    """
    工廠：lazy 建一個 Ollama-backed `generate_fn(prompt)->str`（同步、httpx 呼叫本機服務）。

    httpx 在此才 import（ImportError 時給清楚訊息）；連線 / 服務錯誤由呼叫端處理。
    溫度預設略低（0.2）讓摘要穩定但保留改寫流暢度。測試不會呼叫本工廠（會打到 Ollama）。
    """
    try:
        import httpx
    except ImportError as e:  # pragma: no cover - 環境缺套件才會走到
        raise ImportError("需要 httpx：pip install httpx") from e

    base = host.rstrip("/")

    def generate_fn(prompt: str) -> str:
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature},
        }
        resp = httpx.post(f"{base}/api/generate", json=payload, timeout=timeout)
        resp.raise_for_status()
        return resp.json().get("response", "")

    return generate_fn


if __name__ == "__main__":
    import sys

    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    # 純函式 demo（不需 Ollama）：用 fake generate_fn 走完整流程。
    demo_sentences = [
        KeySentence("OpenAI 發表新模型 GPT-5，主打更強的推理能力。", source_id=101, source="Threads"),
        KeySentence("官方表示 GPT-5 的 API 價格與前代相同。", source_id=102, source="Threads"),
        KeySentence("有開發者實測指出回應速度略有下降。", source_id=103, source="Threads"),
    ]
    print(build_summary_prompt(demo_sentences))
    print("\n--- fake 輸出解析 ---")
    fake = "OpenAI 發表 GPT-5，主打更強推理 [1]。API 價格與前代相同 [2]。實測回應速度略降 [3]。"
    summ, iss = summarize_event(demo_sentences, lambda _p: fake)
    print("cited:", sorted(summ.cited_ids), "| ok:", iss.ok)
    for s in summ.sentences:
        print("  -", s)
