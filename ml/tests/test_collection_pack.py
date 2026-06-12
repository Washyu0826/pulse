"""collection_pack 純函式測試（不需網路；generate_fn 用 fake）。"""
import json

from ml.collection_pack import (
    THEME_ORDER,
    build_distill_prompt,
    build_pack,
    deterministic_section,
    format_sources_jsonl,
    group_by_theme,
)

POSTS = [
    {"id": 1, "title": "Tool A", "title_zh": "工具 A", "snippet": "do x", "source": "threads",
     "url": "http://a", "models": ["claude"], "theme": "新工具", "posted_at": "2026-06-10"},
    {"id": 2, "title": "How to RAG", "title_zh": None, "snippet": "steps", "source": "hackernews",
     "url": "http://b", "models": [], "theme": "使用方法", "posted_at": None},
    {"id": 3, "title": "Weird", "snippet": "", "source": "devto", "url": None,
     "models": [], "theme": "不存在的主題", "posted_at": None},
]


def test_group_by_theme_order_and_unknown_bucket():
    g = group_by_theme(POSTS)
    # 只回有資料的主題，且依 THEME_ORDER 排序
    assert list(g.keys()) == [t for t in THEME_ORDER if t in ("新工具", "使用方法", "其他")]
    # 未知主題歸「其他」
    assert g["其他"][0]["id"] == 3


def test_build_distill_prompt_has_sources_and_rules():
    p = build_distill_prompt("使用方法", [POSTS[1]])
    assert "主題是「使用方法」" in p
    assert "[1]" in p and "How to RAG" in p
    assert p.rstrip().endswith("材料：")


def test_deterministic_section_has_citation_and_link():
    s = deterministic_section("新工具", [POSTS[0]])
    assert "工具 A" in s and "[1]" in s and "http://a" in s


def test_build_pack_with_fake_llm_distills_and_cites():
    calls = []

    def fake(prompt: str) -> str:
        calls.append(prompt)
        return "- 重點 [1]。"

    pack = build_pack(POSTS, fake, title="測試包")
    assert pack["n_posts"] == 3
    assert "# 測試包" in pack["markdown"]
    assert "## 主題：新工具（收藏 1 篇）" in pack["markdown"]
    assert "重點 [1]。" in pack["markdown"]
    # 每個有資料主題各呼叫一次 LLM
    assert len(calls) == len(group_by_theme(POSTS))
    assert all(t["distilled"] for t in pack["themes"])


def test_build_pack_llm_failure_falls_back():
    def boom(_p: str) -> str:
        raise RuntimeError("ollama down")

    pack = build_pack([POSTS[0]], boom)
    # 失敗 → 退回確定性段落（仍有標題與來源）
    assert "工具 A" in pack["markdown"]
    assert pack["themes"][0]["distilled"] is False


def test_build_pack_no_llm_is_deterministic():
    pack = build_pack(POSTS, None)
    assert all(t["distilled"] is False for t in pack["themes"])
    assert "工具 A" in pack["markdown"]


def test_format_sources_jsonl_roundtrip():
    out = format_sources_jsonl(POSTS)
    rows = [json.loads(line) for line in out.strip().splitlines()]
    assert len(rows) == 3
    assert rows[0]["id"] == 1 and rows[0]["title"] == "工具 A"
    assert rows[2]["theme"] == "不存在的主題"  # 原樣保留於 sources（分組才兜底）
