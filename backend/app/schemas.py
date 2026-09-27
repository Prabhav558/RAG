"""Pydantic contracts. The nested `ScorecardDefinition` is also the JSON import/export format
used by data/scorecards/*.json and the ingestion tool."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Aggregation = Literal["weighted_mean", "minimum"]


class ThresholdIn(BaseModel):
    min_value: float | None = None
    max_value: float | None = None
    score: float


class MetricIn(BaseModel):
    code: str = Field(min_length=1, max_length=60)
    name: str = Field(min_length=1, max_length=200)
    unit: str | None = None
    data_type: Literal["number", "percent", "count", "boolean"] = "number"
    description: str | None = None
    thresholds: list[ThresholdIn] = Field(default_factory=list)


class CriterionIn(BaseModel):
    score_min: int
    score_max: int
    qualitative: str = ""
    quantitative: str | None = None


class ParameterIn(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    weight: float = Field(default=1.0, ge=0)
    aggregation: Aggregation = "weighted_mean"
    is_critical: bool = False
    min_acceptable_score: float | None = None
    is_optional: bool = False
    criteria: list[CriterionIn] = Field(default_factory=list)
    metrics: list[MetricIn] = Field(default_factory=list)
    children: list[ParameterIn] = Field(default_factory=list)


class VersionIn(BaseModel):
    purpose: str = ""
    scope: str = ""
    objective: str = ""
    guidance: str | None = None
    rating_scale: str = "0-10-rag"  # rating_scale.code
    target_score: float = 8
    aggregation: Aggregation = "weighted_mean"
    max_depth: int = Field(default=4, ge=1, le=6)
    qtc_enabled: bool = False
    change_note: str | None = None
    parameters: list[ParameterIn] = Field(default_factory=list)


class ScorecardDefinition(BaseModel):
    code: str = Field(min_length=2, max_length=60, pattern=r"^[a-z0-9][a-z0-9\-]*$")
    name: str = Field(min_length=1, max_length=200)
    subject_type: str  # subject_type.code
    owner: str | None = None
    tags: list[str] = Field(default_factory=list)
    is_template: bool = False
    version: VersionIn


class ScorecardMetaUpdate(BaseModel):
    name: str | None = None
    subject_type: str | None = None
    owner: str | None = None
    tags: list[str] | None = None
    is_template: bool | None = None


class CloneRequest(BaseModel):
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


class ScaleIn(BaseModel):
    code: str = Field(min_length=2, max_length=40)
    name: str
    min_value: int
    max_value: int
    description: str | None = None
    bands: list[BandOut]


class SubjectTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name: str
    description: str | None = None


class SubjectTypeIn(BaseModel):
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


class EvaluationCreate(BaseModel):
    version_id: int
    subject_name: str = Field(min_length=1, max_length=300)
    subject_ref: str | None = None
    input_text: str | None = None
    evaluator_type: Literal["self", "human", "llm"] = "human"
    evaluator_name: str | None = None
    target_score: float | None = None
    is_private: bool | None = None
    attempt_no: int = Field(default=1, ge=1)
    notes: str | None = None


class RatingIn(BaseModel):
    parameter_id: int
    judged_score: float | None = None
    not_applicable: bool = False
    rationale: str | None = None
    evidence: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    override_reason: str | None = None


class MetricValueIn(BaseModel):
    metric_id: int
    value: float | None  # None clears the value
    source: Literal["manual", "llm", "import"] = "manual"
    note: str | None = None


class EvaluationUpdate(BaseModel):
    ratings: list[RatingIn] = Field(default_factory=list)
    metric_values: list[MetricValueIn] = Field(default_factory=list)
    subject_name: str | None = None
    input_text: str | None = None
    time_met: bool | None = None
    cost_met: bool | None = None
    target_score: float | None = None
    summary: str | None = None
    notes: str | None = None


class VoidRequest(BaseModel):
    reason: str = Field(min_length=3)
