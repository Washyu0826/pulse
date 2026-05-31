"""
主題分類模組 —— 地端 zero-shot（多語 NLI，mDeBERTa-v3-base-mnli-xnli）。

回應使用者需求（同學回饋）：使用者更在意「怎麼用 AI」而非單純風向，故把每篇貼文
標成 3 個實用主題之一，外加 fallback：

- 邊界：AI 的限制 / 風險 / 安全 / 不該用的情況。
- 新工具：新的 AI 工具 / 模型 / 產品 / 發表。
- 使用方法：提示技巧 / 教學 / 工作流 / use case。
- 其他：低信心 fallback（不是候選標籤，而是 top 分數低於門檻時歸此）。

為何 zero-shot：不需標註資料、純地端（符合 [[prefer-local-llm]]），且 XNLI 模型跨語對齊，
英文假設句也能判中文貼文（Threads 中英混雜）。純地端、不打雲端 API。

分類邏輯（classify_batch / _pick）不需模型也能測：給定分數字典即可驗證門檻與 fallback。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

# 載入任何會連外的東西之前先注入 OS 信任庫（企業/校園 TLS 攔截下模型下載不噴 SSL 錯）。
try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli"
_MAX_CHARS = 2000  # 先截斷長文（模型再做 token 級 truncation），省記憶體
_MIN_CONFIDENCE = 0.45  # top 分數低於此 → 歸「其他」
_HYPOTHESIS = "This text is about {}."  # XNLI 跨語：英文假設句也能判中文前提

OTHER_LABEL = "其他"

# 正規標籤 → zero-shot 候選描述（英文，靠 XNLI 跨語對齊）。順序固定。
THEME_HYPOTHESES: dict[str, str] = {
    "邊界": "the limitations, risks, safety, or boundaries of using AI",
    "新工具": "a new AI tool, model, product, or launch",
    "使用方法": "tips, tutorials, prompts, or workflows for using AI",
}
_DESC_TO_LABEL = {desc: label for label, desc in THEME_HYPOTHESES.items()}


@dataclass
class ThemeResult:
    """單則文本的主題分類結果。"""

    label: str  # '邊界' | '新工具' | '使用方法' | '其他'
    confidence: float  # 最佳標籤分數（0-1）
    scores: dict[str, float]  # 3 個主題各自分數
    confident: bool = True  # 是否通過信心門檻（否則 label='其他'）


def _pick(scores: dict[str, float], min_confidence: float) -> ThemeResult:
    """從 3 主題分數挑出結果：top 分數低於門檻 → 歸『其他』。純函式，可測。"""
    best = max(scores, key=scores.get)
    top = scores[best]
    if top < min_confidence:
        return ThemeResult(OTHER_LABEL, top, scores, confident=False)
    return ThemeResult(best, top, scores, confident=True)


class ThemeClassifier:
    """多語 zero-shot 主題分類器。模型在 __init__ 載入（首次下載約 500MB）。"""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        device: str | None = None,
        min_confidence: float = _MIN_CONFIDENCE,
        max_chars: int = _MAX_CHARS,
    ) -> None:
        try:
            import torch
            from transformers import pipeline
        except ImportError as e:
            raise ImportError(
                "需要 torch + transformers + sentencepiece："
                "pip install torch transformers sentencepiece"
            ) from e

        self.model_name = model_name
        self.min_confidence = min_confidence
        self.max_chars = max_chars
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self._candidates = list(THEME_HYPOTHESES.values())

        try:
            self._pipe = pipeline(
                "zero-shot-classification",
                model=model_name,
                device=0 if self.device == "cuda" else -1,
            )
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(
                f"主題模型載入失敗（檢查網路 / truststore / sentencepiece / 模型名 '{model_name}'）：{e}"
            ) from e
        logger.info("主題分類模型就緒：%s（device=%s）", model_name, self.device)

    def classify(self, text: str) -> ThemeResult:
        """分類單則文本。"""
        return self.classify_batch([text])[0]

    def classify_batch(self, texts: list[str], batch_size: int = 16) -> list[ThemeResult]:
        """
        批次 zero-shot 分類。**回傳順序與輸入 1:1 對應**（呼叫端可 zip(post_ids, results)）。

        每則對 3 個候選描述各算一次 NLI 蘊含分數（multi_label=True → 各自獨立 0-1），
        再由 _pick 套門檻挑標籤 / fallback『其他』。
        """
        cleaned = [((t or "").strip() or " ")[: self.max_chars] for t in texts]
        results: list[ThemeResult] = []
        raw = self._pipe(
            cleaned,
            candidate_labels=self._candidates,
            hypothesis_template=_HYPOTHESIS,
            multi_label=True,  # 主題彼此不互斥；各標籤獨立分數，較適合「其他」門檻
            batch_size=batch_size,
        )
        # 單筆輸入時 pipeline 回 dict；多筆回 list。統一成 list。
        if isinstance(raw, dict):
            raw = [raw]
        for item in raw:
            scores_by_desc = dict(zip(item["labels"], item["scores"]))
            scores = {label: float(scores_by_desc[desc]) for desc, label in _DESC_TO_LABEL.items()}
            results.append(_pick(scores, self.min_confidence))
        return results

    @staticmethod
    def distribution(results: list[ThemeResult]) -> dict[str, int]:
        """把一群結果彙總成各主題計數（含『其他』）。純統計，可測。"""
        dist: dict[str, int] = {label: 0 for label in THEME_HYPOTHESES}
        dist[OTHER_LABEL] = 0
        for r in results:
            dist[r.label] = dist.get(r.label, 0) + 1
        return dist


if __name__ == "__main__":
    import sys

    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    clf = ThemeClassifier()
    print(f"\n模型：{clf.model_name} · device={clf.device}\n")

    samples = [
        "Claude 有時候會編造不存在的 API，重要的事一定要自己再查證一次。",  # 邊界
        "Anthropic just launched Claude Skills — a new way to package agent capabilities.",  # 新工具
        "分享我的 prompt 工作流：先讓模型列大綱、再逐段展開，效率高很多。",  # 使用方法
        "Had pizza for lunch, the weather is nice today.",  # 其他
    ]
    icon = {"邊界": "🚧", "新工具": "🆕", "使用方法": "🛠️", "其他": "⚪"}
    print("=== 主題分類（zero-shot + 信心門檻）===")
    for s, r in zip(samples, clf.classify_batch(samples)):
        flag = "" if r.confident else " (低信心→其他)"
        print(f"  {icon.get(r.label, '?')} {r.label:5} {r.confidence:.2f}{flag}  {s[:48]}")
