"""
silver 摘要訓練資料建構 —— 教師蒸餾的純函式層（事件摘要 B 線 Step 2）。

B 線要微調自己的忠實摘要器（scripts/train_summarizer.py），但人工 gold 很貴；
先用地端 Qwen（Ollama）當「教師」，對事件關鍵句生成帶 [n] 引註的摘要當 silver 訓練資料
（教師蒸餾；與 A 線 distill.py 的分類蒸餾同精神）。**不是每筆教師輸出都能進訓練集**：
空摘要、形式不合格（無引註/越界引註）、NLI 忠實度低分的樣本要被過濾——餵髒資料只會教壞學生。

輸出記錄格式 **與 train_summarizer.py 嚴格對齊**（它用 `_load_records` 讀、用
`build_summary_prompt(key_sentences)` 重建 prompt，故 key_sentences 必須能無損 round-trip）：

    {"key_sentences": [{"text": "...", "source_id": 1, "source": ""}, ...],
     "summary": "OpenAI 發表 GPT-5 [1]。價格與前代相同 [2]。",
     "faithfulness_score": 0.83,          # 有跑 NLI 才寫；train_summarizer 缺省視為 1.0
     "max_sentences": 8, "lang": "zh-Hant",
     "event_key": "a1b2c3...", "post_ids": [...], ...}   # provenance（train 端忽略）

設計（與 summarize.py / event_pipeline.py 同風格）：
- 全部純函式 / 純編排：LLM 用 generate_fn 注入、NLI 用 nli_fn 注入，本模組不碰
  網路 / Ollama / transformers → 測試用 fake callable 完全離線。
- 重用既有地基，不重寫：prompt 與解析走 `summarize.summarize_event`（保證教師 prompt ==
  訓練 prompt == 推論 prompt，三者同一份 `build_summary_prompt`）；相異來源編號走
  `event_pipeline.to_summary_key_sentences`（引註↔來源契約）；忠實度走
  `faithfulness.faithfulness_report`。
- 增量續跑靠 `event_key`（成員貼文 id 的確定性雜湊）：同一群貼文重跑會得到同一把 key，
  腳本端據此跳過已生成 / 已拒絕的事件。
"""
from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Callable

from . import event_pipeline, faithfulness, summarize
from .event_cluster import KeySentence as ClusterKeySentence

__all__ = [
    "STATUS_OK",
    "STATUS_NO_KEY_SENTENCES",
    "STATUS_EMPTY_SUMMARY",
    "STATUS_FORMAT_ISSUES",
    "STATUS_LOW_FAITHFULNESS",
    "event_key",
    "key_sentences_to_jsonable",
    "build_silver_record",
    "done_event_keys",
    "DistillOutcome",
    "distill_event",
]

# distill_event 的結果狀態（字串常數，寫進 rejected JSONL 供人工複查時好讀）。
STATUS_OK = "ok"
STATUS_NO_KEY_SENTENCES = "no_key_sentences"  # 事件抽不出關鍵句（不該發生，防呆）
STATUS_EMPTY_SUMMARY = "empty_summary"  # 教師輸出清完是空的
STATUS_FORMAT_ISSUES = "format_issues"  # 形式不合格：有句子沒引註 / 引註越界
STATUS_LOW_FAITHFULNESS = "low_faithfulness"  # NLI 忠實度低於門檻


def event_key(post_ids: Sequence[object]) -> str:
    """
    事件的確定性識別碼：成員貼文 id 排序後串接做 sha1，取前 16 hex。純函式。

    用途＝增量續跑的去重鍵：同一群貼文（不管抓取順序）永遠得到同一把 key，
    腳本據此跳過已處理事件。不同成員集合（即使只差一篇）會得到不同 key——
    這是刻意的：成員變了，關鍵句與摘要都該重生成。
    """
    joined = "␟".join(sorted(str(pid) for pid in post_ids))  # ␟ 分隔避免 id 串接歧義
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()[:16]


def key_sentences_to_jsonable(
    summary_keys: Sequence[summarize.KeySentence],
) -> list[dict]:
    """
    把 summarize.KeySentence 序列化成 JSON 可存的 dict 清單。純函式。

    欄位（text / source_id / source）與 `summarize._coerce` 完全對齊 → train_summarizer
    讀回後重建的 prompt 與教師生成時看到的 prompt **逐字相同**（round-trip 不變量，tests 驗）。
    """
    return [
        {"text": ks.text, "source_id": ks.source_id, "source": ks.source}
        for ks in summary_keys
    ]


