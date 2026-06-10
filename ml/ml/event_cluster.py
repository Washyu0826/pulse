"""
事件聚類 + 句子抽取核心 —— Faithful Event Summarizer 的「分群 → 抽句」階段。

整體管線：Threads AI 貼文 → 向量化 → 分群成「事件」→ 抽代表句 →（後續）LoRA Qwen
帶引用改寫 → NLI 忠實度檢查。本檔負責**分群 + 抽句**，且全部寫成**純函式**：

- 重依賴（FlagEmbedding / BGE-M3、hdbscan、numpy）一律**函式內延遲載入**，
  並讓純邏輯吃**注入的向量 / 可注入的 embedder callable**（embed_fn: str -> vector）。
  因此測試**不需安裝**那些套件即可跑（與 ml/ml/theme.py、ml/ml/charts.py 同套路）。
- 生產路徑用 BGE-M3 向量 + HDBSCAN（density-based、自動定群數、能標雜訊），延遲載入；
  但本檔另提供 `cluster_by_threshold`——免依賴、確定性的 single-link 門檻分群，
  作為測試與小型每日批次的 fallback（每日量小，貪婪 single-link 已夠且結果可重現）。
- 抽句用 MMR（Maximal Marginal Relevance）：在「與事件中心相關」與「彼此不重複」間取捨，
  避免抽到一堆近乎重複的句子（Threads 轉貼多，去重很重要）。

確定性：所有排序穩定、無隨機（向量運算純算術）。
"""
from __future__ import annotations

import math
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

# 型別別名：一條向量就是一串浮點數（list 或 tuple 皆可）。
Vector = Sequence[float]
EmbedFn = Callable[[str], Vector]


# ---------------------------------------------------------------------------
# 向量輔助（純算術，stdlib + math）
# ---------------------------------------------------------------------------
def dot(a: Vector, b: Vector) -> float:
    """內積。長度需相同。"""
    if len(a) != len(b):
        raise ValueError(f"向量維度不符：{len(a)} vs {len(b)}")
    return math.fsum(x * y for x, y in zip(a, b, strict=True))


def norm(a: Vector) -> float:
    """L2 範數。"""
    return math.sqrt(math.fsum(x * x for x in a))


def cosine(a: Vector, b: Vector) -> float:
    """
    餘弦相似度（-1~1；零向量回 0.0，不丟例外）。

    BGE-M3 向量通常已正規化，餘弦≈內積；但仍除以範數以對任意 embedder 安全。
    """
    na, nb = norm(a), norm(b)
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot(a, b) / (na * nb)


def centroid(vectors: Sequence[Vector]) -> list[float]:
    """逐維平均，回傳形心向量。空輸入丟 ValueError。"""
    if not vectors:
        raise ValueError("無法對空集合求形心")
    dim = len(vectors[0])
    sums = [0.0] * dim
    for v in vectors:
        if len(v) != dim:
            raise ValueError("形心要求所有向量等維")
        for i, x in enumerate(v):
            sums[i] += x
    n = len(vectors)
    return [s / n for s in sums]


# ---------------------------------------------------------------------------
# 分群
# ---------------------------------------------------------------------------
@dataclass
class EventCluster:
    """一個事件群：成員索引（指回原貼文清單）、代表（最靠形心者）、大小、可選熱詞。"""

    members: list[int]
    representative: int  # 最靠群形心的成員索引（拿來當「主貼」/題圖種子）
    size: int
    key_terms: list[str] = field(default_factory=list)


def cluster_by_threshold(
    vectors: Sequence[Vector],
    *,
    threshold: float,
    min_size: int = 2,
) -> list[list[int]]:
    """
    確定性的 single-link（單一連結）門檻分群——免 sklearn / hdbscan。

    兩向量餘弦 >= threshold 視為相連；用 union-find 把所有連通分量併成群。
    single-link 的「鏈式」特性正好適合事件：A 像 B、B 像 C 就把三者歸同一事件。

    回傳 list[list[int]]：每群是排序後的原始索引清單。群依「最小成員索引」排序，
    成員內亦升冪 → 結果完全可重現（無隨機、不依賴輸入掃描順序的副作用）。
    大小 < min_size 的群視為雜訊/單例，剔除（HDBSCAN 的 min_cluster_size 同義）。

    生產路徑請用 `hdbscan_cluster`（density-based，能處理不規則密度）；
    本函式是免依賴、確定性的版本，用於測試與小型每日批次。
    """
    n = len(vectors)
    parent = list(range(n))

    def find(x: int) -> int:
        # path compression（純讀寫 list，無隨機）
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    def union(x: int, y: int) -> None:
        rx, ry = find(x), find(y)
        if rx != ry:
            # 永遠把較大的 root 指向較小的 → 結果與掃描順序無關，確定性。
            lo, hi = (rx, ry) if rx < ry else (ry, rx)
            parent[hi] = lo

    for i in range(n):
        for j in range(i + 1, n):
            if cosine(vectors[i], vectors[j]) >= threshold:
                union(i, j)

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)

    clusters = [sorted(members) for members in groups.values() if len(members) >= min_size]
    clusters.sort(key=lambda m: m[0])
    return clusters


