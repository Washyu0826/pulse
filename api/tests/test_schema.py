"""
Schema 定義測試 — 不需要 DB，純粹檢查 SQLAlchemy metadata 是否如預期。

驗證 Week 1 schema 的關鍵約束（給 code review 與 CI 把關）。
"""
from sqlalchemy import inspect

import api.models  # noqa: F401 — 註冊所有表到 Base.metadata
from api.database import Base
from api.models.posts import Post


def test_expected_tables_registered():
    tables = set(Base.metadata.tables)
    assert {"models", "posts", "post_models"} <= tables


def test_posts_has_dqc_columns():
    """v4 要求 posts 帶 DQC 欄位（ADR-009）。"""
    cols = {c.name for c in Post.__table__.columns}
    assert {"quality_score", "quality_flags", "dq_processed_at"} <= cols


def test_quality_score_nullable_quality_flags_not():
    """quality_score 可為 NULL（尚未檢核）；quality_flags 不可為 NULL（預設空陣列）。"""
    cols = Post.__table__.columns
    assert cols["quality_score"].nullable is True
    assert cols["quality_flags"].nullable is False


def test_posts_unique_source_external_id():
    """去重 key = (source, external_id)。"""
    uniques = [
        tuple(c.name for c in con.columns)
        for con in Post.__table__.constraints
        if con.__class__.__name__ == "UniqueConstraint"
    ]
    assert ("source", "external_id") in uniques


def test_posts_has_dq_unprocessed_partial_index():
    by_name = {ix.name: ix for ix in Post.__table__.indexes}
    assert "ix_posts_dq_unprocessed" in by_name
    # 必須是 partial index（ADR-009）：帶 WHERE dq_processed_at IS NULL
    where = by_name["ix_posts_dq_unprocessed"].dialect_options["postgresql"]["where"]
    assert where is not None
    assert "dq_processed_at" in str(where)


def test_timestamps_are_timezone_aware():
    """所有 DateTime 欄位都要 timezone=True（避免 naive datetime）。"""
    for col in Post.__table__.columns:
        if col.type.__class__.__name__ == "DateTime":
            assert col.type.timezone is True, f"{col.name} 不是 timezone-aware"


def test_models_slug_unique():
    insp = inspect(api.models.Model)
    slug = insp.columns["slug"]
    assert slug.unique is True
