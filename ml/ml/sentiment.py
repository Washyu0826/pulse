"""
情緒分析模組 —— RoBERTa（cardiffnlp/twitter-roberta-base-sentiment-latest）。

Pulse 與 HackerNews 的核心差異化：HN 只有讚數，這裡給每則討論的情緒、群體口碑、
口碑翻轉、分歧度。本模組整合多篇文獻的穩健化技術（純 Python、不需重訓練）：

- 信心校準 + 棄答帶：Guo et al. 2017（溫度縮放）、Xin et al. 2021（selective prediction）
  → 低信心預測標記 confident=False，不污染口碑指數。
- 信心加權 soft 聚合 + 小樣本收縮：Dawid & Skene 1979、Brown/Cai/DasGupta 2001
  → 取代 naive (pos-neg)/total，小樣本朝中性收縮避免暴衝。
- 兩比例 z 檢定判翻轉：取代固定 ±20 門檻，統計顯著才算 sentiment_flip。
- 極化/分歧度：Morales et al. 2015 → 區分「又愛又恨」與「普遍平淡」。
- 反諷標記旗標：Joshi et al. 2017 → 標出 /s 等反諷貼文供降權。

完整論文清單見 docs/research/sentiment-literature.md。
純統計邏輯（summarize / detect_flip / 分數）不需模型，可單元測試。
"""
from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass

# 企業 / 校園網路常做 TLS 攔截：根憑證在 OS 信任庫但不在 Python / huggingface_hub 的。
# 在「載入任何會連外的東西之前」就注入，讓模型下載不噴 SSL/TLS 憑證錯誤。
try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "cardiffnlp/twitter-roberta-base-sentiment-latest"
_CANONICAL_LABELS = {"positive", "neutral", "negative"}
_MAX_LENGTH = 512  # twitter-roberta 上限

# --- 文獻參數（可調）---
_MIN_CONFIDENCE = 0.50  # 信心門檻（Xin 2021 selective prediction）
_MIN_MARGIN = 0.10  # top-2 機率差（棄答帶）
_SHRINK_PSEUDO = 3.0  # 小樣本收縮假計數（Beta-Binomial-lite，Brown 2001）
_NEUTRAL_BAND = 10  # summary.label 的中性帶（|index| <= 此值算 neutral）
_Z_SIGNIFICANT = 1.96  # 兩比例 z 檢定 p<0.05

# 反諷標記（Joshi 2017；HN/Reddit 文化常用 /s）—— 高精度規則，標出供降權。
_SARCASM_RE = re.compile(
    r"(/s\b|\byeah,? right\b|\bsure,? totally\b|\bwhat a surprise\b|\boh great\b|\bhow original\b)",
    re.IGNORECASE,
)


@dataclass
class SentimentResult:
    """單則文本的情緒結果。"""

    label: str  # 'positive' | 'neutral' | 'negative'
    score: float  # 該標籤的信心（0-1，溫度校準後）
    scores: dict[str, float]  # 三類各自機率
    confident: bool = True  # 是否通過信心門檻（棄答帶）

    @property
    def signed(self) -> float:
        """帶號分數：positive=+score，negative=-score，neutral=0（給加權平均用）。"""
        if self.label == "positive":
            return self.score
        if self.label == "negative":
            return -self.score
        return 0.0


@dataclass
class SentimentSummary:
    """一群討論的口碑彙總。"""

    total: int
    positive: int
    neutral: int
    negative: int
    index: int  # 口碑淨值 -100..100（信心加權 + 小樣本收縮）
    polarization: int  # 分歧度 0..100（50/50 愛恨 → 100）
    label: str  # 整體傾向


@dataclass
class FlipResult:
    """口碑翻轉偵測結果。"""

    flipped: bool
    direction: str | None  # 'to_negative' | 'to_positive' | None
    from_index: int
    to_index: int
    z: float  # 兩比例 z 檢定統計量
    p_value: float
    reason: str


def flag_sarcasm(text: str) -> bool:
    """偵測反諷標記（/s 等）。命中者建議在聚合時降權（情緒模型對反諷易判錯）。"""
    return bool(_SARCASM_RE.search(text or ""))


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _two_proportion_z(s1: int, n1: int, s2: int, n2: int) -> tuple[float, float]:
    """兩比例 z 檢定（成功數 s / 樣本 n）。回傳 (z, 雙尾 p)。"""
    if n1 == 0 or n2 == 0:
        return 0.0, 1.0
    p1, p2 = s1 / n1, s2 / n2
    pool = (s1 + s2) / (n1 + n2)
    se = math.sqrt(pool * (1 - pool) * (1 / n1 + 1 / n2))
    if se == 0:
        return 0.0, 1.0
    z = (p1 - p2) / se
    return z, 2 * (1 - _norm_cdf(abs(z)))


