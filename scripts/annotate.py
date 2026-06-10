"""
互動式人工標註器 —— 建 gold set（情緒 × 品質），落地 ADR-008 / annotation.py。

從 DB 分層抽樣（預設偏向中文貼文，因為 Pulse 轉向中文優先），在終端逐篇顯示，
按鍵標情緒(1/2/3)與品質(h/m/l)，即時 append 到 JSONL（可隨時中斷續標）。

用法（在你自己的終端跑，需要互動輸入）：
    # 首標：抽 200 篇中文為主的貼文來標
    python scripts/annotate.py --target 200 --zh

    # 續標：自動跳過 gold.jsonl 裡已標過的 post_id
    python scripts/annotate.py --target 200 --zh

    # 一致性重標：隔幾天後重標前 20 筆（round=2），算 self-consistency κ
    python scripts/annotate.py --relabel 20

操作鍵：
    情緒  1=負 2=中 3=正     品質  h=高 m=中 l=低
    主題  t=新工具 m=模型動態 u=使用方法 r=風險限制 e=倫理法規 o=其他
    s=跳過此篇   q=存檔離開
"""
import argparse
import asyncio
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "api"))
sys.path.insert(0, str(_ROOT / "ml"))

from api.database import AsyncSessionLocal  # noqa: E402
from api.models.posts import Post  # noqa: E402
from ml.annotation import (  # noqa: E402
    GoldLabel,
    append_jsonl,
    cohen_kappa,
    labeled_ids,
    load_jsonl,
    parse_quality_key,
    parse_sentiment_key,
    parse_theme_key,
    stratified_sample,
)
from sqlalchemy import select  # noqa: E402

DEFAULT_OUT = _ROOT / "data" / "gold" / "gold.jsonl"
_CJK_RE = re.compile(r"[一-鿿]")
_TEXT_SNIPPET = 600  # 顯示與快照截斷長度


def _cjk_ratio(text: str) -> float:
    """中日韓字元佔比 —— 用來偏向抽中文貼文（中文優先 gold set）。"""
    if not text:
        return 0.0
    return len(_CJK_RE.findall(text)) / len(text)


async def _fetch_candidates(min_quality: int) -> list[dict]:
    """撈可標註的貼文（品質達標 / 未檢核），回傳 dict 清單供分層抽樣。"""
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(Post.id, Post.source, Post.title, Post.content, Post.posted_at)
                .where((Post.quality_score.is_(None)) | (Post.quality_score >= min_quality))
                .order_by(Post.posted_at.desc())
            )
        ).all()
    return [
        {
            "id": r.id,
            "source": r.source,
            "title": r.title or "",
            "content": r.content or "",
            "posted_at": r.posted_at,
        }
        for r in rows
    ]


def _render(post: dict, idx: int, total: int) -> None:
    title, content = post["title"], post["content"]
    body = f"{title}. {content}".strip()
    zh = _cjk_ratio(body)
    print("\n" + "=" * 72)
    print(f"  [{idx}/{total}]  #{post['id']}  ·  {post['source']}  ·  中文比 {zh:.0%}")
    print("-" * 72)
    print(f"  {title}")
    if content:
        snippet = content[:_TEXT_SNIPPET]
        print(f"\n  {snippet}{'…' if len(content) > _TEXT_SNIPPET else ''}")
    print("=" * 72)


def _prompt(label: str, parser) -> str | None:
    """重複問到拿到合法鍵；回傳 None 代表使用者要跳過/離開（由呼叫端處理特殊鍵）。"""
    while True:
        raw = input(label).strip().lower()
        if raw in ("s", "q"):
            return raw  # 特殊鍵原樣回傳
        val = parser(raw)
        if val is not None:
            return val
        print("    ⚠️ 無效輸入，再試一次。")


async def annotate(out: Path, target: int, min_quality: int, zh_only: bool) -> None:
    existing = load_jsonl(out)
    done = labeled_ids(existing, round=1)
    print(f"📂 gold set：{out}（已標 {len(done)} 筆）")

    candidates = await _fetch_candidates(min_quality)
    if zh_only:
        candidates = [c for c in candidates if _cjk_ratio(f"{c['title']}{c['content']}") >= 0.20]
    candidates = [c for c in candidates if c["id"] not in done]
    if not candidates:
        print("✅ 沒有可標的新貼文（都標過了或抽不到）。")
        return

    need = max(0, target - len(done))
    batch = stratified_sample(candidates, need, strata_key="source")
    print(f"🎯 目標 {target} 筆，本次抽 {len(batch)} 筆待標。\n（情緒 1/2/3 · 品質 h/m/l · s 跳過 · q 存檔離開）")

    labeled = 0
    for post in batch:
        if post["id"] in done:  # 防衛：同一輪不重複寫 round=1（理論上 candidates 已去重）
            continue
        _render(post, len(done) + labeled + 1, target)
        sent = _prompt("  情緒 [1 負 / 2 中 / 3 正] > ", parse_sentiment_key)
        if sent == "q":
            break
        if sent == "s":
            continue
        qual = _prompt("  品質 [h 高 / m 中 / l 低] > ", parse_quality_key)
        if qual == "q":
            break
        if qual == "s":
            continue
        theme = _prompt(
            "  主題 [t 新工具 / m 模型動態 / u 使用方法 / r 風險限制 / e 倫理法規 / o 其他] > ",
            parse_theme_key,
        )
        if theme == "q":
            break
        if theme == "s":
            continue
        # 備註走原樣 input，但保留 q/s 語意（q 放棄此筆並離開、s 放棄此筆）
        note = input("  備註（可空白；q 放棄並離開 / s 放棄此篇）> ").strip()
        if note == "q":
            break
        if note == "s":
            continue

        rec = GoldLabel(
            post_id=post["id"],
            source=post["source"],
            sentiment=sent,
            quality=qual,
            text=f"{post['title']}. {post['content']}"[:_TEXT_SNIPPET],
            annotated_at=datetime.now(UTC).isoformat(),
            round=1,
            theme=theme,
            note=note,
        )
        append_jsonl(out, rec.to_json())
        done.add(post["id"])  # 即時記入，避免本輪後續或重入時重複
        labeled += 1

    print(f"\n💾 本次新標 {labeled} 筆，累計 {len(done) + labeled} / {target}。")


