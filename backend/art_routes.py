from typing import Literal

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, Response

from backend.art_context import PUBLIC, font_manifest
from backend.art_models import (
    ArtSnapshot,
    Background,
    BackgroundRequest,
    PosterArtifact,
    RenderRequest,
)
from backend.art_storage import sha
from backend.intent_rules import domain_error

router = APIRouter(prefix="/api", tags=["art"])


@router.get("/backgrounds/{background_id}/unapproved.png")
async def unapproved_background(background_id: str, request: Request):
    service = request.app.state.art
    background = service.repo.background(background_id)
    if background.status != "blocked" or "VISION_UNSUPPORTED" not in background.reasons:
        raise domain_error(
            "ART_BLOCKED", "Only images pending unavailable visual QA use this preview"
        )
    raw = service.storage.read(background.sha256)
    return Response(
        raw,
        media_type="image/png",
        headers={
            "X-Artifact-Approval": "blocked",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
            "Content-Disposition": "inline; filename=unapproved-image.png",
        },
    )


@router.post("/campaigns/{campaign_id}/backgrounds", response_model=Background)
async def background(campaign_id: str, body: BackgroundRequest, request: Request):
    return await request.app.state.art.background(campaign_id, body)


@router.post("/campaigns/{campaign_id}/assets/render", response_model=PosterArtifact)
async def render(campaign_id: str, body: RenderRequest, request: Request):
    return await request.app.state.art.render(campaign_id, body)


@router.get("/campaigns/{campaign_id}/assets", response_model=ArtSnapshot)
async def assets(campaign_id: str, request: Request):
    return request.app.state.art.repo.snapshot(campaign_id)


@router.post("/campaigns/{campaign_id}/logos", response_model=str)
async def logo(
    campaign_id: str,
    request: Request,
    expected_revision: int = Query(ge=1),
    owner_approves_logo: bool = Query(),
):
    if not owner_approves_logo:
        raise domain_error("ART_BLOCKED", "Owner review of the PNG logo is required")
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 2 * 1024 * 1024:
            raise domain_error("ART_INVALID", "Logo exceeds 2MB")
    return await request.app.state.art.upload_logo(
        campaign_id, expected_revision, bytes(raw), request.headers.get("content-type", "")
    )


@router.get("/assets/{asset_id}")
async def asset(asset_id: str, request: Request):
    raw = request.app.state.art.bytes(asset_id)
    return Response(
        raw,
        media_type="image/png",
        headers={
            "X-Content-Type-Options": "nosniff",
            "ETag": f'"{sha(raw)}"',
            "Cache-Control": "no-store",
            "Content-Disposition": f'inline; filename="draft-{sha(raw)}.png"',
            "X-Artifact-Approval": "pending",
        },
    )


@router.get("/assets/{asset_id}/record", response_model=PosterArtifact)
async def record(asset_id: str, request: Request):
    return request.app.state.art.repo.poster(asset_id)


@router.get("/render/fonts/{filename}")
async def font(filename: Literal["NotoSans.ttf", "NotoSansKannada.ttf"]):
    font_manifest()
    return FileResponse(
        PUBLIC / "fonts" / filename,
        media_type="font/ttf",
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.get("/render/canvas.js")
async def canvas():
    return FileResponse(PUBLIC / "renderer/canvas.js", media_type="application/javascript")


@router.get("/render/worker", response_class=HTMLResponse)
async def worker():
    return HTMLResponse(
        '<!doctype html><html><head><meta charset="utf-8">'
        '<script src="/api/render/canvas.js" defer></script></head>'
        "<body></body></html>",
        headers={
            "Content-Security-Policy": "default-src 'none'; script-src 'self'; img-src 'self'; "
            "font-src 'self'; connect-src 'self'"
        },
    )
