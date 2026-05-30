"""
共用失敗告警 —— task 失敗時發 Slack（best-effort，無 webhook / 失敗都不影響主流程）。

不依賴 Slack Connection，改用 Airflow Variable `slack_webhook_url`（由 compose 的
AIRFLOW_VAR_SLACK_WEBHOOK_URL 注入）。沒設或發送失敗只記 log，絕不再丟例外蓋掉原始錯誤。
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def notify_slack(context: dict) -> None:
    """on_failure_callback：把失敗的 dag/task/run + log 連結貼到 Slack。"""
    try:
        from airflow.models import Variable

        webhook = Variable.get("slack_webhook_url", default_var="")
        if not webhook:
            return  # 未設定 webhook → 安靜略過（本機開發常見）

        ti = context.get("task_instance")
        text = (
            f":red_circle: *{getattr(ti, 'dag_id', '?')}.{getattr(ti, 'task_id', '?')}* 失敗\n"
            f"run: `{context.get('run_id', '?')}`\n"
            f"log: {getattr(ti, 'log_url', 'n/a')}"
        )

        import httpx

        httpx.post(webhook, json={"text": text}, timeout=10.0)
    except Exception:  # noqa: BLE001 — 告警失敗絕不能蓋掉原始 task 錯誤
        logger.exception("Slack 失敗告警送出失敗（已忽略，不影響 task 狀態）")
