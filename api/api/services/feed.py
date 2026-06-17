"""
每日實用情報 feed 服務 —— 定位 C 的核心：以「主題」為主軸（新工具/模型動態/使用方法/
風險限制/倫理法規），模型 / 情緒 / 來源 / 時間為篩選維度。供首頁主題分區與主題列表頁共用。

只看高品質、非重複貼文（沿用 DQC 下游門檻 quality_post_filter），且只取「高信心」主題
（themes.confident），「其他」不在實用情報內。
"""
import re
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.models import Model, PostModel
from api.models.posts import Post
from api.models.sentiment import Sentiment
from api.models.theme import Theme
from api.models.translation import Translation
from api.services._quality import quality_post_filter
from api.services.recency import recency_column, recency_cutoff

# 重用 monorepo 的 ml 純函式做 per-source 平衡排序（與 routers/collection.py 同作法：
# 把 D:\pulse\ml 加進 path）。hotness 為純算術、無重依賴，import 安全。
_ML = Path(__file__).resolve().parents[3] / "ml"
if str(_ML) not in sys.path:
    sys.path.insert(0, str(_ML))

from ml import hotness as _hot  # noqa: E402

# 候選池上限：每主題在時間視窗內最多撈這麼多筆候選，再用 per-source 平衡排序在
# Python 端取 limit_per_theme 篇。設上限避免撈整表（某主題視窗內可能上千筆）；夠大
# 才能讓各來源（尤其量級低的 Threads）都進到候選、平衡排序才有東西可輪。視窗 7 天、
# 主力來源每天數十筆量級，200 足以涵蓋各來源典型量並留餘裕。
_CANDIDATE_POOL_CAP = 200

# 實用情報的五大主題（不含「其他」），與 ml/ml/theme.py THEME_HYPOTHESES 及前端
# web/components/theme-meta.tsx THEME_ORDER 對齊。順序＝首頁分區順序（新工具量最大擺第一）。
ACTIONABLE_THEMES: tuple[str, ...] = ("新工具", "模型動態", "使用方法", "風險限制", "倫理法規")

# legacy 映射：2026-06 主題改版（3 類 → 5 類）前，DB themes 表仍有少量舊「邊界」標籤
# （約 265 筆，尚未重跑分類）。「邊界」語意最接近「風險限制」（實務限制/失敗/風險），
# 故查詢層把它映射進「風險限制」，避免這批資料默默消失；輸出一律用正規標籤。
# 舊資料全數重跑分類後即可移除這個映射。
LEGACY_THEME_ALIASES: dict[str, tuple[str, ...]] = {"風險限制": ("邊界",)}

# 反向表：DB 舊標籤 → 正規標籤（彙總計數時用）。
_ALIAS_TO_CANONICAL: dict[str, str] = {
    alias: canonical for canonical, aliases in LEGACY_THEME_ALIASES.items() for alias in aliases
}


def _db_labels(label: str) -> tuple[str, ...]:
    """單一正規主題在 DB 中對應的標籤集合（含 legacy 別名）。"""
    return (label, *LEGACY_THEME_ALIASES.get(label, ()))

_WS_RE = re.compile(r"\s+")


def _clean(text: str | None, limit: int) -> str:
    """收合換行/多餘空白並截斷（Threads 內文常夾多重換行）。"""
    return _WS_RE.sub(" ", (text or "").strip())[:limit]


async def _slugs_by_post(session: AsyncSession, post_ids: list[int]) -> dict[int, list[str]]:
    """一次查出這批貼文各自命中的模型 slug（避免 N+1）。"""
    out: dict[int, list[str]] = {}
    if not post_ids:
        return out
    rows = await session.execute(
        select(PostModel.post_id, Model.slug)
        .join(Model, Model.id == PostModel.model_id)
        .where(PostModel.post_id.in_(post_ids))
    )
    for pid, slug in rows:
        out.setdefault(pid, []).append(slug)
    return out


def _base_filters(
    stmt: Select,
    *,
    source: str | None,
    sentiment: str | None,
    cutoff: datetime,
    model: str | None,
) -> Select:
    """套用共用篩選：品質門檻 + 時間窗 + 來源 + 情緒 + 模型。

    時間窗用 created_at（入庫時間）而非 posted_at，與電子報 / 今日事件一致：
    Threads 常青貼（posted_at 舊、今天才入庫）才進得來。詳見 services/recency.py。
    """
    stmt = stmt.where(*quality_post_filter()).where(recency_column() >= cutoff)
    if source:
        stmt = stmt.where(Post.source == source)
    if sentiment:
        stmt = stmt.where(Sentiment.label == sentiment)  # 指定情緒 → 只取已分析且相符
    if model:
        stmt = stmt.where(
            Post.id.in_(
                select(PostModel.post_id)
                .join(Model, Model.id == PostModel.model_id)
                .where(Model.slug == model)
            )
        )
    return stmt


