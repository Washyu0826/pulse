"""
ml/dedup.py —— 跨來源近似重複偵測（純函式）。

同一篇故事常被貼到多個來源（HN / Lobsters 連同一篇 blog、Dev.to 轉文）。同來源已被
posts 的 UNIQUE(source, external_id) 擋掉，這裡處理**跨來源**：
1. URL 正規化後完全相同（最強訊號，O(n) 分桶）；
2. 標題 SimHash 分桶 + token Jaccard 接受（殘餘的同文不同網址，近 O(n)）。

用 union-find 合併兩種證據成 cluster，選一篇 canonical（最早發佈優先），其餘標 DUPLICATE。
全部純函式、可單元測試；DB I/O 在服務層（pipeline/quality.py）。
"""
from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit

__all__ = [
    "canonicalize_url",
    "normalize_title",
    "title_tokens",
    "simhash64",
    "hamming",
    "jaccard",
    "build_clusters",
    "select_canonical",
    "reconcile_dedup_flags",
    "SIMHASH_MAX_HAMMING",
    "JACCARD_MIN",
    "MIN_TITLE_TOKENS",
]

# ---- 近似重複判定門檻（雙重門檻，保守偏向「少誤合」）----
# SimHash 兩指紋的最大 Hamming 距離。64-bit SimHash 上 <=3 對應「絕大多數 token 相同」；
# 經典 SimHash 去重（Manku et al. 2007, WWW）用 k=3 作 web 近重門檻，這裡沿用且更保守
# （再加 Jaccard 第二道）。調大→召回升、誤合升；調小→更嚴。
SIMHASH_MAX_HAMMING = 3
# token Jaccard 下限：標題實際 token 重疊需 >=80% 才接受為同故事。SimHash 過桶後的二次確認，
# 擋掉「指紋碰巧接近但用字差很多」的偽陽。0.8 是常見的高精度近重門檻（偏 precision）。
JACCARD_MIN = 0.8
# 進 SimHash 分桶的最小標題 token 數。太短（<4 字詞）的標題語意稀薄、SimHash 不穩，
# 易把不相干短標題誤合 → 直接略過，只靠 URL 完全相同那條證據。
MIN_TITLE_TOKENS = 4

# 純分析用、可安全移除的追蹤參數。
_TRACKING_EXACT = {
    "fbclid", "gclid", "dclid", "msclkid", "yclid", "igshid", "mc_cid", "mc_eid",
    "ref_src", "ref_url", "_hsenc", "_hsmi", "vero_id", "spm", "scm",
}
_TRACKING_PREFIXES = ("utm_",)

# canonical 選擇的來源優先序（數字小 = 優先；偏好討論濃度高的來源）。
_SOURCE_RANK = {"lobsters": 0, "hackernews": 1, "devto": 2, "reddit": 3, "threads": 4}

_HN_PREFIX = re.compile(r"^\s*(show|ask|tell)\s+hn[:\-\s]+", re.IGNORECASE)
_BRACKETS = re.compile(r"[\[(]\s*(pdf|video|2\d{3}|19\d{2}|slides?|gist)\s*[\])]", re.IGNORECASE)
_NONWORD = re.compile(r"[^\w\s]", re.UNICODE)
_WS = re.compile(r"\s+")


def _is_tracking(key: str) -> bool:
    k = key.lower()
    return k in _TRACKING_EXACT or k.startswith(_TRACKING_PREFIXES)


def canonicalize_url(raw: str | None) -> str | None:
    """正規化外部 URL 供跨來源比對。回傳 scheme-less、去 fragment、host 小寫、去追蹤參數、
    query 排序的字串；文字貼文 / 無法解析 → None（不參與 URL 分桶）。純函式。"""
    if not raw or not raw.strip():
        return None
    raw = raw.strip()
    # 有 scheme 但非 http(s)（mailto:/javascript:/ftp: …）→ 不參與比對；無 scheme 才補 http://。
    m = re.match(r"^([a-zA-Z][a-zA-Z0-9+.\-]*):", raw)
    if m:
        if m.group(1).lower() not in ("http", "https"):
            return None
    else:
        raw = "http://" + raw
    parts = urlsplit(raw)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None

    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if parts.port and parts.port not in (80, 443):
        host = f"{host}:{parts.port}"

    path = parts.path or "/"
    if len(path) > 1:
        path = path.rstrip("/")

    kept = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not _is_tracking(k)]
    kept.sort()
    query = urlencode(kept)

    # 自行組字串（不用 urlunsplit，避免空 scheme 產生 '//' 前綴）。
    return f"{host}{path}?{query}" if query else f"{host}{path}"