def build_silver_record(
    summary_keys: Sequence[summarize.KeySentence],
    summary_text: str,
    *,
    faithfulness_score: float | None = None,
    max_sentences: int = 8,
    lang: str = "zh-Hant",
    extra: dict | None = None,
) -> dict:
    """
    組一列 train_summarizer.py 期望的訓練記錄。純函式。

    核心欄位（train 端讀取）：key_sentences / summary / max_sentences / lang，
    faithfulness_score 只在有跑 NLI 時寫入（train 端缺省視為 1.0，故沒分數就不要亂填）。
    extra 放 provenance（event_key、post_ids、model、created_at…），train 端會忽略；
    為防汙染，extra 不得覆寫核心欄位（核心欄位後寫、優先）。
    """
    record: dict = dict(extra or {})
    record.update(
        {
            "key_sentences": key_sentences_to_jsonable(summary_keys),
            "summary": (summary_text or "").strip(),
            "max_sentences": int(max_sentences),
            "lang": str(lang),
        }
    )
    if faithfulness_score is not None:
        record["faithfulness_score"] = round(float(faithfulness_score), 4)
    return record


def done_event_keys(records: Iterable[dict]) -> set[str]:
    """從既有 JSONL 記錄抽出已處理的 event_key 集合（缺欄位者忽略）。純函式。"""
    return {str(r["event_key"]) for r in records if r.get("event_key")}


@dataclass
class DistillOutcome:
    """單一事件蒸餾的結果（純資料）。record 只在 status == ok 時非 None。"""

    status: str  # STATUS_* 之一
    record: dict | None = None  # 可進訓練集的記錄（僅 ok）
    summary_text: str = ""  # 教師摘要（清理後；拒絕樣本也保留，供人工複查）
    faithfulness_score: float | None = None  # 有跑 NLI 才有
    issues: summarize.SummaryIssues | None = None

    @property
    def ok(self) -> bool:
        return self.status == STATUS_OK


def distill_event(
    cluster_keys: Sequence[ClusterKeySentence],
    generate_fn: Callable[[str], str],
    nli_fn: faithfulness.NliFn | None = None,
    *,
    max_sentences: int = 8,
    lang: str = "zh-Hant",
    min_faithfulness: float = 0.5,
    require_ok: bool = True,
    entail_threshold: float = 0.5,
    contradict_threshold: float = 0.5,
    extra: dict | None = None,
) -> DistillOutcome:
    """
    對單一事件的關鍵句做教師蒸餾：生成 → 解析 → 形式檢查 → NLI 忠實度過濾 → 組訓練記錄。

    流程（對注入的 generate_fn / nli_fn 為純編排，不碰任何網路 / 模型）：
    1. `event_pipeline.to_summary_key_sentences`：建 1-based 相異來源編號（引註↔來源契約）。
    2. `summarize.summarize_event(…, generate_fn)`：教師生成帶 [n] 引註的摘要 + 形式檢查。
    3. 過濾閘門（依序、先便宜後昂貴）：
       a. 空摘要 → STATUS_EMPTY_SUMMARY（沒東西可學）。
       b. require_ok 且形式不合格（無引註句 / 越界引註）→ STATUS_FORMAT_ISSUES
          （引註壞掉的樣本會教學生亂標來源，先擋掉再省下 NLI 計算）。
       c. nli_fn 有給 → `faithfulness_report`，綜合分 < min_faithfulness →
          STATUS_LOW_FAITHFULNESS（教師也會幻覺；低分樣本不配進訓練集）。
    4. 全過 → `build_silver_record` 組 train_summarizer 對齊的記錄，STATUS_OK。

    nli_fn=None 表示跳過 NLI（如環境沒裝 transformers）：記錄不寫 faithfulness_score，
    此時只剩形式過濾——品質較弱，腳本端會明確警告。
    """
    if not cluster_keys:
        return DistillOutcome(status=STATUS_NO_KEY_SENTENCES)

    summary_keys = event_pipeline.to_summary_key_sentences(cluster_keys)
    sources = event_pipeline.build_sources(summary_keys)

    summary, issues = summarize.summarize_event(
        summary_keys, generate_fn, max_sentences=max_sentences, lang=lang
    )

    if issues.empty:
        return DistillOutcome(
            status=STATUS_EMPTY_SUMMARY, summary_text=summary.text, issues=issues
        )
    if require_ok and not issues.ok:
        return DistillOutcome(
            status=STATUS_FORMAT_ISSUES, summary_text=summary.text, issues=issues
        )

    score: float | None = None
    if nli_fn is not None:
        report = faithfulness.faithfulness_report(
            summary.text,
            sources,
            nli_fn,
            entail_threshold=entail_threshold,
            contradict_threshold=contradict_threshold,
        )
        score = report.faithfulness_score
        if score < min_faithfulness:
            return DistillOutcome(
                status=STATUS_LOW_FAITHFULNESS,
                summary_text=summary.text,
                faithfulness_score=score,
                issues=issues,
            )

    record = build_silver_record(
        summary_keys,
        summary.text,
        faithfulness_score=score,
        max_sentences=max_sentences,
        lang=lang,
        extra=extra,
    )
    return DistillOutcome(
        status=STATUS_OK,
        record=record,
        summary_text=summary.text,
        faithfulness_score=score,
        issues=issues,
    )