class SentimentAnalyzer:
    """RoBERTa 情緒分析器。模型在 __init__ 載入（首次會下載約 500MB）。"""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        device: str | None = None,
        max_length: int = _MAX_LENGTH,
        temperature: float = 1.0,  # Guo 2017 溫度縮放（需標註資料擬合；預設 1.0）
        min_confidence: float = _MIN_CONFIDENCE,
        min_margin: float = _MIN_MARGIN,
    ) -> None:
        try:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
        except ImportError as e:
            raise ImportError("需要 torch 與 transformers：pip install torch transformers") from e

        self._torch = torch
        self.model_name = model_name
        self.max_length = max_length
        self.temperature = max(temperature, 1e-6)
        self.min_confidence = min_confidence
        self.min_margin = min_margin
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")

        try:
            self.tokenizer = AutoTokenizer.from_pretrained(model_name)
            self.model = AutoModelForSequenceClassification.from_pretrained(model_name)
            self.model.to(self.device)
            self.model.eval()
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(
                f"模型載入失敗（檢查網路 / truststore / 模型名稱 '{model_name}'）：{e}"
            ) from e

        self.id2label = {int(k): v.lower() for k, v in self.model.config.id2label.items()}
        # 守衛：summarize/signed 依賴標準標籤名；非標準（如 LABEL_0）會靜默變成永遠中性。
        if set(self.id2label.values()) != _CANONICAL_LABELS:
            raise RuntimeError(
                f"模型標籤 {set(self.id2label.values())} 非 {_CANONICAL_LABELS}；"
                f"請改用 3 類 pos/neu/neg 情緒模型，或自行 remap。"
            )
        logger.info("情緒模型就緒：%s（device=%s, T=%.2f）", model_name, self.device, self.temperature)

    def analyze(self, text: str) -> SentimentResult:
        """分析單則文本。"""
        return self.analyze_batch([text])[0]

    def analyze_batch(self, texts: list[str], batch_size: int = 32) -> list[SentimentResult]:
        """
        批次分析（自動 truncate；溫度校準；信心棄答帶）。

        **回傳順序與輸入 1:1 對應**（呼叫端可 zip(post_ids, results)）——
        勿在內部依長度排序，否則會打亂對應。
        """
        torch = self._torch
        cleaned = [(t or "").strip() or " " for t in texts]
        results: list[SentimentResult] = []
        for i in range(0, len(cleaned), batch_size):
            chunk = cleaned[i : i + batch_size]
            enc = self.tokenizer(
                chunk, return_tensors="pt", truncation=True, max_length=self.max_length, padding=True
            ).to(self.device)
            with torch.no_grad():
                logits = self.model(**enc).logits / self.temperature  # 溫度校準
            probs = torch.softmax(logits, dim=-1).cpu().tolist()
            for row in probs:
                scores = {self.id2label[j]: float(row[j]) for j in range(len(row))}
                ordered = sorted(scores.values(), reverse=True)
                label = max(scores, key=scores.get)
                margin = ordered[0] - ordered[1] if len(ordered) > 1 else ordered[0]
                confident = ordered[0] >= self.min_confidence and margin >= self.min_margin
                results.append(SentimentResult(label, scores[label], scores, confident))
        return results

    @staticmethod
    def summarize(results: list[SentimentResult], *, shrink: float = _SHRINK_PSEUDO) -> SentimentSummary:
        """
        把一群情緒結果彙總成口碑指數（信心加權 soft + 小樣本收縮）+ 分歧度。純統計，可測。

        index = 100 · (Σ wᵢ·sᵢ / Σ wᵢ) · n/(n+shrink)
          其中 sᵢ = p(pos)-p(neg)（soft），wᵢ = 信心。小樣本收縮避免少數貼文暴衝。
        """
        total = len(results)
        if total == 0:
            return SentimentSummary(0, 0, 0, 0, 0, 0, "neutral")
        positive = sum(1 for r in results if r.label == "positive")
        negative = sum(1 for r in results if r.label == "negative")
        neutral = total - positive - negative

        num = sum(r.score * (r.scores["positive"] - r.scores["negative"]) for r in results)
        den = sum(r.score for r in results) or 1.0
        soft = num / den  # -1..1
        shrunk = soft * total / (total + shrink)  # Beta-Binomial-lite 收縮
        index = round(shrunk * 100)

        pos_frac, neg_frac = positive / total, negative / total
        polarization = round(2 * min(pos_frac, neg_frac) * 100)  # 50/50 → 100

        label = "positive" if index > _NEUTRAL_BAND else "negative" if index < -_NEUTRAL_BAND else "neutral"
        return SentimentSummary(total, positive, neutral, negative, index, polarization, label)

    @classmethod
    def detect_flip(
        cls,
        prev: list[SentimentResult] | SentimentSummary,
        curr: list[SentimentResult] | SentimentSummary,
        *,
        min_samples: int = 5,
        threshold: int = 20,
    ) -> FlipResult:
        """
        口碑翻轉偵測：兩比例 z 檢定（負評率）+ 極性跨越，雙重條件避免小樣本假警報。

        需 (a) 負評率變化「統計顯著」(p<0.05) 且 (b) index 由 >=+threshold 跨到 <=-threshold（或反之）。
        """
        ps = prev if isinstance(prev, SentimentSummary) else cls.summarize(prev)
        cs = curr if isinstance(curr, SentimentSummary) else cls.summarize(curr)
        z, p = _two_proportion_z(cs.negative, cs.total, ps.negative, ps.total)
        if ps.total < min_samples or cs.total < min_samples:
            return FlipResult(False, None, ps.index, cs.index, z, p, "樣本不足，不判定")
        significant = p < 0.05
        if significant and ps.index >= threshold and cs.index <= -threshold:
            return FlipResult(True, "to_negative", ps.index, cs.index, z, p,
                              f"負評率顯著上升（z={z:.2f}, p={p:.3f}）：口碑 +{ps.index} → {cs.index}")
        if significant and ps.index <= -threshold and cs.index >= threshold:
            return FlipResult(True, "to_positive", ps.index, cs.index, z, p,
                              f"負評率顯著下降（z={z:.2f}, p={p:.3f}）：口碑 {ps.index} → +{cs.index}")
        return FlipResult(False, None, ps.index, cs.index, z, p,
                          f"無顯著翻轉（z={z:.2f}, p={p:.3f}）")


