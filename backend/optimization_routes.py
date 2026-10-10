from fastapi import APIRouter, Request

from backend.optimization_models import (
    Audit,
    OptimizationRun,
    OptimizationSnapshot,
    OptimizeRequest,
)
from backend.schemas import RevisionRequest

router = APIRouter(prefix="/api", tags=["optimization"])


@router.post("/campaigns/{campaign_id}/optimize", response_model=OptimizationRun, status_code=202)
async def optimize(campaign_id: str, body: OptimizeRequest, request: Request):
    return request.app.state.optimization.start(campaign_id, body)


@router.get("/campaigns/{campaign_id}/optimization", response_model=OptimizationSnapshot)
async def snapshot(campaign_id: str, request: Request):
    return request.app.state.optimization.repo.snapshot(campaign_id)


@router.get("/optimization/jobs/{run_id}", response_model=OptimizationRun)
async def job(run_id: str, request: Request):
    service = request.app.state.optimization
    run = service.repo.get(run_id)
    current = service.repo.generation.campaigns.get(run.campaign_id)
    if current.revision != run.campaign_revision and run.status != "stale":
        service.repo.stop(run.id, "stale", "REVISION_CONFLICT")
        run = service.repo.get(run.id)
    return run


@router.post("/assets/{asset_id}/audit", response_model=Audit)
async def audit(asset_id: str, body: RevisionRequest, request: Request):
    return await request.app.state.optimization.audit_poster(asset_id, body.expected_revision)


@router.get("/audits/{audit_id}", response_model=Audit)
async def saved_audit(audit_id: str, request: Request):
    return request.app.state.optimization.repo.audit(audit_id)
