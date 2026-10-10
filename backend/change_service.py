"""R8 proposes; owner confirms; code publishes one revision in one transaction."""

import json
from uuid import uuid4

from backend.campaign_service import prompt, validate_forms
from backend.change import edited_template, prepare
from backend.contracts import utc_now
from backend.delivery_models import ChangeParse, Proposal
from backend.generation_context import dependency_hash, eligible_segments
from backend.intent_rules import digest, domain_error, require_ready
from backend.ledger import Ledger, fingerprint
from backend.schemas import FactSurface, SurfaceResult
from backend.surface_policy import surface_constraints


class ChangeService:
    def __init__(self, store, client):
        self.client, self.ledger = client, Ledger(store)

    async def propose(self, campaign_id, request):
        campaign = self.ledger.locked(campaign_id, request.expected_revision)
        row = self.ledger.db.execute(
            "SELECT request_hash,payload FROM change_proposals WHERE campaign_id=? "
            "AND request_key=?",
            (campaign_id, request.idempotency_key),
        ).fetchone()
        if row:
            if row[0] != digest(request.model_dump()):
                raise domain_error(
                    "IDEMPOTENCY_CONFLICT", "Change key already binds another request"
                )
            return Proposal.model_validate_json(row[1])
        items = self.ledger.sync(campaign)
        parsed = await self.client.structured(
            json.dumps(
                {
                    "text": request.text,
                    "facts": [
                        {
                            "key": f.key,
                            "canonical": f.canonical.model_dump() if f.canonical else None,
                        }
                        for f in campaign.facts
                    ],
                    "allowed_targets": [
                        "FACT:<KEY>",
                        "AUDIENCE",
                        "TONE",
                        "THEME",
                        "HOOK",
                        "CTA",
                        "LANGUAGE_MIX",
                        "CHANNELS",
                        "LAYOUT_EMPHASIS",
                    ],
                    "revision": campaign.revision,
                    "scope_ids": request.scope_ids,
                },
                ensure_ascii=False,
            ),
            ChangeParse,
            self.client.budget(calls=3, seconds=90),
            system_prompt=prompt("R8"),
            max_tokens=4096,
        )
        classification, candidate, changed, diffs = prepare(
            campaign, request, parsed, items, fingerprint
        )
        proposal = Proposal(
            id=uuid4().hex,
            campaign_id=campaign_id,
            expected_revision=campaign.revision,
            request=request,
            classification=classification,
            status="rejected" if classification == "rejected" else "proposed",
            operations=parsed.operations,
            diffs=diffs,
            questions=parsed.questions,
            candidate=candidate,
            changed_keys=changed,
            mode=campaign.mode,
            captured_at=utc_now(),
            prompt_hash=digest(prompt("R8")),
        )
        with self.ledger.db:
            self.ledger.locked(campaign_id, request.expected_revision)
            self.ledger.db.execute(
                "INSERT INTO change_proposals VALUES(?,?,?,?,?)",
                (
                    proposal.id,
                    campaign_id,
                    request.idempotency_key,
                    digest(request.model_dump()),
                    proposal.model_dump_json(),
                ),
            )
            self.ledger.event(campaign, "change_proposed", classification)
        return proposal

    def confirm(self, campaign_id, request):
        db = self.ledger.db
        db.execute("BEGIN IMMEDIATE")
        try:
            duplicate = self.ledger.duplicate(campaign_id, request.idempotency_key, request)
            if duplicate:
                db.commit()
                return Proposal.model_validate_json(duplicate)
            campaign = self.ledger.locked(campaign_id, request.expected_revision)
            proposal = self.ledger.proposal(request.proposal_id, campaign_id)
            allowed = (
                {"proposed", "confirmed", "forms_review"}
                if request.decision == "cancel"
                else {"proposed"}
            )
            if proposal.expected_revision != campaign.revision or proposal.status not in allowed:
                raise domain_error("REVISION_CONFLICT", "Proposal is stale or already resolved")
            proposal.status = "cancelled" if request.decision == "cancel" else "confirmed"
            self.ledger.save_proposal(proposal)
            self.ledger.event(
                campaign, "change_" + proposal.status, "No partial operation committed"
            )
            self.ledger.action(
                campaign_id, request.idempotency_key, request, proposal.model_dump_json()
            )
            db.commit()
            return proposal
        except BaseException:
            db.rollback()
            raise

    async def surfaces(self, campaign_id, request):
        campaign = self.ledger.locked(campaign_id, request.expected_revision)
        proposal = self.ledger.proposal(request.proposal_id, campaign_id)
        if (
            proposal.status not in {"confirmed", "forms_review"}
            or proposal.expected_revision != campaign.revision
        ):
            raise domain_error("CHANGE_INVALID", "Confirm the diff before proposing forms")
        candidate = proposal.candidate
        need = [
            f
            for f in candidate.facts
            if f.canonical is not None
            and (not f.surface or set(f.surface) != set(candidate.languages))
        ]
        forms = []
        if need:
            result = (
                await self.client.structured(
                    json.dumps(
                        {
                            "facts": [
                                {"key": f.key, "canonical": f.canonical.model_dump()} for f in need
                            ],
                            "languages": candidate.languages,
                            "surface_constraints": surface_constraints(need, candidate.languages),
                        },
                        ensure_ascii=False,
                    ),
                    SurfaceResult,
                    self.client.budget(calls=3, seconds=90),
                    system_prompt=prompt("R2"),
                    max_tokens=8192,
                    validate=lambda value: validate_forms(
                        candidate.model_copy(update={"facts": need}), value.result.forms
                    )
                    if value.result.status == "success"
                    else None,
                )
            ).result
            if result.status != "success":
                raise domain_error(
                    "FORMS_NOT_READY", "Surface proposal unavailable; owner can retry"
                )
            forms = result.forms
        suggested = {f.key: f for f in forms}
        proposal.forms = [
            suggested.get(f.key, FactSurface(key=f.key, surface=f.surface))
            for f in candidate.facts
            if f.canonical is not None
        ]
        validate_forms(candidate, proposal.forms)
        with self.ledger.db:
            self.ledger.locked(campaign_id, request.expected_revision)
            saved = self.ledger.proposal(proposal.id, campaign_id)
            if saved.status not in {"confirmed", "forms_review"}:
                raise domain_error(
                    "REVISION_CONFLICT", "Proposal was cancelled during form generation"
                )
            proposal.status = "forms_review"
            self.ledger.save_proposal(proposal)
        return proposal

    def publish(self, campaign_id, request):
        db = self.ledger.db
        campaign = self.ledger.campaigns.get(campaign_id)
        self.ledger.sync(campaign)
        db.execute("BEGIN IMMEDIATE")
        try:
            duplicate = self.ledger.duplicate(campaign_id, request.idempotency_key, request)
            if duplicate:
                db.commit()
                return Proposal.model_validate_json(duplicate)
            old = self.ledger.locked(campaign_id, request.expected_revision)
            proposal = self.ledger.proposal(request.proposal_id, campaign_id)
            if proposal.expected_revision != old.revision or proposal.status not in {
                "confirmed",
                "forms_review",
            }:
                raise domain_error("REVISION_CONFLICT", "Proposal is not current and confirmed")
            candidate = proposal.candidate.model_copy(deep=True)
            forms = request.reviewed_forms
            if proposal.changed_keys or candidate.languages != old.languages:
                validate_forms(candidate, forms)
                approved = {f.key: f.surface for f in forms}
                for fact in candidate.facts:
                    if fact.canonical is not None:
                        if (
                            fact.key not in proposal.changed_keys
                            and candidate.languages == old.languages
                            and approved[fact.key] != fact.surface
                        ):
                            raise domain_error(
                                "CHANGE_INVALID",
                                "Unrelated forms changed outside the confirmed diff",
                            )
                        fact.surface = approved[fact.key]
                        previous = next(f for f in old.facts if f.key == fact.key)
                        if fact.surface != previous.surface and fact.version == previous.version:
                            fact.version += 1
                            proposal.changed_keys.append(fact.key)
            elif forms:
                raise domain_error(
                    "CHANGE_INVALID", "Preference-only publication accepts no fact forms"
                )
            stamp = utc_now()
            for fact in candidate.facts:
                if fact.key in proposal.changed_keys:
                    fact.status = "locked" if fact.canonical else "not_specified"
                    fact.approved_at = stamp
                    fact.approval_id = proposal.id
            candidate.revision = old.revision + 1
            candidate.status = "locked"
            candidate.approved_at = stamp
            candidate.fact_hash = digest(
                [
                    {"key": f.key, "canonical": f.canonical.model_dump() if f.canonical else None}
                    for f in candidate.facts
                ]
            )
            require_ready(candidate)
            eligible_segments(candidate)
            if candidate.brand != old.brand:
                candidate.brand_revision = old.brand_revision + 1
                db.execute(
                    "INSERT INTO brand_kits VALUES(?,?,?)",
                    (campaign_id, candidate.brand_revision, candidate.brand.model_dump_json()),
                )
            self.ledger.campaigns.write_facts(candidate, old.facts)
            db.execute(
                "UPDATE campaigns SET revision=?,status=?,payload=? WHERE id=? AND revision=?",
                (
                    candidate.revision,
                    "locked",
                    candidate.model_dump_json(),
                    campaign_id,
                    old.revision,
                ),
            )
            self.ledger.remember(old)
            self.ledger.remember(candidate)
            plan = self.ledger.generation.plan(campaign_id, old.revision)
            if plan and all(a.segment in eligible_segments(candidate) for a in plan.audiences):
                plan = plan.model_copy(deep=True)
                plan.id = uuid4().hex
                plan.campaign_revision = candidate.revision
                plan.dependency_hash = dependency_hash(candidate)
                for audience in plan.audiences:
                    audience.eligibility_fact_version = next(
                        f.version for f in candidate.facts if f.key == "ELIGIBILITY"
                    )
                db.execute(
                    "INSERT INTO strategy_plans VALUES(?,?,?,?)",
                    (plan.id, campaign_id, candidate.revision, plan.model_dump_json()),
                )
            invalidated, preserved = [], []
            derived_templates = {}
            for item in self.ledger.active(old):
                relevant = [
                    d
                    for d in proposal.diffs
                    if item.id in d.affected_ids and not d.target.startswith("FACT:")
                ]
                changed = fingerprint(candidate, item) != item.dependency_hash or bool(relevant)
                if not changed:
                    self.ledger.insert(item, candidate.revision)
                    prior = db.execute(
                        "SELECT approval_id FROM item_approvals WHERE campaign_id=? AND "
                        "revision=? AND item_id=?",
                        (campaign_id, old.revision, item.id),
                    ).fetchone()
                    if prior:
                        db.execute(
                            "INSERT INTO item_approvals VALUES(?,?,?,?)",
                            (campaign_id, candidate.revision, item.id, prior[0]),
                        )
                    preserved.append(item.id)
                    continue
                invalidated.append(item.id)
                structural = any(
                    d.consequence == "regenerate" and item.id in d.affected_ids
                    for d in proposal.diffs
                )
                if item.kind == "poster" or structural:
                    db.execute(
                        "INSERT INTO delivery_links VALUES(?,?,?,?)",
                        (campaign_id, candidate.revision, item.id, "regeneration_required"),
                    )
                if not structural:
                    template = edited_template(item, proposal)
                    template_key = digest([item.variant.id, template.model_dump()])
                    if template_key not in derived_templates:
                        derived_templates[template_key] = self.ledger.derive(
                            candidate, item, template
                        )
            proposal.status = "published"
            proposal.published_revision = candidate.revision
            self.ledger.save_proposal(proposal)
            self.ledger.event(
                candidate,
                "revision_published",
                "Owner diff and forms approved atomically",
                invalidated,
                preserved,
            )
            self.ledger.action(
                campaign_id, request.idempotency_key, request, proposal.model_dump_json()
            )
            db.commit()
            return proposal
        except BaseException:
            db.rollback()
            raise
