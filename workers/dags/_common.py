"""
共用 DAG 設定 —— default_args（retries=3 指數退避 + Slack 告警）、start_date，
以及 best-effort 的 truststore 注入（企業/校園 TLS 攔截環境用；無攔截也安全）。
"""
from __future__ import annotations

import pendulum

from _callbacks import notify_slack

# 企業/校園網路常做 TLS 攔截 → 改用 OS 信任庫。在 DAG 解析時就注入，
# 確保任何 task 的 HTTPS（httpx / asyncpraw）之前已生效。plugin 也會注入一次（雙保險）。
try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass

# 業務邏輯執行用的獨立 venv 直譯器（SQLAlchemy 2.0，與 Airflow 的 1.4 隔離）。
# DAG task 以 @task.external_python(python=PULSE_PYTHON) 在此 venv 執行（見 Dockerfile.airflow）。
PULSE_PYTHON = "/opt/airflow/pulse-venv/bin/python"

# 固定的過去日期（不可用 datetime.now()，會破壞排程）；明確 tz 讓 cron 時間無歧義。
START_DATE = pendulum.datetime(2026, 5, 1, tz="UTC")

# ADR-007 / TASKS：retries=3 + 指數退避；失敗發 Slack。
# 冪等寫入（upsert on-conflict / dedup_key）保證 retry 安全。
DEFAULT_ARGS = {
    "owner": "pulse",
    "retries": 3,
    "retry_delay": pendulum.duration(minutes=2),
    "retry_exponential_backoff": True,
    "max_retry_delay": pendulum.duration(minutes=30),
    # 安全網：避免某次外部 HTTP 卡死的 run 佔住唯一 active slot（max_active_runs=1）
    # → 之後排程被靜默跳過、管線無聲停擺。逾時即失敗 → 走 retry / 告警。
    "execution_timeout": pendulum.duration(minutes=15),
    "on_failure_callback": notify_slack,
}
