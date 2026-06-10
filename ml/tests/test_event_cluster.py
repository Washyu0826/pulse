"""
事件聚類 + 句子抽取純邏輯測試 —— 餘弦 / 門檻分群 / MMR / 句子切分 / 端到端。

不載入任何重依賴（BGE-M3 / hdbscan / numpy 只在生產函式內延遲 import）：
測試一律注入**假的確定性 embedder**（hashing token-bag → 小向量），故可完全離線跑。
"""
import math

from ml.event_cluster import (
    EventCluster,
    KeySentence,
    centroid,
    cluster_by_threshold,
    cluster_events,
    cosine,
    dot,
    extract_key_sentences,
    mmr_select,
    norm,
    split_sentences,
)

# ---------------------------------------------------------------------------
# 假 embedder：把文字切成 token，hash 進固定維度的 bag-of-tokens，再 L2 正規化。
# 完全確定性、無外部依賴；同字句 → 同向量，語意相近（共享 token）→ 餘弦高。
# ---------------------------------------------------------------------------
_DIM = 16


def _tokens(text: str) -> list[str]:
    out: list[str] = []
    word = ""
    for ch in text.lower():
        if ch.isalnum() and ch.isascii():
            word += ch
        else:
            if word:
                out.append(word)
                word = ""
            if "一" <= ch <= "鿿":  # 中文字逐字當 token
                out.append(ch)
    if word:
        out.append(word)
    return out


def fake_embed(text: str) -> list[float]:
    """確定性假 embedder：token bag → _DIM 維 → L2 正規化。"""
    vec = [0.0] * _DIM
    for tok in _tokens(text):
        vec[hash_token(tok) % _DIM] += 1.0
    n = math.sqrt(sum(x * x for x in vec))
    if n == 0.0:
        return vec
    return [x / n for x in vec]


def hash_token(tok: str) -> int:
    """穩定 hash（內建 hash 對 str 在不同 run 會變，這裡用固定演算法）。"""
    h = 2166136261
    for ch in tok:
        h = (h ^ ord(ch)) * 16777619 % (2**32)
    return h


def onehot(slot: int, value: float = 1.0) -> list[float]:
    """直接造一條 one-hot 向量，方便測純向量運算。"""
    v = [0.0] * _DIM
    v[slot] = value
    return v


# ---------------------------------------------------------------------------
# 向量輔助
# ---------------------------------------------------------------------------
def test_dot_and_norm():
    assert dot([1.0, 2.0, 3.0], [4.0, 5.0, 6.0]) == 32.0
    assert norm([3.0, 4.0]) == 5.0


def test_dot_dimension_mismatch_raises():
    try:
        dot([1.0], [1.0, 2.0])
    except ValueError:
        pass
    else:
        raise AssertionError("維度不符應丟 ValueError")


def test_cosine_identical_is_one():
    v = [0.1, 0.2, 0.3]
    assert abs(cosine(v, v) - 1.0) < 1e-9


def test_cosine_orthogonal_is_zero():
    assert abs(cosine([1.0, 0.0], [0.0, 1.0])) < 1e-9


