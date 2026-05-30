"""
crawl_x —— 每 30 分鐘抓 X/Twitter（best-effort 選配，需帳號 cookie）→ UPSERT posts。

預設 paused：2026 X 無免費官方 API，需 twscrape + 帳號 cookie。task 會自我偵測 cookie：
缺則記 log 並回傳零統計（不算失敗），有則正常爬取並標記 POSTS Dataset。
等 .env 填好 X_AUTH_TOKEN/X_CT0/X_USERNAME 後在 UI unpause 即可。
頻率較低（每 30 分鐘、於第 11 分起錯開）以降低 X 限流/封號風險。task 以 ExternalPython 在業務 venv 執行。
"""
from __future__ import annotations

from airflow.decorators import dag, task

from _common import DEFAULT_ARGS, PULSE_PYTHON, START_DATE
from _datasets import POSTS


@dag(
    dag_id="crawl_x",
    schedule="11-59/30 * * * *",  # 每 30 分鐘，與其他爬蟲錯開
    start_date=START_DATE,
    catchup=False,
    max_active_runs=1,
    is_paused_upon_creation=True,  # 無 cookie → 預設不啟用
    default_args=DEFAULT_ARGS,
    tags=["pulse", "crawl"],
    doc_md=__doc__,
)
def crawl_x_dag():
    @task.external_python(python=PULSE_PYTHON, outlets=[POSTS], expect_airflow=False)
    def crawl_and_upsert() -> dict:
        import asyncio

        from pipeline.crawl import crawl_twitter_to_db

        return asyncio.run(crawl_twitter_to_db(limit=30))

    crawl_and_upsert()


crawl_x_dag()
