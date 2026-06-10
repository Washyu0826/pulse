"""
Pulse API - main entry point.

啟動: uv run uvicorn api.main:app --reload
"""
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import settings
from api.routers import (
    corpus,
    decide,
    events,
    events_today,
    feed,
    health,
    metrics,
    models,
    releases,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    FastAPI 啟動 / 關閉時的鉤子。

    啟動時：
    - 載入情緒分析模型（Week 3 加入）
    - 連接資料庫

    關閉時：
    - 釋放模型記憶體
    - 關閉 DB connection pool
    """
    # TODO Week 3: app.state.sentiment_pipeline = load_sentiment_model()
    yield
    # 清理邏輯


app = FastAPI(
    title="Pulse API",
    description="AI 工程師的每日情報秘書",
    version="0.1.0",
    lifespan=lifespan,
)


# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Routers
app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(models.router, prefix="/api", tags=["models"])
app.include_router(feed.router, prefix="/api", tags=["feed"])
app.include_router(releases.router, prefix="/api", tags=["releases"])
app.include_router(events.router, prefix="/api", tags=["events"])
app.include_router(events_today.router, prefix="/api", tags=["events"])
app.include_router(decide.router, prefix="/api", tags=["decide"])
app.include_router(corpus.router, prefix="/api", tags=["corpus"])
# Prometheus 業務指標（無 /api 前綴，scrape URL = /metrics）
app.include_router(metrics.router, tags=["metrics"])


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "name": "Pulse API",
        "version": "0.1.0",
        "docs": "/docs",
    }
