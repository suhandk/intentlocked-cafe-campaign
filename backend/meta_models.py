"""Delivery contracts are separate from inference and from owner fact publication."""

from typing import Literal

from pydantic import Field, SecretStr, model_validator

from backend.contracts import StrictModel
from backend.schemas import RevisionRequest

Platform = Literal["whatsapp", "facebook", "instagram"]


class MetaPreview(RevisionRequest):
    platform: Platform
    text_item_id: str = Field(min_length=1, max_length=128)
    poster_item_id: str | None = Field(default=None, max_length=128)
    observed_hashes: dict[str, str]
    idempotency_key: str = Field(min_length=8, max_length=128)
    recipient: SecretStr = SecretStr("")
    recipient_consented: bool = False
    template_name: str | None = Field(default=None, pattern=r"^[a-z0-9_]{1,100}$")
    template_language: str | None = Field(default=None, pattern=r"^[a-z]{2}(?:_[A-Z]{2})?$")

    @model_validator(mode="after")
    def platform_fields(self):
        if self.platform != "whatsapp" and (
            self.recipient.get_secret_value()
            or self.recipient_consented
            or self.template_name
            or self.template_language
        ):
            raise ValueError("Recipient and template fields are WhatsApp-only")
        if bool(self.template_name) != bool(self.template_language):
            raise ValueError("Template name and language must be supplied together")
        if self.template_name and self.poster_item_id:
            raise ValueError("This scope supports static text templates only")
        return self


class MetaConfirm(RevisionRequest):
    preview_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    confirmation_token: SecretStr
    owner_confirms_delivery: Literal[True]


class MetaWorkInput(RevisionRequest):
    operation_id: str = Field(min_length=1, max_length=128)


class MetaOperation(StrictModel):
    id: str
    campaign_id: str
    campaign_revision: int
    platform: Platform
    status: Literal[
        "pending_confirmation",
        "queued",
        "submitting",
        "processing",
        "accepted",
        "published",
        "delivered",
        "read",
        "failed",
        "cancelled",
        "stale",
        "delivery_unknown",
    ]
    mode: Literal["mock", "live"]
    source_mode: Literal["mock", "live", "cached"]
    created_at: str
    updated_at: str
    destination_label: str
    text: str
    approved_hashes: dict[str, str]
    artifact_hashes: dict[str, str]
    delivery_media_hash: str | None = None
    preview_hash: str
    job_id: str | None = None
    provider_id: str | None = None
    provider_media_id: str | None = None
    container_id: str | None = None
    attempts: int = 0
    error_code: str | None = None
    changed_after_submission: bool = False
    cached: bool = False
    provenance: dict[str, dict] = Field(default_factory=dict)
    cost_status: Literal["not_applicable_mock", "unknown_provider_charge"]
    # Only returned at the authenticated preview endpoint; never in jobs or traces.
    confirmation_token: str | None = None


class MetaStatus(StrictModel):
    enabled: bool
    mode: Literal["mock", "live"]
    graph_version: str
    instagram_flow: Literal["facebook_login"] = "facebook_login"
    platforms: dict[str, str]
    authenticated_checks: str = "NOT_TESTED; deployment operator must verify each platform"
