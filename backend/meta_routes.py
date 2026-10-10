import hmac

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse, Response

from backend.intent_rules import domain_error
from backend.meta_models import MetaConfirm, MetaOperation, MetaPreview, MetaStatus, Platform

router = APIRouter(prefix="/api", tags=["optional owner-confirmed Meta delivery"])


@router.get("/meta/status", response_model=MetaStatus)
async def status(request: Request):
    return request.app.state.meta.status()


@router.post("/meta/connections/{platform}/check")
async def connection(platform: Platform, request: Request):
    request.app.state.meta.owner(request)
    return await request.app.state.meta.check_connection(platform)


@router.post("/campaigns/{campaign_id}/meta/preview", response_model=MetaOperation)
async def preview(campaign_id: str, body: MetaPreview, request: Request):
    service = request.app.state.meta
    service.owner(request)
    return service.preview(campaign_id, body)


@router.get("/campaigns/{campaign_id}/meta", response_model=list[MetaOperation])
async def operations(campaign_id: str, request: Request):
    service = request.app.state.meta
    service.owner(request)
    request.app.state.work.campaigns.repo.get(campaign_id)
    return [
        service.public(service.load(row[0]))
        for row in service.db.execute(
            "SELECT id FROM meta_operations WHERE campaign_id=? ORDER BY rowid DESC LIMIT 50",
            (campaign_id,),
        ).fetchall()
    ]


@router.post(
    "/campaigns/{campaign_id}/meta/{operation_id}/confirm",
    response_model=MetaOperation,
    status_code=202,
)
async def confirm(campaign_id: str, operation_id: str, body: MetaConfirm, request: Request):
    service = request.app.state.meta
    service.owner(request)
    return service.confirm(campaign_id, operation_id, body)


@router.get("/campaigns/{campaign_id}/meta/{operation_id}/preview-image")
async def preview_image(campaign_id: str, operation_id: str, request: Request):
    service = request.app.state.meta
    service.owner(request)
    raw, mime = service.revalidate(service.load(operation_id, campaign_id))
    if not raw:
        raise domain_error("META_NOT_FOUND", "This delivery has no image")
    return Response(raw, media_type=mime, headers={"Cache-Control": "no-store"})


@router.post("/campaigns/{campaign_id}/meta/{operation_id}/cancel", response_model=MetaOperation)
async def cancel(campaign_id: str, operation_id: str, request: Request):
    service = request.app.state.meta
    service.owner(request)
    saved = service.load(operation_id, campaign_id)
    service.cancel(operation_id)
    if saved["operation"]["job_id"]:
        await request.app.state.work.cancel(saved["operation"]["job_id"])
    return service.public(service.load(operation_id))


@router.get("/meta/media/{token}")
async def media(token: str, request: Request):
    if len(token) > 100:
        raise domain_error("META_NOT_FOUND", "Delivery media grant is unavailable")
    raw, mime = request.app.state.meta.read_media(token)
    return Response(
        raw,
        media_type=mime,
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.post("/campaigns/{campaign_id}/meta/{operation_id}/reconcile", response_model=MetaOperation)
async def reconcile(campaign_id: str, operation_id: str, request: Request):
    service = request.app.state.meta
    service.owner(request)
    return await service.reconcile(campaign_id, operation_id)


@router.get("/meta/webhook")
async def verify_webhook(request: Request):
    settings = request.app.state.settings
    expected = settings.meta_webhook_verify_token.get_secret_value()
    if (
        not settings.meta_enabled
        or not expected
        or request.query_params.get("hub.mode") != "subscribe"
        or not hmac.compare_digest(expected, request.query_params.get("hub.verify_token", ""))
    ):
        raise domain_error("META_SIGNATURE", "Webhook verification failed")
    challenge = request.query_params.get("hub.challenge", "")
    if not challenge.isdigit() or len(challenge) > 100:
        raise domain_error("META_INVALID", "Webhook challenge is invalid")
    return PlainTextResponse(challenge)


@router.post("/meta/webhook")
async def webhook(request: Request):
    if not request.app.state.settings.meta_enabled:
        raise domain_error("META_DISABLED", "Meta delivery is disabled")
    # Limit while streaming, rather than allocate an unbounded request body.
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 256 * 1024:
            raise domain_error("META_INVALID", "Webhook exceeds the byte limit")
    return request.app.state.meta.webhook(bytes(body), request.headers.get("X-Hub-Signature-256"))
