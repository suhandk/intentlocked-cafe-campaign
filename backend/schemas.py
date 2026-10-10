"""Version b1.1: canonical facts and campaign contracts shared through OpenAPI."""

import re
from datetime import date
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from backend.contracts import StrictModel

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Lang = Literal["en", "kn", "kn-Latn"]
Channel = Literal["instagram", "whatsapp", "facebook", "poster"]
SlotKey = Literal[
    "CAFE",
    "LOCATION",
    "OFFER",
    "PRODUCT",
    "DAYS",
    "DATES",
    "ELIGIBILITY",
    "ID_RULE",
    "TIME_WINDOW",
    "DINE_IN_RULE",
    "MIN_PURCHASE_RULE",
    "COMBINE_RULE",
]
KEYS = [
    "CAFE",
    "LOCATION",
    "OFFER",
    "PRODUCT",
    "DAYS",
    "DATES",
    "ELIGIBILITY",
    "ID_RULE",
    "TIME_WINDOW",
    "DINE_IN_RULE",
    "MIN_PURCHASE_RULE",
    "COMBINE_RULE",
]
CORE = {"CAFE", "LOCATION", "OFFER", "PRODUCT", "DATES", "DAYS"}


class NamedValue(StrictModel):
    kind: Literal["text"] = "text"
    value: Text


class PercentOffer(StrictModel):
    kind: Literal["percent_off"] = "percent_off"
    value: float = Field(gt=0, le=100)
    unit: Literal["percent"] = "percent"


class AmountOffer(StrictModel):
    kind: Literal["amount_off"] = "amount_off"
    amount: float = Field(gt=0, le=1_000_000)
    currency: Literal["INR"] = "INR"


class BuyGetOffer(StrictModel):
    kind: Literal["buy_get"] = "buy_get"
    buy: int = Field(ge=1, le=100)
    get: int = Field(ge=1, le=100)


class DatesValue(StrictModel):
    kind: Literal["dates"] = "dates"
    start: str
    end: str
    original_phrase: str = Field(max_length=200)
    timezone: Literal["Asia/Kolkata"] = "Asia/Kolkata"

    @model_validator(mode="after")
    def valid_dates(self):
        for value in [self.start, self.end]:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                raise ValueError("Use absolute ISO dates")
            date.fromisoformat(value)
        if self.end < self.start:
            raise ValueError("End date precedes start date")
        if (date.fromisoformat(self.end) - date.fromisoformat(self.start)).days > 366:
            raise ValueError("Validity cannot exceed 366 days")
        return self


