"""Owner planning only: no timer jobs, inference, sending or automatic approval."""

import re
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Query, Request
from pydantic import Field, field_validator, model_validator

from backend.contracts import StrictModel
from backend.errors import ProviderError
from backend.intent_rules import INDIA, digest, domain_error, today
from backend.repository import CampaignRepository
from backend.schemas import BrandKit, Campaign, CampaignCreate


class PlanDetails(StrictModel):
    title: str = Field(min_length=1, max_length=120)
    brief: str = Field(default="", max_length=2000)
    platform: str = Field(pattern=r"^(instagram|facebook|whatsapp)$")
    planned_for: str
    timezone: str = Field(default="Asia/Kolkata", pattern=r"^Asia/Kolkata$")
    campaign_id: str | None = Field(default=None, max_length=100)
    campaign_revision: int | None = Field(default=None, ge=1)
    item_ids: list[str] = Field(default_factory=list, max_length=10)
    source_campaign_id: str | None = Field(default=None, max_length=100)

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value):
        if not value.strip():
            raise ValueError("Title cannot be blank")
        return value.strip()

    @field_validator("planned_for")
    @classmethod
    def local_time(cls, value):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", value):
            raise ValueError("Use a local date and time")
        parsed = datetime.fromisoformat(value)
        if not 2020 <= parsed.year <= 2100:
            raise ValueError("Date is outside the planning range")
        return value

    @model_validator(mode="after")
    def selection(self):
        if len(set(self.item_ids)) != len(self.item_ids):
            raise ValueError("Select each item once")
        if self.item_ids and (not self.campaign_id or not self.campaign_revision):
            raise ValueError("Approved selections require a campaign and revision")
        if self.campaign_revision is not None and not self.campaign_id:
            raise ValueError("Revision requires a campaign")
        return self


class CreatePlan(PlanDetails):
    idempotency_key: str = Field(min_length=8, max_length=128)


class UpdatePlan(PlanDetails):
    expected_version: int = Field(ge=1)


class Plan(PlanDetails):
    id: str
    version: int
    status: str = Field(default="planned", pattern=r"^(planned|cancelled|owner_posted)$")


class PlanAction(StrictModel):
    expected_version: int = Field(ge=1)


class FinishPlan(PlanAction):
    owner_confirms_manual_post: bool


class PlanView(Plan):
    readiness: str
    reasons: list[str]
    due: bool


class CampaignChoice(StrictModel):
    id: str
    label: str
    revision: int
    status: str
    mode: str


class PlanningSnapshot(StrictModel):
    now: str
    timezone: str = "Asia/Kolkata"
    plans: list[PlanView]
    campaigns: list[CampaignChoice]


