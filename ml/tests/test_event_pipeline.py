"""
端到端膠合層測試 —— 串接 event_cluster → summarize → faithfulness 的純編排。

不載入任何重依賴：三個模型（embed_fn / generate_fn / nli_fn）全部注入假的確定性版本，
故可完全離線跑。重點驗證「引註 [n] ↔ sources[n-1]」對齊不變量、adapter 的 1-based 連續
相異來源編號、以及整條管線的確定性與基本契約。
"""
import math
import re

from ml import event_pipeline
from ml.event_cluster import EventCluster, KeySentence
from ml.summarize import KeySentence as SumKeySentence

# ---------------------------------------------------------------------------
# 假 embedder：token bag → 固定維度 → L2 正規化（與 test_event_cluster 同套路）。
# 同字句 → 同向量；共享 token → 餘弦高。確定性、無外部依賴。
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
            if "一" <= ch <= "鿿":
                out.append(ch)
    if word:
        out.append(word)
    return out


def _hash_token(tok: str) -> int:
    h = 2166136261
    for ch in tok:
        h = (h ^ ord(ch)) * 16777619 % (2**32)
    return h


def fake_embed(text: str) -> list[float]:
    vec = [0.0] * _DIM
    for tok in _tokens(text):
        vec[_hash_token(tok) % _DIM] += 1.0
    n = math.sqrt(sum(x * x for x in vec))
    if n == 0.0:
        return vec
    return [x / n for x in vec]


# ---------------------------------------------------------------------------
# 假 generate_fn：從 prompt 的「來源：」區塊解析出 [k] 編號句，
# 對每條來源輸出「<該來源前幾個字> [k]。」，組成一段良好引註的摘要。
# 這模擬一個忠實模型：只用來源句的字、且逐句標正確編號。
# ---------------------------------------------------------------------------
_SRC_LINE_RE = re.compile(r"^\[(\d+)\]\s*(.*?)(?:（來源：.*）)?\s*$")


def _parse_prompt_sources(prompt: str) -> list[tuple[int, str]]:
    """從 summarize.build_summary_prompt 的 prompt 抽出 (編號, 來源文字) 清單。"""
    out: list[tuple[int, str]] = []
    in_block = False
    for line in prompt.splitlines():
        if line.strip() == "來源：":
            in_block = True
            continue
        if not in_block:
            continue
        if line.strip() == "事件摘要：":
            break
        m = _SRC_LINE_RE.match(line.strip())
        if m:
            out.append((int(m.group(1)), m.group(2).strip()))
    return out


def faithful_generate(prompt: str) -> str:
    """忠實 fake：每條來源 → 取其前 8 字 + [k]。，全部串成摘要。"""
    srcs = _parse_prompt_sources(prompt)
    parts = []
    for n, text in srcs:
        head = text[:8] if text else text
        parts.append(f"{head} [{n}]。")
    return "".join(parts)


def out_of_range_generate(prompt: str) -> str:
    """越界 fake：引用一個不存在的來源編號（來源數 + 5），觸發 issues。"""
    srcs = _parse_prompt_sources(prompt)
    bad = len(srcs) + 5
    return f"這是一個亂引用的句子 [{bad}]。"


def empty_generate(_prompt: str) -> str:
    """空輸出 fake。"""
    return ""


# ---------------------------------------------------------------------------
# 假 nli_fn：hypothesis 的 token 若 ⊆ premise → 高蘊含；否則中性。確定性。
# ---------------------------------------------------------------------------
def fake_nli(premise: str, hypothesis: str) -> dict:
    p = set(_tokens(premise))
    h = set(_tokens(hypothesis))
    if h and h <= p:
        return {"entailment": 0.9, "neutral": 0.08, "contradiction": 0.02}
    if h & p:
        return {"entailment": 0.4, "neutral": 0.5, "contradiction": 0.1}
    return {"entailment": 0.05, "neutral": 0.9, "contradiction": 0.05}


# ---------------------------------------------------------------------------
# 共用資料：兩個清楚分離的事件群。
# ---------------------------------------------------------------------------
def _two_cluster_posts():
    return [
        {"id": "a1", "text": "新模型 發表 評測 跑分 推理"},
        {"id": "a2", "text": "新模型 發表 評測 跑分 推理"},
        {"id": "b1", "text": "美食 旅遊 景點 推薦 行程"},
        {"id": "b2", "text": "美食 旅遊 景點 推薦 行程"},
    ]


