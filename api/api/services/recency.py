"""共用的「近期視窗」定義 —— 全產品一致用 created_at（入庫時間）篩「今日/近期內容」。

為什麼用 created_at（DB 入庫時間）而不是 posted_at（來源平台原始發佈時間）：

    Threads（主力來源，[[threads-main-source]]）的搜尋會撈出「舊發文日的常青貼」——
    posted_at 很舊、但今天才被我們收進來（created_at 新）。若用 posted_at 過濾近期視窗，
    當天大量入庫的 Threads 會被幾乎全濾掉，導致電子報有、網站沒有的不一致。
    改用 created_at（「最近被我們收進來」）就能把這批常青貼一致地納進今日視窗。
    HN / devto / PTT 為即時貼文（posted_at ≈ created_at），改用 created_at 不受影響。

注意語意分界：
    這個「近期視窗」是給「今日/近期內容」讀取（feed、今日事件、電子報）用的。
    「逐日分布趨勢圖」（dashboard）的 x 軸本就該用 posted_at（發文時間），語意不同，
    不該套這裡的定義。

電子報 scripts/send_newsletter.py:_fetch 已直接用 created_at 當基準，本模組把同一定義
抽成共用 helper，讓 feed（api）與 build_today_events（scripts，會 import api）共用。
"""
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import InstrumentedAttribute

from api.models.posts import Post

# 近期視窗依據的 DB 欄位名（原始 SQL 用，例如 scripts/build_today_events.py 的 text()）。
RECENCY_COLUMN_NAME = "created_at"


def recency_column() -> InstrumentedAttribute:
    """近期視窗排序/過濾要用的 ORM 欄位（created_at，入庫時間）。"""
    return Post.created_at


def recency_cutoff(*, days: int = 0, hours: int = 0) -> datetime:
    """近期視窗的起點（now - 區間，UTC aware）。days / hours 擇一或並用。"""
    return datetime.now(UTC) - timedelta(days=days, hours=hours)
