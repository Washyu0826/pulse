"""
共用 Airflow Datasets —— 用「資料感知排程」串起 producer（爬蟲）→ consumer（事件偵測）。

爬蟲 DAG 的 upsert task 以 outlets 標記對應 Dataset（成功才標記）；
事件偵測 DAG 以 schedule=[POSTS, RELEASE_EVENTS] 訂閱，有新資料才觸發 —— 不空轉。
"""
from airflow.datasets import Dataset

# 新/更新的貼文（HN / Dev.to / Lobsters / Reddit 爬蟲產生）。
POSTS = Dataset("pulse://posts")

# 新的發布事件（HF Hub / GitHub Releases）。
RELEASE_EVENTS = Dataset("pulse://release_events")

# 佔位：已評分的貼文情緒。目前情緒分析由本機 GPU 腳本寫入（torch 不進 Airflow image），
# 故此 Dataset 暫無 producer/consumer；待日後若把 sentiment DAG 納入排程再啟用。
SENTIMENTS = Dataset("pulse://sentiments")

# 佔位：DQC 通過品質門檻的貼文。DQC 尚未實作 —— 先定義 URI，
# 之後事件偵測只要把 schedule 從 [POSTS] 換成 [POSTS_DQ_PASSED] 即可，producer 不必動。
POSTS_DQ_PASSED = Dataset("pulse://posts_dq_passed")
