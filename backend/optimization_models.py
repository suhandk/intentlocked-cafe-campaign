"""B5.1 persisted prediction, bounded edits and blinded audit contracts."""

from typing import Literal

from pydantic import Field, model_validator

from backend.contracts import StrictModel
from backend.generation_models import BaselineVariant, PersonaProfile
from backend.guardian.report import GuardianReport
from backend.schemas import (
    FACT_KINDS,
    Canonical,
    RevisionRequest,
    SlotKey,
    TemplateContent,
    VariantContract,
)


class Judgment(StrictModel):
    persona_id: str
    choice: Literal["X", "Y", "tie"]
    reason: str = Field(min_length=1, max_length=300)


class JudgeResult(StrictModel):
    judgments: list[Judgment] = Field(max_length=5)


class Edit(StrictModel):
    target: str = Field(max_length=100)
    value: str = Field(max_length=4000)


class CritiqueResult(StrictModel):
    critique: str = Field(min_length=1, max_length=500)
    edits: list[Edit] = Field(max_length=4)
    no_change: bool


class Evidence(StrictModel):
    field: str
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    quote: str = Field(min_length=1, max_length=500)


class Expectation(StrictModel):
    key: SlotKey
    state: Literal["stated", "not_stated", "ambiguous"]
    canonical: Canonical | None
    evidence: list[Evidence] = Field(max_length=4)

    @model_validator(mode="after")
    def type_matches_key(self):
        if self.canonical is not None and self.canonical.kind not in FACT_KINDS[self.key]:
            raise ValueError("Extract the canonical type belonging to this fact key")
        return self


class Promise(StrictModel):
    description: str = Field(min_length=1, max_length=300)
    evidence: Evidence


class ReaderResult(StrictModel):
    expectations: list[Expectation] = Field(min_length=12, max_length=12)
    other_promises: list[Promise] = Field(max_length=10)
    ambiguities: list[str] = Field(max_length=10)
    back_translation: str = Field(max_length=4000)


class Feature(StrictModel):
    name: str
    applicable: bool
    value: float | None
    measurement: str


class MappedVote(StrictModel):
    persona_id: str
    order: Literal["AB", "BA"]
    winner_id: str | None
    outcome: Literal["baseline", "candidate", "tie", "missing"]
    reason: str


class Score(StrictModel):
    scoring_version: Literal["b5.1"] = "b5.1"
    features: list[Feature]
    feature_mean: float | None
    tournament: float | None
    overall: float | None
    weighted_wins: float
    complete_judgments: int
    votes: list[MappedVote]
    sensitivity_band: list[float] | None
    order_disagreement: int
    baseline_convention: bool = False
    label: str = "Predicted preference — simulated personas + rules; not a CTR forecast."
    band_label: str = (
        "Tournament sensitivity from paired simulated judges; not a confidence interval."
    )


class CallEvidence(StrictModel):
    role: str
    cache_key: str
    provenance: Literal["mock", "live", "cache"]
    source_mode: Literal["mock", "live", "cached"]
    captured_at: str
    model: str
    prompt_hash: str
    input_hash: str
    output_hash: str | None
    call_ids: list[str]
    error_code: str | None
    elapsed_ms: float


class Audit(StrictModel):
    id: str
    campaign_id: str
    campaign_revision: int
    content_hash: str
    dependency_hash: str
    artifact_hash: str | None
    status: Literal["PASS", "BLOCKED", "PENDING"]
    findings: list[str]
    warning_ids: list[str]
    reader: ReaderResult | None
    guardian: GuardianReport
    provenance: list[dict]
    call: CallEvidence
    measured_features: list[Feature] = Field(default_factory=list)
    remote_vision: Literal["NOT_TESTED"] = "NOT_TESTED"
    approval_ready: Literal[False] = False


class Round(StrictModel):
    number: int
    candidate_id: str
    candidate_template: TemplateContent | None = None
    critique: str = ""
    edits: list[Edit] = Field(default_factory=list)
    guardian: GuardianReport | None = None
    audit: Audit | None = None
    score: Score | None = None
    accepted: bool = False
    reasons: list[str] = Field(default_factory=list)
    calls: list[CallEvidence] = Field(default_factory=list)
    elapsed_ms: float = 0


class OptimizationGroup(StrictModel):
    baseline: BaselineVariant
    current_id: str
    current_template: TemplateContent
    baseline_score: Score
    current_score: Score
    baseline_audit: Audit | None = None
    final_audit: Audit | None = None
    rounds: list[Round] = Field(default_factory=list)
    stop_reason: str | None = None


class OptimizeRequest(RevisionRequest):
    variant_ids: list[str] = Field(min_length=1, max_length=3)
    idempotency_key: str = Field(min_length=8, max_length=128)


class OptimizationRun(StrictModel):
    id: str
    campaign_id: str
    campaign_revision: int
    context_hash: str
    request: OptimizeRequest
    personas: list[PersonaProfile]
    persona_hash: str
    baseline_hash: str
    mode: Literal["mock", "live", "cached"]
    model: str
    prompt_hashes: dict[str, str]
    status: Literal["queued", "running", "completed", "failed", "stale", "interrupted", "cancelled"]
    phase: str
    groups: list[OptimizationGroup]
    max_rounds: int
    max_calls: int
    max_steps: int
    steps_used: int = 0
    calls_used: int = 0
    deadline_at: str
    created_at: str
    updated_at: str
    elapsed_ms: float = 0
    known_cost_usd: float = 0
    unknown_cost_calls: int = 0
    mock_calls: int = 0
    stop_reason: str | None = None
    prompt_version: Literal["b5.1"] = "b5.1"


class OptimizationSnapshot(StrictModel):
    runs: list[OptimizationRun]
    unscored_variant_ids: list[str]


class OptimizedVariant(VariantContract):
    report: GuardianReport
    mode: Literal["mock", "live", "cached"]
    baseline: Literal[False] = False
