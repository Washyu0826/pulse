"""
SQLAlchemy models 套件。

集中 re-export 所有 model，讓 Alembic env.py 只要 `import api.models`
就能讓 autogenerate 偵測到全部資料表（不會漏掉新表）。
"""
from api.models.event import Event
from api.models.models import Model, PostModel
from api.models.posts import Post
from api.models.release import ReleaseEvent
from api.models.sentiment import Sentiment
from api.models.theme import Theme
from api.models.trending import TrendingKeyword

__all__ = [
    "Event", "Model", "Post", "PostModel", "ReleaseEvent", "Sentiment", "Theme", "TrendingKeyword",
]
