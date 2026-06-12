"""
收藏 → 知識材料包 —— 把使用者精選的收藏貼文，蒸成「做 skill / agent 的材料」。

產品定位（[[user-rag-differentiate]]：避開純 RAG）：這是「策展 → 生成行動產物」，
不是檢索。把同主題的收藏交給地端 LLM 蒸成可重用材料（使用方法→步驟流程；
新工具/模型動態→工具卡），每點附來源編號 [n]，再配一份 sources.jsonl 附原始貼文。

設計（與 summarize.py 同風格）：
- 純函式 group_by_theme / build_distill_prompt / deterministic_section / assemble_markdown /
  format_sources_jsonl 不需網路 → 可單元測試。
- LLM 呼叫以 generate_fn 注入（distill_section 接 `generate_fn(prompt)->str`），
  測試傳 fake、正式由 API 傳 Ollama-backed；本模組不碰任何網路。
- 無 LLM（或失敗）時 deterministic_section 提供確定性退場（標題＋來源連結條列）。
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from typing import Any

def _clean_llm_output(text: str) -> str:
    """清掉 LLM 常見雜訊：外層 markdown code fence（```lang … ```）。純函式。"""
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[^\n]*\n?", "", t)
        t = re.sub(r"\n?```\s*$", "", t)
    return t.strip()

# 主題顯示順序（對齊 ml.theme / 前端 ThemeLabel）。未知主題歸到「其他」。
THEME_ORDER = ["新工具", "模型動態", "使用方法", "風險限制", "倫理法規", "其他"]
_VALID = set(THEME_ORDER)

# 各主題給 LLM 的蒸餾指引（決定輸出長相）。
# 一律用「粗體小標 + 條列」而非表格：實測 7b 看到全形｜欄位｜會誤排成亂掉的 markdown 表格。
_THEME_GUIDE = {
    "使用方法": "抽成「可照做的步驟流程」：用條列（必要時分小節），不要用表格。",
    "新工具": "抽成「工具卡」：每個工具一個條目，以粗體小標分列 能做什麼 / 何時用 / 連結，不要用表格。",
    "模型動態": "抽成「重點動態」：每則一個條目，以粗體小標分列 發生什麼 / 影響 / 連結，不要用表格。",
    "風險限制": "抽成「風險清單」：每項一個條目，以粗體小標分列 風險 / 情境 / 如何留意，不要用表格。",
    "倫理法規": "抽成「倫理／法規要點」：每項一個條目，以粗體小標分列 議題 / 立場或規範 / 出處，不要用表格。",
    "其他": "抽成精簡重點條列，不要用表格。",
}


def _pick(post: dict, *keys: str) -> str:
    """取第一個非空欄位（繁中優先）。"""
    for k in keys:
        v = post.get(k)
        if v:
            return str(v).strip()
    return ""


def group_by_theme(posts: Sequence[dict]) -> dict[str, list[dict]]:
    """把貼文依主題分組，回傳「有資料的主題」依 THEME_ORDER 排序的 dict。未知主題→其他。純函式。"""
    buckets: dict[str, list[dict]] = {t: [] for t in THEME_ORDER}
    for p in posts:
        theme = p.get("theme") if p.get("theme") in _VALID else "其他"
        buckets[theme].append(p)
    return {t: buckets[t] for t in THEME_ORDER if buckets[t]}


def _format_sources_block(posts: Sequence[dict]) -> str:
    """編號來源區塊 [1] 標題（來源）連結 —— 給 LLM prompt 與引註對齊用。"""
    lines = []
    for n, p in enumerate(posts, start=1):
        title = _pick(p, "title_zh", "title")
        src = _pick(p, "source")
        url = _pick(p, "url")
        tag = f"（{src}）" if src else ""
        link = f" {url}" if url else ""
        lines.append(f"[{n}] {title}{tag}{link}")
    return "\n".join(lines)


def build_distill_prompt(theme: str, posts: Sequence[dict]) -> str:
    """組「把同主題收藏蒸成材料」的 prompt（繁中、強制引註 [n]、只用來源事實）。純函式。"""
    guide = _THEME_GUIDE.get(theme, _THEME_GUIDE["其他"])
    sources = _format_sources_block(posts)
    return (
        "你是一位嚴謹的技術編輯，要把多則同主題的收藏整理成「可重複使用的知識材料」"
        "（之後拿來做 skill / agent 的素材）。\n"
        "請用繁體中文（台灣用語），並嚴格遵守：\n"
        f"1. 主題是「{theme}」。{guide}\n"
        "2. 只能使用下方編號來源裡出現的事實；不得加入來源沒寫到的資訊或臆測。\n"
        "3. 每個要點結尾標註支持它的來源編號，格式 [n]（多個寫 [1][3]）。\n"
        "4. 精簡、客觀、可操作；直接輸出 markdown 條列本文，不要前言或結語。\n\n"
        "來源：\n"
        f"{sources}\n\n"
        "材料："
    )


def deterministic_section(theme: str, posts: Sequence[dict]) -> str:
    """無 LLM 時的確定性退場：標題 + 來源連結條列（每則附來源編號與平台）。純函式。"""
    lines = []
    for n, p in enumerate(posts, start=1):
        title = _pick(p, "title_zh", "title") or "(無標題)"
        src = _pick(p, "source")
        url = _pick(p, "url")
        snippet = _pick(p, "snippet_zh", "snippet")
        head = f"- **{title}**" + (f"（{src}）" if src else "") + f" [{n}]"
        lines.append(head)
        if snippet and snippet != title:
            lines.append(f"  - {snippet}")
        if url:
            lines.append(f"  - 來源：{url}")
    return "\n".join(lines)


def assemble_markdown(sections: Sequence[tuple[str, int, str]], *, title: str = "收藏知識材料包") -> str:
    """把各主題段落組成完整 markdown 文件。sections=[(主題, 篇數, 內文), ...]。純函式。"""
    out = [f"# {title}", ""]
    for theme, count, body in sections:
        out.append(f"## 主題：{theme}（收藏 {count} 篇）")
        out.append("")
        out.append(body.strip() or "_（無內容）_")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def format_sources_jsonl(posts: Sequence[dict]) -> str:
    """把所有收藏輸出成 sources.jsonl（一行一筆，含 id/主題/標題/來源/連結）。純函式。"""
    rows = []
    for p in posts:
        rows.append(json.dumps({
            "id": p.get("id"),
            "theme": p.get("theme"),
            "title": _pick(p, "title_zh", "title"),
            "title_original": p.get("title"),
            "source": p.get("source"),
            "url": p.get("url"),
            "models": p.get("models", []),
            "posted_at": p.get("posted_at"),
        }, ensure_ascii=False))
    return "\n".join(rows) + ("\n" if rows else "")


def build_pack(
    posts: Sequence[dict],
    generate_fn: Callable[[str], str] | None = None,
    *,
    title: str = "收藏知識材料包",
) -> dict[str, Any]:
    """
    主流程：分組 → 每組蒸餾（有 generate_fn 用 LLM，否則確定性退場）→ 組 markdown + sources.jsonl。

    generate_fn 由呼叫端注入（API 傳 Ollama-backed；測試傳 fake）。單組 LLM 失敗 → 退回該組確定性段落
    （不讓整包壞掉）。回傳 {markdown, sources_jsonl, themes:[{theme,count,distilled}], n_posts}。
    """
    grouped = group_by_theme(posts)
    sections: list[tuple[str, int, str]] = []
    theme_meta: list[dict] = []
    for theme, items in grouped.items():
        distilled = False
        body = ""
        if generate_fn is not None:
            try:
                body = _clean_llm_output(generate_fn(build_distill_prompt(theme, items)))
                distilled = bool(body)
            except Exception:
                body = ""
        if not body:
            body = deterministic_section(theme, items)
        sections.append((theme, len(items), body))
        theme_meta.append({"theme": theme, "count": len(items), "distilled": distilled})
    markdown = assemble_markdown(sections, title=title)
    if any(m["distilled"] for m in theme_meta):
        # 蒸餾內容由地端 LLM 生成、可能有出入 → 提醒對照 sources.jsonl（誠實，非裝飾）。
        markdown += (
            "\n---\n_本材料由地端模型蒸餾自你的收藏，可能與原文有出入；"
            "引用前請對照同捆的 `sources.jsonl` 與原始連結。_\n"
        )
    return {
        "markdown": markdown,
        "sources_jsonl": format_sources_jsonl(posts),
        "themes": theme_meta,
        "n_posts": len(posts),
    }