def normalize_title(title: str | None) -> str:
    """標題正規化：去 Show/Ask HN 前綴、[pdf]/(2024) 等附註、標點，小寫，壓空白。純函式。"""
    if not title:
        return ""
    t = title.lower()
    t = _HN_PREFIX.sub("", t)
    t = _BRACKETS.sub(" ", t)
    t = _NONWORD.sub(" ", t)
    return _WS.sub(" ", t).strip()


def title_tokens(title: str | None) -> frozenset[str]:
    norm = normalize_title(title)
    return frozenset(norm.split())


def simhash64(tokens: frozenset[str]) -> int:
    """64-bit SimHash 指紋（token 集合）。近似標題 → 指紋 Hamming 距離小。純函式。"""
    if not tokens:
        return 0
    v = [0] * 64
    for tok in tokens:
        h = int.from_bytes(hashlib.blake2b(tok.encode("utf-8"), digest_size=8).digest(), "big")
        for i in range(64):
            v[i] += 1 if (h >> i) & 1 else -1
    out = 0
    for i in range(64):
        if v[i] > 0:
            out |= 1 << i
    return out


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class _UnionFind:
    def __init__(self, ids) -> None:
        self.parent = {i: i for i in ids}

    def find(self, x):
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:  # path compression
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a, b) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def build_clusters(posts: list[dict]) -> list[list[dict]]:
    """
    把 posts（dict 需含 id, url, title）依「URL 正規化相同」+「標題 SimHash 近似」分群。
    回傳所有大小 >= 2 的 cluster（list[list[post_dict]]）。純函式，O(n)~近 O(n)（分桶避免全配對）。
    """
    if len(posts) < 2:
        return []
    by_id = {p["id"]: p for p in posts}
    uf = _UnionFind(by_id.keys())

    # 1) URL 完全相同 → 同故事
    by_url: dict[str, list[int]] = {}
    for p in posts:
        cu = canonicalize_url(p.get("url"))
        if cu is not None:
            by_url.setdefault(cu, []).append(p["id"])
    for ids in by_url.values():
        for other in ids[1:]:
            uf.union(ids[0], other)

    # 2) 標題 SimHash 4×16-bit 分桶，桶內才比 Hamming + Jaccard（雙重門檻，保守）
    sig: dict[int, tuple[int, frozenset[str]]] = {}
    bands: dict[tuple[int, int], list[int]] = {}
    for p in posts:
        toks = title_tokens(p.get("title"))
        if len(toks) < MIN_TITLE_TOKENS:  # 太短/太泛的標題不進 SimHash（避免誤合）
            continue
        h = simhash64(toks)
        sig[p["id"]] = (h, toks)
        for b in range(4):
            band = (h >> (16 * b)) & 0xFFFF
            bands.setdefault((b, band), []).append(p["id"])
    for ids in bands.values():
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                a, b = ids[i], ids[j]
                if uf.find(a) == uf.find(b):
                    continue
                ha, ta = sig[a]
                hb, tb = sig[b]
                if hamming(ha, hb) <= SIMHASH_MAX_HAMMING and jaccard(ta, tb) >= JACCARD_MIN:
                    uf.union(a, b)

    clusters: dict[int, list[dict]] = {}
    for pid in by_id:
        clusters.setdefault(uf.find(pid), []).append(by_id[pid])
    return [c for c in clusters.values() if len(c) >= 2]


def select_canonical(cluster: list[dict]) -> int:
    """
    從一個重複 cluster 選 canonical（保留）。規則（依序）：
    最早 posted_at → 互動高（score+num_comments）→ 來源優先序 → 最小 id（確保 idempotent）。
    """
    def key(p: dict):
        posted = p.get("posted_at")
        # None posted_at 視為最大（最不可能是「最早」）
        posted_rank = (1, 0) if posted is None else (0, posted.timestamp())
        engagement = -((p.get("score") or 0) + (p.get("num_comments") or 0))
        src_rank = _SOURCE_RANK.get(p.get("source", ""), 99)
        return (posted_rank, engagement, src_rank, p["id"])

    return min(cluster, key=key)["id"]


def reconcile_dedup_flags(
    current_flags: list[str], is_canonical: bool, canonical_id: int | None
) -> list[str]:
    """
    純函式：在現有 quality_flags 上**只**更新去重標記，保留其它品質 flag。
    去掉舊的 DUPLICATE / CANONICAL:* → 非 canonical 才加新的。冪等（套兩次 == 套一次）。
    """
    kept = [f for f in current_flags if f != "DUPLICATE" and not f.startswith("CANONICAL:")]
    if not is_canonical and canonical_id is not None:
        kept.append("DUPLICATE")
        kept.append(f"CANONICAL:{canonical_id}")
    return sorted(set(kept))
