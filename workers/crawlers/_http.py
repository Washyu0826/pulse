"""共用的 httpx 重試設定（HF / GitHub 等 REST 來源用）。"""
import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential


def _is_retryable(exc: BaseException) -> bool:
    """逾時 / 連線錯誤 / 5xx / 429 才重試；其餘 4xx（壞請求、404）不重試。"""
    if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500 or exc.response.status_code == 429
    return False


def http_retry(attempts: int = 4):
    """產生一個 tenacity 重試 decorator（指數退避，只重試暫時性 HTTP 錯誤）。"""
    return retry(
        retry=retry_if_exception(_is_retryable),
        wait=wait_exponential(multiplier=2, min=2, max=60),
        stop=stop_after_attempt(attempts),
        reraise=True,
    )
