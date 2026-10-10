"""Secret-bearing requests require direct TLS and never enter the inference queue."""

import io
import zipfile

from fastapi import APIRouter, Request
from fastapi.responses import Response

from backend.website_models import (
    ConnectionInput,
    DraftSave,
    GenerateWebsite,
    ImageUpload,
    PublishInput,
)
from backend.website_service import WebsiteError

router = APIRouter(prefix="/api", tags=["website wizard"])


def service(request):
    return request.app.state.website


def public_bundle(value):
    return {key: item for key, item in value.items() if key not in {"bytes", "html"}}


@router.get("/website/config")
async def config(request: Request):
    settings = request.app.state.settings
    return {
        "providers": ["netlify"],
        "publish_enabled": settings.website_publish_enabled,
        "remember_available": bool(settings.website_token_key.get_secret_value()),
        "design": {
            "provider": "OpenRouter",
            "model": settings.website_model,
            "mode": settings.website_ai_mode.upper(),
            "available": settings.website_ai_mode == "mock"
            or bool(settings.openrouter_api_key.get_secret_value()),
        },
        "permissions_note": "Use a dedicated Netlify account/team with only needed site access. "
        "Personal access tokens may be broader than deploy-only; connection "
        "testing does not verify deploy permission.",
    }


@router.get("/campaigns/{campaign_id}/website")
async def draft(campaign_id: str, request: Request):
    return service(request).draft(campaign_id)


@router.put("/websites/{draft_id}")
async def save(draft_id: str, body: DraftSave, request: Request):
    return service(request).save(draft_id, body)


@router.get("/websites/{draft_id}/offer")
async def offer(draft_id: str, request: Request):
    return service(request).offer(draft_id)


@router.post("/websites/{draft_id}/suggest")
async def suggest(draft_id: str, request: Request):
    return service(request).suggest(draft_id)


@router.post("/websites/{draft_id}/images", status_code=201)
async def images(draft_id: str, body: ImageUpload, request: Request):
    return service(request).upload(draft_id, body)


@router.post("/websites/{draft_id}/generate")
async def generate(draft_id: str, body: GenerateWebsite, request: Request):
    return public_bundle(await service(request).generate_with_ai(draft_id, body))


@router.get("/websites/{draft_id}/bundle")
async def bundle(draft_id: str, request: Request):
    return public_bundle(service(request).bundle(draft_id))


@router.get("/websites/{draft_id}/download.zip")
async def download(draft_id: str, request: Request):
    value = service(request).bundle(draft_id)
    return Response(
        value["bytes"],
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="cafe-website.zip"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "X-Bundle-SHA256": value["sha256"],
        },
    )


@router.get("/websites/{draft_id}/preview/{filename:path}")
async def preview(draft_id: str, filename: str, request: Request):
    value = service(request).bundle(draft_id)
    with zipfile.ZipFile(io.BytesIO(value["bytes"])) as archive:
        if filename not in archive.namelist() or filename == "_headers":
            raise WebsiteError("NOT_FOUND", "Preview file not found", 404)
        raw = archive.read(filename)
    mime = (
        "text/html"
        if filename == "index.html"
        else "text/css"
        if filename == "style.css"
        else "image/png"
    )
    return Response(
        raw,
        media_type=mime,
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; img-src 'self'; style-src 'self'; "
            "base-uri 'none'; frame-ancestors 'self'",
        },
    )


@router.post("/websites/{draft_id}/connection")
async def connection(draft_id: str, body: ConnectionInput, request: Request):
    return await service(request).connect(draft_id, body)


@router.get("/website/token")
async def token_status(request: Request):
    return service(request).remembered()


@router.delete("/website/token")
async def disconnect(request: Request):
    return await service(request).disconnect()


@router.post("/websites/{draft_id}/publish", status_code=202)
async def publish(draft_id: str, body: PublishInput, request: Request):
    return service(request).publish(draft_id, body)


@router.get("/website/jobs/{job_id}")
async def job(job_id: str, request: Request):
    return service(request).job(job_id)
