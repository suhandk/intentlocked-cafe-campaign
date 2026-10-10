from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ErrorBody(StrictModel):
    code: str
    message: str
    details: dict[str, str | int | list[str]] = Field(default_factory=dict)
    trace_id: str
    retryable: bool = False


class Health(StrictModel):
    status: Literal["ok"] = "ok"
    stage: Literal["B7"] = "B7"
    mode: Literal["LIVE", "MOCK", "SAVED DEMO OUTPUT"]
    provider: str = "kRouter"
    text_model: str = "ollama/gpt-oss:120b"
    image_model: str = "nb/nanobanana-flash"
    image_provider: str = "gateway"
    image_configuration_notice: str | None = None
    image_generation_enabled: bool = False
    vision_supported: bool = False
    live_contract: Literal["NOT_TESTED"] = "NOT_TESTED"
    schema_version: Literal["b7.1"] = "b7.1"
    video_enabled: bool


class Usage(StrictModel):
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)


class CallRecord(StrictModel):
    id: str
    trace_id: str
    run_id: str
    work_id: str | None = None
    timestamp: str
    mode: Literal["mock", "live", "cached"]
    model: str
    provider: str | None = None
    transport_endpoint: str | None = None
    operation: str
    attempt: int
    repair: int
    status: str
    sent: bool = True
    http_status: int | None = None
    queue_wait_ms: float
    duration_ms: float
    usage: Usage | None = None
    list_price_estimate_usd: float | None = None
    provider_reported_cost_usd: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class TraceEvent(StrictModel):
    id: int
    trace_id: str
    run_id: str
    timestamp: str
    stage: Literal["B0", "B5"] = "B0"
    campaign_id: str | None = None
    revision: int | None = None
    event: str
    message: str


class Cost(StrictModel):
    currency: Literal["USD"] = "USD"
    calls: int
    mock_calls: int
    known_list_price_estimate: float
    unknown_cost_calls: int
    actual_billing: Literal["unknown"] = "unknown"
    label: str = "List-price estimate; mock calls excluded. Actual billing is unknown."


class SmokeResult(StrictModel):
    message: str = Field(min_length=1, max_length=100)


def utc_now() -> str:
    from datetime import UTC

    return datetime.now(UTC).isoformat()