class Planner:
    def __init__(self, app, clock=None):
        self.app = app
        self.db = app.state.store.connection
        self.campaigns = CampaignRepository(app.state.store)
        self.clock = clock or (lambda: datetime.now(INDIA))

    def get(self, plan_id):
        row = self.db.execute(
            "SELECT payload FROM campaign_plans WHERE id=?", (plan_id,)
        ).fetchone()
        if not row:
            raise domain_error("DELIVERY_NOT_FOUND", "Plan not found")
        return Plan.model_validate_json(row[0])

    def validate_refs(self, body):
        if body.source_campaign_id:
            self.campaigns.get(body.source_campaign_id)
        if body.campaign_id:
            campaign = self.campaigns.get(body.campaign_id)
            if body.campaign_revision and campaign.revision != body.campaign_revision:
                raise domain_error(
                    "REVISION_CONFLICT", "Campaign changed. Review its current output."
                )
            for item_id in body.item_ids:
                item = self.app.state.changes.ledger.raw_item(item_id)
                if item.campaign_id != body.campaign_id or (
                    item.variant.channel != body.platform
                    and not (item.kind == "poster" and item.variant.channel == "poster")
                ):
                    raise domain_error(
                        "APPROVAL_INVALID", "Selection must belong to this campaign/platform"
                    )

    def write(self, plan):
        self.db.execute(
            "UPDATE campaign_plans SET version=?,payload=? WHERE id=?",
            (plan.version, plan.model_dump_json(), plan.id),
        )

    def create(self, body):
        values = body.model_dump(exclude={"idempotency_key"})
        hashed = digest(values)
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            row = self.db.execute(
                "SELECT id,create_hash FROM campaign_plans WHERE create_key=?",
                (body.idempotency_key,),
            ).fetchone()
            if row:
                if row[1] != hashed:
                    raise domain_error(
                        "IDEMPOTENCY_CONFLICT", "This save key belongs to another plan"
                    )
                return self.get(row[0])
            self.validate_refs(body)
            plan = Plan(**values, id=uuid4().hex, version=1)
            self.db.execute(
                "INSERT INTO campaign_plans VALUES(?,?,?,?,?)",
                (plan.id, plan.version, body.idempotency_key, hashed, plan.model_dump_json()),
            )
            return plan

    def checked(self, plan_id, version):
        plan = self.get(plan_id)
        if plan.version != version:
            raise domain_error("REVISION_CONFLICT", "Plan changed. Reload before editing.")
        if plan.status != "planned":
            raise domain_error("APPROVAL_INVALID", "This plan is closed; create another plan")
        return plan

    def update(self, plan_id, body):
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            current = self.checked(plan_id, body.expected_version)
            self.validate_refs(body)
            updated = Plan(
                **body.model_dump(exclude={"expected_version"}),
                id=current.id,
                version=current.version + 1,
                status=current.status,
            )
            self.write(updated)
            return updated

    def view(self, plan):
        readiness, reasons = "brief_only", []
        if plan.campaign_id:
            campaign = self.campaigns.get(plan.campaign_id)
            readiness = "review_required"
            if plan.campaign_revision and campaign.revision != plan.campaign_revision:
                readiness, reasons = (
                    "stale",
                    ["Linked revision changed; approve and select current output."],
                )
            elif plan.item_ids:
                try:
                    self.app.state.approvals.export(
                        campaign.id,
                        campaign.revision,
                        plan.item_ids,
                        saved_view=campaign.mode == "cached",
                        transaction_owned=self.db.in_transaction,
                    )
                    readiness = "ready"
                except ProviderError as exc:
                    reasons = [exc.body.message]
            else:
                reasons = [
                    "Review the linked campaign, then add its approved selection from export."
                ]
            dates = next((f.canonical for f in campaign.facts if f.key == "DATES"), None)
            if dates and plan.planned_for[:10] > dates.end:
                readiness = "review_required" if readiness == "ready" else readiness
                reasons.append("Planned posting is after the offer ends. Review the timing.")
        return PlanView(
            **plan.model_dump(),
            readiness=readiness,
            reasons=reasons,
            due=plan.status == "planned"
            and datetime.fromisoformat(plan.planned_for).replace(tzinfo=INDIA) <= self.clock(),
        )

    def snapshot(self, month):
        plans = [
            Plan.model_validate_json(row[0])
            for row in self.db.execute(
                "SELECT payload FROM campaign_plans WHERE json_extract(payload,'$.planned_for') "
                "LIKE ? ORDER BY json_extract(payload,'$.planned_for') LIMIT 200",
                (month + "-%",),
            )
        ]
        campaigns = []
        for row in self.db.execute("SELECT payload FROM campaigns ORDER BY rowid DESC LIMIT 100"):
            c = Campaign.model_validate_json(row[0])
            name = next((f.canonical for f in c.facts if f.key == "CAFE"), None)
            campaigns.append(
                CampaignChoice(
                    id=c.id,
                    label=name.value if name else "Unnamed draft",
                    revision=c.revision,
                    status=c.status,
                    mode=c.mode,
                )
            )
        return PlanningSnapshot(
            now=self.clock().isoformat(), plans=[self.view(p) for p in plans], campaigns=campaigns
        )

    def start(self, plan_id, body):
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            plan = self.get(plan_id)
            if plan.status != "planned":
                raise domain_error("APPROVAL_INVALID", "This plan is closed")
            if plan.campaign_id:
                return self.campaigns.get(plan.campaign_id)
            plan = self.checked(plan_id, body.expected_version)
            config = self.app.state.settings
            source = (
                self.campaigns.get(plan.source_campaign_id) if plan.source_campaign_id else None
            )
            campaign = self.campaigns.create(
                CampaignCreate(
                    languages=source.languages if source else ["en"], channels=[plan.platform]
                ),
                config.inference_mode,
                today(config.today_override).isoformat(),
                bool(config.today_override),
                transaction_owned=True,
            )
            campaign.transcript = plan.brief
            if source:
                campaign.brand = BrandKit(
                    tone=source.brand.tone, theme=source.brand.theme, colors=source.brand.colors
                )
            self.db.execute(
                "UPDATE campaigns SET payload=? WHERE id=?",
                (campaign.model_dump_json(), campaign.id),
            )
            self.db.execute(
                "UPDATE brand_kits SET payload=? WHERE campaign_id=? AND version=1",
                (campaign.brand.model_dump_json(), campaign.id),
            )
            plan.campaign_id, plan.version = campaign.id, plan.version + 1
            self.write(plan)
            return campaign

    def finish(self, plan_id, body, cancelled=False):
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            plan = self.get(plan_id)
            target = "cancelled" if cancelled else "owner_posted"
            if plan.status == target:
                return plan
            plan = self.checked(plan_id, body.expected_version)
            if not cancelled and (
                not body.owner_confirms_manual_post or self.view(plan).readiness != "ready"
            ):
                raise domain_error(
                    "APPROVAL_INVALID", "Confirm manual posting of current approved output first"
                )
            plan.status, plan.version = target, plan.version + 1
            self.write(plan)
            return plan


router = APIRouter(prefix="/api/plans", tags=["owner content planning"])


@router.get("", response_model=PlanningSnapshot)
async def list_plans(
    request: Request, month: str = Query(pattern=r"^(20\d{2}|2100)-(0[1-9]|1[0-2])$")
):
    return Planner(request.app).snapshot(month)


@router.post("", response_model=Plan, status_code=201)
async def create_plan(body: CreatePlan, request: Request):
    return Planner(request.app).create(body)


@router.put("/{plan_id}", response_model=Plan)
async def update_plan(plan_id: str, body: UpdatePlan, request: Request):
    return Planner(request.app).update(plan_id, body)


@router.post("/{plan_id}/start", response_model=Campaign)
async def start_plan(plan_id: str, body: PlanAction, request: Request):
    return Planner(request.app).start(plan_id, body)


@router.post("/{plan_id}/cancel", response_model=Plan)
async def cancel_plan(plan_id: str, body: PlanAction, request: Request):
    return Planner(request.app).finish(plan_id, body, cancelled=True)


@router.post("/{plan_id}/posted", response_model=Plan)
async def posted_plan(plan_id: str, body: FinishPlan, request: Request):
    return Planner(request.app).finish(plan_id, body)
