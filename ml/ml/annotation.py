"""
ml/annotation.py —— 標註用純函式：分層抽樣、Cohen's κ、JSONL 讀寫、按鍵解析。

落地 ADR-008 的「人工標註 gold set」這塊，並補齊三個 mentor 點的共同缺口：
沒有標註資料 → 模型選型無法佐證、DQC 門檻無法驗證、溫度校準做不了。

設計（與 data_quality.py / sentiment.py 同風格）：
- 全部純函式、無 DB / 網路依賴 → 可單元測試；DB I/O 在 scripts/annotate.py。
- gold set 存成 JSONL（一行一筆、可版控、可重現、可續標），每筆同時帶情緒與品質標註。
- 一致性用 Cohen's κ（自己隔時間重標 20 筆，目標 κ > 0.8，依標註指南）。
"""
from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass, field
from pathlib import Path

__all__ = [
    "SENTIMENT_LABELS",
    "QUALITY_LABELS",
    "SENTIMENT_KEYS",
    "QUALITY_KEYS",
    "THEME_LABELS",
    "THEME_KEYS",
    "GoldLabel",
    "parse_sentiment_key",
    "parse_quality_key",
    "parse_theme_key",
    "stratified_sample",
    "cohen_kappa",
    "krippendorff_alpha",
    "bootstrap_ci",
    "load_jsonl",
    "append_jsonl",
    "save_jsonl",
    "labeled_ids",
]

# 標籤定義（鏡像 sentiment.py 的 _CANONICAL_LABELS 與 ADR-009 的品質帶）。
SENTIMENT_LABELS = ("positive", "neutral", "negative")
QUALITY_LABELS = ("high", "mid", "low")
# 主題 5 類 + 其他，對齊 theme.py（THEME_HYPOTHESES 五類 + OTHER_LABEL）。字面定義避免依賴 theme.py。
THEME_LABELS = ("新工具", "模型動態", "使用方法", "風險限制", "倫理法規", "其他")

# 互動標註按鍵 → 標籤。情緒 1/2/3（負→中→正）；品質 h/m/l；主題 t/m/u/r/e/o（與 s/q 不衝突）。
SENTIMENT_KEYS = {"1": "negative", "2": "neutral", "3": "positive"}
QUALITY_KEYS = {"h": "high", "m": "mid", "l": "low"}
THEME_KEYS = {
    "t": "新工具", "m": "模型動態", "u": "使用方法",
    "r": "風險限制", "e": "倫理法規", "o": "其他",
}


@dataclass
class GoldLabel:
    """單筆人工標註（情緒 + 品質 + 主題）。round=1 首標，round=2 為一致性重標。"""

    post_id: int
    source: str
    sentiment: str  # SENTIMENT_LABELS 之一
    quality: str  # QUALITY_LABELS 之一
    text: str  # 標註當下看到的文字快照（標題 + 內文截斷），供事後查核
    annotated_at: str  # ISO8601
    round: int = 1
    theme: str = field(default="")  # THEME_LABELS 之一（舊資料可能空字串）
    note: str = field(default="")

    def to_json(self) -> dict:
        return asdict(self)


def parse_sentiment_key(key: str) -> str | None:
    """把按鍵轉成情緒標籤；非法回傳 None。"""
    return SENTIMENT_KEYS.get((key or "").strip().lower())


def parse_quality_key(key: str) -> str | None:
    """把按鍵轉成品質標籤；非法回傳 None。"""
    return QUALITY_KEYS.get((key or "").strip().lower())


def parse_theme_key(key: str) -> str | None:
    """把按鍵轉成主題標籤；非法回傳 None。"""
    return THEME_KEYS.get((key or "").strip().lower())


def stratified_sample(
    posts: list[dict], n: int, *, strata_key: str = "source", seed: int = 42
) -> list[dict]:
    """
    分層隨機抽樣（依 strata_key，預設 source）。讓 gold set 涵蓋各來源、不 cherry-pick。

    作法：各層內以 seed 洗牌後輪流取（round-robin），每一輪再洗層的造訪順序，
    讓「取到一半就滿額」的最後半輪不會偏向層名字母序在前的來源。
    確定性（同 seed 同結果，因 rng 已固定 seed）。純函式 —— 不改動輸入。
    """
    if n <= 0 or not posts:
        return []
    rng = random.Random(seed)
    strata: dict[str, list[dict]] = {}
    for p in posts:
        strata.setdefault(str(p.get(strata_key, "")), []).append(p)
    # 各層獨立洗牌（先依層名排序確保建構順序確定，再由 seeded rng 洗內容）
    queues = []
    for key in sorted(strata):
        items = strata[key][:]
        rng.shuffle(items)
        queues.append(items)

    picked: list[dict] = []
    while len(picked) < n and any(queues):
        rng.shuffle(queues)  # 每輪洗層造訪順序 → 消除 partial pass 的字母序偏斜
        for q in queues:
            if q:
                picked.append(q.pop())
                if len(picked) >= n:
                    break
        queues = [q for q in queues if q]
    return picked


