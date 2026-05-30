"""
event_detection —— F8 多源事件偵測（discussion_spike / launch / sentiment_flip）→ UPSERT events。

資料感知排程：訂閱 POSTS + RELEASE_EVENTS Datasets —— 只要任一爬蟲寫入新資料就觸發，
不空轉。另以每日 01:00 當安全網（即使無新資料也每日重算一次對帳）。

delete（對帳）+ upsert 在同一交易內完成 → retry 安全。
（DQC 上線後把 schedule 的 POSTS 換成 POSTS_DQ_PASSED 即可，本檔其餘不動。）
task 以 ExternalPythonOperator 在業務 venv（SQLAlchemy 2.0）執行。
"""
from __future__ import annotations

from airflow.decorators import dag, task
from airflow.timetables.datasets import DatasetOrTimeSchedule
from airflow.timetables.trigger import CronTriggerTimetable

from _common import DEFAULT_ARGS, PULSE_PYTHON, START_DATE
from _datasets import POSTS, RELEASE_EVENTS


@dag(
    dag_id="event_detection",
    # 有新貼文/發布就跑；另以每日 01:00 當安全網重算對帳。
    schedule=DatasetOrTimeSchedule(
        timetable=CronTriggerTimetable("0 1 * * *", timezone="UTC"),
        datasets=[POSTS, RELEASE_EVENTS],
    ),
    start_date=START_DATE,
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    tags=["pulse", "events"],
    doc_md=__doc__,
)
def event_detection_dag():
    @task.external_python(python=PULSE_PYTHON, expect_airflow=False)
    def detect_and_upsert() -> dict:
        import asyncio

        from pipeline.events import run_event_detection

        return asyncio.run(run_event_detection())

    detect_and_upsert()


event_detection_dag()
