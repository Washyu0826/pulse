"""
決策報告服務（F3/F4）—— 「Claude 還是 GPT 適合做 X?」

差異化：不是 LLM 空想，而是用 Pulse 的**真實資料**（口碑、討論量、熱門討論、發布）
產出有證據的結構化比較。LLM 只是選配的「自然語言合成」層（有 ANTHROPIC_API_KEY 才啟用）。
"""
import logging
from collections.abc import Sequence
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.models.models import Model, PostModel
from api.models.posts import Post
from api.services.models import get_model_dashboard

logger = logging.getLogger(__name__)


async def _top_discussions(
    session: AsyncSession, model_id: int, topic: str | None, n: int
) -> list[dict]:
    """某模型最熱門的討論（可選 topic 關鍵字過濾），依分數排序。"""
    stmt = (
        select(Post.title, Post.score, Post.url, Post.permalink, Post.source)
        .join(PostModel, PostModel.post_id == Post.id)
        .where(PostModel.model_id == model_id)
        .order_by(Post.score.desc())
        .limit(n)
    )
    if topic:
        like = f"%{topic}%"
        stmt = stmt.where(or_(Post.title.ilike(like), Post.content.ilike(like)))
    rows = (await session.execute(stmt)).all()
    return [
        {"title": r.title, "score": r.score, "url": r.url or r.permalink, "source": r.source}
        for r in rows
    ]


def _recommend(models: list[dict]) -> dict[str, Any]:
    """資料驅動推薦：以口碑為主、討論量為輔，選出最佳並說明理由。"""
    scored = [m for m in models if m.get("sentiment_index") is not None]
    if not scored:
        # 無情緒資料 → 退回「最多討論」
        winner = max(models, key=lambda m: m["posts_total"], default=None)
        if not winner:
            return {"winner": None, "reason": "資料不足，無法比較。"}
        return {
            "winner": winner["slug"],
            "reason": f"{winner['name']} 討論量最高（{winner['posts_total']:,} 篇），但尚無情緒資料。",
        }
    # 口碑優先；同分時看討論量
    winner = max(scored, key=lambda m: (m["sentiment_index"], m["posts_total"]))
    others = [m for m in scored if m["slug"] != winner["slug"]]
    detail = "、".join(f"{o['name']} 口碑 {o['sentiment_index']:+d}" for o in others)
    return {
        "winner": winner["slug"],
        "reason": (
            f"{winner['name']} 口碑最高（{winner['sentiment_index']:+d}），"
            f"近 7 天 {winner['posts_recent']} 篇討論。" + (f"相比之下 {detail}。" if detail else "")
        ),
    }


def _template_summary(topic: str | None, models: list[dict], rec: dict) -> str:
    """無 LLM 時的結構化文字摘要（資料驅動）。"""
    head = f"關於「{topic}」，" if topic else ""
    lines = [
        f"- **{m['name']}**：口碑 "
        + (f"{m['sentiment_index']:+d}" if m["sentiment_index"] is not None else "—")
        + f" · 累計討論 {m['posts_total']:,} · 近 7 天 {m['posts_recent']}"
        for m in models
    ]
    body = "\n".join(lines)
    verdict = f"\n\n**建議**：{rec['reason']}" if rec.get("winner") else ""
    return f"{head}各模型在 Pulse 上的真實數據：\n\n{body}{verdict}"


async def _llm_summary(topic: str | None, models: list[dict], rec: dict) -> str | None:
    """有 ANTHROPIC_API_KEY 時，用 Claude Haiku 把證據寫成自然語言。否則回 None。"""
    if not settings.anthropic_api_key:
        return None
    try:
        import anthropic  # 延遲 import：沒 key 就不需要這套件
    except ImportError:
        logger.warning("有 ANTHROPIC_API_KEY 但未裝 anthropic 套件，退回模板摘要。")
        return None
    evidence = "\n".join(
        f"{m['name']}: 口碑={m['sentiment_index']}, 討論總數={m['posts_total']}, "
        f"近7天={m['posts_recent']}, 熱門討論={[d['title'] for d in m['top_discussions']]}"
        for m in models
    )
    prompt = (
        f"你是 AI 模型選型顧問。根據以下 Pulse 真實社群數據，"
        f"針對問題「{topic or '整體比較'}」給出 3-5 句、有證據的中文建議，"
        f"明確指出推薦哪個模型與理由。只根據數據，不要編造。\n\n數據：\n{evidence}"
    )
    try:
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        msg = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text
    except Exception:  # noqa: BLE001 — LLM 失敗不該擋住報告
        logger.exception("LLM 合成失敗，退回模板摘要。")
        return None


async def compare_models(
    session: AsyncSession,
    slugs: Sequence[str],
    topic: str | None = None,
    top_n: int = 3,
) -> dict[str, Any]:
    """產出多模型比較報告（資料驅動，LLM 選配）。"""
    dashboard = {d["slug"]: d for d in await get_model_dashboard(session)}
    id_by_slug = {
        s: i for i, s in (await session.execute(select(Model.id, Model.slug))).all()
    }

    models: list[dict] = []
    for slug in slugs:
        d = dashboard.get(slug)
        mid = id_by_slug.get(slug)
        if not d or mid is None:
            continue
        models.append({**d, "top_discussions": await _top_discussions(session, mid, topic, top_n)})

    rec = _recommend(models)
    summary = await _llm_summary(topic, models, rec)
    return {
        "topic": topic,
        "models": models,
        "recommendation": rec,
        "summary": summary or _template_summary(topic, models, rec),
        "generated_by": "llm" if summary else "data",
    }
