"""健康檢查端點 - 給 Prometheus / Railway 用。"""
import logging

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db

logger = logging.getLogger("pulse.api")

router = APIRouter()


@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    """檢查 API 與 DB 是否健康。

    不對外洩漏內部例外細節（連線字串 / 堆疊）：未知錯誤一律回通用 "unhealthy"，
    詳細原因只記在伺服器端日誌。
    """
    try:
        await db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        logger.exception("health check DB probe 失敗")
        db_status = "unhealthy"

    return {
        "status": "healthy" if db_status == "ok" else "unhealthy",
        "db": db_status,
    }