def _report_kappa(records: list[dict], field: str, label_zh: str) -> None:
    """報某維度（情緒/主題）的 self-consistency κ；空標籤（舊資料缺主題）不計。"""
    r1 = {r["post_id"]: r.get(field) for r in records if r.get("round", 1) == 1 and r.get(field)}
    r2 = {r["post_id"]: r.get(field) for r in records if r.get("round", 1) == 2 and r.get(field)}
    common = sorted(set(r1) & set(r2))
    if len(common) < 2:
        print(f"（{label_zh}：兩輪皆有的標註不足 2，暫不算 κ。）")
        return
    a = [r1[pid] for pid in common]
    b = [r2[pid] for pid in common]
    k = cohen_kappa(a, b)
    agree = sum(1 for x, y in zip(a, b, strict=True) if x == y) / len(common)
    flag = "  ✅ 達標" if k > 0.8 else "  ⚠️ 未達 0.8，檢視指南/難例"
    print(f"📐 self-consistency（{label_zh}，n={len(common)}）：κ={k:.3f} · 完全一致率={agree:.0%}{flag}")


async def relabel(out: Path, n: int) -> None:
    """一致性重標：取 round=1 前 n 筆重標成 round=2，算 self-consistency κ（情緒+主題）。"""
    existing = load_jsonl(out)
    round1 = [r for r in existing if r.get("round", 1) == 1][:n]
    if not round1:
        print("⚠️ 還沒有 round=1 的標註可重標。")
        return
    already2 = labeled_ids(existing, round=2)
    todo = [r for r in round1 if r["post_id"] not in already2]
    print(f"🔁 一致性重標：{len(round1)} 筆目標，{len(todo)} 筆待重標（隔時間盲標，別看舊答案）。")

    for i, old in enumerate(todo, 1):
        print("\n" + "=" * 72)
        print(f"  [重標 {i}/{len(todo)}]  #{old['post_id']}  ·  {old['source']}")
        print("-" * 72)
        print(f"  {old['text']}")
        print("=" * 72)
        sent = _prompt("  情緒 [1 負 / 2 中 / 3 正] > ", parse_sentiment_key)
        if sent in ("q", "s"):
            if sent == "q":
                break
            continue
        qual = _prompt("  品質 [h 高 / m 中 / l 低] > ", parse_quality_key)
        if qual in ("q", "s"):
            if qual == "q":
                break
            continue
        theme = _prompt(
            "  主題 [t 新工具 / m 模型動態 / u 使用方法 / r 風險限制 / e 倫理法規 / o 其他] > ",
            parse_theme_key,
        )
        if theme in ("q", "s"):
            if theme == "q":
                break
            continue
        rec = GoldLabel(
            post_id=old["post_id"], source=old["source"], sentiment=sent, quality=qual,
            text=old["text"], annotated_at=datetime.now(UTC).isoformat(), round=2, theme=theme,
        )
        append_jsonl(out, rec.to_json())

    # 算 self-consistency κ（只取兩輪都有的 post_id），情緒與主題各報一個。
    records = load_jsonl(out)
    print()
    _report_kappa(records, "sentiment", "情緒")
    _report_kappa(records, "theme", "主題")


def main() -> None:
    ap = argparse.ArgumentParser(description="Pulse 互動式人工標註器（gold set）")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="gold set JSONL 路徑")
    ap.add_argument("--target", type=int, default=200, help="目標標註總筆數")
    ap.add_argument("--min-quality", type=int, default=0, help="只標品質分 >= 此值（0=含未檢核）")
    ap.add_argument("--zh", action="store_true", help="只抽中文為主的貼文（CJK 比 >= 20%%）")
    ap.add_argument("--relabel", type=int, metavar="N", help="一致性重標前 N 筆（round=2）")
    args = ap.parse_args()

    if args.relabel is not None:
        asyncio.run(relabel(args.out, args.relabel))
    else:
        asyncio.run(annotate(args.out, args.target, args.min_quality, args.zh))


if __name__ == "__main__":
    main()
