"""B6.1 owner proposals, immutable delivery records and authorized exports."""

from typing import Literal

from pydantic import Field

from backend.contracts import StrictModel
from backend.guardian.report import GuardianReport
from backend.schemas import (
    Campaign,
    Canonical,
    CaseForms,
    FactSurface,
    Lang,
    RevisionRequest,
    SourceSpan,
    VariantContract,
)


class Operation(StrictModel):
    target: str = Field(min_length=1, max_length=80)
    canonical: Canonical | None = None
    value: str | list[str] | None = None
    surface: dict[Lang, CaseForms] | None = None
    scope_ids: list[str] = Field(default_factory=list, max_length=30)
    evidence: SourceSpan


class ChangeParse(StrictModel):
    operations: list[Operation] = Field(max_length=8)
    questions: list[str] = Field(default_factory=list, max_length=8)


class ChangeRequest(RevisionRequest):
    text: str = Field(min_length=1, max_length=2000)
    scope_ids: list[str] = Field(default_factory=list, max_length=30)
    idempotency_key: str = Field(min_length=8, max_length=128)


class Diff(StrictModel):
    target: str
    before: str
    after: str
    affected_ids: list[str]
    consequence: Literal["refill", "regenerate", "copy_review", "rerender", "unchanged"]


class Proposal(StrictModel):
    id: str
    campaign_id: str
    expected_revision: int
    request: ChangeRequest
    classification: Literal["mutable", "immutable", "mixed", "rejected"]
    status: Literal["proposed", "confirmed", "forms_review", "published", "cancelled", "rejected"]
    operations: list[Operation]
    diffs: list[Diff]
    questions: list[str]
    candidate: Campaign
    changed_keys: list[str]
    forms: list[FactSurface] = Field(default_factory=list)
    published_revision: int | None = None
    mode: Literal["live", "mock", "cached"]
    captured_at: str
    prompt_hash: str


class ConfirmRequest(RevisionRequest):
    proposal_id: str
    decision: Literal["confirm", "cancel"]
    idempotency_key: str = Field(min_length=8, max_length=128)


class PublishRequest(RevisionRequest):
    proposal_id: str
    reviewed_forms: list[FactSurface] = Field(max_length=12)
    approve_diff_and_forms: Literal[True]
    idempotency_key: str = Field(min_length=8, max_length=128)


class DeliveryItem(StrictModel):
    id: str
    campaign_id: str
    created_revision: int
    kind: Literal["text", "poster"]
    variant: VariantContract
    audience: str
    fields: dict[str, str]
    dependency_hash: str
    sha256: str
    byte_count: int
    source_table: Literal["baseline_variants", "poster_artifacts", "optimization", "derived"]
    source_id: str
    source_hash: str
    poster_id: str | None = None
    snapshot_hash: str
    mode: Literal["live", "mock", "cached"]
    status: Literal["pending", "approved", "blocked", "regeneration_required", "historical"] = (
        "pending"
    )
    audit_id: str | None = None
    audit_status: Literal["PASS", "PENDING", "BLOCKED"] | None = None
    approval_id: str | None = None
    warnings: list[str] = Field(default_factory=list)
    audit_findings: list[str] = Field(default_factory=list)
    approval_blockers: list[str] = Field(default_factory=list)
    report: GuardianReport


class ApprovalRequest(RevisionRequest):
    item_ids: list[str] = Field(min_length=1, max_length=30)
    observed_hashes: dict[str, str]
    acknowledged_warning_ids: list[str] = Field(default_factory=list, max_length=100)
    native_review_confirmed: bool = False
    owner_approves: Literal[True]
    idempotency_key: str = Field(min_length=8, max_length=128)


class AssetApproval(StrictModel):
    id: str
    campaign_id: str
    approved_revision: int
    approved_at: str
    item_hashes: dict[str, str]
    acknowledged_warning_ids: list[str]
    native_review_confirmed: bool


class Version(StrictModel):
    revision: int
    current: bool
    campaign: Campaign


class DeliverySnapshot(StrictModel):
    campaign_revision: int
    items: list[DeliveryItem]
    proposals: list[Proposal]
    versions: list[Version]
    ledger: list[dict]


class ExportFile(StrictModel):
    item_id: str
    filename: str
    sha256: str
    byte_count: int
    language: Lang
    channel: str
    approved_revision: int
    approval_id: str
    dependency_hash: str
    content_hash: str
    artifact_url: str | None
    mode: Literal["live", "mock", "cached"]
    source_fact_versions: dict[str, int]
    source_mode: Literal["live", "mock", "cached"] | None = None
    cached_evidence: list[dict] = Field(default_factory=list)
    captured_at: str | None = None
    provider: str = "kRouter"
    prompt_hashes: dict[str, str] = Field(default_factory=dict)
    cache_hits: list[str] = Field(default_factory=list)


class ExportPack(StrictModel):
    campaign_id: str
    campaign_revision: int
    generated_at: str
    mode: Literal["live", "mock", "cached"]
    files: list[ExportFile]
    copy_text: dict[str, str]
    whatsapp_drafts: dict[str, str]
    warning_acknowledgments: list[str]
    current_fact_versions: dict[str, int]
    source_mode: Literal["live", "mock", "cached"] | None = None
    view_label: str = "Current authorized output"
    disclaimer: str = "WhatsApp opens a prefilled draft; it sends nothing and attaches no files."


class RedTeamRequest(RevisionRequest):
    mode: Literal["instruct_ai", "edit_copy"]
    text: str = Field(min_length=1, max_length=2000)
    language: Lang = "en"
    idempotency_key: str = Field(min_length=8, max_length=128)


class RedTeamResult(StrictModel):
    mode: Literal["instruct_ai", "edit_copy"]
    proposal: Proposal | None = None
    report: GuardianReport | None = None
