"""
silver 摘要訓練資料建構測試 —— 教師蒸餾純函式層（完全離線）。

generate_fn / nli_fn 全部注入假的確定性版本（與 test_event_pipeline.py 同套路），
不打 Ollama、不載任何模型。重點驗證：
- event_key 的確定性 / 順序不變性（增量續跑的去重鍵）。
- 訓練記錄與 train_summarizer.py 的對齊：欄位形狀、prompt round-trip 不變量
  （key_sentences 存進 JSON 再讀回，重建的 prompt 必須與教師生成時逐字相同）。
- distill_event 的過濾閘門：空摘要 / 形式不合格 / NLI 低分 各自被正確拒絕。
"""
import re

from ml import silver_summaries as ss
from ml.event_cluster import KeySentence as ClusterKeySentence
from ml.summarize import KeySentence as SumKeySentence, build_summary_prompt

# ---------------------------------------------------------------------------
# 假模型（確定性、零依賴）
# ---------------------------------------------------------------------------
_SRC_LINE_RE = re.compile(r"^\[(\d+)\]\s*(.*?)(?:（來源：.*）)?\s*$")


def _parse_prompt_sources(prompt: str) -> list[tuple[int, str]]:
    """從 build_summary_prompt 的「來源：」區塊抽 (編號, 文字)。"""
    out: list[tuple[int, str]] = []
    in_block = False
    for line in prompt.splitlines():
        s = line.strip()
        if s == "來源：":
            in_block = True
            continue
        if not in_block:
            continue
        if s == "事件摘要：":
            break
        m = _SRC_LINE_RE.match(s)
        if m:
            out.append((int(m.group(1)), m.group(2).strip()))
    return out


def faithful_generate(prompt: str) -> str:
    """忠實假教師：逐來源取前段文字並附正確 [n] 引註。"""
    parts = []
    for n, text in _parse_prompt_sources(prompt):
        head = text[:12].rstrip("，,。.、")
        if head:
            parts.append(f"{head} [{n}]。")
    return "".join(parts)


def uncited_generate(prompt: str) -> str:
    """壞教師：有內容但完全不標引註（該被 format_issues 擋下）。"""
    srcs = _parse_prompt_sources(prompt)
    return "".join(f"{text[:10]}。" for _, text in srcs if text)


def empty_generate(_prompt: str) -> str:
    """壞教師：只回前言雜訊，清完是空的。"""
    return "摘要："


def _char_tokens(text: str) -> set[str]:
    return {ch for ch in text if not ch.isspace()}


def subset_nli(premise: str, hypothesis: str) -> dict:
    """子集蘊含假 NLI：hypothesis 字元 ⊆ premise → 高蘊含。"""
    p, h = _char_tokens(premise), _char_tokens(hypothesis)
    if h and h <= p:
        return {"entailment": 0.9, "neutral": 0.08, "contradiction": 0.02}
    if h & p:
        return {"entailment": 0.4, "neutral": 0.5, "contradiction": 0.1}
    return {"entailment": 0.05, "neutral": 0.9, "contradiction": 0.05}


def low_nli(_premise: str, _hypothesis: str) -> dict:
    """一律低蘊含的假 NLI（模擬教師整段幻覺）。"""
    return {"entailment": 0.1, "neutral": 0.3, "contradiction": 0.6}


def _cluster_keys() -> list[ClusterKeySentence]:
    """三句關鍵句、兩個相異來源（th_1 出現兩句 → 共用編號）。"""
    return [
        ClusterKeySentence(text="OpenAI 發表新模型 GPT-5", post_index=0, post_id="th_1", rank=0),
        ClusterKeySentence(text="API 價格與前代相同", post_index=1, post_id="th_2", rank=1),
        ClusterKeySentence(text="GPT-5 主打更強推理能力", post_index=0, post_id="th_1", rank=2),
    ]


# ---------------------------------------------------------------------------
# event_key / done_event_keys
# ---------------------------------------------------------------------------
class TestEventKey:
    def test_deterministic_and_order_insensitive(self):
        assert ss.event_key(["a", "b", 3]) == ss.event_key([3, "b", "a"])
        assert ss.event_key(["a", "b"]) == ss.event_key(["a", "b"])

    def test_different_members_different_key(self):
        assert ss.event_key(["a", "b"]) != ss.event_key(["a", "b", "c"])
        # id 串接不得產生歧義：["ab"] ≠ ["a","b"]
        assert ss.event_key(["ab"]) != ss.event_key(["a", "b"])

    def test_hex_shape(self):
        key = ss.event_key(["x"])
        assert re.fullmatch(r"[0-9a-f]{16}", key)

    def test_done_event_keys(self):
        records = [
            {"event_key": "k1"},
            {"event_key": "k2", "summary": "…"},
            {"summary": "沒 key 的舊記錄"},
            {"event_key": ""},
        ]
        assert ss.done_event_keys(records) == {"k1", "k2"}

    def test_done_event_keys_empty(self):
        assert ss.done_event_keys([]) == set()


