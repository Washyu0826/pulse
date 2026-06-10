"""
EvaluationRuns 表 —— 模型離線評測（Offline Evaluation）的歷史紀錄。

落地 ADR-008：用人工標註 gold set 比較兩個模型（如英文 twitter-roberta vs 微調
chinese-macbert），算 macro/weighted-F1、per-class P/R、confusion matrix，並用
McNemar 檢定判斷差異是否統計顯著（Dietterich 1998；Dror et al. 2018）。

每跑一次評測寫一筆，連結 MLflow run 供重現。這不是 A/B Test（無使用者流量分流），
是 Offline Evaluation —— 兩模型在同一份 labeled set 上的配對比較。
"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from api.database import Base
from api.models.mixins import TimestampMixin


class EvaluationRun(Base, TimestampMixin):
    """單次離線評測結果（一個模型 vs 一個 baseline，在一份 gold set 上）。"""

    __tablename__ = "evaluation_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    # ---- 被評模型與資料集 ----
    task: Mapped[str] = mapped_column(Text)  # 'sentiment' | 'theme' | 'quality'
    model_version: Mapped[str] = mapped_column(Text)  # 被評模型（如 'macbert-sentiment-v1'）
    evaluation_set: Mapped[str] = mapped_column(Text)  # gold set 版本（如 'gold_zh_v1'）
    sample_size: Mapped[int] = mapped_column(Integer)

    # ---- 指標 ----
    f1_macro: Mapped[float | None] = mapped_column(Float)
    f1_weighted: Mapped[float | None] = mapped_column(Float)
    accuracy: Mapped[float | None] = mapped_column(Float)
    precision_per_class: Mapped[dict | None] = mapped_column(JSONB)  # {label: precision}
    recall_per_class: Mapped[dict | None] = mapped_column(JSONB)  # {label: recall}
    confusion_matrix: Mapped[dict | None] = mapped_column(JSONB)  # {labels, matrix}

    # ---- 標註品質 ----
    cohen_kappa: Mapped[float | None] = mapped_column(Float)  # gold set self-consistency
    kappa_ci_low: Mapped[float | None] = mapped_column(Float)  # bootstrap 95% CI
    kappa_ci_high: Mapped[float | None] = mapped_column(Float)

    # ---- 對比 baseline（McNemar 配對檢定）----
    baseline_model: Mapped[str | None] = mapped_column(Text)
    mcnemar_statistic: Mapped[float | None] = mapped_column(Float)
    mcnemar_p_value: Mapped[float | None] = mapped_column(Float)
    f1_delta: Mapped[float | None] = mapped_column(Float)  # 本模型 - baseline 的 macro-F1
    f1_delta_ci_low: Mapped[float | None] = mapped_column(Float)  # paired bootstrap CI
    f1_delta_ci_high: Mapped[float | None] = mapped_column(Float)

    # ---- 重現 ----
    mlflow_run_id: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_evaluation_runs_task", "task"),
        Index("ix_evaluation_runs_model_version", "model_version"),
    )
