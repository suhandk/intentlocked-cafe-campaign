from fastapi import APIRouter, Request

from backend.generation_models import GenerateRequest, GenerationRun, MatrixSnapshot, StrategyPlan
from backend.schemas import RevisionRequest

router = APIRouter(prefix="/api", tags=["generation"])


@router.post("/campaigns/{campaign_id}/strategy", response_model=StrategyPlan)
async def strategy(campaign_id: str, body: RevisionRequest, request: Request):
    return await request.app.state.generation.strategy(campaign_id, body.expected_revision)


@router.post("/campaigns/{campaign_id}/generate", response_model=GenerationRun, status_code=202)
async def generate(campaign_id: str, body: GenerateRequest, request: Request):
    return request.app.state.generation.start(campaign_id, body)


@router.get("/campaigns/{campaign_id}/matrix", response_model=MatrixSnapshot)
async def matrix(campaign_id: str, request: Request):
    return request.app.state.generation.repo.matrix(campaign_id)


@router.get("/jobs/{run_id}", response_model=GenerationRun)
async def job(run_id: str, request: Request):
    service = request.app.state.generation
    run = service.repo.get(run_id)
    current = service.repo.campaigns.get(run.campaign_id)
    if current.revision != run.campaign_revision and run.status != "stale":
        service.repo.stop(run_id, "stale", "REVISION_CONFLICT")
        run = service.repo.get(run_id)
    return run
