"""
fetch_releases —— 每小時抓 HF Hub + GitHub Releases（免 key）→ UPSERT release_events。

成功時標記 RELEASE_EVENTS Dataset → 觸發 event_detection 重算 launch 事件。
發布頻率低，每小時足夠（不必跟貼文一樣 15 分鐘）。
task 以 ExternalPythonOperator 在業務 venv 執行。
"""
from __future__ import annotations

from airflow.decorators import dag, task

from _common import DEFAULT_ARGS, PULSE_PYTHON, START_DATE
from _datasets import RELEASE_EVENTS


@dag(
    dag_id="fetch_releases",
    schedule="@hourly",
    start_date=START_DATE,
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    tags=["pulse", "releases"],
    doc_md=__doc__,
)
def fetch_releases_dag():
    @task.external_python(python=PULSE_PYTHON, outlets=[RELEASE_EVENTS], expect_airflow=False)
    def fetch_and_upsert() -> dict:
        import asyncio

        from pipeline.crawl import fetch_releases_to_db

        return asyncio.run(fetch_releases_to_db(source="all"))

    fetch_and_upsert()


fetch_releases_dag()
