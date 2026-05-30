"""
workers/pipeline —— 可重用的非同步資料管線編排層。

設計目的（單一真實來源 / DRY）：
- 爬蟲（crawlers.*，純輸出 dict）與寫入服務（api.services.*，純 UPSERT）原本由
  手動腳本（scripts/*.py）串接；Airflow DAG 也需要同一串接邏輯。
- 與其讓腳本與 DAG 各寫一份，這裡把「抓 → UPSERT」「事件偵測」收斂成少數
  async 函式，讓 scripts/ 與 workers/dags/ 都直接呼叫，行為一致、好測。

執行環境假設：
- api / ml / crawlers 套件都在 import path 上
  （Airflow 容器靠 PYTHONPATH；手動腳本靠 sys.path.insert）。
- 每次呼叫都建立自己的 AsyncSession，呼叫端用 asyncio.run() 驅動（DAG task 即如此）。
- 不載入 torch —— 事件偵測只用 ml.sentiment 的純統計函式（torch 在其 __init__ 才 import）。
"""
from pipeline.crawl import (
    crawl_devto_to_db,
    crawl_hackernews_to_db,
    crawl_lobsters_to_db,
    crawl_reddit_to_db,
    fetch_releases_to_db,
)
from pipeline.events import run_event_detection
from pipeline.quality import detect_duplicates, process_quality, run_dqc

__all__ = [
    "crawl_hackernews_to_db",
    "crawl_devto_to_db",
    "crawl_lobsters_to_db",
    "crawl_reddit_to_db",
    "fetch_releases_to_db",
    "run_event_detection",
    "process_quality",
    "detect_duplicates",
    "run_dqc",
]
