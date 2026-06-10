"""
主題分類模組 —— 地端 zero-shot（多語 NLI，mDeBERTa-v3-base-mnli-xnli）。

5 個實用主題 + fallback（2026-06 依需求研究改版，見 docs/research/offline-evaluation-literature.md
以及 AI 資訊需求研究）。原本只有 邊界/新工具/使用方法 3 類，缺口是：缺「模型動態與評測」
（#1 常青需求：哪個模型最好/比較/價格），且「邊界」把實務限制與倫理法規混在一起：

- 新工具：新的 AI 工具 / app / 產品 / 功能發表。
- 模型動態：模型比較 / 評測 / 排名 / 價格 / 能力更新（「哪個最好」）。
- 使用方法：提示技巧 / 教學 / 工作流 / use case（台灣旗艦需求：補「高自信低行動」鴻溝）。
- 風險限制：實務限制 / 失敗 / 幻覺 / 不該用的情況。
- 倫理法規：倫理 / 法規 / 政策 / 隱私（台灣此焦慮特別高）。
- 其他：低信心 fallback（top 分數低於門檻時歸此）。

主題彼此不互斥（一篇可同時是「新工具 + 使用方法」），故 multi_label 並**輸出 top-2**
（label 為主、secondary 為次，次主題分數需過 _SECONDARY_MIN）。

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
_SECONDARY_MIN = 0.40  # 次主題分數需過此才輸出 top-2 的 secondary
_HYPOTHESIS = "This text is about {}."  # XNLI 跨語：英文假設句也能判中文前提

OTHER_LABEL = "其他"

# 正規標籤 → zero-shot 候選描述（英文，靠 XNLI 跨語對齊）。順序固定；假設句刻意寫得彼此可分。
THEME_HYPOTHESES: dict[str, str] = {
    "新工具": "a new AI tool, app, product, or feature being launched or introduced",
    "模型動態": "a comparison, benchmark, ranking, price, or capability update of AI models",
    "使用方法": "tips, tutorials, prompts, or workflows for using AI effectively",
    "風險限制": "the practical limitations, failures, hallucinations, or risks of using AI tools",
    "倫理法規": "the ethics, regulation, law, policy, or privacy concerns of AI",
}
_DESC_TO_LABEL = {desc: label for label, desc in THEME_HYPOTHESES.items()}


@dataclass
class ThemeResult:
    """單則文本的主題分類結果（含 top-2）。"""

    label: str  # 主主題（5 類之一或 '其他'）
    confidence: float  # 最佳標籤分數（0-1）
    scores: dict[str, float]  # 5 個主題各自分數
    confident: bool = True  # 是否通過信心門檻（否則 label='其他'）
    secondary: str | None = None  # 次主題（分數過 _SECONDARY_MIN 才有；多主題貼文用）

    @property
    def labels(self) -> list[str]:
        """主 + 次主題（去重、保序）。供「一篇可屬多主題」的瀏覽/篩選用。"""
        out = [self.label]
        if self.secondary and self.secondary != self.label:
            out.append(self.secondary)
        return out


def _pick(
    scores: dict[str, float], min_confidence: float, secondary_min: float = _SECONDARY_MIN
) -> ThemeResult:
    """從主題分數挑結果：top<門檻→『其他』；否則取 top-1，次高過 secondary_min 則附為 secondary。純函式。"""
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    best, top = ranked[0]
    if top < min_confidence:
        return ThemeResult(OTHER_LABEL, top, scores, confident=False)
    secondary = ranked[1][0] if len(ranked) > 1 and ranked[1][1] >= secondary_min else None
    return ThemeResult(best, top, scores, confident=True, secondary=secondary)


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
        "Anthropic just launched Claude Skills — a new way to package agent capabilities.",  # 新工具
        "GPT-5 vs Claude on SWE-bench：誰比較會寫 code？順便看一下兩邊的 API 價格。",  # 模型動態
        "分享我的 prompt 工作流：先讓模型列大綱、再逐段展開，效率高很多。",  # 使用方法
        "Claude 有時候會編造不存在的 API，重要的事一定要自己再查證一次。",  # 風險限制
        "歐盟 AI Act 上路，這些用途會被視為高風險，企業要注意資料隱私。",  # 倫理法規
        "Had pizza for lunch, the weather is nice today.",  # 其他
    ]
    icon = {"新工具": "🆕", "模型動態": "📊", "使用方法": "🛠️", "風險限制": "🚧", "倫理法規": "⚖️", "其他": "⚪"}
    print("=== 主題分類（zero-shot + 信心門檻 + top-2）===")
    for s, r in zip(samples, clf.classify_batch(samples)):
        flag = "" if r.confident else " (低信心→其他)"
        sec = f"  +{r.secondary}" if r.secondary else ""
        print(f"  {icon.get(r.label, '?')} {r.label:5} {r.confidence:.2f}{flag}{sec}  {s[:44]}")