def hdbscan_cluster(
    vectors: Sequence[Vector],
    *,
    min_cluster_size: int = 2,
    min_samples: int | None = None,
    metric: str = "euclidean",
) -> list[list[int]]:
    """
    生產路徑分群：延遲載入 hdbscan（density-based，自動定群數、標雜訊）。

    BGE-M3 向量建議先 L2 正規化，使歐氏距離與餘弦單調對應後再丟進來。
    回傳格式與 `cluster_by_threshold` 一致（list[群成員索引]，雜訊 label=-1 已剔除，
    每群成員升冪、群依最小索引排序）。無測試需要它跑——測試走純 fallback。
    """
    try:
        import hdbscan  # type: ignore[import-not-found]
        import numpy as np
    except ImportError as e:  # pragma: no cover - 環境未裝重依賴時的明確訊息
        raise ImportError(
            "hdbscan_cluster 需要 hdbscan + numpy："
            "pip install hdbscan numpy（測試/小批次請改用 cluster_by_threshold）"
        ) from e

    if not vectors:
        return []
    arr = np.asarray(vectors, dtype="float64")
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=min_samples,
        metric=metric,
    )
    labels = clusterer.fit_predict(arr)
    groups: dict[int, list[int]] = {}
    for idx, lab in enumerate(labels):
        lab = int(lab)
        if lab == -1:  # 雜訊點
            continue
        groups.setdefault(lab, []).append(idx)
    clusters = [sorted(members) for members in groups.values()]
    clusters.sort(key=lambda m: m[0])
    return clusters


# ---------------------------------------------------------------------------
# MMR 句子選取
# ---------------------------------------------------------------------------
def mmr_select(
    candidate_vectors: Sequence[Vector],
    query_vector: Vector,
    *,
    k: int,
    lambda_: float = 0.7,
) -> list[int]:
    """
    Maximal Marginal Relevance —— 在相關性與多樣性間取捨地選 k 個候選。

    每步挑最大化 `lambda_ * sim(候選, query) - (1-lambda_) * max sim(候選, 已選)` 的候選。
    lambda_=1 純相關（可能選到重複句）；lambda_=0 純多樣。回傳**選取順序**的索引清單。

    純函式、確定性：分數相同時取較小索引（穩定 tie-break），故近重複句不會兩個都被選。
    """
    n = len(candidate_vectors)
    if k <= 0 or n == 0:
        return []
    if not 0.0 <= lambda_ <= 1.0:
        raise ValueError("lambda_ 需介於 0~1")

    rel = [cosine(candidate_vectors[i], query_vector) for i in range(n)]
    selected: list[int] = []
    remaining = set(range(n))
    target = min(k, n)

    while len(selected) < target:
        best_idx = -1
        best_score = -math.inf
        # 依索引升冪掃 → tie 時取較小索引，確定性。
        for i in sorted(remaining):
            if selected:
                diversity = max(
                    cosine(candidate_vectors[i], candidate_vectors[j]) for j in selected
                )
            else:
                diversity = 0.0
            score = lambda_ * rel[i] - (1.0 - lambda_) * diversity
            if score > best_score:
                best_score = score
                best_idx = i
        selected.append(best_idx)
        remaining.discard(best_idx)
    return selected


# ---------------------------------------------------------------------------
# 句子切分
# ---------------------------------------------------------------------------
# 中文句末標點 + 英文句末標點 + 換行皆為切點。保留標點在前句尾。
_SENT_SPLIT_RE = re.compile(r"(?<=[。！？.!?])|[\n\r]+")
_MIN_SENT_CHARS = 2  # 過短碎片（如單一表情/標點）丟棄


def split_sentences(text: str) -> list[str]:
    """
    中英文句子切分：以 。！？.!? 與換行為界，去頭尾空白、剔除過短碎片。

    Threads 貼文中英混雜，故同時吃中文全形與英文半形句末標點。純函式。
    """
    if not text:
        return []
    parts = _SENT_SPLIT_RE.split(text)
    out: list[str] = []
    for p in parts:
        if p is None:
            continue
        s = p.strip()
        # 去掉只剩標點/空白的碎片
        if len(s) >= _MIN_SENT_CHARS and re.search(r"[\w一-鿿]", s):
            out.append(s)
    return out


