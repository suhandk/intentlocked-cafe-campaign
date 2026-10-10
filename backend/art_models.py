"""B4.1 persisted art, server-owned canvas inputs and validated artifact contracts."""

from typing import Literal

from pydantic import Field

from backend.contracts import StrictModel
from backend.future_contracts import AssetContract
from backend.guardian.report import GuardianReport
from backend.schemas import Lang, RevisionRequest

Size = Literal["feed", "square", "story", "landscape"]
SIZES = {
    "feed": (1080, 1350, "1:1"),
    "square": (1080, 1080, "1:1"),
    "story": (1080, 1920, "9:16"),
    "landscape": (1200, 630, "16:9"),
}


class BackgroundQA(StrictModel):
    recommendation: Literal["usable", "reject", "uncertain"]
    image_loaded: bool
    inspected_all_regions: bool
    lettering_or_numbers: bool
    logos_or_watermarks: bool
    products_or_extra_items: bool
    venue_features: bool
    promotional_implications: bool
    evidence: list[str] = Field(min_length=1, max_length=8)


class Background(StrictModel):
    id: str
    campaign_id: str
    art_key: str
    ratio: str
    status: Literal["ready", "blocked"]
    provenance: Literal["live", "mock", "deterministic"]
    source: Literal["provider", "agnes", "deterministic"]
    sha256: str
    byte_count: int
    width: int
    height: int
    captured_at: str
    brief: dict
    qa: BackgroundQA | None
    qa_version: Literal["r9-b4.1", "r9-pinterest-b1.0", "r9-commercial-b1.0"] = "r9-commercial-b1.0"
    reasons: list[str]
    calls_used: int
    run_id: str | None = None
    prompt_version: Literal[
        "t1-b4.1", "t1-pinterest-b1.0", "t1-commercial-b1.0", "t1-modern-cafe-b1.0"
    ] = "t1-modern-cafe-b1.0"
    generation_model: str | None = None
    qa_model: str | None = None


class BackgroundRequest(RevisionRequest):
    size: Size
    source: Literal["provider", "agnes", "deterministic"] = "provider"


class RenderRequest(RevisionRequest):
    variant_id: str = Field(min_length=1, max_length=100)
    size: Size
    background_id: str = Field(min_length=1, max_length=100)
    logo_id: str | None = Field(default=None, min_length=1, max_length=100)


class CanvasInput(StrictModel):
    schema_version: Literal["canvas-input-b4.1"] = "canvas-input-b4.1"
    width: int
    height: int
    size: Size
    language: Lang
    fields: dict[str, str]
    offer_forms: list[str] = Field(default_factory=list)
    background_url: str
    logo_url: str | None
    font_urls: dict[str, str]
    font_hash: str
    renderer_version: str
    renderer_hash: str
    background_hash: str
    logo_hash: str | None
    layout_hash: str


class TextLine(StrictModel):
    field: str
    text: str
    x: float
    y: float
    width: float
    height: float
    font_size: float


class CanvasValidation(StrictModel):
    passed: bool
    reasons: list[str]
    font_loaded: bool
    grapheme_engine: bool
    contrast: float
    offer_area_ratio: float | None = Field(default=None, ge=0, le=1)
    safe_area: list[float]
    lines: list[TextLine]
    logo_bounds: list[float] | None
    renderer_version: str


class PosterArtifact(AssetContract):
    kind: Literal["poster"] = "poster"
    mime_type: Literal["image/png"] = "image/png"
    render_input: CanvasInput
    validation: CanvasValidation
    guardian: GuardianReport
    background_id: str
    logo_id: str | None
    approval_ready: Literal[False] = False
    native_review: Literal["PENDING"] = "PENDING"
    copy_provenance: Literal["live", "mock", "cached"]


class ArtSnapshot(StrictModel):
    backgrounds: list[Background]
    posters: list[PosterArtifact]
    logos: list[str]