async def _query_theme(
    session: AsyncSession, label: str, *, model, sentiment, source, cutoff, limit
) -> list[dict]:
    """取單一主題、套篩選後的 top N 貼文。

    排序改用 per-source 正規化熱度 + round-robin 平衡（hotness.rank_balanced）：先在時間
    視窗內撈一個夠大的候選池（上限 _CANDIDATE_POOL_CAP，以 created_at 最新優先），再在
    Python 端用各來源互動中位數基準正規化熱度、跨來源輪流取，使各來源（尤其量級低的
    Threads）都露出、不被高量級來源或單一來源的數量洗版。與電子報 select_highlights 同套
    排序邏輯（共用 ml.hotness），確保 feed 與電子報行為一致。
    """
    stmt = (
        select(
            Post.id, Post.title, Post.content, Post.source,
            Post.url, Post.permalink, Post.posted_at, Post.score, Post.num_comments,
            Theme.confidence, Sentiment.label.label("sentiment"),
            Translation.title_zh, Translation.snippet_zh,
        )
        .join(Theme, Theme.post_id == Post.id)
        .outerjoin(Sentiment, Sentiment.post_id == Post.id)
        .outerjoin(Translation, Translation.post_id == Post.id)
        .where(Theme.confident.is_(True), Theme.label.in_(_db_labels(label)))
        # 候選池以「最近被我們收進來」為準（created_at）撈最新一批，再交給 rank_balanced
        # 做 per-source 平衡；上限避免撈整表（見 _CANDIDATE_POOL_CAP）。
        .order_by(recency_column().desc(), Post.id.desc())
        .limit(_CANDIDATE_POOL_CAP)
    )
    stmt = _base_filters(stmt, source=source, sentiment=sentiment, cutoff=cutoff, model=model)
    rows = (await session.execute(stmt)).all()

    # per-source 平衡排序：各來源依正規化熱度排序，再 round-robin 取前 limit 篇。
    # engagement 取 score（讚/分數）+ num_comments（留言）；指定 source 篩選時等同單來源
    # 純熱度排序（仍比純時間排序更能把高互動貼文排前）。
    candidates = [
        {
            "id": r.id,
            "source": r.source,
            "score": r.score,
            "num_comments": r.num_comments,
            "_row": r,
        }
        for r in rows
    ]
    ranked = _hot.rank_balanced(candidates, k=limit)
    chosen = [c["_row"] for c in ranked]

    slugs = await _slugs_by_post(session, [r.id for r in chosen])
    return [
        {
            "id": r.id,
            "title": _clean(r.title, 120),
            "title_zh": _clean(r.title_zh, 120) or None,  # 繁中譯文（英文貼才有）
            "snippet": _clean(r.content, 160),
            "snippet_zh": _clean(r.snippet_zh, 200) or None,
            "source": r.source,
            "url": r.permalink or r.url,
            "models": slugs.get(r.id, []),
            "sentiment": r.sentiment,  # None = 未分析
            "theme": label,
            "theme_confidence": round(r.confidence, 3),
            "score": r.score,
            "posted_at": r.posted_at.isoformat() if r.posted_at else None,
        }
        for r in chosen
    ]


async def get_feed(
    session: AsyncSession,
    *,
    model: str | None = None,
    sentiment: str | None = None,
    source: str | None = None,
    days: int = 7,
    limit_per_theme: int = 6,
    theme: str | None = None,
) -> dict[str, list[dict]]:
    """
    回傳各實用主題的 top N 貼文。`theme` 指定 → 只回該主題（量加大，給主題列表頁）。
    回傳 {主題: [貼文卡, ...]}（順序同 ACTIONABLE_THEMES）。
    """
    cutoff = recency_cutoff(days=days)
    labels = (theme,) if theme in ACTIONABLE_THEMES else ACTIONABLE_THEMES
    out: dict[str, list[dict]] = {}
    for label in labels:
        out[label] = await _query_theme(
            session, label, model=model, sentiment=sentiment, source=source,
            cutoff=cutoff, limit=limit_per_theme,
        )
    return out


async def get_feed_summary(
    session: AsyncSession,
    *,
    model: str | None = None,
    sentiment: str | None = None,
    source: str | None = None,
    days: int = 7,
) -> dict[str, int]:
    """各實用主題在篩選條件下的貼文數（給首頁今日摘要列）。"""
    cutoff = recency_cutoff(days=days)
    all_db_labels = tuple(db for label in ACTIONABLE_THEMES for db in _db_labels(label))
    stmt = (
        select(Theme.label, func.count().label("n"))
        .join(Post, Post.id == Theme.post_id)
        .outerjoin(Sentiment, Sentiment.post_id == Post.id)
        .where(Theme.confident.is_(True), Theme.label.in_(all_db_labels))
        .group_by(Theme.label)
    )
    stmt = _base_filters(stmt, source=source, sentiment=sentiment, cutoff=cutoff, model=model)
    rows = (await session.execute(stmt)).all()
    counts: dict[str, int] = {label: 0 for label in ACTIONABLE_THEMES}
    for r in rows:
        # legacy 標籤（如「邊界」）併入對應正規主題的計數
        counts[_ALIAS_TO_CANONICAL.get(r.label, r.label)] += r.n
    return counts