# ---------------------------------------------------------------------------
# 端到端：抽代表句 / 事件分群
# ---------------------------------------------------------------------------
def _post_text(post: dict) -> str:
    """從貼文 dict 取文字（容忍 text / content / body 欄位）。"""
    for key in ("text", "content", "body"):
        v = post.get(key)
        if isinstance(v, str) and v.strip():
            return v
    return ""


def _post_id(post: dict, fallback_index: int) -> object:
    """取貼文 id（容忍 id / post_id），沒有就用其在群內的索引。"""
    for key in ("id", "post_id", "pk"):
        if key in post and post[key] is not None:
            return post[key]
    return fallback_index


@dataclass
class KeySentence:
    """一條被抽出的代表句，帶回原貼文來源（供下游建引用）。"""

    text: str
    post_index: int  # 在輸入 posts 清單中的索引
    post_id: object  # 原貼文 id（沒有就同 post_index）
    rank: int  # MMR 選取順序（0 = 最具代表性）


def extract_key_sentences(
    posts: Sequence[dict],
    embed_fn: EmbedFn,
    *,
    k: int = 8,
    lambda_: float = 0.7,
) -> list[KeySentence]:
    """
    對一個事件群（posts：含 text 的 dict 清單）抽 k 句代表句。

    流程：每篇切句 → 每句經注入的 `embed_fn`（str -> vector）向量化 →
    以群形心為 query 做 MMR 選 top-k → 回傳帶來源（post_index / post_id）的句子，
    依 MMR 選取順序排列，方便下游做引用（citation）。

    純編排——向量全來自注入的 embed_fn，故測試可餵假的確定性 embedder。
    """
    sentences: list[str] = []
    src_index: list[int] = []
    src_id: list[object] = []
    for pi, post in enumerate(posts):
        for sent in split_sentences(_post_text(post)):
            sentences.append(sent)
            src_index.append(pi)
            src_id.append(_post_id(post, pi))

    if not sentences:
        return []

    vectors = [list(embed_fn(s)) for s in sentences]
    query = centroid(vectors)  # 群形心當 query → 抽最能代表整群的句子
    order = mmr_select(vectors, query, k=k, lambda_=lambda_)
    return [
        KeySentence(
            text=sentences[i],
            post_index=src_index[i],
            post_id=src_id[i],
            rank=rank,
        )
        for rank, i in enumerate(order)
    ]


def cluster_events(
    posts: Sequence[dict],
    embed_fn: EmbedFn,
    *,
    threshold: float = 0.6,
    min_size: int = 2,
) -> list[EventCluster]:
    """
    便利函式：把貼文向量化 → 門檻分群 → 包成 EventCluster（含代表貼文）。

    代表貼文 = 群內最靠形心者（餘弦最大），拿來當事件主貼 / 題圖種子。
    向量來自注入的 embed_fn，故可離線測；生產可換成 BGE-M3 embedder。
    回傳依群最小成員索引排序，內部成員升冪 → 確定性。
    """
    if not posts:
        return []
    vectors = [list(embed_fn(_post_text(p))) for p in posts]
    groups = cluster_by_threshold(vectors, threshold=threshold, min_size=min_size)

    events: list[EventCluster] = []
    for members in groups:
        member_vecs = [vectors[i] for i in members]
        cen = centroid(member_vecs)
        # 代表 = 群內最靠形心者；tie 取較小索引（確定性）。
        rep = max(members, key=lambda i: (cosine(vectors[i], cen), -i))
        events.append(EventCluster(members=members, representative=rep, size=len(members)))
    return events


# ---------------------------------------------------------------------------
# 生產 embedder（延遲載入 BGE-M3）—— 不在測試路徑上
# ---------------------------------------------------------------------------
def build_bge_m3_embedder(model_name: str = "BAAI/bge-m3"):  # pragma: no cover - 需重依賴
    """
    回傳一個 embed_fn（str -> list[float]），底層用 BGE-M3（dense 向量，已 L2 正規化）。

    延遲載入 FlagEmbedding；缺套件時丟明確 ImportError。把它注入
    extract_key_sentences / cluster_events 即切到生產路徑。
    """
    try:
        from FlagEmbedding import BGEM3FlagModel  # type: ignore[import-not-found]
    except ImportError as e:
        raise ImportError(
            "build_bge_m3_embedder 需要 FlagEmbedding：pip install FlagEmbedding"
            "（測試請改注入假 embedder）"
        ) from e

    model = BGEM3FlagModel(model_name, use_fp16=True)

    def embed(text: str) -> list[float]:
        out = model.encode([text or " "], return_dense=True)["dense_vecs"][0]
        return [float(x) for x in out]

    return embed
