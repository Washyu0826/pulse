"""
crawl_reddit —— 每 15 分鐘抓 Reddit（需 credential）→ UPSERT posts。

預設 paused：使用者目前無 Reddit key。task 會自我偵測 credential：
缺 key 時記 log 並回傳零統計（不算失敗），有 key 時正常爬取並標記 POSTS Dataset。
等 .env 填好 REDDIT_CLIENT_ID/SECRET 後在 UI unpause 即可。
task 以 ExternalPythonOperator 在業務 venv 執行。
"""
from __future__ import annotations

from airflow.decorators import dag, task

from _common import DEFAULT_ARGS, PULSE_PYTHON, START_DATE
from _datasets import POSTS


@dag(
    dag_id="crawl_reddit",
    schedule="3-59/15 * * * *",  # 與其他爬蟲錯開
    start_date=START_DATE,
    catchup=False,
    max_active_runs=1,
    is_paused_upon_creation=True,  # 無 credential → 預設不啟用
    default_args=DEFAULT_ARGS,
    tags=["pulse", "crawl"],
    doc_md=__doc__,
)
def crawl_reddit_dag():
    @task.external_python(python=PULSE_PYTHON, outlets=[POSTS], expect_airflow=False)
    def crawl_and_upsert() -> dict:
        import asyncio

        from pipeline.crawl import crawl_reddit_to_db

        return asyncio.run(crawl_reddit_to_db(limit=50))

    crawl_and_upsert()


crawl_reddit_dag()
