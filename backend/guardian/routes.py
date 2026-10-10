from fastapi import APIRouter, Request

from backend.contracts import ErrorBody
from backend.guardian.report import CheckRequest, GuardianReport
from backend.guardian.rules import check
from backend.repository import CampaignRepository

router = APIRouter(prefix="/api/guardian", tags=["guardian"])


@router.post(
    "/check",
    response_model=GuardianReport,
    responses={code: {"model": ErrorBody} for code in [404, 409, 422]},
)
async def guardian_check(body: CheckRequest, request: Request):
    campaign = CampaignRepository(request.app.state.store).get(body.campaign_id)
    return check(campaign, body)
