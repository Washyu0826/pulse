"""
crawl_threads —— 每天一次抓 Threads（Meta，best-effort 選配，Selenium）→ UPSERT posts。

預設 paused：Threads 有登入牆 + 反爬，且需容器內裝 Chromium（見 Dockerfile.airflow）。
task 自我偵測 cookie：有 THREADS_SESSIONID 走登入模式，缺則以未登入嘗試（資料可能很少）。
每天只跑一次（02:30 UTC，與 daily_snapshot 01:00 錯開）以最小化封號 / 反爬風險。
瀏覽器重（載入 + 捲動 + 多查詢）→ execution_timeout 放寬到 25 分。
等 Dockerfile.airflow 重建（含 chromium）+ .env 填好 THREADS_SESSIONID 後，在 UI unpause 即可。
task 以 ExternalPython 在業務 venv 執行。
"""
from __future__ import annotations

import pendulum
from airflow.decorators import dag, task

from _common import DEFAULT_ARGS, PULSE_PYTHON, START_DATE
from _datasets import POSTS


@dag(
    dag_id="crawl_threads",
    schedule="30 2 * * *",  # 每天一次（02:30 UTC，與 daily_snapshot 01:00 錯開）
    start_date=START_DATE,
    catchup=False,
    max_active_runs=1,
    is_paused_upon_creation=True,  # 需 Chromium image + cookie → 預設不啟用
    # 瀏覽器自動化比 HTTP 慢很多（載入 + 捲動 + 多查詢）→ 放寬逾時，覆蓋 default_args 的 15 分。
    default_args={**DEFAULT_ARGS, "execution_timeout": pendulum.duration(minutes=25)},
    tags=["pulse", "crawl"],
    doc_md=__doc__,
)
def crawl_threads_dag():
    @task.external_python(python=PULSE_PYTHON, outlets=[POSTS], expect_airflow=False)
    def crawl_and_upsert() -> dict:
        import asyncio

        from pipeline.crawl import crawl_threads_to_db

        # 每日目標 ~100 篇：6 模型查詢 × 40 上限、scroll 5（中庸值，避免觸發反爬限流）。
        # 去重 + 關鍵字過濾後實得通常 60~100；Threads 反爬下「每天剛好 100」屬 best-effort。
        return asyncio.run(crawl_threads_to_db(max_posts=40, scroll_times=5))

    crawl_and_upsert()


crawl_threads_dag()
