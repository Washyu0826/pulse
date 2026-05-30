"""
data_quality —— DQC：評分（quality_score/quality_flags）+ 跨來源去重，寫回 posts。

資料感知排程：訂閱 POSTS Dataset（有新貼文就重跑），另以每日 02:00 安全網全表重算去重對帳。
成功後標記 POSTS_DQ_PASSED Dataset —— 未來事件偵測/彙總可改吃這個（只看通過品質門檻的貼文）。
冪等：評分只挑未處理、去重全表對帳，retry 安全。task 以 ExternalPython 在業務 venv 執行。
"""
from __future__ import annotations

from airflow.decorators import dag, task
from airflow.timetables.datasets import DatasetOrTimeSchedule
from airflow.timetables.trigger import CronTriggerTimetable

from _common import DEFAULT_ARGS, PULSE_PYTHON, START_DATE
from _datasets import POSTS, POSTS_DQ_PASSED


@dag(
    dag_id="data_quality",
    schedule=DatasetOrTimeSchedule(
        timetable=CronTriggerTimetable("0 2 * * *", timezone="UTC"),
        datasets=[POSTS],
    ),
    start_date=START_DATE,
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    tags=["pulse", "dqc"],
    doc_md=__doc__,
)
def data_quality_dag():
    @task.external_python(python=PULSE_PYTHON, outlets=[POSTS_DQ_PASSED], expect_airflow=False)
    def run_quality() -> dict:
        import asyncio

        from pipeline.quality import run_dqc

        return asyncio.run(run_dqc())

    run_quality()


data_quality_dag()
