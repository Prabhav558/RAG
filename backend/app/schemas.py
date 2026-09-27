"""Pydantic contracts. The nested `ScorecardDefinition` is also the JSON import/export format
used by data/scorecards/*.json and the ingestion tool."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Aggregation = Literal["weighted_mean", "minimum"]

# Size limits (Cycle 2: unbounded text was accepted, see docs/cycle2/corruption_report_baseline.md)
NAME_MAX = 200
TEXT_MAX = 20_000  # purpose, scope, guidelines, rationale
INPUT_MAX = 400_000  # pasted input to evaluate (same limit as extracted documents)
WEIGHT_MAX = 1_000_000


class Contract(BaseModel):
    """Base for every inbound payload: NaN and +/-Infinity are never valid business values."""

    model_config = ConfigDict(allow_inf_nan=False)


class ThresholdIn(Contract):
    min_value: float | None = None
    max_value: float | None = None
    score: float


class MetricIn(Contract):
    code: str = Field(min_length=1, max_length=60)
    name: str = Field(min_length=1, max_length=NAME_MAX)
    unit: str | None = Field(default=None, max_length=40)
    data_type: Literal["number", "percent", "count", "boolean"] = "number"
    description: str | None = Field(default=None, max_length=TEXT_MAX)
    thresholds: list[ThresholdIn] = Field(default_factory=list)


class CriterionIn(Contract):
    score_min: int
    score_max: int
    qualitative: str = Field(default="", max_length=TEXT_MAX)
    quantitative: str | None = Field(default=None, max_length=TEXT_MAX)


class ParameterIn(Contract):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=NAME_MAX)
    description: str | None = Field(default=None, max_length=TEXT_MAX)
    weight: float = Field(default=1.0, ge=0, le=WEIGHT_MAX)
    aggregation: Aggregation = "weighted_mean"
    is_critical: bool = False
    min_acceptable_score: float | None = None
    is_optional: bool = False
    criteria: list[CriterionIn] = Field(default_factory=list)
    metrics: list[MetricIn] = Field(default_factory=list)
    children: list[ParameterIn] = Field(default_factory=list)


class VersionIn(Contract):
    purpose: str = Field(default="", max_length=TEXT_MAX)
    scope: str = Field(default="", max_length=TEXT_MAX)
    objective: str = Field(default="", max_length=TEXT_MAX)
    guidance: str | None = Field(default=None, max_length=TEXT_MAX)
    rating_scale: str = "0-10-rag"  # rating_scale.code
    target_score: float = 8
    aggregation: Aggregation = "weighted_mean"
    max_depth: int = Field(default=4, ge=1, le=6)
    qtc_enabled: bool = False
    required_judges: int = Field(default=1, ge=1, le=5)
    judge_tolerance_pct: float = Field(default=10.0, ge=0, le=100)
    require_self_appraisal: bool = False
    is_foundational: bool = False
    change_note: str | None = Field(default=None, max_length=TEXT_MAX)
    parameters: list[ParameterIn] = Field(default_factory=list)


class ScorecardDefinition(Contract):
    code: str = Field(min_length=2, max_length=60, pattern=r"^[a-z0-9][a-z0-9\-]*$")
    name: str = Field(min_length=1, max_length=NAME_MAX)
    subject_type: str  # subject_type.code
    owner: str | None = Field(default=None, max_length=120)
    tags: list[str] = Field(default_factory=list)
    is_template: bool = False
    requires_review: bool = False
    version: VersionIn


class ScorecardMetaUpdate(Contract):
    requires_review: bool | None = None
    name: str | None = None
    subject_type: str | None = None
    owner: str | None = None
    tags: list[str] | None = None
    is_template: bool | None = None


class CloneRequest(Contract):
    code: str = Field(min_length=2, max_length=60, pattern=r"^[a-z0-9][a-z0-9\-]*$")
    name: str
    version_id: int | None = None


# ---------------------------------------------------------------- output views


class Issue(BaseModel):
    code: str
    severity: Literal["error", "warning"]
    message: str
    path: str | None = None


class BandOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    label: str
    lower_bound: float
    color_hex: str
    font_hex: str
    rag: str
    meaning: str | None = None


class ScaleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name: str
    min_value: int
    max_value: int
    description: str | None = None
    bands: list[BandOut]


class BandIn(Contract):
    label: str = Field(min_length=1, max_length=40)
    lower_bound: float
    color_hex: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    font_hex: str = Field(default="#000000", pattern=r"^#[0-9A-Fa-f]{6}$")
    rag: Literal["GREEN", "AMBER", "RED"]
    meaning: str | None = Field(default=None, max_length=TEXT_MAX)


class ScaleIn(Contract):
    code: str = Field(min_length=2, max_length=40, pattern=r"^[a-z0-9][a-z0-9\-]*$")
    name: str = Field(min_length=1, max_length=120)
    min_value: int
    max_value: int
    description: str | None = Field(default=None, max_length=TEXT_MAX)
    bands: list[BandIn] = Field(min_length=1, max_length=50)


class SubjectTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name: str
    description: str | None = None


class SubjectTypeIn(Contract):
    code: str = Field(min_length=2, max_length=40, pattern=r"^[a-z0-9][a-z0-9_\-]*$")
    name: str
    description: str | None = None


class VersionSummary(BaseModel):
    id: int
    version_no: int
    status: str
    published_at: datetime | None
    created_at: datetime


class ScorecardSummary(BaseModel):
    id: int
    code: str
    name: str
    subject_type: str
    subject_type_name: str
    owner: str | None
    tags: list[str]
    is_template: bool
    purpose: str
    parameter_count: int
    leaf_count: int
    depth: int
    evaluation_count: int
    versions: list[VersionSummary]


# ---------------------------------------------------------------- evaluation contracts


class EvaluationCreate(Contract):
    version_id: int
    subject_name: str = Field(min_length=1, max_length=300)
    subject_ref: str | None = Field(default=None, max_length=120)
    input_text: str | None = Field(default=None, max_length=INPUT_MAX)
    evaluator_type: Literal["self", "human", "llm"] = "human"
    evaluator_name: str | None = Field(default=None, max_length=120)
    target_score: float | None = None
    is_private: bool | None = None
    attempt_no: int = Field(default=1, ge=1)
    notes: str | None = Field(default=None, max_length=TEXT_MAX)


class RatingIn(Contract):
    parameter_id: int
    judged_score: float | None = None
    not_applicable: bool = False
    rationale: str | None = Field(default=None, max_length=TEXT_MAX)
    evidence: str | None = Field(default=None, max_length=TEXT_MAX)
    confidence: float | None = Field(default=None, ge=0, le=1)
    override_reason: str | None = Field(default=None, max_length=TEXT_MAX)


class MetricValueIn(Contract):
    metric_id: int
    value: float | None  # None clears the value
    source: Literal["manual", "llm", "import"] = "manual"
    note: str | None = Field(default=None, max_length=TEXT_MAX)


class EvaluationUpdate(Contract):
    ratings: list[RatingIn] = Field(default_factory=list)
    metric_values: list[MetricValueIn] = Field(default_factory=list)
    subject_name: str | None = Field(default=None, min_length=1, max_length=300)
    input_text: str | None = Field(default=None, max_length=INPUT_MAX)
    time_met: bool | None = None
    cost_met: bool | None = None
    target_score: float | None = None
    summary: str | None = Field(default=None, max_length=TEXT_MAX)
    notes: str | None = Field(default=None, max_length=TEXT_MAX)


class VoidRequest(Contract):
    reason: str = Field(min_length=3, max_length=TEXT_MAX)
