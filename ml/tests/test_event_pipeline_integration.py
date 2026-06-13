"""
事件摘要端到端整合測試（SLOW）—— 接真實 BGE-M3 + 地端 Ollama + mDeBERTa-NLI。

純函式管線測試在 test_event_pipeline.py（注入假模型，永遠跑）。本檔不同：它真的把三個重模型
（embed_fn=BGE-M3、generate_fn=Ollama Qwen、nli_fn=mDeBERTa）接上 event_pipeline.run_pipeline /
summarize_one_event，鎖住「重模型路徑」端到端不退化。

**預設 SKIP**（讓 CI 與一般純函式套件不需重依賴即全綠）。同時滿足以下才會跑：
  1. 環境變數 PULSE_RUN_SLOW_INTEGRATION=1（明確啟用）；
  2. FlagEmbedding / transformers / httpx 都裝得起來（importorskip）；
  3. 本機 Ollama 服務可連、且目標模型已 pull。
缺任一條件 → pytest.skip（不是 error），故 `pytest -q` 在無重模型環境仍乾淨地跳過。

啟用方式（本機、已備妥模型時）：
    PULSE_RUN_SLOW_INTEGRATION=1 pytest ml/tests/test_event_pipeline_integration.py -q
可選環境變數：OLLAMA_HOST、PULSE_SUMMARIZE_MODEL（預設 qwen2.5:7b）。
"""
import os

import pytest

# 1) 明確啟用旗標：未設就整檔跳過（最便宜的閘門，先擋）。
if os.environ.get("PULSE_RUN_SLOW_INTEGRATION") != "1":
    pytest.skip(
        "慢速整合測試預設跳過；設 PULSE_RUN_SLOW_INTEGRATION=1 才跑（需 BGE-M3 + Ollama + mDeBERTa）。",
        allow_module_level=True,
    )

# 2) 重依賴可用性閘門：缺套件 → skip（不是 error）。
pytest.importorskip("FlagEmbedding", reason="需要 FlagEmbedding（BGE-M3）")
pytest.importorskip("transformers", reason="需要 transformers（mDeBERTa NLI）")
httpx = pytest.importorskip("httpx", reason="需要 httpx（呼叫 Ollama）")

from ml import event_pipeline  # noqa: E402
from ml.event_cluster import build_bge_m3_embedder  # noqa: E402
from ml.faithfulness import build_nli_fn  # noqa: E402
from ml.summarize import build_ollama_generate_fn  # noqa: E402

_OLLAMA = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
_SUMMARIZE_MODEL = os.environ.get("PULSE_SUMMARIZE_MODEL", "qwen2.5:7b")


def _ollama_ready() -> bool:
    """本機 Ollama 服務可連、且目標模型已 pull。"""
    try:
        r = httpx.get(f"{_OLLAMA}/api/tags", timeout=3.0)
        r.raise_for_status()
        names = {m.get("name", "") for m in r.json().get("models", [])}
        # 容忍 'qwen2.5:7b' vs 'qwen2.5:7b-instruct' 等變體：前綴比對。
        base = _SUMMARIZE_MODEL.split(":")[0]
        return any(n.startswith(base) for n in names)
    except Exception:  # noqa: BLE001 — 連不上即視為不可用 → skip
        return False


# 3) Ollama 服務閘門。
pytestmark = pytest.mark.skipif(
    not _ollama_ready(),
    reason=f"本機 Ollama（{_OLLAMA}）不可用或未 pull {_SUMMARIZE_MODEL}",
)


# 同一事件的多篇來源貼文（中英混雜，模擬 Threads/HN 轉貼）。
_POSTS = [
    {"id": 1, "text": "OpenAI 今天發表了 GPT-5，官方說在程式與推理上大幅進步。"},
    {"id": 2, "text": "GPT-5 released by OpenAI today. Big gains on coding and reasoning benchmarks."},
    {"id": 3, "text": "剛看到 OpenAI 推出 GPT-5，據說 coding 能力比前代強很多。"},
    {"id": 4, "text": "我家的貓今天很可愛，跟 AI 完全無關的一篇貼文。"},
]


@pytest.fixture(scope="module")
def heavy_fns():
    """惰性建三個重模型 callable；建不起來（下載失敗等）→ skip 而非 error。"""
    try:
        embed_fn = build_bge_m3_embedder()
        generate_fn = build_ollama_generate_fn(model=_SUMMARIZE_MODEL, host=_OLLAMA)
        nli_fn = build_nli_fn()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"重模型建置失敗（下載/環境問題）：{e}")
    yield embed_fn, generate_fn, nli_fn
    # 釋放 NLI 的 VRAM（若提供 release）。
    release = getattr(nli_fn, "release", None)
    if callable(release):
        release()


def test_run_pipeline_real_models_end_to_end(heavy_fns):
    """run_pipeline 接真實三模型：至少聚出 GPT-5 那一群，且摘要忠實度結構完整。"""
    embed_fn, generate_fn, nli_fn = heavy_fns
    results = event_pipeline.run_pipeline(
        _POSTS, embed_fn, generate_fn, nli_fn, threshold=0.6, min_size=2
    )
    # 4 篇裡 3 篇談 GPT-5、1 篇談貓 → 應至少聚出 1 個事件群（GPT-5）。
    assert len(results) >= 1
    r = results[0]
    # 契約：sources 長度 == summary 看到的關鍵句數；引註 [n] 對齊 sources[n-1]。
    assert r.summary is not None
    assert r.faithfulness is not None
    assert len(r.sources) >= 1
    assert r.faithfulness.n_sentences >= 1
    # 忠實度分數落在合法區間。
    assert 0.0 <= r.faithfulness.faithfulness_score <= 1.0
    # 事件群至少 2 篇（min_size=2），且代表貼文索引在成員內。
    assert r.cluster.size >= 2
    assert r.cluster.representative in r.cluster.members


def test_summarize_one_event_real_models(heavy_fns):
    """summarize_one_event 單一事件路徑：直接餵一個已知群，驗證引註↔來源對齊。"""
    embed_fn, generate_fn, nli_fn = heavy_fns
    from ml.event_cluster import cluster_events

    clusters = cluster_events(_POSTS, embed_fn, threshold=0.6, min_size=2)
    assert clusters, "真實 BGE-M3 應能把 3 篇 GPT-5 貼文聚成一群"
    res = event_pipeline.summarize_one_event(clusters[0], _POSTS, embed_fn, generate_fn, nli_fn)
    assert res.summary is not None and res.summary.text.strip()
    # 每個被引用的 source id 都落在 sources 範圍內（無越界引用）。
    n = len(res.sources)
    for se in res.faithfulness.per_sentence:
        for c in se.citations:
            assert 1 <= c <= n or c not in se.used_sources
