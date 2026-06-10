"""add evaluation_runs table

Revision ID: e1f2a3b4c5d6
Revises: d9e2f3a4b5c6
Create Date: 2026-06-05 11:00:00.000000

落地 ADR-008 Offline Evaluation：記錄每次模型評測（F1 / per-class P-R /
confusion matrix / Cohen κ + CI / McNemar 對比 baseline / MLflow run）。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e1f2a3b4c5d6"
down_revision: str | None = "d9e2f3a4b5c6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("task", sa.Text(), nullable=False),
        sa.Column("model_version", sa.Text(), nullable=False),
        sa.Column("evaluation_set", sa.Text(), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("f1_macro", sa.Float(), nullable=True),
        sa.Column("f1_weighted", sa.Float(), nullable=True),
        sa.Column("accuracy", sa.Float(), nullable=True),
        sa.Column("precision_per_class", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("recall_per_class", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("confusion_matrix", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("cohen_kappa", sa.Float(), nullable=True),
        sa.Column("kappa_ci_low", sa.Float(), nullable=True),
        sa.Column("kappa_ci_high", sa.Float(), nullable=True),
        sa.Column("baseline_model", sa.Text(), nullable=True),
        sa.Column("mcnemar_statistic", sa.Float(), nullable=True),
        sa.Column("mcnemar_p_value", sa.Float(), nullable=True),
        sa.Column("f1_delta", sa.Float(), nullable=True),
        sa.Column("f1_delta_ci_low", sa.Float(), nullable=True),
        sa.Column("f1_delta_ci_high", sa.Float(), nullable=True),
        sa.Column("mlflow_run_id", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "evaluated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evaluation_runs")),
    )
    op.create_index("ix_evaluation_runs_task", "evaluation_runs", ["task"], unique=False)
    op.create_index(
        "ix_evaluation_runs_model_version", "evaluation_runs", ["model_version"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_evaluation_runs_model_version", table_name="evaluation_runs")
    op.drop_index("ix_evaluation_runs_task", table_name="evaluation_runs")
    op.drop_table("evaluation_runs")
