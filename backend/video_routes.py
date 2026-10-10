from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from backend.local_video import LocalVideoApproval
from backend.video_service import binary

router = APIRouter(prefix="/api", tags=["optional video drafts"])


@router.get("/video/config")
async def config(request: Request):
    settings = request.app.state.settings
    try:
        binary("ffmpeg")
        binary("ffprobe")
        tools_available = True
    except Exception:
        tools_available = False
    return {
        "model": settings.video_model,
        "enabled": settings.enable_video,
        "mode": settings.inference_mode,
        "price_verified": False,
        "approval_enabled": False,
        "local_enabled": settings.local_video_enabled and tools_available,
        "local_tools_available": tools_available,
    }


@router.get("/campaigns/{campaign_id}/videos")
async def videos(campaign_id: str, request: Request):
    return request.app.state.video.snapshot(campaign_id)


@router.get("/videos/{video_id}/draft.mp4")
async def artifact(video_id: str, request: Request):
    path = request.app.state.video.artifact(video_id)
    return FileResponse(
        path,
        media_type="video/mp4",
        headers={
            "X-Artifact-Approval": "unapproved",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
            "Content-Disposition": 'inline; filename="video-draft.mp4"',
        },
    )


@router.post("/videos/{video_id}/approve")
async def approve(video_id: str, body: LocalVideoApproval, request: Request):
    return request.app.state.video.approve_local(video_id, body)


@router.get("/videos/{video_id}/manifest")
async def manifest(video_id: str, request: Request, saved_view: bool = False):
    return request.app.state.video.local_manifest(video_id, saved_view=saved_view)


@router.get("/videos/{video_id}/approved.mp4")
async def approved(video_id: str, request: Request, saved_view: bool = False):
    service = request.app.state.video
    manifest = service.local_manifest(video_id, saved_view=saved_view)
    return FileResponse(
        service.artifact(video_id),
        media_type="video/mp4",
        headers={
            "X-Artifact-Approval": "approved",
            "X-Artifact-Source": "local_animation",
            "X-Artifact-Mode": manifest["mode"],
            "X-Artifact-Source-Mode": manifest["source_mode"],
            "X-Artifact-SHA256": manifest["sha256"],
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
        filename="approved-poster-animation.mp4",
    )


@router.get("/videos/{video_id}/clips/{index}.mp4")
async def clip(video_id: str, index: int, request: Request):
    return FileResponse(
        request.app.state.video.artifact(video_id, index),
        media_type="video/mp4",
        headers={"X-Artifact-Approval": "unapproved", "Cache-Control": "no-store"},
    )
