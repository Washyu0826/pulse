"""
Pulse API - main entry point.

啟動: uv run uvicorn api.main:app --reload
"""
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from api.config import settings
from api.middleware import (
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
    install_exception_handlers,
)
from api.routers import (
    collection,
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

# 統一日誌格式（含時間 / level / logger）。等級走設定（PULSE LOG_LEVEL）。
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
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
    logging.getLogger("pulse.api").info(
        "Pulse API 啟動 · env=%s · log_level=%s", settings.environment, settings.log_level
    )
    yield
    # 清理邏輯
    logging.getLogger("pulse.api").info("Pulse API 關閉")


app = FastAPI(
    title="Pulse API",
    description="AI 工程師的每日情報秘書",
    version="0.1.0",
    lifespan=lifespan,
)


# 中介層（Starlette：後加 = 更外層）。順序刻意：
# GZip / 安全標頭 / request context 為內層，CORS 最後加＝最外層（預檢與 CORS 標頭包住全部）。
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(SecurityHeadersMiddleware, hsts=settings.environment == "production")
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    # 收緊：本 API 只用 GET/POST（OPTIONS 為預檢必要），不開放整個 "*"。
    allow_methods=["GET", "POST", "OPTIONS"],
    # 只放行實際會用到的 header（JSON 內容協商 + request 追蹤），不開放 "*"。
    allow_headers=["Accept", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID", "Server-Timing"],
)

# 全域例外處理（結構化錯誤 + request_id）。
install_exception_handlers(app)


# Routers
app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(models.router, prefix="/api", tags=["models"])
app.include_router(feed.router, prefix="/api", tags=["feed"])
app.include_router(releases.router, prefix="/api", tags=["releases"])
app.include_router(events.router, prefix="/api", tags=["events"])
app.include_router(events_today.router, prefix="/api", tags=["events"])
app.include_router(decide.router, prefix="/api", tags=["decide"])
app.include_router(corpus.router, prefix="/api", tags=["corpus"])
app.include_router(collection.router, prefix="/api", tags=["collection"])
# Prometheus 業務指標（無 /api 前綴，scrape URL = /metrics）
app.include_router(metrics.router, tags=["metrics"])


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "name": "Pulse API",
        "version": app.version,
        "environment": settings.environment,
        "docs": "/docs",
    }