def cohen_kappa(a: list[str], b: list[str]) -> float:
    """
    Cohen's κ：兩組標註的一致性，扣除隨機巧合（ADR-008 目標 self-consistency κ > 0.8）。

    κ = (po - pe) / (1 - pe)，po=實際一致率、pe=隨機巧合一致率。純函式。
    完全一致（含 pe==1 的退化情形）回傳 1.0。
    """
    if len(a) != len(b):
        raise ValueError("兩組標註長度需相同")
    n = len(a)
    if n == 0:
        return 1.0
    po = sum(1 for x, y in zip(a, b, strict=True) if x == y) / n
    labels = set(a) | set(b)
    pe = sum((a.count(lbl) / n) * (b.count(lbl) / n) for lbl in labels)
    if pe >= 1.0:  # 兩組都壓在同一個標籤 → 無從扣除巧合，視為完全一致
        return 1.0
    return (po - pe) / (1.0 - pe)


def krippendorff_alpha(units: list[list[str]]) -> float:
    """
    Krippendorff's α（nominal）：多標註者、可缺值的一致性係數。

    比 Cohen's κ 適合 gold set 報告（IAA 指南 2026 建議）：支援 >2 標註者、容許某些
    單位只被部分人標過（缺值）。輸入 `units`：每個單位一個 list，內含各標註者給的標籤
    （長度可不同；長度<2 的單位不貢獻配對，會被略過）。

    α = 1 - (n-1)·Σ_{c≠k} o_ck / Σ_{c≠k} n_c·n_k
      o = coincidence matrix（單位內每個有序標籤對 +1/(m-1)）；n_c = 邊際；n = Σ n_c。
    全體標籤相同（無從不一致）→ 視為完全一致回傳 1.0。純函式。
    """
    o: dict[str, dict[str, float]] = {}
    labels: set[str] = set()
    for unit in units:
        vals = [v for v in unit if v is not None]
        m = len(vals)
        if m < 2:
            continue  # 單一標註無法構成配對
        w = 1.0 / (m - 1)
        for i, ci in enumerate(vals):
            labels.add(ci)
            for j, ck in enumerate(vals):
                if i == j:
                    continue
                o.setdefault(ci, {}).setdefault(ck, 0.0)
                o[ci][ck] += w

    if not o:
        return 1.0
    marg = {c: sum(o.get(c, {}).values()) for c in labels}
    n = sum(marg.values())
    if n <= 1:
        return 1.0
    num = sum(o[c].get(k, 0.0) for c in o for k in o[c] if k != c)
    den = sum(marg[c] * marg[k] for c in labels for k in labels if k != c)
    if den == 0:  # 只有一種標籤 → 無從扣除巧合，視為完全一致
        return 1.0
    return 1.0 - (n - 1) * num / den


def bootstrap_ci(
    data: list,
    stat_fn,
    *,
    n_boot: int = 1000,
    ci: float = 0.95,
    seed: int = 42,
) -> tuple[float, float]:
    """
    通用 bootstrap 信賴區間（百分位法）。IAA / F1 / κ 都該報 CI 而非裸點估計
    （Berg-Kirkpatrick 2012；IAA 指南 2026）。

    `data`：可重抽樣的樣本清單（如配對標註 [(a₁,b₁), ...]）。
    `stat_fn`：吃一份（重抽後）樣本、回傳一個 float 統計量。
    回傳 (低, 高) 分位。純函式（固定 seed → 可重現）。
    """
    if not data:
        return (0.0, 0.0)
    rng = random.Random(seed)
    n = len(data)
    stats: list[float] = []
    for _ in range(n_boot):
        sample = [data[rng.randrange(n)] for _ in range(n)]
        stats.append(stat_fn(sample))
    stats.sort()
    lo_idx = int((1.0 - ci) / 2.0 * n_boot)
    hi_idx = int((1.0 + ci) / 2.0 * n_boot) - 1
    lo_idx = max(0, min(lo_idx, n_boot - 1))
    hi_idx = max(0, min(hi_idx, n_boot - 1))
    return (stats[lo_idx], stats[hi_idx])


def load_jsonl(path: str | Path) -> list[dict]:
    """讀 JSONL（不存在回傳空清單）。略過空行。"""
    p = Path(path)
    if not p.exists():
        return []
    out: list[dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def append_jsonl(path: str | Path, record: dict) -> None:
    """附加一筆（續標安全 —— 即使中途中斷，已標的都在檔案裡）。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def save_jsonl(path: str | Path, records: list[dict]) -> None:
    """整檔覆寫（用於去重 / 重整）。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def labeled_ids(records: list[dict], *, round: int = 1) -> set[int]:
    """某一輪已標過的 post_id 集合（給續標 / 重標挑樣用）。"""
    return {r["post_id"] for r in records if r.get("round", 1) == round}
