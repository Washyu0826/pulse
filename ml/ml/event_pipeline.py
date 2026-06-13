"""
端到端膠合層 —— 把 Faithful Event Summarizer 的三個階段串成一條管線。

三個既有姊妹模組各自獨立、各自純函式（重依賴一律延遲載入）：

1. `event_cluster.py`：貼文 → 向量化 → 門檻分群成「事件」（`cluster_events`），
   並對單一事件群抽代表句（`extract_key_sentences`，回傳其**自己版本**的 `KeySentence`，
   欄位為 `text / post_index / post_id / rank`）。
2. `summarize.py`：把關鍵句組 prompt，請 LLM 產生帶 inline `[n]` 引註的事件摘要
   （`summarize_event`，吃其**自己版本**的 `KeySentence`，欄位為 `text / source_id / source`）。
3. `faithfulness.py`：對生成摘要逐句跑 NLI，量測忠實度（`faithfulness_report`，
   吃生成文字 + 一個 `sources` 文字清單，引註 `[n]` 對齊 `sources[n-1]`）。

本模組只做**純編排**：三個模型（embed_fn / generate_fn / nli_fn）全部由呼叫端注入，
本檔不碰任何網路 / Ollama / transformers，故可完全離線單元測試。只 import 三個姊妹模組
（它們自己保留重依賴的延遲載入），不引入任何重依賴。

────────────────────────────────────────────────────────────────────────
引註 ↔ 來源對齊契約（CITATION ↔ SOURCE CONTRACT）—— 全管線的正確性命脈
────────────────────────────────────────────────────────────────────────
兩個姊妹模組的 `KeySentence` 形狀不同，且 `summarize` / `faithfulness` 都用 1-based 的
inline `[n]` 來指涉「第 n 個來源」。為了讓三者對齊，本模組定下唯一契約：

  **引註 `[n]` ↔ 第 n 個「相異來源貼文」（distinct source post），n 為 1-based 連續編號。**

具體做法（見 `to_summary_key_sentences`）：
- 我們對 event_cluster 抽出的關鍵句，依其**首次出現順序**收集相異來源（以 `post_id`
  為相異鍵；`post_id` 缺時退回 `post_index + 1`），給每個相異來源一個 1-based 連續編號。
- 同一來源貼文的多句關鍵句，共用同一個編號（避免「同一篇被當成多個來源」灌水覆蓋率）。
- 產生的 `summarize.KeySentence.source_id` 即填這個 1-based 連續編號。
- `summarize.format_sources` 會把第 k 個關鍵句渲染成 `[k] ...`（注意：summarize 內部的顯示
  編號 `[k]` 是「第 k 個關鍵句」，**不是** source_id）。因此為了讓 summarize 的顯示編號
  與我們的相異來源編號一致，我們在組 sources 清單時，**以 summarize 看到的關鍵句順序為準**
  逐一去重建立 `sources`：第一個出現的關鍵句 → `[1]`、`sources[0]`，依此類推。
- 換言之：傳給 `faithfulness_report` 的 `sources` 清單，其 `sources[n-1]` 就是「summary 的
  `[n]` 所引用的那個來源的文字」。`summary` 的引註 `[n]`、`sources[n-1]`、以及我們給
  summarize 的關鍵句第 n 條，三者編號完全一致。

不變量（tests 會驗）：
- adapter 產出的 source_id 為 1-based、連續、且同來源共用編號。
- `sources` 長度 == summary 看到的關鍵句數；citation `[n]` 對齊 `sources[n-1]`。
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from . import event_cluster, faithfulness, summarize

__all__ = [
    "EventSummaryResult",
    "to_summary_key_sentences",
    "build_sources",
    "summarize_one_event",
    "run_pipeline",
]


def _distinct_key(ks: event_cluster.KeySentence) -> object:
    """
    取一條 event_cluster 關鍵句的「相異來源鍵」。

    優先用原貼文 id（`post_id`）；缺（None）時退回 `post_index`，使每篇仍可被區分。
    回傳值只用於判斷「是否同一來源」，不直接當顯示編號。
    """
    if ks.post_id is not None:
        return ("id", ks.post_id)
    return ("idx", ks.post_index)


def to_summary_key_sentences(
    cluster_key_sentences: Sequence[event_cluster.KeySentence],
) -> list[summarize.KeySentence]:
    """
    ADAPTER：把 event_cluster 的 `KeySentence` 轉成 summarize 的 `KeySentence`。

    依「引註↔來源契約」給每個**相異來源貼文**一個 1-based 連續編號（依關鍵句首次出現順序），
    並把它填進 `summarize.KeySentence.source_id`。同一來源的多句共用同一編號。

    回傳的清單**保持原順序**（與 summarize 後續看到的關鍵句順序一致），這樣 summarize
    的顯示編號 `[k]`、本契約的相異來源編號、以及 `build_sources` 的索引才能三者對齊。
    純函式、確定性。
    """
    source_id_of: dict[object, int] = {}
    out: list[summarize.KeySentence] = []
    for ks in cluster_key_sentences:
        key = _distinct_key(ks)
        sid = source_id_of.get(key)
        if sid is None:
            sid = len(source_id_of) + 1  # 1-based、連續
            source_id_of[key] = sid
        out.append(summarize.KeySentence(text=ks.text, source_id=sid, source=""))
    return out


def build_sources(summary_key_sentences: Sequence[summarize.KeySentence]) -> list[str]:
    """
    依「引註↔來源契約」建給 `faithfulness_report` 用的 `sources` 文字清單。

    summarize 的顯示編號為「第 k 個關鍵句 → [k]」，故 `sources` 必須**逐關鍵句**排列：
    `sources[k-1]` = 第 k 條關鍵句的文字。如此 summary 的 `[n]` 即對齊 `sources[n-1]`。

    （注意：這裡刻意不以 source_id 去重——summarize 把每條關鍵句各給一個 `[k]`，
    faithfulness 也以「第幾個來源」逐條對照；兩者都以關鍵句序為準，故 sources 亦逐條排。）
    純函式。
    """
    return [(ks.text or "").strip() for ks in summary_key_sentences]


@dataclass
class EventSummaryResult:
    """單一事件跑完整管線的結果（純資料，無模型）。"""

    cluster: event_cluster.EventCluster
    key_sentences: list[event_cluster.KeySentence] = field(default_factory=list)
    summary: summarize.EventSummary | None = None
    issues: summarize.SummaryIssues | None = None
    faithfulness: faithfulness.FaithfulnessReport | None = None
    sources: list[str] = field(default_factory=list)


def summarize_one_event(
    cluster: event_cluster.EventCluster,
    posts: Sequence[dict],
    embed_fn: event_cluster.EmbedFn,
    generate_fn: summarize.GenerateFn,
    nli_fn: faithfulness.NliFn,
    *,
    k: int = 8,
    lambda_: float = event_cluster.DEFAULT_MMR_LAMBDA,
    max_sentences: int = 8,
    lang: str = "zh-Hant",
    entail_threshold: float = faithfulness.DEFAULT_ENTAIL_THRESHOLD,
    contradict_threshold: float = faithfulness.DEFAULT_CONTRADICT_THRESHOLD,
) -> EventSummaryResult:
    """
    對單一 `EventCluster` 跑完整管線：抽句 → 適配 → 摘要 → 忠實度。

    流程：
    1. 依 `cluster.members` 取出該事件的成員貼文。
    2. `extract_key_sentences` 在這些成員上抽 k 句代表句（向量來自注入的 embed_fn）。
    3. `to_summary_key_sentences` 適配成 summarize 形狀（建立 1-based 相異來源編號）。
    4. `summarize_event` 用注入的 generate_fn 產生帶引註摘要 + 形式檢查 issues。
    5. `build_sources` 依契約建 sources 清單，`faithfulness_report` 用注入的 nli_fn 量測。

    全程對三個注入 callable 為純編排；不碰網路 / 模型。回傳 `EventSummaryResult`。
    成員為空（理論上不會發生，min_size>=1）時回傳僅含 cluster 的結果。
    """
    member_posts = [posts[i] for i in cluster.members]

    cluster_keys = event_cluster.extract_key_sentences(
        member_posts, embed_fn, k=k, lambda_=lambda_
    )
    summary_keys = to_summary_key_sentences(cluster_keys)
    sources = build_sources(summary_keys)

    summary, issues = summarize.summarize_event(
        summary_keys, generate_fn, max_sentences=max_sentences, lang=lang
    )
    report = faithfulness.faithfulness_report(
        summary.text,
        sources,
        nli_fn,
        entail_threshold=entail_threshold,
        contradict_threshold=contradict_threshold,
    )
    return EventSummaryResult(
        cluster=cluster,
        key_sentences=cluster_keys,
        summary=summary,
        issues=issues,
        faithfulness=report,
        sources=sources,
    )


def run_pipeline(
    posts: Sequence[dict],
    embed_fn: event_cluster.EmbedFn,
    generate_fn: summarize.GenerateFn,
    nli_fn: faithfulness.NliFn,
    *,
    threshold: float = event_cluster.DEFAULT_CLUSTER_THRESHOLD,
    min_size: int = 2,
    k: int = 8,
    lambda_: float = event_cluster.DEFAULT_MMR_LAMBDA,
    max_sentences: int = 8,
    lang: str = "zh-Hant",
    entail_threshold: float = faithfulness.DEFAULT_ENTAIL_THRESHOLD,
    contradict_threshold: float = faithfulness.DEFAULT_CONTRADICT_THRESHOLD,
) -> list[EventSummaryResult]:
    """
    端到端管線：`cluster_events` → 對每個事件群跑 `summarize_one_event`。

    純編排，串起三個注入的模型 callable（embed_fn / generate_fn / nli_fn）。
    回傳每個事件一份 `EventSummaryResult`，順序同 `cluster_events`（依群最小成員索引排序，
    故確定性）。無貼文或無事件群時回傳空清單。
    """
    clusters = event_cluster.cluster_events(
        posts, embed_fn, threshold=threshold, min_size=min_size
    )
    return [
        summarize_one_event(
            cluster,
            posts,
            embed_fn,
            generate_fn,
            nli_fn,
            k=k,
            lambda_=lambda_,
            max_sentences=max_sentences,
            lang=lang,
            entail_threshold=entail_threshold,
            contradict_threshold=contradict_threshold,
        )
        for cluster in clusters
    ]