def test_cosine_zero_vector_is_zero_not_error():
    assert cosine([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_cosine_opposite_is_minus_one():
    assert abs(cosine([1.0, 0.0], [-1.0, 0.0]) + 1.0) < 1e-9


def test_centroid_averages_per_dim():
    assert centroid([[0.0, 0.0], [2.0, 4.0]]) == [1.0, 2.0]


def test_centroid_empty_raises():
    try:
        centroid([])
    except ValueError:
        pass
    else:
        raise AssertionError("空集合求形心應丟 ValueError")


# ---------------------------------------------------------------------------
# 門檻分群
# ---------------------------------------------------------------------------
def test_cluster_two_clear_groups():
    # 兩組各自指向不同 one-hot 方向 → 組內餘弦 1、組間 0。
    vecs = [onehot(0), onehot(0), onehot(5), onehot(5)]
    clusters = cluster_by_threshold(vecs, threshold=0.9, min_size=2)
    assert clusters == [[0, 1], [2, 3]]


def test_cluster_drops_singletons_below_min_size():
    # idx 2 自成一群（與其他正交）→ 應被 min_size=2 剔除。
    vecs = [onehot(0), onehot(0), onehot(7)]
    clusters = cluster_by_threshold(vecs, threshold=0.9, min_size=2)
    assert clusters == [[0, 1]]


def test_cluster_min_size_one_keeps_singletons():
    vecs = [onehot(0), onehot(7)]
    clusters = cluster_by_threshold(vecs, threshold=0.9, min_size=1)
    assert clusters == [[0], [1]]


def test_cluster_single_link_chains():
    # A 像 B、B 像 C，但 A 與 C 不直接夠近 → single-link 仍併成一群。
    a = [1.0, 0.0, 0.0]
    b = [1.0, 1.0, 0.0]  # 與 a、c 各 cos≈0.707
    c = [0.0, 1.0, 0.0]  # 與 a 正交（cos 0）
    clusters = cluster_by_threshold([a, b, c], threshold=0.7, min_size=2)
    assert clusters == [[0, 1, 2]]


def test_cluster_high_threshold_breaks_chain():
    a = [1.0, 0.0, 0.0]
    b = [1.0, 1.0, 0.0]
    c = [0.0, 1.0, 0.0]
    # 門檻 0.8 > 0.707 → 鏈斷開，三者各自單例 → 全被 min_size=2 剔除。
    clusters = cluster_by_threshold([a, b, c], threshold=0.8, min_size=2)
    assert clusters == []


def test_cluster_empty_input():
    assert cluster_by_threshold([], threshold=0.5) == []


def test_cluster_is_deterministic_and_sorted():
    vecs = [onehot(5), onehot(0), onehot(5), onehot(0)]
    a = cluster_by_threshold(vecs, threshold=0.9, min_size=2)
    b = cluster_by_threshold(vecs, threshold=0.9, min_size=2)
    assert a == b
    # 群依最小成員索引排序、成員內升冪
    assert a == [[0, 2], [1, 3]]


# ---------------------------------------------------------------------------
# MMR
# ---------------------------------------------------------------------------
def test_mmr_picks_most_relevant_first():
    query = onehot(0)
    cands = [onehot(3), onehot(0), onehot(7)]  # idx1 與 query 完全相關
    order = mmr_select(cands, query, k=1, lambda_=0.7)
    assert order == [1]


def test_mmr_dedups_near_duplicates_via_diversity():
    query = onehot(0)
    # idx0、idx1 幾乎相同（都極相關但彼此重複）；idx2 不同方向。
    cands = [onehot(0), onehot(0), onehot(4)]
    order = mmr_select(cands, query, k=2, lambda_=0.3)
    # 第一個選最相關（tie → 取較小索引 0）；第二個因多樣性懲罰應跳過重複的 1，選 2。
    assert order[0] == 0
    assert order[1] == 2


def test_mmr_lambda_one_is_pure_relevance():
    query = onehot(0)
    # 兩條都與 query 相關但彼此重複；lambda_=1 不懲罰重複 → 仍選兩條近重複。
    cands = [onehot(0), [1.0] + [0.0] * (_DIM - 1), onehot(4)]
    order = mmr_select(cands, query, k=2, lambda_=1.0)
    assert set(order) == {0, 1}


def test_mmr_k_larger_than_n_returns_all():
    cands = [onehot(0), onehot(1)]
    order = mmr_select(cands, onehot(0), k=10)
    assert sorted(order) == [0, 1]


def test_mmr_k_zero_and_empty():
    assert mmr_select([onehot(0)], onehot(0), k=0) == []
    assert mmr_select([], onehot(0), k=3) == []


def test_mmr_invalid_lambda_raises():
    try:
        mmr_select([onehot(0)], onehot(0), k=1, lambda_=1.5)
    except ValueError:
        pass
    else:
        raise AssertionError("lambda_ 超界應丟 ValueError")


def test_mmr_is_deterministic():
    query = onehot(0)
    cands = [onehot(0), onehot(0), onehot(4), onehot(4)]
    assert mmr_select(cands, query, k=3) == mmr_select(cands, query, k=3)


# ---------------------------------------------------------------------------
# 句子切分
# ---------------------------------------------------------------------------
def test_split_chinese():
    assert split_sentences("今天發表了新模型。大家都很興奮！真的嗎？") == [
        "今天發表了新模型。",
        "大家都很興奮！",
        "真的嗎？",
    ]


def test_split_english():
    assert split_sentences("OpenAI shipped a new model. People are excited! Really?") == [
        "OpenAI shipped a new model.",
        "People are excited!",
        "Really?",
    ]


def test_split_mixed_and_newlines():
    out = split_sentences("Claude 推出 Skills。\nThis is huge!\n真的很方便")
    assert out == ["Claude 推出 Skills。", "This is huge!", "真的很方便"]


def test_split_drops_short_punctuation_fragments():
    # 純標點/表情碎片應被剔除，但有字的保留。
    out = split_sentences("好。。。真的好用！")
    assert out == ["好。", "真的好用！"]


def test_split_empty_and_none_like():
    assert split_sentences("") == []
    assert split_sentences("   \n  ") == []


# ---------------------------------------------------------------------------
# 端到端：extract_key_sentences
# ---------------------------------------------------------------------------
def test_extract_key_sentences_returns_sources():
    posts = [
        {"id": "p1", "text": "Claude 推出 Skills 功能。這很實用。"},
        {"id": "p2", "text": "GPT 也更新了價格。"},
    ]
    out = extract_key_sentences(posts, fake_embed, k=3, lambda_=0.7)
    assert all(isinstance(s, KeySentence) for s in out)
    assert len(out) == 3
    # 來源索引與 id 正確對回原貼文
    by_text = {s.text: s for s in out}
    assert by_text["GPT 也更新了價格。"].post_index == 1
    assert by_text["GPT 也更新了價格。"].post_id == "p2"
    # rank 連續從 0 起
    assert sorted(s.rank for s in out) == [0, 1, 2]


def test_extract_respects_k_limit():
    posts = [{"id": "p1", "text": "一。二。三。四。五。"}]
    out = extract_key_sentences(posts, fake_embed, k=2)
    assert len(out) == 2


def test_extract_uses_fallback_id_when_missing():
    posts = [{"text": "沒有 id 的貼文。"}]
    out = extract_key_sentences(posts, fake_embed, k=1)
    assert out[0].post_id == 0  # fallback = post_index


def test_extract_empty_posts():
    assert extract_key_sentences([], fake_embed, k=5) == []
    assert extract_key_sentences([{"text": ""}], fake_embed, k=5) == []


def test_extract_dedups_repeated_posts():
    # 三篇近乎重複轉貼 + 一篇不同 → MMR 應優先涵蓋兩種內容，不全給重複句。
    posts = [
        {"id": 1, "text": "新模型發表了。"},
        {"id": 2, "text": "新模型發表了。"},
        {"id": 3, "text": "新模型發表了。"},
        {"id": 4, "text": "完全不同的另一個主題討論。"},
    ]
    out = extract_key_sentences(posts, fake_embed, k=2, lambda_=0.5)
    texts = {s.text for s in out}
    assert "完全不同的另一個主題討論。" in texts  # 多樣性確保異質內容被選入


# ---------------------------------------------------------------------------
# 端到端：cluster_events
# ---------------------------------------------------------------------------
def test_cluster_events_groups_similar_posts():
    posts = [
        {"id": "a", "text": "新模型 發表 評測 跑分"},
        {"id": "b", "text": "新模型 發表 評測 跑分"},  # 與 a 幾乎相同
        {"id": "c", "text": "完全 不同 的 美食 旅遊 主題"},
        {"id": "d", "text": "完全 不同 的 美食 旅遊 主題"},  # 與 c 幾乎相同
    ]
    events = cluster_events(posts, fake_embed, threshold=0.9, min_size=2)
    assert len(events) == 2
    assert all(isinstance(e, EventCluster) for e in events)
    member_sets = [set(e.members) for e in events]
    assert {0, 1} in member_sets
    assert {2, 3} in member_sets


def test_cluster_events_representative_and_size():
    posts = [
        {"id": "a", "text": "新模型 發表"},
        {"id": "b", "text": "新模型 發表"},
    ]
    events = cluster_events(posts, fake_embed, threshold=0.9, min_size=2)
    assert len(events) == 1
    e = events[0]
    assert e.size == 2
    assert e.representative in e.members


def test_cluster_events_empty():
    assert cluster_events([], fake_embed) == []


def test_cluster_events_singletons_dropped():
    # 三篇互不相似 → 全單例 → min_size=2 全剔除。
    posts = [
        {"text": "alpha beta"},
        {"text": "gamma delta"},
        {"text": "epsilon zeta"},
    ]
    assert cluster_events(posts, fake_embed, threshold=0.9, min_size=2) == []


# ---------------------------------------------------------------------------
# 額外邊界：向量輔助
# ---------------------------------------------------------------------------
def test_centroid_dimension_mismatch_raises():
    try:
        centroid([[1.0, 2.0], [1.0]])
    except ValueError:
        pass
    else:
        raise AssertionError("不等維向量求形心應丟 ValueError")


def test_cosine_zero_vectors_both_sides():
    # 兩邊都是零向量也不該炸，回 0.0。
    assert cosine([0.0, 0.0], [0.0, 0.0]) == 0.0


def test_cosine_at_threshold_boundary_is_inclusive():
    # cos([1,1],[1,0]) = 1/sqrt(2) ≈ 0.7071；門檻剛好 0.7071 時 >= 應成立（相連）。
    a, b = [1.0, 1.0], [1.0, 0.0]
    c = cosine(a, b)
    # 門檻略低於該值 → 相連成群；略高 → 斷開。驗證 >= 的邊界語意。
    assert cluster_by_threshold([a, b], threshold=c - 1e-9, min_size=2) == [[0, 1]]
    assert cluster_by_threshold([a, b], threshold=c + 1e-9, min_size=2) == []


# ---------------------------------------------------------------------------
# 額外邊界：門檻分群
# ---------------------------------------------------------------------------
def test_cluster_all_duplicate_vectors_one_group():
    # 完全相同的向量（餘弦 1）→ 全併一群。
    vecs = [onehot(0)] * 4
    assert cluster_by_threshold(vecs, threshold=0.9, min_size=2) == [[0, 1, 2, 3]]


def test_cluster_single_item_min_size_one_and_two():
    assert cluster_by_threshold([onehot(0)], threshold=0.5, min_size=1) == [[0]]
    assert cluster_by_threshold([onehot(0)], threshold=0.5, min_size=2) == []


def test_cluster_single_item_input():
    # n==1：內層 j 迴圈不執行，仍要正確處理。
    assert cluster_by_threshold([onehot(3)], threshold=0.0, min_size=1) == [[0]]


# ---------------------------------------------------------------------------
# 額外邊界：MMR
# ---------------------------------------------------------------------------
def test_mmr_negative_k_returns_empty():
    assert mmr_select([onehot(0), onehot(1)], onehot(0), k=-3) == []


def test_mmr_all_identical_vectors_still_returns_distinct_indices():
    # 全相同向量：多樣性懲罰最大，但仍要回 k 個相異索引（不重複、不卡住）。
    cands = [onehot(0), onehot(0), onehot(0)]
    order = mmr_select(cands, onehot(0), k=3, lambda_=0.5)
    assert sorted(order) == [0, 1, 2]
    assert len(set(order)) == 3  # 無重複


def test_mmr_k_larger_than_n_with_duplicates():
    cands = [onehot(0), onehot(0), onehot(5)]
    order = mmr_select(cands, onehot(0), k=99)
    assert sorted(order) == [0, 1, 2]


def test_mmr_lambda_zero_pure_diversity_no_crash():
    # lambda_=0：純多樣性（相關性權重 0）；不該炸，且回滿額相異索引。
    cands = [onehot(0), onehot(1), onehot(2)]
    order = mmr_select(cands, onehot(0), k=3, lambda_=0.0)
    assert sorted(order) == [0, 1, 2]


def test_mmr_lambda_boundary_values_accepted():
    # lambda_ 邊界 0.0 與 1.0 皆合法、不丟例外。
    assert mmr_select([onehot(0)], onehot(0), k=1, lambda_=0.0) == [0]
    assert mmr_select([onehot(0)], onehot(0), k=1, lambda_=1.0) == [0]


def test_mmr_negative_lambda_raises():
    try:
        mmr_select([onehot(0)], onehot(0), k=1, lambda_=-0.1)
    except ValueError:
        pass
    else:
        raise AssertionError("lambda_ 負值應丟 ValueError")


# ---------------------------------------------------------------------------
# 額外邊界：句子切分（unicode / zh 標點 / 表情）
# ---------------------------------------------------------------------------
def test_split_pure_punctuation_only_is_empty():
    assert split_sentences("。。。") == []
    assert split_sentences("！？！") == []


def test_split_emoji_only_dropped():
    # 純表情符號（非中日韓、非英數）→ 無實質內容，剔除。
    assert split_sentences("😀😀😀") == []


def test_split_keeps_two_char_chinese_with_punct():
    # '好。' 共兩字（含標點）達 _MIN_SENT_CHARS 且含中文 → 保留。
    assert split_sentences("好。") == ["好。"]


def test_split_full_width_and_half_width_mixed():
    out = split_sentences("第一句。Second sentence! 第三句？")
    assert out == ["第一句。", "Second sentence!", "第三句？"]


def test_split_carriage_return_newline():
    # \r\n 換行也是切點。
    assert split_sentences("甲乙\r\n丙丁") == ["甲乙", "丙丁"]


# ---------------------------------------------------------------------------
# 額外邊界：extract_key_sentences / cluster_events
# ---------------------------------------------------------------------------
def test_extract_k_zero_returns_empty():
    posts = [{"id": "p1", "text": "一句話。兩句話。"}]
    assert extract_key_sentences(posts, fake_embed, k=0) == []


def test_extract_alternate_text_fields():
    # _post_text 容忍 content / body 欄位。
    posts = [{"id": "p1", "content": "用 content 欄位的內容。"}]
    out = extract_key_sentences(posts, fake_embed, k=1)
    assert out and out[0].text == "用 content 欄位的內容。"


def test_extract_post_id_alternate_keys():
    # _post_id 容忍 post_id / pk。
    posts = [{"post_id": "alt", "text": "有 post_id 的貼文。"}]
    out = extract_key_sentences(posts, fake_embed, k=1)
    assert out[0].post_id == "alt"


def test_extract_all_blank_text_returns_empty():
    posts = [{"text": "   "}, {"text": ""}]
    assert extract_key_sentences(posts, fake_embed, k=3) == []


def test_cluster_events_min_size_one_keeps_singletons():
    posts = [{"text": "alpha beta"}, {"text": "gamma delta"}]
    events = cluster_events(posts, fake_embed, threshold=0.99, min_size=1)
    assert len(events) == 2
    for e in events:
        assert e.size == 1
        assert e.representative in e.members
