"""
SQLAlchemy models 套件。

集中 re-export 所有 model，讓 Alembic env.py 只要 `import api.models`
就能讓 autogenerate 偵測到全部資料表（不會漏掉新表）。
"""
from api.models.models import Model, PostModel
from api.models.posts import Post

__all__ = ["Model", "Post", "PostModel"]