# ---------------------------------------------------------------------------
# 記錄組裝 / train_summarizer 對齊
# ---------------------------------------------------------------------------
class TestBuildSilverRecord:
    def _keys(self) -> list[SumKeySentence]:
        return [
            SumKeySentence(text="句一", source_id=1, source="Threads"),
            SumKeySentence(text="句二", source_id=2, source=""),
        ]

    def test_core_fields(self):
        rec = ss.build_silver_record(
            self._keys(), " 摘要 [1]。 ", faithfulness_score=0.8341,
            max_sentences=6, lang="zh-Hant",
        )
        assert rec["summary"] == "摘要 [1]。"  # 去頭尾空白
        assert rec["max_sentences"] == 6
        assert rec["lang"] == "zh-Hant"
        assert rec["faithfulness_score"] == 0.8341
        assert rec["key_sentences"] == [
            {"text": "句一", "source_id": 1, "source": "Threads"},
            {"text": "句二", "source_id": 2, "source": ""},
        ]

    def test_no_nli_no_score_field(self):
        """沒跑 NLI 就不寫 faithfulness_score（train 端缺省當 1.0，不能亂填）。"""
        rec = ss.build_silver_record(self._keys(), "摘要 [1]。")
        assert "faithfulness_score" not in rec

    def test_extra_merged_but_cannot_overwrite_core(self):
        rec = ss.build_silver_record(
            self._keys(), "摘要 [1]。",
            extra={"event_key": "k1", "post_ids": ["a"], "summary": "汙染", "lang": "en"},
        )
        assert rec["event_key"] == "k1"
        assert rec["post_ids"] == ["a"]
        assert rec["summary"] == "摘要 [1]。"  # 核心欄位優先
        assert rec["lang"] == "zh-Hant"

    def test_prompt_roundtrip_invariant(self):
        """KEYSTONE：key_sentences 存成 JSON 再讀回，重建 prompt 必須逐字相同
        （train_summarizer 用同一份 build_summary_prompt 重建 → 訓練 prompt == 教師 prompt）。"""
        keys = self._keys()
        rec = ss.build_silver_record(keys, "摘要 [1]。", max_sentences=8)
        original = build_summary_prompt(keys, max_sentences=8)
        rebuilt = build_summary_prompt(rec["key_sentences"], max_sentences=rec["max_sentences"])
        assert rebuilt == original


# ---------------------------------------------------------------------------
# distill_event 過濾閘門
# ---------------------------------------------------------------------------
class TestDistillEvent:
    def test_happy_path(self):
        out = ss.distill_event(
            _cluster_keys(), faithful_generate, subset_nli,
            min_faithfulness=0.5, extra={"event_key": "k1", "post_ids": ["th_1", "th_2"]},
        )
        assert out.ok and out.status == ss.STATUS_OK
        rec = out.record
        assert rec is not None
        # train_summarizer._load_records 的必要條件：非空 key_sentences + 非空 summary
        assert rec["key_sentences"] and rec["summary"]
        assert rec["event_key"] == "k1"
        # 相異來源編號契約：th_1 兩句共用 1、th_2 為 2
        sids = [k["source_id"] for k in rec["key_sentences"]]
        assert sids == [1, 2, 1]
        # 忠實假教師 + 子集 NLI → 高綜合分且寫進記錄
        assert out.faithfulness_score is not None
        assert rec["faithfulness_score"] == round(out.faithfulness_score, 4)
        assert rec["faithfulness_score"] >= 0.5
        # 摘要帶合法引註
        assert "[1]" in rec["summary"] and "[2]" in rec["summary"]

    def test_empty_summary_rejected(self):
        out = ss.distill_event(_cluster_keys(), empty_generate, subset_nli)
        assert not out.ok and out.status == ss.STATUS_EMPTY_SUMMARY
        assert out.record is None

    def test_uncited_rejected_when_require_ok(self):
        out = ss.distill_event(_cluster_keys(), uncited_generate, subset_nli)
        assert out.status == ss.STATUS_FORMAT_ISSUES
        assert out.record is None
        assert out.issues is not None and out.issues.uncited_sentences

    def test_uncited_allowed_when_not_require_ok(self):
        """關掉形式閘門時，無引註摘要可通過（NLI 退回全來源對照仍可能高蘊含）。"""
        out = ss.distill_event(
            _cluster_keys(), uncited_generate, subset_nli,
            require_ok=False, min_faithfulness=0.0,
        )
        assert out.ok
        assert out.record is not None

    def test_low_faithfulness_rejected(self):
        out = ss.distill_event(
            _cluster_keys(), faithful_generate, low_nli, min_faithfulness=0.5
        )
        assert out.status == ss.STATUS_LOW_FAITHFULNESS
        assert out.record is None
        assert out.faithfulness_score is not None and out.faithfulness_score < 0.5
        assert out.summary_text  # 拒絕樣本仍保留摘要文字供人工複查

    def test_no_nli_skips_score(self):
        out = ss.distill_event(_cluster_keys(), faithful_generate, None)
        assert out.ok
        assert out.faithfulness_score is None
        assert "faithfulness_score" not in out.record

    def test_no_key_sentences(self):
        out = ss.distill_event([], faithful_generate, subset_nli)
        assert out.status == ss.STATUS_NO_KEY_SENTENCES
        assert out.record is None

    def test_record_lang_and_max_sentences_propagated(self):
        out = ss.distill_event(
            _cluster_keys(), faithful_generate, None, max_sentences=5, lang="zh-Hant"
        )
        assert out.record["max_sentences"] == 5
        assert out.record["lang"] == "zh-Hant"
