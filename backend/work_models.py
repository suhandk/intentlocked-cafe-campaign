from typing import Literal

from pydantic import Field

from backend.contracts import StrictModel
from backend.schemas import RevisionRequest

Kind = Literal[
    "intent",
    "forms",
    "strategy",
    "generate",
    "optimize",
    "background",
    "render",
    "poster_batch",
    "poster_audit",
    "item_audit",
    "change",
    "change_forms",
    "red_team",
    "meta_delivery",
    "video",
    "local_video",
]
Status = Literal[
    "queued", "running", "completed", "partial", "failed", "cancelled", "interrupted", "stale"
]


class WorkRequest(StrictModel):
    kind: Kind
    idempotency_key: str = Field(min_length=8, max_length=128)
    input: dict
    target_id: str | None = Field(default=None, max_length=128)


class WorkRetry(RevisionRequest):
    idempotency_key: str = Field(min_length=8, max_length=128)


class WorkJob(StrictModel):
    id: str
    campaign_id: str
    campaign_revision: int
    kind: Kind
    status: Status
    mode: Literal["mock", "live", "cached"]
    created_at: str
    started_at: str | None = None
    updated_at: str
    deadline: str
    max_calls: int = 48
    max_steps: int = 6
    completed_steps: int = 0
    result: dict | None = None
    error_code: str | None = None
    calls: int = 0
    list_price_estimate_usd: float = 0
    unknown_cost_calls: int = 0
    queue_position: int = 0
    estimated_wait_seconds: float = 0
    elapsed_seconds: float = 0
    provider: str = "kRouter"
    prompt_hashes: dict[str, str] = Field(default_factory=dict)
    cache_hits: list[str] = Field(default_factory=list)
    native_run_id: str | None = None
    input: dict = Field(default_factory=dict)
    target_id: str | None = None
    notices: list[str] = Field(default_factory=list)


class WorkflowEvent(StrictModel):
    id: int
    campaign_id: str
    timestamp: str
    event: str
    message: str
    job_id: str | None = None
    run_id: str | None = None
    revision: int | None = None


class WorkSnapshot(StrictModel):
    jobs: list[WorkJob]
    concurrency_limit: int = 2
    queue_limit: int = 16
    active: int
    queued: int
    mode: Literal["mock", "live", "cached"]
    latest_event_id: int


class PosterBatchInput(StrictModel):
    expected_revision: int = Field(ge=1)
    variant_id: str
    sizes: list[Literal["feed", "square", "story", "landscape"]] = Field(min_length=1, max_length=3)
    source: Literal["provider", "agnes", "deterministic"]
    logo_id: str | None = None
