"""Dependency-scoped immutable output lineage and transaction-owned publication."""

import json
from uuid import uuid4

from backend.art_context import LAYOUT, font_manifest, renderer_hash
from backend.art_repository import ArtRepository
from backend.art_storage import sha
from backend.contracts import utc_now
from backend.delivery_models import DeliveryItem, Proposal, Version
from backend.generation_models import BaselineVariant
from backend.generation_repository import GenerationRepository
from backend.guardian.policy import CONDITIONS, VERSION
from backend.guardian.report import CheckRequest
from backend.guardian.rules import check
from backend.intent_rules import digest, domain_error
from backend.repository import CampaignRepository
from backend.schemas import Campaign


def text_bytes(fields):
    return "\n".join(v for v in fields.values() if v).encode("utf-8")


def item_hash(item):
    return digest(
        item.model_dump(
            exclude={
                "snapshot_hash",
                "status",
                "audit_id",
                "audit_status",
                "approval_id",
                "warnings",
                "audit_findings",
                "approval_blockers",
            }
        )
    )


def fingerprint(campaign, item):
    keys = set(item.variant.slots_used) | CONDITIONS | {"ELIGIBILITY"}
    return digest(
        {
            "facts": {
                f.key: {
                    "canonical": f.canonical.model_dump() if f.canonical else None,
                    "surface": f.surface[item.variant.language].model_dump()
                    if item.variant.language in f.surface
                    else None,
                }
                for f in campaign.facts
                if f.key in keys
            },
            "audience": item.audience,
            "policy": VERSION,
            "must_say": campaign.brand.must_say,
            "must_not_say": campaign.brand.must_not_say,
            "visual": {
                "colors": campaign.brand.colors,
                "theme": campaign.brand.theme,
                "font": font_manifest(),
                "renderer": renderer_hash(),
                "layout": digest(LAYOUT),
            }
            if item.kind == "poster"
            else None,
        }
    )


