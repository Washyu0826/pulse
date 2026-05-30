"""
Airflow plugin —— 在 worker / scheduler / webserver 行程啟動時注入 truststore。

企業/校園 TLS 攔截環境下，根憑證在 OS 信任庫但不在 Python 的 → httpx / asyncpraw 會踩
CERTIFICATE_VERIFY_FAILED。truststore 讓 Python 改用 OS 信任庫（無攔截的網路也安全）。

best-effort：truststore 沒裝就略過（production Airflow 多半無攔截，OS 信任庫即正確）。
此檔被 Airflow plugin manager 於啟動時 import，module 層的注入即生效，早於任何 task 的 HTTPS。
"""
import logging

logger = logging.getLogger(__name__)

try:
    import truststore

    truststore.inject_into_ssl()
    logger.info("truststore.inject_into_ssl() 已注入（改用 OS 信任庫）")
except ImportError:
    logger.info("未安裝 truststore，略過 TLS 注入")


class TruststorePlugin:
    """空 plugin 類別：讓 Airflow plugin manager 認得本模組並完成 import（注入在 module 層）。"""

    name = "truststore_init"
