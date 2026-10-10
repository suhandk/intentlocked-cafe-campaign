from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response

from backend.delivery_models import (
    ApprovalRequest,
    AssetApproval,
    ChangeRequest,
    ConfirmRequest,
    DeliverySnapshot,
    ExportPack,
    Proposal,
    PublishRequest,
    RedTeamRequest,
    RedTeamResult,
    Version,
)
from backend.errors import ProviderError
from backend.guardian.report import CheckRequest
from backend.guardian.rules import check
from backend.optimization_models import Audit
from backend.schemas import RevisionRequest, TemplateContent

router = APIRouter(prefix="/api", tags=["changes and owner delivery"])


@router.post("/campaigns/{campaign_id}/change", response_model=Proposal)
async def propose(campaign_id: str, body: ChangeRequest, request: Request):
    return await request.app.state.changes.propose(campaign_id, body)


@router.post("/campaigns/{campaign_id}/change/confirm", response_model=Proposal)
async def confirm(campaign_id: str, body: ConfirmRequest, request: Request):
    return request.app.state.changes.confirm(campaign_id, body)


@router.post("/campaigns/{campaign_id}/change/{proposal_id}/surface", response_model=Proposal)
async def surface(campaign_id: str, proposal_id: str, body: RevisionRequest, request: Request):
    from types import SimpleNamespace

    return await request.app.state.changes.surfaces(
        campaign_id,
        SimpleNamespace(expected_revision=body.expected_revision, proposal_id=proposal_id),
    )


@router.post("/campaigns/{campaign_id}/change/publish", response_model=Proposal)
async def publish(campaign_id: str, body: PublishRequest, request: Request):
    return request.app.state.changes.publish(campaign_id, body)


@router.get("/campaigns/{campaign_id}/delivery", response_model=DeliverySnapshot)
async def delivery(campaign_id: str, request: Request):
    ledger = request.app.state.changes.ledger
    campaign = ledger.campaigns.get(campaign_id)
    items = ledger.sync(campaign)
    for item in items:
        try:
            request.app.state.approvals.verify(campaign, item)
            if item.audit_status == "PASS":
                request.app.state.approvals.readiness(campaign, item)
        except ProviderError as exc:
            item.approval_blockers = [exc.body.message]
    proposals = [
        Proposal.model_validate_json(r[0])
        for r in ledger.db.execute(
            "SELECT payload FROM change_proposals WHERE campaign_id=? ORDER BY rowid DESC",
            (campaign_id,),
        )
    ]
    return DeliverySnapshot(
        campaign_revision=campaign.revision,
        items=items,
        proposals=proposals,
        versions=ledger.versions(campaign_id),
        ledger=events(ledger, campaign_id),
    )


def events(ledger, campaign_id):
    import json

    return [
        {"id": i, "revision": r, **json.loads(p)}
        for i, r, p in ledger.db.execute(
            "SELECT id,revision,payload FROM ledger_events WHERE campaign_id=? ORDER BY id DESC",
            (campaign_id,),
        )
    ]


@router.get("/campaigns/{campaign_id}/ledger", response_model=list[dict])
async def ledger(campaign_id: str, request: Request):
    request.app.state.changes.ledger.campaigns.get(campaign_id)
    return events(request.app.state.changes.ledger, campaign_id)


@router.get("/campaigns/{campaign_id}/versions", response_model=list[Version])
async def versions(campaign_id: str, request: Request):
    return request.app.state.changes.ledger.versions(campaign_id)


@router.post("/campaigns/{campaign_id}/delivery/{item_id}/audit", response_model=Audit)
async def audit(campaign_id: str, item_id: str, body: RevisionRequest, request: Request):
    return await request.app.state.approvals.audit(campaign_id, item_id, body.expected_revision)


@router.post("/campaigns/{campaign_id}/approve", response_model=AssetApproval)
async def approve(campaign_id: str, body: ApprovalRequest, request: Request):
    return request.app.state.approvals.approve(campaign_id, body)


@router.get("/campaigns/{campaign_id}/export", response_model=ExportPack)
async def export(
    campaign_id: str,
    request: Request,
    expected_revision: int = Query(ge=1),
    item_ids: Annotated[list[str] | None, Query()] = None,
    saved_view: bool = Query(default=False),
):
    return request.app.state.approvals.export(campaign_id, expected_revision, item_ids, saved_view)[
        0
    ]


@router.get("/campaigns/{campaign_id}/export.zip")
async def zip_export(
    campaign_id: str,
    request: Request,
    expected_revision: int = Query(ge=1),
    item_ids: Annotated[list[str] | None, Query()] = None,
    saved_view: bool = Query(default=False),
):
    raw = request.app.state.approvals.zip(campaign_id, expected_revision, item_ids, saved_view)
    return Response(
        raw,
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="approved-campaign.zip"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/campaigns/{campaign_id}/export/files/{item_id}")
async def file_export(
    campaign_id: str,
    item_id: str,
    request: Request,
    expected_revision: int = Query(ge=1),
    saved_view: bool = Query(default=False),
):
    pack, files = request.app.state.approvals.export(
        campaign_id, expected_revision, [item_id], saved_view
    )
    entry = pack.files[0]
    return Response(
        files[entry.filename],
        media_type="image/png" if entry.filename.endswith("png") else "text/plain; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{entry.filename}"',
            "Cache-Control": "no-store",
            "X-Artifact-Approval": "approved",
            "ETag": f'"{entry.sha256}"',
        },
    )


@router.post("/campaigns/{campaign_id}/red-team", response_model=RedTeamResult)
async def red_team(campaign_id: str, body: RedTeamRequest, request: Request):
    if body.mode == "instruct_ai":
        proposal = await request.app.state.changes.propose(
            campaign_id,
            ChangeRequest(
                expected_revision=body.expected_revision,
                text=body.text,
                idempotency_key=body.idempotency_key,
            ),
        )
        return RedTeamResult(mode=body.mode, proposal=proposal)
    campaign = request.app.state.changes.ledger.locked(campaign_id, body.expected_revision)
    report = check(
        campaign,
        CheckRequest(
            campaign_id=campaign_id,
            expected_revision=body.expected_revision,
            mode="fragment",
            language=body.language,
            channel="whatsapp",
            template=TemplateContent(headline="", body=body.text, cta="", hashtags=[], alt_text=""),
        ),
    )
    return RedTeamResult(mode=body.mode, report=report)
