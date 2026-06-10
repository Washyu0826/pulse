"""
語料庫（corpus）唯讀 endpoint —— 對外攤平多來源貼文語料 + 標註結果。

供作品集 / 研究檢視用，全部唯讀（SELECT only）：
- GET /api/corpus/stats             → 全語料彙總（總數 / 各來源 / 各主題 / 各情緒 / 品質三級）。
- GET /api/corpus/posts?source=&theme=&sentiment=&limit=&offset=
                                    → 可篩選 + 分頁的貼文清單，左接主題與情緒。

設計取捨：沿用既有 async session DI（`Depends(get_db)`），參數化查詢（無 SQL injection），
limit 上限封頂 100，避免一次拉爆整個語料庫。
"""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.services.corpus import get_corpus_stats, list_corpus_posts

router = APIRouter()

# limit 封頂，避免一次拉太多。
_MAX_LIMIT = 100


class QualityBreakdown(BaseModel):
    """品質三級分佈計數。"""

    high: int = 0
    mid: int = 0
    low: int = 0


class CorpusStats(BaseModel):
    """全語料彙總統計回應。"""

    total: int = Field(description="貼文總數")
    by_source: dict[str, int] = Field(default_factory=dict, description="各來源計數")
    by_theme: dict[str, int] = Field(default_factory=dict, description="各主題計數（已標註者）")
    by_sentiment: dict[str, int] = Field(
        default_factory=dict, description="各情緒計數（已分析者）"
    )
    quality: QualityBreakdown = Field(
        default_factory=QualityBreakdown, description="品質三級分佈"
    )


class CorpusPost(BaseModel):
    """單筆語料貼文（含左接的主題 / 情緒；未標註者為 None）。"""

    id: int
    source: str
    title: str
    content: str
    author: str | None = None
    quality_score: int | None = None
    quality_flags: list[str] = Field(default_factory=list)
    posted_at: str | None = None
    theme: str | None = None
    theme_confidence: float | None = None
    sentiment: str | None = None
    sentiment_score: float | None = None


class CorpusPostsPage(BaseModel):
    """貼文分頁回應。"""

    total: int = Field(description="符合篩選條件的總數")
    limit: int
    offset: int
    items: list[CorpusPost] = Field(default_factory=list)


@router.get("/corpus/stats", response_model=CorpusStats)
async def corpus_stats(db: AsyncSession = Depends(get_db)) -> CorpusStats:
    """全語料的彙總統計（唯讀）：總數、各來源、各主題、各情緒、品質三級。"""
    stats = await get_corpus_stats(db)
    return CorpusStats(**stats)


@router.get("/corpus/posts", response_model=CorpusPostsPage)
async def corpus_posts(
    source: str | None = Query(None, description="來源篩選，如 threads / hackernews"),
    theme: str | None = Query(None, description="主題篩選，如 新工具 / 使用方法"),
    sentiment: str | None = Query(
        None, description="情緒篩選：positive / neutral / negative"
    ),
    limit: int = Query(20, ge=1, le=_MAX_LIMIT, description="每頁筆數（上限 100）"),
    offset: int = Query(0, ge=0, description="分頁位移"),
    db: AsyncSession = Depends(get_db),
) -> CorpusPostsPage:
    """可篩選 + 分頁的語料貼文清單，左接主題與情緒（唯讀，最新優先）。"""
    page = await list_corpus_posts(
        db,
        source=source,
        theme=theme,
        sentiment=sentiment,
        limit=limit,
        offset=offset,
    )
    return CorpusPostsPage(**page)
