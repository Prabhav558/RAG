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
    Index,
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
    requires_review: Mapped[bool] = mapped_column(Boolean, default=False)  # publish only via reviewer approval
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
        CheckConstraint("status in ('draft','in_review','published','retired')", name="ck_version_status"),
        CheckConstraint("required_judges between 1 and 5", name="ck_version_judges"),
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
    # Cycle 3: how submissions are judged
    required_judges: Mapped[int] = mapped_column(Integer, default=1)
    judge_tolerance_pct: Mapped[float] = mapped_column(Float, default=10.0)  # max score spread, % of scale
    require_self_appraisal: Mapped[bool] = mapped_column(Boolean, default=False)
    is_foundational: Mapped[bool] = mapped_column(Boolean, default=False)  # red blocks the project
    row_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)  # optimistic concurrency
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

    __mapper_args__ = {"version_id_col": row_version}


class Parameter(Base):
    """A KPI / parameter node. Self-referencing tree; leaves are rated, non-leaves are rolled up."""

    __tablename__ = "parameter"
    __table_args__ = (
        UniqueConstraint("version_id", "code"),
        CheckConstraint("weight >= 0", name="ck_param_weight"),
        CheckConstraint("aggregation in ('weighted_mean','minimum')", name="ck_param_agg"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("scorecard_version.id", ondelete="CASCADE"), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("parameter.id", ondelete="CASCADE"), index=True)
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
        # tuning: analytics and lists filter on these
        Index("ix_evaluation_version_status", "version_id", "status"),
        Index("ix_evaluation_status_private", "status", "is_private"),
        Index("ix_evaluation_subject_ref", "subject_ref"),
        Index("ix_evaluation_submission", "submission_id"),
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
    gate_failure_count: Mapped[int] = mapped_column(Integer, default=0)  # SQL-aggregatable (JSON is not portable)
    summary: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voided_reason: Mapped[str | None] = mapped_column(Text)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    subject_id: Mapped[int | None] = mapped_column(ForeignKey("subject.id"))
    submission_id: Mapped[int | None] = mapped_column(ForeignKey("submission.id"))

    version: Mapped[ScorecardVersion] = relationship()
    submission: Mapped["Submission | None"] = relationship(back_populates="evaluations")
    row_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)  # optimistic concurrency
    __mapper_args__ = {"version_id_col": row_version}
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


# ---------------------------------------------------------------- Cycle 3: behaviour


class VersionReview(Base):
    """Governance trail of a scorecard version: submitted, approved, changes requested, published, retired."""

    __tablename__ = "version_review"

    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("scorecard_version.id", ondelete="CASCADE"))
    action: Mapped[str] = mapped_column(String(20))
    actor: Mapped[str] = mapped_column(String(120))
    comment: Mapped[str | None] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Subject(Base):
    """A thing being scored (task, milestone, project, team, document, ...). Subjects form a tree."""

    __tablename__ = "subject"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(60), unique=True)
    name: Mapped[str] = mapped_column(String(300))
    subject_type_id: Mapped[int] = mapped_column(ForeignKey("subject_type.id"))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("subject.id"), index=True)
    owner: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # ODTQRC: Time (also QTC: agreed time)
    budget: Mapped[float | None] = mapped_column(Float)  # ODTQRC: Cost (also QTC: agreed cost)
    # ODTQRC task definition (docs/12_ARCHITECTURE.md): Objective, Deliverable, Time (due_at), Quality, Risk,
    # Cost (budget) — the fields a clarity agent (app/clarity.py) reviews for vagueness before work starts.
    objective: Mapped[str | None] = mapped_column(Text)
    deliverable: Mapped[str | None] = mapped_column(Text)
    quality_bar: Mapped[str | None] = mapped_column(Text)
    risks: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    subject_type: Mapped[SubjectType] = relationship()
    parent: Mapped["Subject | None"] = relationship(remote_side="Subject.id", back_populates="children")
    children: Mapped[list["Subject"]] = relationship(back_populates="parent")
    submissions: Mapped[list["Submission"]] = relationship(back_populates="subject", order_by="Submission.id")


