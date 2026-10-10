from fastapi import APIRouter, Request

from backend.campaign_service import CampaignService
from backend.contracts import ErrorBody
from backend.intent_rules import today
from backend.schemas import (
    Campaign,
    CampaignCreate,
    DraftRequest,
    IntentRequest,
    LockRequest,
    SurfaceRequest,
)

router = APIRouter(
    prefix="/api/campaigns",
    tags=["campaigns"],
    responses={code: {"model": ErrorBody} for code in [404, 409, 422, 500, 502]},
)


def service(request: Request) -> CampaignService:
    return CampaignService(
        request.app.state.store, request.app.state.client, request.app.state.settings
    )


@router.post("", response_model=Campaign, status_code=201)
async def create(body: CampaignCreate, request: Request):
    settings = request.app.state.settings
    return service(request).repo.create(
        body,
        settings.inference_mode,
        today(settings.today_override).isoformat(),
        bool(settings.today_override),
    )


@router.get("/{campaign_id}", response_model=Campaign)
async def get(campaign_id: str, request: Request):
    return service(request).repo.get(campaign_id)


@router.post("/{campaign_id}/intent", response_model=Campaign)
async def intent(campaign_id: str, body: IntentRequest, request: Request):
    return await service(request).intent(campaign_id, body)


@router.put("/{campaign_id}/facts/draft", response_model=Campaign)
async def draft(campaign_id: str, body: DraftRequest, request: Request):
    return service(request).draft(campaign_id, body)


@router.post("/{campaign_id}/facts/surface", response_model=Campaign)
async def surfaces(campaign_id: str, body: SurfaceRequest, request: Request):
    return await service(request).surfaces(campaign_id, body)


@router.post("/{campaign_id}/facts/lock", response_model=Campaign)
async def lock(campaign_id: str, body: LockRequest, request: Request):
    return service(request).lock(campaign_id, body)