class DaysValue(StrictModel):
    kind: Literal["days"] = "days"
    weekdays: list[Literal["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]] = Field(
        min_length=1, max_length=7
    )


class EligibilityValue(StrictModel):
    kind: Literal["eligibility"] = "eligibility"
    scope: Literal["all", "students", "custom"]
    description: str = Field(default="", max_length=200)

    @model_validator(mode="after")
    def custom_description(self):
        if self.scope == "custom" and not self.description.strip():
            raise ValueError("Custom eligibility needs its exact restriction")
        return self


class IDRule(StrictModel):
    kind: Literal["id_rule"] = "id_rule"
    required: bool


class TimeWindow(StrictModel):
    kind: Literal["time_window"] = "time_window"
    start: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    end: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")

    @model_validator(mode="after")
    def same_day_window(self):
        if self.end <= self.start:
            raise ValueError("End must follow start; overnight windows need explicit support")
        return self


class DineInRule(StrictModel):
    kind: Literal["dine_in_rule"] = "dine_in_rule"
    scope: Literal["dine_in_only", "takeaway_only", "both"]


class MinimumPurchase(StrictModel):
    kind: Literal["minimum_purchase"] = "minimum_purchase"
    amount: float = Field(ge=0, le=1_000_000)
    currency: Literal["INR"] = "INR"


class CombineRule(StrictModel):
    kind: Literal["combine_rule"] = "combine_rule"
    allowed: bool


Canonical = Annotated[
    NamedValue
    | PercentOffer
    | AmountOffer
    | BuyGetOffer
    | DatesValue
    | DaysValue
    | EligibilityValue
    | IDRule
    | TimeWindow
    | DineInRule
    | MinimumPurchase
    | CombineRule,
    Field(discriminator="kind"),
]


FACT_KINDS = {
    "CAFE": ["text"],
    "LOCATION": ["text"],
    "PRODUCT": ["text"],
    "OFFER": ["percent_off", "amount_off", "buy_get"],
    "DATES": ["dates"],
    "DAYS": ["days"],
    "ELIGIBILITY": ["eligibility"],
    "ID_RULE": ["id_rule"],
    "TIME_WINDOW": ["time_window"],
    "DINE_IN_RULE": ["dine_in_rule"],
    "MIN_PURCHASE_RULE": ["minimum_purchase"],
    "COMBINE_RULE": ["combine_rule"],
}


class FactInput(StrictModel):
    key: SlotKey
    canonical: Canonical | None

    @model_validator(mode="after")
    def kind_matches_key(self):
        if self.canonical is not None and self.canonical.kind not in FACT_KINDS[self.key]:
            raise ValueError("Canonical type does not match fact key")
        return self


class SourceSpan(StrictModel):
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    quote: str = Field(min_length=1, max_length=2000)


Form = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Forms = Annotated[list[Form], Field(min_length=1, max_length=4)]


class CaseForms(StrictModel):
    nom: Forms
    dat: Forms | None = None
    gen: Forms | None = None
    loc: Forms | None = None


class Fact(FactInput):
    version: int = Field(ge=1)
    status: Literal["proposed", "locked", "not_specified"]
    source_span: SourceSpan | None = None
    source: Literal["owner", "R1", "derived", "unspecified"]
    surface: dict[Lang, CaseForms] = Field(default_factory=dict)
    canonical_hash: str
    approved_at: str | None = None
    approval_id: str | None = None


class BrandKit(StrictModel):
    colors: list[Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")]] = Field(
        default_factory=list, max_length=5
    )
    tone: str = Field(default="", max_length=100)
    theme: str = Field(default="", max_length=100)
    must_say: list[Text] = Field(default_factory=list, max_length=10)
    must_not_say: list[Text] = Field(default_factory=list, max_length=10)
    # Café identity comes from CAFE; uploads and factual claims need later approval paths.


class Warning(StrictModel):
    id: str
    message: str


class Clarification(StrictModel):
    key: SlotKey
    question: str
    required: bool


class CampaignCreate(StrictModel):
    languages: list[Lang] = Field(default_factory=lambda: ["en"], min_length=1, max_length=3)
    channels: list[Channel] = Field(
        default_factory=lambda: ["whatsapp"], min_length=1, max_length=4
    )


class RevisionRequest(StrictModel):
    expected_revision: int = Field(ge=1)


class IntentRequest(RevisionRequest):
    transcript: str = Field(min_length=1, max_length=2000)


class DraftRequest(RevisionRequest):
    facts: list[FactInput] = Field(max_length=12)
    languages: list[Lang] = Field(min_length=1, max_length=3)
    channels: list[Channel] = Field(min_length=1, max_length=4)
    target_audiences: list[Text] = Field(max_length=3)
    brand: BrandKit
    acknowledged_warning_ids: list[str] = Field(default_factory=list, max_length=20)
    # Explicit owner fallback: preserve the brief without calling it model-extracted.
    transcript: str | None = Field(default=None, min_length=1, max_length=2000)


class SurfaceRequest(RevisionRequest):
    confirm_canonical: Literal[True]


class FactSurface(StrictModel):
    key: SlotKey
    surface: dict[Lang, CaseForms]


class LockRequest(RevisionRequest):
    idempotency_key: str = Field(min_length=8, max_length=128)
    reviewed_fact_versions: dict[SlotKey, int]
    forms: list[FactSurface] = Field(min_length=1, max_length=12)
    approve_canonical_and_forms: Literal[True]
    acknowledged_warning_ids: list[str] = Field(max_length=20)


class Campaign(StrictModel):
    id: str
    revision: int
    status: Literal["draft", "canonical_confirmed", "forms_review", "locked"]
    mode: Literal["mock", "live", "cached"]
    languages: list[Lang]
    channels: list[Channel]
    target_audiences: list[str]
    transcript: str
    facts: list[Fact]
    brand: BrandKit
    brand_revision: int
    warnings: list[Warning]
    clarifications: list[Clarification]
    agent_questions: list[str] = Field(default_factory=list)
    acknowledged_warning_ids: list[str]
    reference_date: str
    timezone: Literal["Asia/Kolkata"] = "Asia/Kolkata"
    demo_clock: bool
    fact_hash: str | None = None
    approved_at: str | None = None
    native_review: Literal["NOT_REVIEWED"] = "NOT_REVIEWED"
    prompt_version: Literal["b1.1"] = "b1.1"


class ProposedFact(FactInput):
    evidence: SourceSpan


class DateProposal(StrictModel):
    phrase: str = Field(min_length=1, max_length=200)
    evidence: SourceSpan


class IntentSuccess(StrictModel):
    status: Literal["success"] = "success"
    facts: list[ProposedFact] = Field(max_length=10)
    date_proposal: DateProposal | None
    target_audiences: list[Text] = Field(max_length=3)
    clarification_questions: list[Text] = Field(max_length=8)
    warnings: list[Text] = Field(max_length=8)


class NeedsInput(StrictModel):
    status: Literal["needs_input"]
    questions: list[Text] = Field(min_length=1, max_length=8)


class RoleFailure(StrictModel):
    status: Literal["error"]
    reason: Literal["unable_to_interpret", "unsupported_language", "uncertain_forms"]


class IntentResult(StrictModel):
    result: Annotated[IntentSuccess | NeedsInput | RoleFailure, Field(discriminator="status")]


class SurfaceSuccess(StrictModel):
    status: Literal["success"] = "success"
    forms: list[FactSurface] = Field(min_length=1, max_length=12)
    uncertainties: list[Text] = Field(max_length=10)


class SurfaceResult(StrictModel):
    result: Annotated[SurfaceSuccess | NeedsInput | RoleFailure, Field(discriminator="status")]


# Shared boundaries reserved now, with no unimplemented endpoints or fake results.
class TemplateContent(StrictModel):
    headline: str
    body: str
    cta: str
    hashtags: list[str]
    alt_text: str


class DependencyVersions(StrictModel):
    facts: dict[SlotKey, int]
    brand_revision: int
    prompt_version: str
    policy_version: str
    renderer_version: str | None = None
    font_hash: str | None = None
    background_hash: str | None = None
    layout_hash: str | None = None


class VariantContract(StrictModel):
    id: str
    campaign_id: str
    campaign_revision: int
    audience_id: str
    language: Lang
    channel: Channel
    template: TemplateContent
    slots_used: list[SlotKey]
    fact_hash: str
    dependency_hash: str
    content_hash: str
    render_hash: str | None
    status: Literal["approved", "stale", "pending", "blocked"]
    parent_id: str | None
    dependencies: DependencyVersions


class CheckResult(StrictModel):
    rule: str
    applicable: bool
    completed: bool
    passed: bool | None
    severity: Literal["BLOCK", "WARN", "INFO"]
    message: str


class GuardianContract(StrictModel):
    variant_id: str
    content_hash: str
    checks: list[CheckResult]
    integrity: float | None
    status: Literal["INCOMPLETE", "PASS", "BLOCKED"]