# ---------------------------------------------------------------------------
# adapter：to_summary_key_sentences
# ---------------------------------------------------------------------------
def test_adapter_produces_1based_contiguous_source_ids():
    keys = [
        KeySentence(text="句一", post_index=0, post_id="p1", rank=0),
        KeySentence(text="句二", post_index=1, post_id="p2", rank=1),
        KeySentence(text="句三", post_index=2, post_id="p3", rank=2),
    ]
    out = event_pipeline.to_summary_key_sentences(keys)
    assert all(isinstance(k, SumKeySentence) for k in out)
    assert [k.source_id for k in out] == [1, 2, 3]


def test_adapter_same_post_shares_source_id():
    # 兩句來自同一篇 (p1) → 共用編號 1；第三句來自 p2 → 編號 2。
    keys = [
        KeySentence(text="句一", post_index=0, post_id="p1", rank=0),
        KeySentence(text="句二", post_index=0, post_id="p1", rank=1),
        KeySentence(text="句三", post_index=1, post_id="p2", rank=2),
    ]
    out = event_pipeline.to_summary_key_sentences(keys)
    assert [k.source_id for k in out] == [1, 1, 2]


def test_adapter_falls_back_to_post_index_when_id_none():
    keys = [
        KeySentence(text="句一", post_index=3, post_id=None, rank=0),
        KeySentence(text="句二", post_index=3, post_id=None, rank=1),
        KeySentence(text="句三", post_index=7, post_id=None, rank=2),
    ]
    out = event_pipeline.to_summary_key_sentences(keys)
    # 同 post_index 共用，相異 post_index 換新編號，皆 1-based 連續。
    assert [k.source_id for k in out] == [1, 1, 2]


def test_adapter_preserves_order_and_text():
    keys = [
        KeySentence(text="alpha", post_index=0, post_id="x", rank=0),
        KeySentence(text="beta", post_index=1, post_id="y", rank=1),
    ]
    out = event_pipeline.to_summary_key_sentences(keys)
    assert [k.text for k in out] == ["alpha", "beta"]


def test_adapter_empty():
    assert event_pipeline.to_summary_key_sentences([]) == []


# ---------------------------------------------------------------------------
# build_sources + 引註↔來源對齊不變量
# ---------------------------------------------------------------------------
def test_build_sources_one_per_keysentence():
    summary_keys = [
        SumKeySentence(text="第一句", source_id=1),
        SumKeySentence(text="第二句", source_id=1),
        SumKeySentence(text="第三句", source_id=2),
    ]
    sources = event_pipeline.build_sources(summary_keys)
    # sources 逐關鍵句排（與 summarize 顯示編號 [k] 對齊），故長度 == 關鍵句數。
    assert sources == ["第一句", "第二句", "第三句"]


def test_citation_source_alignment_invariant():
    """
    核心不變量：summary 的 [n] 必須對齊 sources[n-1]。

    用 faithful_generate（逐來源輸出 <來源前幾字> [n]）跑一個事件，
    再人工核對每個被引用的句子，其引用編號 n 指向的 sources[n-1] 確實含有該句的字。
    """
    posts = [{"id": "a1", "text": "新模型 發表 評測"}, {"id": "a2", "text": "新模型 發表 評測"}]
    cluster = EventCluster(members=[0, 1], representative=0, size=2)
    res = event_pipeline.summarize_one_event(
        cluster, posts, fake_embed, faithful_generate, fake_nli, k=4
    )
    # 對 summary 每一句：其引用編號 n，sources[n-1] 應蘊含該句（fake_nli 高蘊含）。
    assert res.faithfulness is not None
    assert res.faithfulness.n_sentences >= 1
    for se in res.faithfulness.per_sentence:
        for c in se.citations:
            assert 1 <= c <= len(res.sources)
            # sources[c-1] 的 token 應涵蓋該句 hypothesis 的 token（忠實 fake 保證）。
            src_tokens = set(_tokens(res.sources[c - 1]))
            hyp_tokens = set(_tokens(se.text))
            assert hyp_tokens <= src_tokens


def test_sources_length_matches_keysentences():
    posts = [{"id": "a1", "text": "新模型 發表 評測"}, {"id": "a2", "text": "新模型 發表 評測"}]
    cluster = EventCluster(members=[0, 1], representative=0, size=2)
    res = event_pipeline.summarize_one_event(
        cluster, posts, fake_embed, faithful_generate, fake_nli, k=4
    )
    assert len(res.sources) == len(res.key_sentences)


