import asyncio

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import StreamingResponse

from backend.intent_rules import domain_error
from backend.work_models import WorkJob, WorkRequest, WorkRetry, WorkSnapshot

router = APIRouter(prefix="/api", tags=["durable workflow"])


@router.post("/campaigns/{campaign_id}/work", response_model=WorkJob, status_code=202)
async def start(campaign_id: str, body: WorkRequest, request: Request):
    if body.kind == "meta_delivery":
        # Only the separate preview/confirm endpoint can authorize delivery.
        raise domain_error("META_OWNER_REQUIRED", "Use the owner-confirmed delivery endpoint")
    return request.app.state.work.start(campaign_id, body)


@router.get("/campaigns/{campaign_id}/work", response_model=WorkSnapshot)
async def snapshot(campaign_id: str, request: Request):
    return request.app.state.work.snapshot(campaign_id)


@router.get("/work/{job_id}", response_model=WorkJob)
async def job(job_id: str, request: Request):
    saved = request.app.state.work.get(job_id)
    return next(
        (
            j
            for j in request.app.state.work.snapshot(saved.campaign_id, job_id).jobs
            if j.id == job_id
        ),
        saved,
    )


@router.post("/work/{job_id}/cancel", response_model=WorkJob)
async def cancel(job_id: str, request: Request):
    if request.app.state.work.get(job_id).kind == "meta_delivery":
        request.app.state.meta.owner(request)
    return await request.app.state.work.cancel(job_id)


@router.post("/work/{job_id}/retry", response_model=WorkJob, status_code=202)
async def retry(job_id: str, body: WorkRetry, request: Request):
    return request.app.state.work.retry(job_id, body)


@router.get("/stream/{campaign_id}")
async def stream(
    campaign_id: str,
    request: Request,
    after: int = Query(default=0, ge=0),
    last_event_id: str | None = Header(default=None),
):
    service = request.app.state.work
    service.campaigns.repo.get(campaign_id)
    try:
        cursor = max(after, int(last_event_id or 0))
    except ValueError:
        raise domain_error("WORK_INVALID", "Replay cursor must be an integer") from None
    if cursor < 0:
        raise domain_error("WORK_INVALID", "Replay cursor must be nonnegative")

    async def replay():
        nonlocal cursor
        yield "retry: 1500\n\n"
        ticks = 0
        while not await request.is_disconnected():
            events = service.events(campaign_id, cursor)
            for event in events:
                cursor = event.id
                yield f"id: {event.id}\nevent: workflow\ndata: {event.model_dump_json()}\n\n"
            ticks += 1
            if ticks % 10 == 0:
                yield ": heartbeat\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(
        replay(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.get("/campaigns/{campaign_id}/saved-output", response_model=WorkSnapshot)
async def saved(campaign_id: str, request: Request):
    snapshot = request.app.state.work.snapshot(campaign_id)
    if not any(
        j.status in {"completed", "partial"}
        and j.result
        and j.kind in {"generate", "optimize", "poster_batch", "render"}
        for j in snapshot.jobs
    ):
        raise domain_error(
            "SAVED_OUTPUT_MISSING",
            "No captured output exists. Keep the current mode and complete a run first.",
        )
    return snapshot