class Ledger:
    def __init__(self, store):
        self.store, self.db = store, store.connection
        self.campaigns, self.generation, self.art = (
            CampaignRepository(store),
            GenerationRepository(store),
            ArtRepository(store),
        )

    def locked(self, campaign_id, revision):
        return self.generation.locked(campaign_id, revision)

    def remember(self, campaign):
        self.db.execute(
            "INSERT OR IGNORE INTO campaign_versions VALUES(?,?,?)",
            (campaign.id, campaign.revision, campaign.model_dump_json()),
        )

    def event(self, campaign, event, decision, invalidated=None, preserved=None):
        payload = {
            "timestamp": utc_now(),
            "event": event,
            "decision": decision,
            "invalidated_ids": invalidated or [],
            "preserved_ids": preserved or [],
        }
        self.db.execute(
            "INSERT INTO ledger_events(campaign_id,revision,payload) VALUES(?,?,?)",
            (campaign.id, campaign.revision, json.dumps(payload)),
        )

    def raw_item(self, item_id):
        row = self.db.execute(
            "SELECT payload FROM delivery_items WHERE id=?", (item_id,)
        ).fetchone()
        if not row:
            raise domain_error("DELIVERY_NOT_FOUND", "Delivery item not found")
        return DeliveryItem.model_validate_json(row[0])

    def insert(self, item, revision, state="pending"):
        item.snapshot_hash = item_hash(item)
        self.db.execute(
            "INSERT OR IGNORE INTO delivery_items VALUES(?,?,?)",
            (item.id, item.campaign_id, item.model_dump_json()),
        )
        self.db.execute(
            "INSERT OR IGNORE INTO delivery_links VALUES(?,?,?,?)",
            (item.campaign_id, revision, item.id, state),
        )

    def active(self, campaign):
        output = []
        for item_id, state in self.db.execute(
            "SELECT item_id,state FROM delivery_links WHERE campaign_id=? AND revision=?",
            (campaign.id, campaign.revision),
        ):
            item = self.raw_item(item_id)
            item.status = state
            audit = self.db.execute(
                "SELECT audit_id FROM delivery_audits WHERE item_id=?", (item_id,)
            ).fetchone()
            approved = self.db.execute(
                "SELECT approval_id FROM item_approvals WHERE campaign_id=? AND "
                "revision=? AND item_id=?",
                (campaign.id, campaign.revision, item_id),
            ).fetchone()
            item.audit_id = audit[0] if audit else None
            if audit:
                from backend.optimization_models import Audit

                evidence = Audit.model_validate_json(
                    self.db.execute(
                        "SELECT payload FROM semantic_audits WHERE id=?", (audit[0],)
                    ).fetchone()[0]
                )
                item.audit_status = evidence.status
                item.warnings = evidence.warning_ids
                item.audit_findings = evidence.findings
            item.approval_id = approved[0] if approved else None
            if approved and state == "pending":
                item.status = "approved"
            output.append(item)
        return output

    def report(self, campaign, item, template=None):
        if template is None and item.kind == "poster":
            from backend.poster_copy import poster_template

            poster = self.art.poster(item.poster_id)
            if poster.render_input.renderer_version in {
                "canvas-pinterest-b1.0",
                "canvas-commercial-b1.0",
                "canvas-modern-cafe-b1.0",
            }:
                template = poster_template(campaign, item.variant.template)
        return check(
            campaign,
            CheckRequest(
                campaign_id=campaign.id,
                expected_revision=campaign.revision,
                mode="asset",
                language=item.variant.language,
                channel=item.variant.channel,
                template=template or item.variant.template,
                audience=item.audience,
            ),
        )

    def sync(self, campaign):
        """Import server-owned current outputs; no client content/status accepted."""
        existing = {i.id for i in self.active(campaign)}
        matrix = self.generation.matrix(campaign.id)
        variants = (
            [c.variant for c in matrix.run.cells if c.variant and c.state == "ready"]
            if matrix.run and matrix.run.campaign_revision == campaign.revision
            else []
        )
        from backend.optimization_models import OptimizationRun

        for (payload,) in self.db.execute(
            "SELECT payload FROM optimization_runs WHERE campaign_id=? AND status='completed'",
            (campaign.id,),
        ):
            run = OptimizationRun.model_validate_json(payload)
            if run.campaign_revision == campaign.revision:
                variants += [
                    self.art.variant(campaign, g.current_id)
                    for g in run.groups
                    if g.current_id != g.baseline.id
                    and g.final_audit
                    and g.final_audit.status == "PASS"
                ]
        plan = self.generation.plan(campaign.id, campaign.revision)
        for variant in variants:
            if variant.id in existing:
                continue
            audience = next((a.segment for a in plan.audiences if a.id == variant.audience_id), "")
            fields = variant.report.rendered.fields if variant.report.rendered else {}
            raw = text_bytes(fields)
            table = "baseline_variants" if variant.baseline else "optimization"
            if table == "optimization":
                source_id = next(
                    r[0]
                    for r in self.db.execute(
                        "SELECT id FROM optimization_runs WHERE campaign_id=? "
                        "AND status='completed'",
                        (campaign.id,),
                    )
                    if any(
                        g.current_id == variant.id
                        for g in OptimizationRun.model_validate_json(
                            self.db.execute(
                                "SELECT payload FROM optimization_runs WHERE id=?", (r[0],)
                            ).fetchone()[0]
                        ).groups
                    )
                )
                source_hash = digest(
                    json.loads(
                        self.db.execute(
                            "SELECT payload FROM optimization_runs WHERE id=?", (source_id,)
                        ).fetchone()[0]
                    )
                )
            else:
                source_id = variant.id
                source_hash = digest(
                    json.loads(
                        self.db.execute(
                            "SELECT payload FROM baseline_variants WHERE id=?", (variant.id,)
                        ).fetchone()[0]
                    )
                )
            item = DeliveryItem(
                id=variant.id,
                campaign_id=campaign.id,
                created_revision=campaign.revision,
                kind="text",
                variant=variant,
                audience=audience,
                fields=fields,
                dependency_hash="",
                sha256=sha(raw),
                byte_count=len(raw),
                source_table=table,
                source_id=source_id,
                source_hash=source_hash,
                snapshot_hash="",
                mode=variant.mode,
                report=variant.report,
            )
            item.dependency_hash = fingerprint(campaign, item)
            self.insert(item, campaign.revision)
        for (payload,) in self.db.execute(
            "SELECT payload FROM poster_artifacts WHERE campaign_id=?", (campaign.id,)
        ):
            from backend.art_models import PosterArtifact

            poster = PosterArtifact.model_validate_json(payload)
            if (
                poster.id in existing
                or poster.campaign_revision != campaign.revision
                or poster.status != "ready"
            ):
                continue
            variant = self.art.variant(campaign, poster.variant_id)
            audience = (
                next((a.segment for a in plan.audiences if a.id == variant.audience_id), "")
                if plan
                else ""
            )
            item = DeliveryItem(
                id=poster.id,
                campaign_id=campaign.id,
                created_revision=campaign.revision,
                kind="poster",
                variant=variant,
                audience=audience,
                fields=poster.render_input.fields,
                dependency_hash="",
                sha256=poster.sha256,
                byte_count=poster.byte_count,
                source_table="poster_artifacts",
                source_id=poster.id,
                source_hash=digest(json.loads(payload)),
                poster_id=poster.id,
                snapshot_hash="",
                mode=poster.copy_provenance,
                report=poster.guardian,
            )
            item.dependency_hash = fingerprint(campaign, item)
            self.insert(item, campaign.revision)
        self.remember(campaign)
        self.db.commit()
        return self.active(campaign)

    def proposal(self, proposal_id, campaign_id):
        row = self.db.execute(
            "SELECT payload FROM change_proposals WHERE id=? AND campaign_id=?",
            (proposal_id, campaign_id),
        ).fetchone()
        if not row:
            raise domain_error("DELIVERY_NOT_FOUND", "Proposal not found")
        return Proposal.model_validate_json(row[0])

    def save_proposal(self, proposal):
        self.db.execute(
            "UPDATE change_proposals SET payload=? WHERE id=?",
            (proposal.model_dump_json(), proposal.id),
        )

    def duplicate(self, campaign_id, key, request):
        row = self.db.execute(
            "SELECT request_hash,payload FROM owner_actions WHERE campaign_id=? AND action_key=?",
            (campaign_id, key),
        ).fetchone()
        if row and row[0] != digest(request.model_dump()):
            raise domain_error("IDEMPOTENCY_CONFLICT", "Owner action key binds another request")
        return row[1] if row else None

    def action(self, campaign_id, key, request, payload):
        self.db.execute(
            "INSERT INTO owner_actions VALUES(?,?,?,?)",
            (campaign_id, key, digest(request.model_dump()), payload),
        )

    def versions(self, campaign_id):
        current = self.campaigns.get(campaign_id)
        return [
            Version(
                revision=r, current=r == current.revision, campaign=Campaign.model_validate_json(p)
            )
            for r, p in self.db.execute(
                "SELECT revision,payload FROM campaign_versions WHERE campaign_id=? "
                "ORDER BY revision DESC",
                (campaign_id,),
            )
        ]

    def derive(self, campaign, item, template):
        report = self.report(campaign, item, template)
        fields = report.rendered.fields if report.rendered else {}
        variant = BaselineVariant(
            **{
                **item.variant.model_dump(exclude={"report", "mode", "baseline"}),
                "id": uuid4().hex,
                "campaign_revision": campaign.revision,
                "template": template,
                "slots_used": report.rendered.slots_used if report.rendered else [],
                "fact_hash": campaign.fact_hash,
                "dependency_hash": report.dependency_hash,
                "content_hash": report.content_hash,
                "status": "blocked" if report.status == "BLOCKED" else "pending",
                "parent_id": item.variant.id,
                "dependencies": item.variant.dependencies.model_copy(
                    update={
                        "facts": {f.key: f.version for f in campaign.facts},
                        "brand_revision": campaign.brand_revision,
                    }
                ),
                "report": report,
                "mode": campaign.mode,
            }
        )
        raw = text_bytes(fields)
        derived = DeliveryItem(
            id=variant.id,
            campaign_id=campaign.id,
            created_revision=campaign.revision,
            kind="text",
            variant=variant,
            audience=item.audience,
            fields=fields,
            dependency_hash="",
            sha256=sha(raw),
            byte_count=len(raw),
            source_table="derived",
            source_id=variant.id,
            source_hash=digest(variant.model_dump()),
            snapshot_hash="",
            mode=campaign.mode,
            report=report,
        )
        derived.dependency_hash = fingerprint(campaign, derived)
        self.insert(
            derived, campaign.revision, "blocked" if report.status == "BLOCKED" else "pending"
        )
        return derived
