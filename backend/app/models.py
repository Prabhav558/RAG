"""Relational model for the generic Scorecard Creation & Rating System.

Source of truth for the schema. `python -m app.dump_schema` exports the DDL to docs/schema.sql.
Field-level rules are documented in docs/03_DATA_DICTIONARY.md.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- reference data


class RatingScale(Base):
    __tablename__ = "rating_scale"
    __table_args__ = (CheckConstraint("max_value > min_value", name="ck_scale_range"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    min_value: Mapped[int] = mapped_column(Integer)
    max_value: Mapped[int] = mapped_column(Integer)
    description: Mapped[str | None] = mapped_column(Text)

    bands: Mapped[list["RatingBand"]] = relationship(
        back_populates="scale", cascade="all, delete-orphan", order_by="RatingBand.lower_bound.desc()"
    )


class RatingBand(Base):
    __tablename__ = "rating_band"
    __table_args__ = (UniqueConstraint("scale_id", "lower_bound"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    scale_id: Mapped[int] = mapped_column(ForeignKey("rating_scale.id", ondelete="CASCADE"))
    label: Mapped[str] = mapped_column(String(40))
    lower_bound: Mapped[float] = mapped_column(Float)  # band applies to scores >= lower_bound
    color_hex: Mapped[str] = mapped_column(String(7))
    font_hex: Mapped[str] = mapped_column(String(7), default="#000000")
    rag: Mapped[str] = mapped_column(String(5))  # GREEN | AMBER | RED — for roll-up views
    meaning: Mapped[str | None] = mapped_column(Text)

    scale: Mapped[RatingScale] = relationship(back_populates="bands")


class SubjectType(Base):
    """What can be scored: task, project, document, team, individual, product, assessment, ...
    User-extendable; the engine never branches on it."""

    __tablename__ = "subject_type"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)


# ---------------------------------------------------------------- scorecard definition


class Scorecard(Base):
    """Stable identity of a scorecard across its versions."""

    __tablename__ = "scorecard"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(60), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    subject_type_id: Mapped[int] = mapped_column(ForeignKey("subject_type.id"))
    owner: Mapped[str | None] = mapped_column(String(120))
    tags: Mapped[list] = mapped_column(JSON, default=list)
    is_template: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    subject_type: Mapped[SubjectType] = relationship()
    versions: Mapped[list["ScorecardVersion"]] = relationship(
        back_populates="scorecard", cascade="all, delete-orphan", order_by="ScorecardVersion.version_no"
    )


class ScorecardVersion(Base):
    """A draft is editable; a published version is immutable and is what evaluations reference."""

    __tablename__ = "scorecard_version"
    __table_args__ = (
        UniqueConstraint("scorecard_id", "version_no"),
        CheckConstraint("status in ('draft','published','retired')", name="ck_version_status"),
        CheckConstraint("aggregation in ('weighted_mean','minimum')", name="ck_version_agg"),
        CheckConstraint("max_depth between 1 and 6", name="ck_version_depth"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    scorecard_id: Mapped[int] = mapped_column(ForeignKey("scorecard.id", ondelete="CASCADE"))
    version_no: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(12), default="draft")
    purpose: Mapped[str] = mapped_column(Text, default="")
    scope: Mapped[str] = mapped_column(Text, default="")
    objective: Mapped[str] = mapped_column(Text, default="")
    guidance: Mapped[str | None] = mapped_column(Text)  # scoring manual / how to judge
    rating_scale_id: Mapped[int] = mapped_column(ForeignKey("rating_scale.id"))
    target_score: Mapped[float] = mapped_column(Float)
    aggregation: Mapped[str] = mapped_column(String(20), default="weighted_mean")  # root-level roll-up
    max_depth: Mapped[int] = mapped_column(Integer, default=4)
    qtc_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    based_on_version_id: Mapped[int | None] = mapped_column(ForeignKey("scorecard_version.id"))
    change_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    scorecard: Mapped[Scorecard] = relationship(back_populates="versions")
    rating_scale: Mapped[RatingScale] = relationship()
    parameters: Mapped[list["Parameter"]] = relationship(
        back_populates="version", cascade="all, delete-orphan", order_by="Parameter.sort_order"
    )


class Parameter(Base):
    """A KPI / parameter node. Self-referencing tree; leaves are rated, non-leaves are rolled up."""

    __tablename__ = "parameter"
    __table_args__ = (
        UniqueConstraint("version_id", "code"),
        CheckConstraint("weight >= 0", name="ck_param_weight"),
        CheckConstraint("aggregation in ('weighted_mean','minimum')", name="ck_param_agg"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("scorecard_version.id", ondelete="CASCADE"))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("parameter.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(40))  # e.g. "2.3.1" — stable within a version
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    weight: Mapped[float] = mapped_column(Float, default=1.0)  # relative to siblings
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    aggregation: Mapped[str] = mapped_column(String(20), default="weighted_mean")  # for non-leaves
    is_critical: Mapped[bool] = mapped_column(Boolean, default=False)
    min_acceptable_score: Mapped[float | None] = mapped_column(Float)  # gate floor when critical
    is_optional: Mapped[bool] = mapped_column(Boolean, default=False)  # may be marked N/A

    version: Mapped[ScorecardVersion] = relationship(back_populates="parameters")
    parent: Mapped["Parameter | None"] = relationship(remote_side="Parameter.id", back_populates="children")
    children: Mapped[list["Parameter"]] = relationship(back_populates="parent", order_by="Parameter.sort_order")
    criteria: Mapped[list["RatingCriterion"]] = relationship(
        back_populates="parameter", cascade="all, delete-orphan", order_by="RatingCriterion.score_max.desc()"
    )
    metrics: Mapped[list["Metric"]] = relationship(
        back_populates="parameter", cascade="all, delete-orphan", order_by="Metric.sort_order"
    )


class RatingCriterion(Base):
    """One row of a leaf's rating matrix: a score range with its qualitative and quantitative guideline."""

    __tablename__ = "rating_criterion"
    __table_args__ = (CheckConstraint("score_max >= score_min", name="ck_criterion_range"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    parameter_id: Mapped[int] = mapped_column(ForeignKey("parameter.id", ondelete="CASCADE"))
    score_min: Mapped[int] = mapped_column(Integer)
    score_max: Mapped[int] = mapped_column(Integer)
    qualitative: Mapped[str] = mapped_column(Text)
    quantitative: Mapped[str | None] = mapped_column(Text)

    parameter: Mapped[Parameter] = relationship(back_populates="criteria")


class Metric(Base):
    """A quantitative measure attached to a leaf. Values map to scores through thresholds."""

    __tablename__ = "metric"
    __table_args__ = (
        UniqueConstraint("parameter_id", "code"),
        CheckConstraint("data_type in ('number','percent','count','boolean')", name="ck_metric_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    parameter_id: Mapped[int] = mapped_column(ForeignKey("parameter.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(60))
    name: Mapped[str] = mapped_column(String(200))
    unit: Mapped[str | None] = mapped_column(String(40))
    data_type: Mapped[str] = mapped_column(String(10), default="number")
    description: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    parameter: Mapped[Parameter] = relationship(back_populates="metrics")
    thresholds: Mapped[list["MetricThreshold"]] = relationship(
        back_populates="metric", cascade="all, delete-orphan", order_by="MetricThreshold.score.desc()"
    )


class MetricThreshold(Base):
    """value in [min_value, max_value) -> score. Null bound = unbounded on that side."""

    __tablename__ = "metric_threshold"

    id: Mapped[int] = mapped_column(primary_key=True)
    metric_id: Mapped[int] = mapped_column(ForeignKey("metric.id", ondelete="CASCADE"))
    min_value: Mapped[float | None] = mapped_column(Float)
    max_value: Mapped[float | None] = mapped_column(Float)
    score: Mapped[float] = mapped_column(Float)

    metric: Mapped[Metric] = relationship(back_populates="thresholds")


# ---------------------------------------------------------------- evaluation (the "response")


class Evaluation(Base):
    __tablename__ = "evaluation"
    __table_args__ = (
        CheckConstraint("status in ('draft','completed','void')", name="ck_eval_status"),
        CheckConstraint("evaluator_type in ('self','human','llm')", name="ck_eval_type"),
        CheckConstraint("origin in ('app','import')", name="ck_eval_origin"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("scorecard_version.id"))
    subject_name: Mapped[str] = mapped_column(String(300))
    subject_ref: Mapped[str | None] = mapped_column(String(120))  # external id; links evaluations of one subject
    input_text: Mapped[str | None] = mapped_column(Text)
    evaluator_type: Mapped[str] = mapped_column(String(10))
    evaluator_name: Mapped[str | None] = mapped_column(String(120))
    judge_model: Mapped[str | None] = mapped_column(String(80))
    is_private: Mapped[bool] = mapped_column(Boolean, default=False)  # self-appraisal privacy
    status: Mapped[str] = mapped_column(String(12), default="draft")
    target_score: Mapped[float] = mapped_column(Float)  # copied from version, overridable per context
    time_met: Mapped[bool | None] = mapped_column(Boolean)
    cost_met: Mapped[bool | None] = mapped_column(Boolean)
    attempt_no: Mapped[int] = mapped_column(Integer, default=1)  # resubmissions of the same subject
    origin: Mapped[str] = mapped_column(String(10), default="app")  # app | import
    origin_ref: Mapped[str | None] = mapped_column(String(300))  # e.g. "legacy.xlsx!Ratings:12"
    # computed on every save
    final_score: Mapped[float | None] = mapped_column(Float)
    band_label: Mapped[str | None] = mapped_column(String(40))
    rag: Mapped[str | None] = mapped_column(String(5))
    quality_met: Mapped[bool | None] = mapped_column(Boolean)
    qtc_green: Mapped[bool | None] = mapped_column(Boolean)
    gate_failures: Mapped[list] = mapped_column(JSON, default=list)
    summary: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voided_reason: Mapped[str | None] = mapped_column(Text)

    version: Mapped[ScorecardVersion] = relationship()
    results: Mapped[list["ParameterResult"]] = relationship(back_populates="evaluation", cascade="all, delete-orphan")
    metric_values: Mapped[list["MetricValue"]] = relationship(
        back_populates="evaluation", cascade="all, delete-orphan"
    )
    documents: Mapped[list["EvaluationDocument"]] = relationship(
        back_populates="evaluation", cascade="all, delete-orphan"
    )


class EvaluationDocument(Base):
    __tablename__ = "evaluation_document"

    id: Mapped[int] = mapped_column(primary_key=True)
    evaluation_id: Mapped[int] = mapped_column(ForeignKey("evaluation.id", ondelete="CASCADE"))
    filename: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str | None] = mapped_column(String(100))
    content_text: Mapped[str] = mapped_column(Text)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    evaluation: Mapped[Evaluation] = relationship(back_populates="documents")


class MetricValue(Base):
    __tablename__ = "metric_value"
    __table_args__ = (UniqueConstraint("evaluation_id", "metric_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    evaluation_id: Mapped[int] = mapped_column(ForeignKey("evaluation.id", ondelete="CASCADE"))
    metric_id: Mapped[int] = mapped_column(ForeignKey("metric.id"))
    value: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual | llm | import
    note: Mapped[str | None] = mapped_column(Text)

    evaluation: Mapped[Evaluation] = relationship(back_populates="metric_values")
    metric: Mapped[Metric] = relationship()


class ParameterResult(Base):
    """Per-parameter outcome. Leaves carry judged/computed/final scores; non-leaves carry the roll-up."""

    __tablename__ = "parameter_result"
    __table_args__ = (
        UniqueConstraint("evaluation_id", "parameter_id"),
        CheckConstraint(
            "score_source in ('judged','metric','override','rollup','not_applicable','pending')",
            name="ck_result_source",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    evaluation_id: Mapped[int] = mapped_column(ForeignKey("evaluation.id", ondelete="CASCADE"))
    parameter_id: Mapped[int] = mapped_column(ForeignKey("parameter.id"))
    is_leaf: Mapped[bool] = mapped_column(Boolean)
    judged_score: Mapped[float | None] = mapped_column(Float)
    computed_score: Mapped[float | None] = mapped_column(Float)
    final_score: Mapped[float | None] = mapped_column(Float)
    score_source: Mapped[str] = mapped_column(String(20), default="pending")
    not_applicable: Mapped[bool] = mapped_column(Boolean, default=False)
    rationale: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)  # 0..1, mainly for LLM judge
    override_reason: Mapped[str | None] = mapped_column(Text)
    effective_weight: Mapped[float | None] = mapped_column(Float)  # share of final score, 0..1
    band_label: Mapped[str | None] = mapped_column(String(40))

    evaluation: Mapped[Evaluation] = relationship(back_populates="results")
    parameter: Mapped[Parameter] = relationship()
