"""Owner approval and each export recheck stored truth, audit, dependencies and bytes."""

import io
import json
import zipfile
from urllib.parse import quote
from uuid import uuid4

from backend.art_context import LAYOUT, RENDERER_VERSION, font_manifest, renderer_hash
from backend.art_service import qa_passes, validate_canvas
from backend.art_storage import ArtStorage, sha
from backend.contracts import utc_now
from backend.delivery_models import AssetApproval, ExportFile, ExportPack
from backend.guardian.report import Finding, summarize
from backend.intent_rules import digest, domain_error
from backend.ledger import Ledger, fingerprint, item_hash, text_bytes
from backend.optimization_models import Audit
from backend.optimization_service import OptimizationService
from backend.semantic_audit import compare


class ApprovalService:
    def __init__(self, store, client, optimization=None):
        self.ledger, self.client = Ledger(store), client
        self.optimization = optimization or OptimizationService(store, client)
        self.storage = ArtStorage(client.settings.asset_path)

    def current_item(self, campaign, item_id):
        items = self.ledger.active(campaign)
        item = next((i for i in items if i.id == item_id), None)
        if not item or item.status in {"blocked", "regeneration_required", "historical"}:
            raise domain_error("APPROVAL_INVALID", "Choose a current, complete pending item")
        return item

    def verify(self, campaign, item):
        if (
            item_hash(item) != item.snapshot_hash
            or fingerprint(campaign, item) != item.dependency_hash
        ):
            raise domain_error(
                "APPROVAL_INVALID", "Content or dependency changed; revalidate and approve"
            )
        if (
            item.variant.language not in campaign.languages
            or item.variant.channel not in campaign.channels
        ):
            raise domain_error("APPROVAL_INVALID", "Item language/channel is no longer selected")
        if item.source_table in {"baseline_variants", "poster_artifacts", "optimization"}:
            table = (
                "optimization_runs" if item.source_table == "optimization" else item.source_table
            )
            row = self.ledger.db.execute(
                f"SELECT payload FROM {table} WHERE id=?", (item.source_id,)
            ).fetchone()
            if not row or digest(json.loads(row[0])) != item.source_hash:
                raise domain_error("APPROVAL_INVALID", "Stored source is missing or modified")
        report = self.ledger.report(campaign, item)
        if (
            not report.rendered
            or report.rendered.fields != item.fields
            or report.status == "BLOCKED"
        ):
            raise domain_error("APPROVAL_INVALID", "Guardian blocks current content")
        if item.kind == "poster":
            poster = self.ledger.art.poster(item.poster_id)
            value = poster.render_input
            if (
                poster.status != "ready"
                or poster.sha256 != item.sha256
                or value.fields != item.fields
                or value.font_hash != font_manifest()
                or value.renderer_hash != renderer_hash()
                or value.renderer_version != RENDERER_VERSION
                or value.layout_hash != digest(LAYOUT)
            ):
                raise domain_error(
                    "APPROVAL_INVALID", "Poster bytes, font, renderer or layout changed"
                )
            validate_canvas(value, poster.validation)
            pixel_check = next(c for c in report.checks if c.rule == "G12")
            pixel_check.completed = True
            if pixel_check.passed is None:
                pixel_check.passed = True
            pixel_check.findings += [
                Finding(
                    field="*",
                    source="policy",
                    message="Persisted canvas bounds, font, layout and exact PNG validated",
                )
            ]
            report.status, report.missing_checks, report.warning_ids, report.integrity = summarize(
                report.checks
            )
            background = self.ledger.art.background(poster.background_id)
            if (
                background.status != "ready"
                or background.sha256 != value.background_hash
                or (
                    background.provenance != "deterministic"
                    and (not background.qa or not qa_passes(background.qa))
                )
            ):
                raise domain_error("APPROVAL_INVALID", "Poster background is missing or unchecked")
            self.storage.read(background.sha256)
            if poster.logo_id:
                logo = self.ledger.art.logo(poster.logo_id, campaign.id)
                if logo["sha256"] != value.logo_hash:
                    raise domain_error("APPROVAL_INVALID", "Poster logo changed")
                self.storage.read(logo["sha256"])
            raw = self.storage.read(item.sha256)
        else:
            raw = text_bytes(report.rendered.fields)
        if sha(raw) != item.sha256 or len(raw) != item.byte_count:
            raise domain_error("APPROVAL_INVALID", "Content byte hash changed")
        return report, raw

    async def audit(self, campaign_id, item_id, revision):
        campaign = self.ledger.locked(campaign_id, revision)
        self.ledger.sync(campaign)
        item = self.current_item(campaign, item_id)
        report, _ = self.verify(campaign, item)
        audit = await self.optimization.audit_report(
            campaign,
            report,
            item.variant.language,
            "poster" if item.kind == "poster" else item.variant.channel,
            self.client.budget(calls=3, seconds=90),
            [],
            artifact_hash=item.sha256 if item.kind == "poster" else None,
            poster=self.ledger.art.poster(item.poster_id) if item.kind == "poster" else None,
        )
        with self.ledger.db:
            current = self.ledger.locked(campaign_id, revision)
            self.verify(current, self.current_item(current, item_id))
            self.ledger.db.execute(
                "INSERT INTO delivery_audits VALUES(?,?) ON CONFLICT(item_id) DO "
                "UPDATE SET audit_id=excluded.audit_id",
                (item_id, audit.id),
            )
        return audit

    def readiness(self, campaign, item):
        report, raw = self.verify(campaign, item)
        row = self.ledger.db.execute(
            "SELECT a.payload FROM semantic_audits a JOIN delivery_audits d ON "
            "a.id=d.audit_id WHERE d.item_id=?",
            (item.id,),
        ).fetchone()
        if not row:
            raise domain_error("APPROVAL_INVALID", "Run the blinded customer audit before approval")
        audit = Audit.model_validate_json(row[0])
        if (
            audit.campaign_id != campaign.id
            or audit.content_hash not in {report.content_hash, item.report.content_hash}
            or audit.artifact_hash != (item.sha256 if item.kind == "poster" else None)
            or audit.guardian.rendered is None
            or audit.guardian.rendered.fields != item.fields
        ):
            raise domain_error(
                "APPROVAL_INVALID", "Audit does not bind the current content/artifact"
            )
        result = compare(
            campaign, report, audit.reader, item.variant.language, audit.call, audit.artifact_hash
        )
        if audit.status != "PASS" or result.status != "PASS" or result.guardian.missing_checks:
            raise domain_error("APPROVAL_INVALID", "Required audit/checks are pending or blocked")
        return result, raw

    def approve(self, campaign_id, request):
        campaign = self.ledger.campaigns.get(campaign_id)
        self.ledger.sync(campaign)
        db = self.ledger.db
        db.execute("BEGIN IMMEDIATE")
        try:
            duplicate = self.ledger.duplicate(campaign_id, request.idempotency_key, request)
            if duplicate:
                db.commit()
                return AssetApproval.model_validate_json(duplicate)
            campaign = self.ledger.locked(campaign_id, request.expected_revision)
            if len(set(request.item_ids)) != len(request.item_ids) or set(
                request.observed_hashes
            ) != set(request.item_ids):
                raise domain_error("APPROVAL_INVALID", "Approve each observed item exactly once")
            hashes = {}
            for item_id in request.item_ids:
                item = self.current_item(campaign, item_id)
                audit, _ = self.readiness(campaign, item)
                if request.observed_hashes[item_id] != item.snapshot_hash:
                    raise domain_error("REVISION_CONFLICT", "Owner preview hash changed")
                if not set(audit.warning_ids) <= set(request.acknowledged_warning_ids):
                    raise domain_error(
                        "REVIEW_REQUIRED",
                        "Acknowledge each visible warning",
                        missing=audit.warning_ids,
                    )
                if item.variant.language != "en" and not request.native_review_confirmed:
                    raise domain_error(
                        "REVIEW_REQUIRED", "Confirm native Kannada/Kanglish review before approval"
                    )
                hashes[item_id] = item.snapshot_hash
            approval = AssetApproval(
                id=uuid4().hex,
                campaign_id=campaign_id,
                approved_revision=campaign.revision,
                approved_at=utc_now(),
                item_hashes=hashes,
                acknowledged_warning_ids=request.acknowledged_warning_ids,
                native_review_confirmed=request.native_review_confirmed,
            )
            db.execute(
                "INSERT INTO asset_approvals VALUES(?,?,?)",
                (approval.id, campaign_id, approval.model_dump_json()),
            )
            for item_id in hashes:
                db.execute(
                    "INSERT INTO item_approvals VALUES(?,?,?,?) ON "
                    "CONFLICT(campaign_id,revision,item_id) DO UPDATE SET "
                    "approval_id=excluded.approval_id",
                    (campaign_id, campaign.revision, item_id, approval.id),
                )
            self.ledger.event(
                campaign, "owner_approved", "Exact content, dependencies and bytes approved"
            )
            self.ledger.action(
                campaign_id, request.idempotency_key, request, approval.model_dump_json()
            )
            db.commit()
            return approval
        except BaseException:
            db.rollback()
            raise

    def capture(self, item):
        from backend.optimization_models import OptimizationRun
        from backend.work_models import WorkJob

        evidence = []
        if item.source_table == "optimization":
            row = self.ledger.db.execute(
                "SELECT payload FROM optimization_runs WHERE id=?", (item.source_id,)
            ).fetchone()
            if row:
                run = OptimizationRun.model_validate_json(row[0])
                evidence = [
                    c.model_dump()
                    for g in run.groups
                    if g.current_id == item.variant.id
                    for r in g.rounds
                    for c in r.calls
                    if c.provenance == "cache"
                ]
        captured_at, prompt_hashes, cache_hits = None, {}, []
        for (payload,) in self.ledger.db.execute(
            "SELECT payload FROM work_jobs WHERE campaign_id=? ORDER BY rowid DESC",
            (item.campaign_id,),
        ):
            job = WorkJob.model_validate_json(payload)
            if (
                job.kind in {"generate", "optimize", "render", "poster_batch"}
                and job.result
                and item.variant.id in json.dumps(job.result)
            ):
                captured_at, prompt_hashes = job.updated_at, job.prompt_hashes
                cache_hits = job.cache_hits
                break
        return {
            "cached_evidence": evidence,
            "captured_at": captured_at,
            "prompt_hashes": prompt_hashes,
            "cache_hits": cache_hits,
        }

    def export(
        self, campaign_id, revision, item_ids=None, saved_view=False, *, transaction_owned=False
    ):
        db = self.ledger.db
        if not transaction_owned:
            db.execute("BEGIN IMMEDIATE")
        try:
            campaign = self.ledger.locked(campaign_id, revision)
            selected = item_ids or [i.id for i in self.ledger.active(campaign)]
            if not selected or len(set(selected)) != len(selected):
                raise domain_error(
                    "EXPORT_UNAUTHORIZED", "Select at least one unique approved item"
                )
            files, copies, links, acknowledgments, bytes_by_name = [], {}, {}, set(), {}
            for item_id in selected:
                item = self.current_item(campaign, item_id)
                if not item.approval_id:
                    raise domain_error("EXPORT_UNAUTHORIZED", "Pending items cannot be exported")
                approval = AssetApproval.model_validate_json(
                    db.execute(
                        "SELECT payload FROM asset_approvals WHERE id=?", (item.approval_id,)
                    ).fetchone()[0]
                )
                audit, raw = self.readiness(campaign, item)
                if (
                    approval.campaign_id != campaign_id
                    or approval.item_hashes.get(item_id) != item.snapshot_hash
                    or not set(audit.warning_ids) <= set(approval.acknowledged_warning_ids)
                ):
                    raise domain_error(
                        "EXPORT_UNAUTHORIZED", "Approval no longer binds current evidence"
                    )
                suffix = "png" if item.kind == "poster" else "txt"
                filename = f"{item.variant.language}-{item.variant.channel}-{item.id}.{suffix}"
                files.append(
                    ExportFile(
                        item_id=item.id,
                        filename=filename,
                        sha256=sha(raw),
                        byte_count=len(raw),
                        language=item.variant.language,
                        channel=item.variant.channel,
                        approved_revision=approval.approved_revision,
                        approval_id=approval.id,
                        dependency_hash=item.dependency_hash,
                        content_hash=item.report.content_hash,
                        artifact_url=f"/api/campaigns/{campaign_id}/export/files/{item.id}?expected_revision={revision}"
                        if item.kind == "poster"
                        else None,
                        mode="cached" if saved_view else item.mode,
                        source_mode=item.mode,
                        **self.capture(item),
                        source_fact_versions=item.variant.dependencies.facts,
                    )
                )
                bytes_by_name[filename] = raw
                acknowledgments.update(approval.acknowledged_warning_ids)
                if item.kind == "text":
                    text = raw.decode("utf-8")
                    copies[item.id] = text
                    if item.variant.channel == "whatsapp":
                        links[item.id] = "https://wa.me/?text=" + quote(text, safe="")
            pack = ExportPack(
                campaign_id=campaign_id,
                campaign_revision=revision,
                generated_at=utc_now(),
                mode="cached" if saved_view else campaign.mode,
                source_mode=campaign.mode,
                view_label=(
                    "SAVED DEMO OUTPUT · cached view of authorized persisted content"
                    if saved_view
                    else "Current authorized output"
                ),
                files=files,
                copy_text=copies,
                whatsapp_drafts=links,
                warning_acknowledgments=sorted(acknowledgments),
                current_fact_versions={f.key: f.version for f in campaign.facts},
            )
            if not transaction_owned:
                db.commit()
            return pack, bytes_by_name
        except BaseException:
            if not transaction_owned:
                db.rollback()
            raise

    def zip(self, campaign_id, revision, item_ids=None, saved_view=False):
        pack, files = self.export(campaign_id, revision, item_ids, saved_view)
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", pack.model_dump_json(indent=2))
            for filename, raw in files.items():
                archive.writestr(filename, raw)
        return output.getvalue()