# ---------------------------------------------------------------------------
# summarize_one_event
# ---------------------------------------------------------------------------
def test_summarize_one_event_basic():
    posts = [{"id": "a1", "text": "新模型 發表 評測"}, {"id": "a2", "text": "新模型 發表 評測"}]
    cluster = EventCluster(members=[0, 1], representative=0, size=2)
    res = event_pipeline.summarize_one_event(
        cluster, posts, fake_embed, faithful_generate, fake_nli, k=4
    )
    assert isinstance(res, event_pipeline.EventSummaryResult)
    assert res.summary is not None and res.summary.text.strip()
    assert res.issues is not None
    assert 0.0 <= res.faithfulness.faithfulness_score <= 1.0


def test_summarize_one_event_uses_only_cluster_members():
    # cluster 只含 0、1；貼文 2、3 是別的內容，不應出現在來源。
    posts = _two_cluster_posts()
    cluster = EventCluster(members=[0, 1], representative=0, size=2)
    res = event_pipeline.summarize_one_event(
        cluster, posts, fake_embed, faithful_generate, fake_nli, k=4
    )
    joined = " ".join(res.sources)
    assert "美食" not in joined and "旅遊" not in joined


def test_summarize_one_event_faithful_score_high():
    posts = [{"id": "a1", "text": "新模型 發表 評測"}, {"id": "a2", "text": "新模型 發表 評測"}]
    cluster = EventCluster(members=[0, 1], representative=0, size=2)
    res = event_pipeline.summarize_one_event(
        cluster, posts, fake_embed, faithful_generate, fake_nli, k=4
    )
    # 忠實 fake → 每句被其來源蘊含、有效引用 → 分數應偏高。
    assert res.faithfulness.faithfulness_score > 0.5
    assert res.issues.ok


# ---------------------------------------------------------------------------
# run_pipeline
# ---------------------------------------------------------------------------
def test_run_pipeline_two_clusters():
    posts = _two_cluster_posts()
    results = event_pipeline.run_pipeline(
        posts, fake_embed, faithful_generate, fake_nli, threshold=0.9, min_size=2, k=4
    )
    assert len(results) == 2
    for res in results:
        assert res.summary is not None and res.summary.text.strip()
        assert res.issues is not None
        assert 0.0 <= res.faithfulness.faithfulness_score <= 1.0
        assert len(res.sources) == len(res.key_sentences)


def test_run_pipeline_empty_posts():
    assert event_pipeline.run_pipeline([], fake_embed, faithful_generate, fake_nli) == []


def test_run_pipeline_no_clusters_when_all_singletons():
    posts = [
        {"id": 1, "text": "電腦 程式 設計"},
        {"id": 2, "text": "貓咪 睡覺 可愛"},
        {"id": 3, "text": "汽車 引擎 維修"},
    ]
    results = event_pipeline.run_pipeline(
        posts, fake_embed, faithful_generate, fake_nli, threshold=0.9, min_size=2
    )
    assert results == []


def test_run_pipeline_out_of_range_citation_flagged():
    posts = [{"id": "a1", "text": "新模型 發表 評測"}, {"id": "a2", "text": "新模型 發表 評測"}]
    results = event_pipeline.run_pipeline(
        posts, fake_embed, out_of_range_generate, fake_nli, threshold=0.9, min_size=2, k=4
    )
    assert len(results) == 1
    res = results[0]
    # 越界引用應被 summarize 的 validate 抓到。
    assert res.issues.out_of_range_ids
    assert not res.issues.ok


def test_run_pipeline_empty_generation_flagged_empty():
    posts = [{"id": "a1", "text": "新模型 發表 評測"}, {"id": "a2", "text": "新模型 發表 評測"}]
    results = event_pipeline.run_pipeline(
        posts, fake_embed, empty_generate, fake_nli, threshold=0.9, min_size=2, k=4
    )
    assert len(results) == 1
    res = results[0]
    assert res.issues.empty
    assert res.faithfulness.n_sentences == 0


def test_run_pipeline_is_deterministic():
    posts = _two_cluster_posts()
    a = event_pipeline.run_pipeline(
        posts, fake_embed, faithful_generate, fake_nli, threshold=0.9, min_size=2, k=4
    )
    b = event_pipeline.run_pipeline(
        posts, fake_embed, faithful_generate, fake_nli, threshold=0.9, min_size=2, k=4
    )
    assert [r.summary.text for r in a] == [r.summary.text for r in b]
    assert [r.sources for r in a] == [r.sources for r in b]
    assert [r.faithfulness.faithfulness_score for r in a] == [
        r.faithfulness.faithfulness_score for r in b
    ]


def test_run_pipeline_results_ordered_by_cluster():
    posts = _two_cluster_posts()
    results = event_pipeline.run_pipeline(
        posts, fake_embed, faithful_generate, fake_nli, threshold=0.9, min_size=2, k=4
    )
    # cluster_events 依群最小成員索引排序 → 第一個結果群含貼文 0。
    assert 0 in results[0].cluster.members
    assert 2 in results[1].cluster.members


