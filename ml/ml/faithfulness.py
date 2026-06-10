"""
忠實度評測模組 —— 證明「事件摘要」沒有幻覺、且確實用了來源（純 stdlib，模型注入）。

這是「Faithful Event Summarizer」的量測地基（也是 #1 去風險項）。產品從一批來源貼文
生成事件摘要，必須**可證明**摘要忠於來源、沒有編造。我們不靠人感覺，而是把忠實度拆成
三個可量測、可單元測試的面向，三者缺一不可：

1. 句級 NLI 蘊含（entailment）——「摘要的每一句，是否能被它引用的來源句子蘊含？」
   蘊含高 = 這句有來源撐腰；蘊含低 = 可能是憑空生成。這是「正向支持」訊號。
2. 句級 NLI 矛盾（contradiction）——「摘要句是否與來源**互相矛盾**？」
   矛盾高是最強的**幻覺/扭曲訊號**（不只是沒講，而是講錯）。我們把它獨立報出，因為
   「沒被蘊含」可能只是來源沒提，但「被矛盾」幾乎一定是錯——兩者的嚴重度不同。
3. 強制行內引用（inline citation）+ 來源覆蓋率——
   - citation_validity：每句是否帶有效引用 `[1]`，抓「無來源的主張」（連可驗證的對象都沒有）。
   - source_coverage：有多少比例的來源真的被引用，抓「忽略大半來源、以偏概全」。

為何「蘊含 + 覆蓋」要一起看：只有高蘊含可能是「只摘一個來源、其餘照抄」（覆蓋低）；
只有高覆蓋可能是「每個來源都點到、但每句都加油添醋」（蘊含低）。忠實的摘要要兩者都好。

設計（與 metrics.py / event_detection.py 同風格）：
- 全部純函式 / 純編排，**真正的 NLI 模型用注入**（nli_fn）。重模型
  MoritzLaurer/mDeBERTa-v3-base-mnli-xnli（theme.py 已用）很重、可能沒裝，
  故**絕不在模組頂層 import transformers**；只有 build_nli_fn 在被呼叫時才惰性載入。
- 測試用一個確定性的假 nli_fn，完全不需要模型即可驗證所有編排邏輯。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

__all__ = [
    "parse_citations",
    "strip_citations",
    "split_summary_sentences",
    "citation_validity",
    "source_coverage",
    "entailment_scores",
    "FaithfulnessReport",
    "faithfulness_report",
    "build_nli_fn",
]

# nli_fn 的型別：給 (premise, hypothesis) 回傳三類機率。premise=來源、hypothesis=摘要句。
NliFn = Callable[[str, str], dict]

# 行內引用標記：抓 [1]、[2][3]、[1,2]、[1, 2] 等。一個 [...] 裡可含多個逗號分隔的數字。
_CITATION_TOKEN = re.compile(r"\[\s*\d+(?:\s*,\s*\d+)*\s*\]")
# 句子切分：中文 。！？ + 英文 .!? + 換行皆視為句界（保留標點不影響後續分析）。
_SENTENCE_SPLIT = re.compile(r"[。！？!?]+|\n+|(?<=[A-Za-z0-9])\.(?:\s+|$)")


def parse_citations(sentence: str) -> list[int]:
    """
    從摘要句抽出行內引用的來源 id（1-based，依產品慣例由作者標）。

    支援 `[1]`、`[2][3]`、`[1,2]`、`[1, 2]` 等寫法；同一句多個標記會合併。
    回傳**去重、保序**的 int 清單（保序＝依首次出現順序，利於除錯對照）。純函式。
    """
    ids: list[int] = []
    seen: set[int] = set()
    for token in _CITATION_TOKEN.findall(sentence):
        for num in re.findall(r"\d+", token):
            i = int(num)
            if i not in seen:
                seen.add(i)
                ids.append(i)
    return ids


def strip_citations(sentence: str) -> str:
    """
    移除行內引用標記，回乾淨文字（拿去餵 NLI 當 hypothesis；標記不該影響蘊含判斷）。

    一併把標記移除後可能殘留的多餘空白收斂。純函式。
    """
    cleaned = _CITATION_TOKEN.sub("", sentence)
    # 收斂連續空白（半形），並去頭尾空白；標記前的空白（如 "句子 [1]"）也一併處理。
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    return cleaned.strip()


def split_summary_sentences(summary: str) -> list[str]:
    """
    把生成摘要切成句子（中文 。！？ + 英文 .!? + 換行為界）。回傳去空白的非空句清單。

    引用標記保留在句內（之後由 parse_citations / strip_citations 各自處理）。
    英文句點只在「字母數字後緊接空白或字串結尾」時才視為句界；若句點後**緊接**
    非空白字元（如小數 "3.5"、網域 "openai.com"）則不切，避免誤切。
    注意：版本號如 "GPT-4. 很強" 的句點後有空白，仍會被切——這是刻意取捨
    （句末的英文句點通常後接空白，優先保證一般句子能正確切分）。純函式。
    """
    if not summary:
        return []
    parts = _SENTENCE_SPLIT.split(summary)
    return [p.strip() for p in parts if p and p.strip()]


def citation_validity(summary: str, *, n_sources: int) -> dict:
    """
    引用有效性：有多少比例的摘要句帶**至少一個有效引用**（id 落在 1..n_sources）。

    抓「無來源的主張」——摘要句若沒引用、或引用了不存在的來源（越界），就是不可驗證、
    可疑為幻覺。回傳：
      - rate：有效引用句 / 總句數（無句子時為 0.0）。
      - n_sentences：總句數。
      - uncited：完全沒引用的句子（原文，含可能的標記）。
      - out_of_range：有引用但**全部越界**（如只標 [9] 但只有 3 個來源）的句子。
    純函式。
    """
    sentences = split_summary_sentences(summary)
    n = len(sentences)
    uncited: list[str] = []
    out_of_range: list[str] = []
    valid = 0
    for s in sentences:
        cites = parse_citations(s)
        if not cites:
            uncited.append(s)
            continue
        in_range = [c for c in cites if 1 <= c <= n_sources]
        if in_range:
            valid += 1
        else:
            out_of_range.append(s)
    return {
        "rate": valid / n if n else 0.0,
        "n_sentences": n,
        "uncited": uncited,
        "out_of_range": out_of_range,
    }


def source_coverage(summary: str, n_sources: int) -> dict:
    """
    來源覆蓋率：有多少比例的來源文件**至少被引用一次**。

    抓「忽略大半來源、以偏概全」——只引一兩個來源就下結論的摘要，即使每句都被蘊含，
    也不算忠實地反映整起事件。只計**有效**引用（落在 1..n_sources，越界引用不算覆蓋）。
    回傳 {rate, n_sources, cited_sources(排序), uncited_sources(排序)}。純函式。
    """
    if n_sources <= 0:
        return {"rate": 0.0, "n_sources": 0, "cited_sources": [], "uncited_sources": []}
    cited: set[int] = set()
    for s in split_summary_sentences(summary):
        for c in parse_citations(s):
            if 1 <= c <= n_sources:
                cited.add(c)
    all_ids = set(range(1, n_sources + 1))
    return {
        "rate": len(cited) / n_sources,
        "n_sources": n_sources,
        "cited_sources": sorted(cited),
        "uncited_sources": sorted(all_ids - cited),
    }


@dataclass
class SentenceEntailment:
    """單句的 NLI 結果（對照它引用的來源）。"""

    sentence: str  # 原文（含引用標記，利於回溯）
    text: str  # 去引用後、實際餵給 NLI 的乾淨文字
    citations: list[int]  # 該句引用的來源 id（去重保序）
    used_sources: list[int]  # 實際用作 premise 的來源 id（有效引用，或 fallback=全部）
    entailment: float  # NLI 蘊含機率（越高越有來源支持）
    contradiction: float  # NLI 矛盾機率（越高越像幻覺/扭曲）
    neutral: float  # NLI 中性機率


def entailment_scores(
    summary: str, sources: list[str], nli_fn: NliFn
) -> list[SentenceEntailment]:
    """
    對摘要每一句跑注入的 nli_fn，premise = 該句**引用的來源**串接（未引用則退回全部來源）。

    為何用「引用的來源」當 premise：忠實度要逐句對「它聲稱的依據」驗證，而非對全部來源
    （對全部來源會讓「來源 A 提了、但這句其實亂編」也可能蒙混過關）。未引用句沒有可對照
    的依據——我們退回「對全部來源」給它最寬鬆的支持機會，但 citation_validity 仍會記它無引用。

    nli_fn(premise, hypothesis) -> {"entailment","neutral","contradiction"}（缺鍵以 0 補）。
    純編排：本函式不碰任何模型，只調 nli_fn。回傳每句一個 SentenceEntailment。
    """
    n_sources = len(sources)
    all_text = "\n".join(sources)
    results: list[SentenceEntailment] = []
    for sent in split_summary_sentences(summary):
        cites = parse_citations(sent)
        hypothesis = strip_citations(sent)
        in_range = [c for c in cites if 1 <= c <= n_sources]
        if in_range:
            premise = "\n".join(sources[c - 1] for c in in_range)
            used = in_range
        else:
            # 無有效引用 → 退回全部來源（最寬鬆），used 記為全部來源 id。
            premise = all_text
            used = list(range(1, n_sources + 1))
        probs = nli_fn(premise, hypothesis) if hypothesis else {}
        results.append(
            SentenceEntailment(
                sentence=sent,
                text=hypothesis,
                citations=cites,
                used_sources=used,
                entailment=float(probs.get("entailment", 0.0)),
                contradiction=float(probs.get("contradiction", 0.0)),
                neutral=float(probs.get("neutral", 0.0)),
            )
        )
    return results


@dataclass
class FaithfulnessReport:
    """
    一份摘要的忠實度總表。所有比例皆 [0,1]；faithfulness_score 為單一綜合分。
    """

    faithfulness_score: float  # 綜合忠實度 [0,1]（組成見 faithfulness_report 文件）
    mean_entailment: float  # 各句蘊含機率平均
    frac_entailed: float  # 蘊含 >= entail_threshold 的句子比例（正向支持率）
    frac_contradicted: float  # 矛盾 >= contradict_threshold 的句子比例（幻覺訊號，越低越好）
    citation_validity: float  # 帶有效引用的句子比例
    source_coverage: float  # 被引用到的來源比例
    n_sentences: int
    unsupported_sentences: list[str] = field(default_factory=list)  # 低蘊含或無有效引用的句子
    contradicted_sentences: list[str] = field(default_factory=list)  # 被來源矛盾的句子（最該人工複查）
    per_sentence: list[SentenceEntailment] = field(default_factory=list)


def faithfulness_report(
    summary: str,
    sources: list[str],
    nli_fn: NliFn,
    *,
    entail_threshold: float = 0.5,
    contradict_threshold: float = 0.5,
) -> FaithfulnessReport:
    """
    把上面各面向匯總成一份 FaithfulnessReport（純編排，模型由 nli_fn 注入）。

    unsupported_sentences = 「蘊含 < entail_threshold」**或**「沒有有效引用」的句子——
    兩種都是「這句站不住腳」的理由（前者來源不撐、後者根本沒指依據）。
    contradicted_sentences = 矛盾 >= contradict_threshold 的句子，是最該人工複查的硬訊號。

    faithfulness_score（[0,1]，組成與權重）：
        score = 0.50 * frac_entailed        # 正向支持是主軸：多數句要被來源蘊含
              + 0.20 * citation_validity    # 每句都要可追溯到來源（無來源主張要扣分）
              + 0.15 * source_coverage      # 要用上多數來源，別以偏概全
              + 0.15 * (1 - frac_contradicted)  # 矛盾＝幻覺，直接懲罰
    權重理由：蘊含是忠實度的核心證據故給最大權重（0.50）；引用有效性其次（0.20，
    「可驗證性」是這套方法的前提）；覆蓋與「無矛盾」各 0.15——覆蓋防以偏概全，
    無矛盾項把「講錯」這種最嚴重的幻覺直接拉低分數。四項權重和為 1，故 score 必落在 [0,1]。
    一份完全忠實（全句被蘊含、全句有效引用、用上全部來源、零矛盾）的摘要得 1.0；
    一份全靠編造（無引用、低蘊含、且有矛盾）的摘要分數會明顯被各項同時拉低。
    """
    per_sentence = entailment_scores(summary, sources, nli_fn)
    n = len(per_sentence)
    cv = citation_validity(summary, n_sources=len(sources))
    cov = source_coverage(summary, len(sources))

    if n:
        mean_ent = sum(se.entailment for se in per_sentence) / n
        frac_ent = sum(1 for se in per_sentence if se.entailment >= entail_threshold) / n
        frac_con = sum(1 for se in per_sentence if se.contradiction >= contradict_threshold) / n
    else:
        mean_ent = frac_ent = frac_con = 0.0

    unsupported: list[str] = []
    contradicted: list[str] = []
    for se in per_sentence:
        has_valid_cite = any(1 <= c <= len(sources) for c in se.citations)
        if se.entailment < entail_threshold or not has_valid_cite:
            unsupported.append(se.sentence)
        if se.contradiction >= contradict_threshold:
            contradicted.append(se.sentence)

    score = (
        0.50 * frac_ent
        + 0.20 * cv["rate"]
        + 0.15 * cov["rate"]
        + 0.15 * (1.0 - frac_con)
    )
    # 數值安全：浮點誤差夾回 [0,1]。
    score = max(0.0, min(1.0, score))

    return FaithfulnessReport(
        faithfulness_score=score,
        mean_entailment=mean_ent,
        frac_entailed=frac_ent,
        frac_contradicted=frac_con,
        citation_validity=cv["rate"],
        source_coverage=cov["rate"],
        n_sentences=n,
        unsupported_sentences=unsupported,
        contradicted_sentences=contradicted,
        per_sentence=per_sentence,
    )


def build_nli_fn(
    model_name: str = "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli",
    device: str | None = None,
    max_chars: int = 2000,
) -> NliFn:
    """
    工廠：惰性載入 transformers，把真實 mDeBERTa NLI 模型包成 nli_fn 簽名。

    **惰性 import**：transformers + torch 很重且可能沒裝，故只有實際呼叫本函式時才載入，
    模組頂層不碰（這樣 faithfulness.py 與其單元測試完全不需要模型）。

    回傳的 nli_fn(premise, hypothesis) 會跑一次 NLI，回 {"entailment","neutral","contradiction"}
    三類機率（softmax 後、和為 1）。沒有任何測試依賴本函式真的能跑。
    """
    try:
        import torch  # noqa: F401  （惰性載入，僅在此函式內需要）
        from transformers import (  # type: ignore
            AutoModelForSequenceClassification,
            AutoTokenizer,
        )
    except ImportError as e:  # pragma: no cover - 取決於環境是否裝了重依賴
        raise ImportError(
            "build_nli_fn 需要 torch + transformers + sentencepiece："
            "pip install torch transformers sentencepiece"
        ) from e

    # 先注入 OS 信任庫（與 theme.py 一致，避開企業/校園 TLS 攔截）。
    try:
        import truststore

        truststore.inject_into_ssl()
    except ImportError:
        pass

    dev = device or ("cuda" if torch.cuda.is_available() else "cpu")
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(model_name).to(dev)
    model.eval()

    # mDeBERTa-v3-mnli-xnli 的 label 順序：0=entailment、1=neutral、2=contradiction。
    # 以 model.config.id2label 對照，避免硬編順序在不同 checkpoint 出錯。
    id2label = {i: lbl.lower() for i, lbl in model.config.id2label.items()}

    def _nli_fn(premise: str, hypothesis: str) -> dict:  # pragma: no cover - 需重模型才跑
        inputs = tokenizer(
            premise[:max_chars],
            hypothesis[:max_chars],
            return_tensors="pt",
            truncation=True,
            max_length=512,
        ).to(dev)
        with torch.no_grad():
            logits = model(**inputs).logits[0]
        probs = torch.softmax(logits, dim=-1).tolist()
        out = {"entailment": 0.0, "neutral": 0.0, "contradiction": 0.0}
        for i, p in enumerate(probs):
            name = id2label.get(i, "")
            if name in out:
                out[name] = float(p)
        return out

    return _nli_fn
