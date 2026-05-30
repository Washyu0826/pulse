"""
crawl_hackernews —— 每 15 分鐘抓 HackerNews（Algolia，免 key）→ UPSERT posts。

Wave 1：最低風險（無需任何 credential），是整條管線的起點。
成功時標記 POSTS Dataset → 觸發下游 event_detection。
冪等：upsert 以 (source, external_id) on-conflict，retry 安全。

task 以 ExternalPythonOperator 在業務 venv（SQLAlchemy 2.0）執行 —— 函式內所有 import 自包含。
"""
from __future__ import annotations

from airflow.decorators import dag, task

from _common import DEFAULT_ARGS, PULSE_PYTHON, START_DATE
from _datasets import POSTS


@dag(
    dag_id="crawl_hackernews",
    schedule="*/15 * * * *",
    start_date=START_DATE,
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    tags=["pulse", "crawl"],
    doc_md=__doc__,
)
def crawl_hackernews_dag():
    @task.external_python(python=PULSE_PYTHON, outlets=[POSTS], expect_airflow=False)
    def crawl_and_upsert() -> dict:
        import asyncio

        from pipeline.crawl import crawl_hackernews_to_db

        return asyncio.run(crawl_hackernews_to_db(hits_per_page=50))

    crawl_and_upsert()


crawl_hackernews_dag()