class Submission(Base):
    """One attempt at getting a subject through a published scorecard version (the quality gate)."""

    __tablename__ = "submission"
    __table_args__ = (
        CheckConstraint(
            "status in ('open','in_review','adjudication','decided','withdrawn','cancelled')", name="ck_sub_status"
        ),
        CheckConstraint("decision is null or decision in ('passed','redo')", name="ck_sub_decision"),
        UniqueConstraint("subject_id", "version_id", "attempt_no"),
        Index("ix_submission_status", "status"),
        Index("ix_submission_decision_owner", "decision", "owner"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subject.id"))
    version_id: Mapped[int] = mapped_column(ForeignKey("scorecard_version.id"))
    attempt_no: Mapped[int] = mapped_column(Integer, default=1)
    previous_id: Mapped[int | None] = mapped_column(ForeignKey("submission.id"))
    owner: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(15), default="open")
    title: Mapped[str | None] = mapped_column(String(300))
    input_text: Mapped[str | None] = mapped_column(Text)
    actual_cost: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # decision (computed by the gate, or recorded by an adjudicator)
    decision: Mapped[str | None] = mapped_column(String(10))
    official_score: Mapped[float | None] = mapped_column(Float)
    official_band: Mapped[str | None] = mapped_column(String(40))
    official_rag: Mapped[str | None] = mapped_column(String(5))
    judge_spread_pct: Mapped[float | None] = mapped_column(Float)
    gate_failures: Mapped[list] = mapped_column(JSON, default=list)
    time_met: Mapped[bool | None] = mapped_column(Boolean)
    cost_met: Mapped[bool | None] = mapped_column(Boolean)
    qtc_green: Mapped[bool | None] = mapped_column(Boolean)
    adjudicated: Mapped[bool] = mapped_column(Boolean, default=False)
    decided_by: Mapped[str | None] = mapped_column(String(120))
    decision_reason: Mapped[str | None] = mapped_column(Text)
    blocks_project: Mapped[bool] = mapped_column(Boolean, default=False)  # foundational red (stop rule)
    row_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)  # optimistic concurrency

    subject: Mapped[Subject] = relationship(back_populates="submissions")
    version: Mapped[ScorecardVersion] = relationship()
    evaluations: Mapped[list[Evaluation]] = relationship(back_populates="submission", order_by="Evaluation.id")

    __mapper_args__ = {"version_id_col": row_version}


class Diagnosis(Base):
    """Why a person keeps getting reds, and what is being done about it (framework §12)."""

    __tablename__ = "diagnosis"
    __table_args__ = (
        CheckConstraint("cause in ('skill','aptitude','will','allocation')", name="ck_diag_cause"),
        CheckConstraint("action in ('train','reassign','discuss','rescope','none')", name="ck_diag_action"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    person: Mapped[str] = mapped_column(String(120))
    cause: Mapped[str] = mapped_column(String(12))
    action: Mapped[str] = mapped_column(String(12))
    notes: Mapped[str | None] = mapped_column(Text)
    submission_id: Mapped[int | None] = mapped_column(ForeignKey("submission.id"))
    recorded_by: Mapped[str] = mapped_column(String(120))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Capability(Base):
    """A person's assessed C1-C6 capability/competency level for a scorecard's skill domain (framework §12): a
    six-rung ladder from novice to expert. Append-only, like Diagnosis — the current level for a person and
    scorecard is the most recent row, so the assessment history is never lost to an overwrite."""

    __tablename__ = "capability"
    __table_args__ = (CheckConstraint("level between 1 and 6", name="ck_capability_level"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    person: Mapped[str] = mapped_column(String(120), index=True)
    scorecard_id: Mapped[int] = mapped_column(ForeignKey("scorecard.id"))
    level: Mapped[int] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    set_by: Mapped[str] = mapped_column(String(120))
    set_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    scorecard: Mapped["Scorecard"] = relationship()


class UserAccount(Base):
    """A login. `display_name` is the identity used everywhere workflow rules and audit trails show an actor."""

    __tablename__ = "user_account"
    __table_args__ = (Index("ix_user_account_username", "username", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(60), unique=True)
    email: Mapped[str | None] = mapped_column(String(200), unique=True)
    display_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(200))
    roles: Mapped[list] = mapped_column(JSON, default=list)  # subset of admin/designer/reviewer/lead/importer
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    sessions: Mapped[list["AuthSession"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class AuthSession(Base):
    """A logged-in session. Only the SHA-256 of the bearer token is stored."""

    __tablename__ = "auth_session"
    __table_args__ = (Index("ix_auth_session_token_hash", "token_hash", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user_account.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[UserAccount] = relationship(back_populates="sessions")


class AuditEvent(Base):
    """Every state transition, with who did it and why."""

    __tablename__ = "audit_event"

    id: Mapped[int] = mapped_column(primary_key=True)
    entity: Mapped[str] = mapped_column(String(30))  # version | submission | subject | evaluation | diagnosis
    entity_id: Mapped[int] = mapped_column(Integer, index=True)
    action: Mapped[str] = mapped_column(String(30))
    from_state: Mapped[str | None] = mapped_column(String(20))
    to_state: Mapped[str | None] = mapped_column(String(20))
    actor: Mapped[str] = mapped_column(String(120))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
