"""Compatibility/catalog DTOs. Implemented routes use their stage-specific models.

B7 durable admission is WorkJob/WorkRequest; this catalog does not define a second
job implementation. See generated route schemas for the authoritative contracts.
"""

from typing import Annotated, Literal

from pydantic import Field

from backend.contracts import StrictModel
from backend.guardian.report import GuardianReport
from backend.schemas import (
    BrandKit,
    Canonical,
    Channel,
    DependencyVersions,
    IntentResult,
    Lang,
    SlotKey,
    SurfaceResult,
    VariantContract,
)


class AudienceContract(StrictModel):
    id: str
    campaign_id: str
    name: str
    insight: str
    angle: str
    eligibility_fact_version: int | None


class AssetContract(StrictModel):
    id: str
    campaign_id: str
    variant_id: str
    campaign_revision: int
    kind: Literal["background", "poster", "video"]
    status: Literal["pending", "ready", "blocked", "stale", "uncertain"]
    mime_type: str
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    byte_count: int | None = Field(default=None, ge=0)
    sha256: str | None
    fact_hash: str
    dependency_hash: str
    content_hash: str
    render_hash: str | None
    dependencies: DependencyVersions
    provenance: Literal["live", "mock", "cached", "deterministic"]
    captured_at: str | None
    # Server-owned id resolves storage; clients never supply filesystem paths/URLs.


class ScoreContract(StrictModel):
    variant_id: str
    content_hash: str
    scoring_version: str
    engagement_prediction: float | None = Field(ge=0, le=100)
    clarity: float | None = Field(ge=0, le=100)
    persuasion: float | None = Field(ge=0, le=100)
    safety_integrity: float | None = Field(ge=0, le=100)
    score_kind: Literal["heuristic_prediction"] = "heuristic_prediction"
    observed_performance: Literal["NOT_MEASURED"] = "NOT_MEASURED"
    completed: bool
    explanations: list[str]


class JobContract(StrictModel):
    run_id: str
    campaign_id: str
    expected_revision: int
    operation: Literal["generate", "optimize", "render", "video"]
    idempotency_key: str
    request_hash: str
    status: Literal[
        "queued", "running", "completed", "failed", "cancelled", "interrupted", "uncertain"
    ]
    deadline_at: str
    call_budget: int = Field(ge=0)
    calls_used: int = Field(ge=0)
    output_ids: list[str]
    error_code: str | None


class ChangeItem(StrictModel):
    key: SlotKey
    before: Canonical | None
    after: Canonical | None
    classification: Literal["FACT_LOCKED"]
    affected_ids: list[str]


class PreferenceSnapshot(StrictModel):
    brand: BrandKit
    target_audiences: list[str]
    languages: list[Lang]
    channels: list[Channel]


class PreferenceChange(StrictModel):
    classification: Literal["SOFT_PREFERENCE"]
    before: PreferenceSnapshot
    after: PreferenceSnapshot
    affected_ids: list[str]


class ChangeProposalContract(StrictModel):
    id: str
    campaign_id: str
    expected_revision: int
    items: list[Annotated[ChangeItem | PreferenceChange, Field(discriminator="classification")]]
    status: Literal["proposed", "needs_input", "confirmed", "rejected", "stale"]
    questions: list[str]
    request_hash: str


class LedgerEventContract(StrictModel):
    id: int
    campaign_id: str
    campaign_revision: int
    run_id: str | None
    timestamp: str
    event: str
    decision: str
    changed_fact_versions: dict[SlotKey, int]
    invalidated_ids: list[str]
    approval_id: str | None


class ExportFileContract(StrictModel):
    asset_id: str
    filename: str
    language: Lang
    channel: Channel
    byte_count: int = Field(ge=1)
    sha256: str
    fact_hash: str
    dependency_hash: str
    content_hash: str
    render_hash: str
    dependencies: DependencyVersions
    provenance: Literal["live", "mock", "cached", "deterministic"]
    captured_at: str | None


class ExportManifestContract(StrictModel):
    campaign_id: str
    campaign_revision: int
    fact_versions: dict[SlotKey, int]
    approval_id: str
    approved_at: str
    mode: Literal["live", "mock", "cached"]
    files: list[ExportFileContract] = Field(min_length=1)
    warning_acknowledgments: list[str]


class BoundaryCatalog(StrictModel):
    """Schema registry only; these fields are not an API request or response."""

    intent: IntentResult
    surfaces: SurfaceResult
    audience: AudienceContract
    variant: VariantContract
    guardian: GuardianReport
    asset: AssetContract
    score: ScoreContract
    job: JobContract
    change: ChangeProposalContract
    ledger: LedgerEventContract
    export: ExportManifestContract
