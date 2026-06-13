"""
中介層與全域例外處理 —— 產品級的可觀測性與安全標頭。

- RequestContextMiddleware：給每個請求一個 request_id（沿用呼叫端 X-Request-ID 或新生），
  記錄 method / path / status / 耗時，並把 request_id + Server-Timing 回寫到回應標頭。
- SecurityHeadersMiddleware：補上常見安全標頭（防 MIME 嗅探 / 點擊劫持 / referrer 洩漏）。
- install_exception_handlers：未捕捉例外 → 結構化 JSON 500（不洩漏堆疊），帶 request_id 方便追。
  RequestValidationError → 422，維持 FastAPI 的 detail 結構並補上 request_id。
"""
from __future__ import annotations

import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

logger = logging.getLogger("pulse.api")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """每請求附 request_id + 存取日誌 + 耗時。"""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        request.state.request_id = rid
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            dur = (time.perf_counter() - start) * 1000
            logger.exception(
                "request_failed rid=%s %s %s dur_ms=%.1f",
                rid, request.method, request.url.path, dur,
            )
            raise
        dur = (time.perf_counter() - start) * 1000
        response.headers["X-Request-ID"] = rid
        response.headers["Server-Timing"] = f"app;dur={dur:.1f}"
        logger.info(
            "%s %s -> %s rid=%s dur_ms=%.1f",
            request.method, request.url.path, response.status_code, rid, dur,
        )
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """補安全標頭；hsts 僅在 HTTPS（production）開，避免本機 http 被強制升級。"""

    def __init__(self, app: Starlette, *, hsts: bool = False) -> None:
        super().__init__(app)
        self._hsts = hsts

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
        )
        if self._hsts:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response


def install_exception_handlers(app: FastAPI) -> None:
    """掛全域例外處理：未捕捉 → 結構化 500（不洩漏堆疊）；驗證錯誤 → 422。"""

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):  # noqa: ANN202
        rid = getattr(request.state, "request_id", None)
        logger.exception("unhandled rid=%s %s %s", rid, request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_server_error",
                "detail": "伺服器發生未預期的錯誤，請稍後再試。",
                "request_id": rid,
            },
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):  # noqa: ANN202
        rid = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=422,
            content=jsonable_encoder(
                {"error": "validation_error", "detail": exc.errors(), "request_id": rid}
            ),
        )