# ---------------------------------------------------------------------------
# 額外邊界：adapter 相異來源鍵
# ---------------------------------------------------------------------------
def test_adapter_post_id_zero_is_valid_and_shared():
    # post_id == 0 是合法 id（非 None）→ 同 id 共用編號，不被當缺失。
    keys = [
        KeySentence(text="句一", post_index=0, post_id=0, rank=0),
        KeySentence(text="句二", post_index=5, post_id=0, rank=1),
    ]
    out = event_pipeline.to_summary_key_sentences(keys)
    assert [k.source_id for k in out] == [1, 1]


def test_adapter_id_and_index_keys_do_not_collide():
    # post_id=0 與 post_index=0 不可被當成同一來源（_distinct_key 以 ("id"/"idx", v) 區分）。
    keys = [
        KeySentence(text="有 id", post_index=9, post_id=0, rank=0),
        KeySentence(text="無 id", post_index=0, post_id=None, rank=1),
    ]
    out = event_pipeline.to_summary_key_sentences(keys)
    assert [k.source_id for k in out] == [1, 2]


def test_adapter_interleaved_sources_keep_first_seen_numbering():
    # 編號依「首次出現順序」給；同來源後續再現沿用既有編號。
    keys = [
        KeySentence(text="a", post_index=0, post_id="p1", rank=0),
        KeySentence(text="b", post_index=1, post_id="p2", rank=1),
        KeySentence(text="c", post_index=0, post_id="p1", rank=2),  # p1 再現 → 仍 1
        KeySentence(text="d", post_index=2, post_id="p3", rank=3),
    ]
    out = event_pipeline.to_summary_key_sentences(keys)
    assert [k.source_id for k in out] == [1, 2, 1, 3]


# ---------------------------------------------------------------------------
# 額外邊界：build_sources
# ---------------------------------------------------------------------------
def test_build_sources_strips_whitespace_and_handles_blank():
    summary_keys = [
        SumKeySentence(text="  前後空白  ", source_id=1),
        SumKeySentence(text="", source_id=2),
    ]
    sources = event_pipeline.build_sources(summary_keys)
    assert sources == ["前後空白", ""]


def test_build_sources_empty():
    assert event_pipeline.build_sources([]) == []


# ---------------------------------------------------------------------------
# 額外邊界：單一成員事件群（min_size=1 路徑）
# ---------------------------------------------------------------------------
def test_summarize_one_event_single_member_cluster():
    posts = [{"id": "solo", "text": "獨立 事件 單篇 貼文"}]
    cluster = EventCluster(members=[0], representative=0, size=1)
    res = event_pipeline.summarize_one_event(
        cluster, posts, fake_embed, faithful_generate, fake_nli, k=4
    )
    assert res.summary is not None
    assert len(res.sources) == len(res.key_sentences)
    assert res.faithfulness is not None
    assert 0.0 <= res.faithfulness.faithfulness_score <= 1.0


def test_run_pipeline_min_size_one_keeps_singletons():
    # min_size=1 → 互不相似的三篇各自成事件，全部跑完管線。
    posts = [
        {"id": 1, "text": "電腦 程式 設計"},
        {"id": 2, "text": "貓咪 睡覺 可愛"},
        {"id": 3, "text": "汽車 引擎 維修"},
    ]
    results = event_pipeline.run_pipeline(
        posts, fake_embed, faithful_generate, fake_nli, threshold=0.99, min_size=1
    )
    assert len(results) == 3
    for res in results:
        assert res.cluster.size == 1
        assert 0.0 <= res.faithfulness.faithfulness_score <= 1.0


def test_pipeline_citation_alignment_holds_with_multi_sentence_posts():
    # 一篇多句：adapter 對「同來源多句」共用 source_id，但 build_sources 逐關鍵句排，
    # 故 [n] 仍對齊 sources[n-1]（n 為關鍵句序）。驗證對齊不變量在多句下成立。
    posts = [
        {"id": "p1", "text": "新模型 發表。新模型 評測。"},
        {"id": "p2", "text": "新模型 發表。新模型 評測。"},
    ]
    cluster = EventCluster(members=[0, 1], representative=0, size=2)
    res = event_pipeline.summarize_one_event(
        cluster, posts, fake_embed, faithful_generate, fake_nli, k=6
    )
    for se in res.faithfulness.per_sentence:
        for c in se.citations:
            assert 1 <= c <= len(res.sources)
            src_tokens = set(_tokens(res.sources[c - 1]))
            hyp_tokens = set(_tokens(se.text))
            assert hyp_tokens <= src_tokens