if __name__ == "__main__":
    import sys

    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    analyzer = SentimentAnalyzer()
    print(f"\n模型：{analyzer.model_name} · device={analyzer.device} · T={analyzer.temperature}\n")

    deepseek_early = [
        "DeepSeek V3 is incredible — same quality as GPT-4 at a tenth of the cost. Game changer.",
        "Switched our coding agent to DeepSeek, the savings are massive and quality holds up.",
        "Honestly impressed, DeepSeek punches way above its weight. Open weights too.",
        "Cheap API and strong benchmarks, DeepSeek is the real deal.",
        "Been using DeepSeek for a week, replaced three other tools. Love it.",
    ]
    deepseek_later = [
        "After a week with DeepSeek the latency is killing us, constant timeouts.",
        "DeepSeek hallucinated badly on our codebase, had to roll back to Claude.",
        "Reliability issues make DeepSeek a no-go for production. Disappointed.",
        "Cheap but you get what you pay for — DeepSeek broke our pipeline twice today.",
        "Regret moving to DeepSeek, the quality dropped and support is nonexistent.",
    ]

    print("=== 單則情緒（含信心棄答帶）===")
    for t in deepseek_early[:2] + deepseek_later[:2]:
        r = analyzer.analyze(t)
        bar = {"positive": "🟢", "neutral": "⚪", "negative": "🔴"}[r.label]
        flag = "" if r.confident else " (低信心)"
        print(f"  {bar} {r.label:8} {r.score:.2f}{flag}  {t[:58]}")

    es = analyzer.summarize(analyzer.analyze_batch(deepseek_early))
    ls = analyzer.summarize(analyzer.analyze_batch(deepseek_later))
    print("\n=== 風向統計（信心加權 + 小樣本收縮）===")
    print(f"  早期 DeepSeek：口碑 {es.index:+d} · 分歧度 {es.polarization}  ({es.positive}↑ {es.negative}↓ /{es.total})")
    print(f"  近期 DeepSeek：口碑 {ls.index:+d} · 分歧度 {ls.polarization}  ({ls.positive}↑ {ls.negative}↓ /{ls.total})")

    flip = analyzer.detect_flip(analyzer.analyze_batch(deepseek_early), analyzer.analyze_batch(deepseek_later))
    print("\n=== 口碑翻轉偵測（兩比例 z 檢定 + 極性跨越）===")
    print(f"  {'⚠️  偵測到翻轉' if flip.flipped else '無翻轉'}：{flip.reason}")
