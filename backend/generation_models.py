"""B3.1 strategy, batched-copy and persisted matrix contracts."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from backend.contracts import StrictModel
from backend.guardian.report import GuardianReport
from backend.schemas import (
    Lang,
    NeedsInput,
    RevisionRequest,
    SlotKey,
    TemplateContent,
    VariantContract,
)

SocialChannel = Literal["instagram", "whatsapp", "facebook"]
Segment = Literal["students", "families", "professionals", "everyone"]
Motivation = Literal["connection", "pause", "routine", "value", "focus"]
Angle = Literal["shared_pause", "personal_ritual", "catch_up", "study_reset", "unwind"]
Tone = Literal["warm", "playful", "calm", "direct", "refined"]


class AudienceProposal(StrictModel):
    segment: Segment
    motivation: Motivation
    angle: Angle
    tone: Tone
    preferred_channel: SocialChannel


class PersonaProposal(StrictModel):
    audience_index: int = Field(ge=0, le=2)
    priority: Motivation
    reading_style: Literal["quick_scan", "detail_reader", "visual_first"]
    decision_style: Literal["spontaneous", "planner", "cautious"]


class StrategySuccess(StrictModel):
    status: Literal["success"] = "success"
    audiences: list[AudienceProposal] = Field(min_length=3, max_length=3)
    personas: list[PersonaProposal] = Field(min_length=5, max_length=5)
    message_hierarchy: list[SlotKey] = Field(min_length=3, max_length=12)
    hero_index: int = Field(ge=0, le=2)

    @model_validator(mode="after")
    def differentiated(self):
        if len({a.angle for a in self.audiences}) != 3:
            raise ValueError("Three distinct communication angles required")
        if len({a.motivation for a in self.audiences}) != 3:
            raise ValueError("Three distinct motivations required")
        if len({p.model_dump_json() for p in self.personas}) != 5:
            raise ValueError("Five distinct persona profiles required")
        if {p.audience_index for p in self.personas} != {0, 1, 2}:
            raise ValueError("Personas must cover all audiences")
        if len(set(self.message_hierarchy)) != len(self.message_hierarchy):
            raise ValueError("Duplicate hierarchy slots")
        return self


class GenerationFailure(StrictModel):
    status: Literal["error"]
    reason: Literal["unable_to_plan", "unable_to_write", "unsupported_language"]


class StrategyResult(StrictModel):
    result: Annotated[
        StrategySuccess | NeedsInput | GenerationFailure, Field(discriminator="status")
    ]


class AudienceStrategy(AudienceProposal):
    id: str
    name: str
    eligibility_fact_version: int


class PersonaProfile(PersonaProposal):
    id: str
    audience_id: str
    hypothetical: Literal[True] = True


class StrategyPlan(StrictModel):
    id: str
    campaign_id: str
    campaign_revision: int
    dependency_hash: str
    audiences: list[AudienceStrategy]
    personas: list[PersonaProfile]
    message_hierarchy: list[SlotKey]
    hero_audience_id: str
    mode: Literal["live", "mock", "cached"]
    prompt_version: Literal["b3.1"] = "b3.1"
    hypothetical: Literal[True] = True
    notices: list[str]


class CopyEntry(StrictModel):
    audience_id: str = Field(min_length=1, max_length=100)
    channel: SocialChannel
    template: TemplateContent

    @model_validator(mode="after")
    def bounded(self):
        from backend.guardian.slots import fields

        if (
            len(self.template.hashtags) > 30
            or sum(map(len, fields(self.template).values())) > 12000
        ):
            raise ValueError("Copy entry exceeds budget")
        return self


class CopySuccess(StrictModel):
    status: Literal["success"] = "success"
    language: Lang
    entries: list[CopyEntry] = Field(max_length=9)


class CopyResult(StrictModel):
    result: Annotated[CopySuccess | NeedsInput | GenerationFailure, Field(discriminator="status")]


class GenerateRequest(RevisionRequest):
    strategy_id: str = Field(min_length=1, max_length=100)
    idempotency_key: str = Field(min_length=8, max_length=128)
    audience_ids: list[str] = Field(min_length=1, max_length=3)
    languages: list[Lang] = Field(min_length=1, max_length=3)
    channels: list[SocialChannel] = Field(min_length=1, max_length=3)
    retry_source_run_id: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def unique(self):
        for selection in [self.audience_ids, self.languages, self.channels]:
            if len(selection) != len(set(selection)):
                raise ValueError("Duplicate selection")
        return self


class BaselineVariant(VariantContract):
    report: GuardianReport
    mode: Literal["live", "mock", "cached"]
    baseline: Literal[True] = True


class CopyAttempt(StrictModel):
    attempt: int
    reasons: list[str]


class MatrixCell(StrictModel):
    audience_id: str
    language: Lang
    channel: SocialChannel
    state: Literal["queued", "running", "ready", "blocked", "stale"] = "queued"
    variant: BaselineVariant | None = None
    reasons: list[str] = Field(default_factory=list)
    attempts: list[CopyAttempt] = Field(default_factory=list)


class GenerationRun(StrictModel):
    id: str
    campaign_id: str
    campaign_revision: int
    strategy_id: str
    mode: Literal["live", "mock", "cached"]
    status: Literal[
        "queued", "running", "completed", "partial", "failed", "stale", "interrupted", "cancelled"
    ]
    request: GenerateRequest
    cells: list[MatrixCell]
    calls_used: int = 0
    error_code: str | None = None
    created_at: str
    updated_at: str


class MatrixSnapshot(StrictModel):
    campaign_id: str
    campaign_revision: int
    strategy: StrategyPlan | None
    run: GenerationRun | None
