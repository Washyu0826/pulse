"""
crawl_community —— 每 15 分鐘抓 Dev.to + Lobsters（皆免 key）→ UPSERT posts。

兩來源各一個 task（失敗模式獨立、可分別 retry），都標記 POSTS Dataset。
與 crawl_hackernews 錯開 7 分鐘起跑，分散對 DB 的瞬間寫入。
task 以 ExternalPythonOperator 在業務 venv 執行。
"""
from __future__ import annotations

from airflow.decorators import dag, task

from _common import DEFAULT_ARGS, PULSE_PYTHON, START_DATE
from _datasets import POSTS


@dag(
    dag_id="crawl_community",
    schedule="7-59/15 * * * *",  # 每 15 分鐘，但於第 7 分鐘起（與 HN 錯開）
    start_date=START_DATE,
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    tags=["pulse", "crawl"],
    doc_md=__doc__,
)
def crawl_community_dag():
    @task.external_python(python=PULSE_PYTHON, outlets=[POSTS], expect_airflow=False)
    def crawl_devto() -> dict:
        import asyncio

        from pipeline.crawl import crawl_devto_to_db

        return asyncio.run(crawl_devto_to_db(per_page=50))

    @task.external_python(python=PULSE_PYTHON, outlets=[POSTS], expect_airflow=False)
    def crawl_lobsters() -> dict:
        import asyncio

        from pipeline.crawl import crawl_lobsters_to_db

        return asyncio.run(crawl_lobsters_to_db())

    # 兩者互相獨立，可並行。
    crawl_devto()
    crawl_lobsters()


crawl_community_dag()
