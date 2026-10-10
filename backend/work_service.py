"""Durable admission around existing services; uncertain work never auto-resumes."""

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from pydantic import ValidationError

from backend.art_models import BackgroundRequest, RenderRequest
from backend.campaign_service import CampaignService
from backend.contracts import utc_now
from backend.delivery_models import ChangeRequest, RedTeamRequest, RedTeamResult
from backend.errors import ProviderError
from backend.generation_models import GenerateRequest
from backend.guardian.report import CheckRequest
from backend.guardian.rules import check
from backend.intent_rules import digest, domain_error
from backend.local_video import LocalVideoInput
from backend.meta_models import MetaWorkInput
from backend.optimization_models import OptimizeRequest
from backend.schemas import IntentRequest, RevisionRequest, SurfaceRequest, TemplateContent
from backend.video_service import VideoInput
from backend.work_context import work_guard, work_id
from backend.work_models import PosterBatchInput, WorkflowEvent, WorkJob, WorkRequest, WorkSnapshot

ACTIVE = {"queued", "running"}
INPUTS = {
    "intent": IntentRequest,
    "forms": SurfaceRequest,
    "strategy": RevisionRequest,
    "generate": GenerateRequest,
    "optimize": OptimizeRequest,
    "background": BackgroundRequest,
    "render": RenderRequest,
    "poster_batch": PosterBatchInput,
    "poster_audit": RevisionRequest,
    "item_audit": RevisionRequest,
    "change": ChangeRequest,
    "change_forms": RevisionRequest,
    "red_team": RedTeamRequest,
    "meta_delivery": MetaWorkInput,
    "video": VideoInput,
    "local_video": LocalVideoInput,
}


class WorkService:
    def __init__(self, app):
        self.app = app
        self.db = app.state.store.connection
        self.campaigns = CampaignService(app.state.store, app.state.client, app.state.settings)
        self.tasks = {}
        self.slots = asyncio.Semaphore(2)
        self.video_slots = asyncio.Semaphore(1)
        for row in self.db.execute(
            "SELECT payload FROM work_jobs WHERE status IN ('queued','running')"
        ).fetchall():
            job = WorkJob.model_validate_json(row[0])
            job.status, job.error_code = "interrupted", "PROCESS_RESTARTED"
            self.save(
                job,
                "Process restarted. Outputs retained; retry explicitly.",
            )

    async def close(self):
        for task in self.tasks.values():
            task.cancel()
        await asyncio.gather(*list(self.tasks.values()), return_exceptions=True)

    def event(self, campaign, event, message, job_id=None, fingerprint=None, run_id=None):
        job_id = job_id or work_id.get()
        job = self.get(job_id) if job_id else None
        payload = WorkflowEvent(
            id=0,
            campaign_id=campaign,
            timestamp=utc_now(),
            event=event,
            message=message,
            job_id=job_id,
            run_id=run_id or (job.native_run_id or job.id if job else None),
            revision=job.campaign_revision if job else self.campaigns.repo.get(campaign).revision,
        )
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO workflow_events(campaign_id,fingerprint,payload) "
                "VALUES(?,?,?)",
                (campaign, fingerprint or uuid4().hex, payload.model_dump_json()),
            )

    def events(self, campaign, after=0, limit=100):
        rows = self.db.execute(
            "SELECT id,payload FROM workflow_events WHERE campaign_id=? AND id>? "
            "ORDER BY id LIMIT ?",
            (campaign, after, limit),
        ).fetchall()
        return [WorkflowEvent.model_validate_json(p).model_copy(update={"id": i}) for i, p in rows]

    def save(self, job, message):
        job.updated_at = utc_now()
        with self.db:
            self.db.execute(
                "UPDATE work_jobs SET status=?,payload=? WHERE id=?",
                (job.status, job.model_dump_json(), job.id),
            )
        self.event(job.campaign_id, job.status, message, job.id)

    def get(self, job_id):
        row = self.db.execute("SELECT payload FROM work_jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            raise domain_error(
                "WORK_NOT_FOUND", "Saved job is unavailable. Reload campaign progress."
            )
        return WorkJob.model_validate_json(row[0])

    def start(self, campaign_id, request):
        campaign = self.campaigns.repo.get(campaign_id)
        try:
            body = INPUTS[request.kind].model_validate(request.input)
        except ValidationError:
            raise domain_error(
                "WORK_INVALID", "Job input does not match its operation schema"
            ) from None
        if request.kind in {"poster_audit", "item_audit", "change_forms"} and not request.target_id:
            raise domain_error("WORK_INVALID", "Choose a saved item for this operation")
        hashed = digest(request.model_dump(exclude={"idempotency_key"}))
        row = self.db.execute(
            "SELECT request_hash,payload FROM work_jobs WHERE campaign_id=? AND idempotency_key=?",
            (campaign_id, request.idempotency_key),
        ).fetchone()
        if row:
            if row[0] != hashed:
                raise domain_error("IDEMPOTENCY_CONFLICT", "Job key already binds another request")
            return WorkJob.model_validate_json(row[1])
        if campaign.revision != body.expected_revision:
            raise domain_error("REVISION_CONFLICT", "Campaign changed. Reload before retrying.")
        if self.app.state.settings.inference_mode == "cached":
            raise domain_error("INFERENCE_DISABLED", "Saved-output mode cannot start work")
        if request.kind == "video" and not self.app.state.settings.enable_video:
            raise domain_error("VIDEO_DISABLED", "No configured video capability is available")
        if request.kind == "local_video" and not self.app.state.settings.local_video_enabled:
            raise domain_error("VIDEO_DISABLED", "Local animation is disabled")
        if (
            request.kind in {"background", "poster_batch"}
            and body.source != "deterministic"
            and not self.app.state.settings.image_generation_enabled
        ):
            raise domain_error(
                "IMAGE_KEY_MISSING"
                if self.app.state.settings.image_provider == "openai"
                else "IMAGE_TRANSPORT_UNVERIFIED",
                "Add OPENAI_API_KEY and restart backend, or choose local artwork"
                if self.app.state.settings.image_provider == "openai"
                else "Choose local artwork or configure a verified compatible image endpoint",
            )
        if request.kind == "local_video":
            job_provider = "Local FFmpeg"
        elif request.kind == "render" or (
            request.kind in {"background", "poster_batch"} and body.source == "deterministic"
        ):
            job_provider = "Local renderer"
        elif (
            request.kind in {"background", "poster_batch"}
            and self.app.state.settings.image_provider == "openai"
        ):
            job_provider = "OpenAI"
        else:
            from urllib.parse import urlsplit

            job_provider = (
                "OpenRouter"
                if urlsplit(self.app.state.settings.inference_base_url).hostname == "openrouter.ai"
                else "Configured gateway"
            )
        count = self.db.execute(
            "SELECT COUNT(*) FROM work_jobs WHERE status IN ('queued','running')"
        ).fetchone()[0]
        if count >= 18:
            raise domain_error(
                "WORK_QUEUE_FULL", "Queue is full. Wait for a job or cancel pending work."
            )
        now = datetime.now(UTC)
        job = WorkJob(
            id=uuid4().hex,
            campaign_id=campaign_id,
            campaign_revision=campaign.revision,
            kind=request.kind,
            status="queued",
            mode=self.app.state.settings.inference_mode,
            created_at=now.isoformat(),
            updated_at=now.isoformat(),
            deadline=(now + timedelta(seconds=480)).isoformat(),
            provider=job_provider,
        )
        job.prompt_hashes = {
            p.stem: digest(p.read_text(encoding="utf-8"))
            for p in (Path(__file__).parent / "prompts").glob("R*.md")
        }
        job.input, job.target_id = body.model_dump(), request.target_id
        if request.kind == "meta_delivery":
            operation = self.app.state.meta.load(body.operation_id, campaign_id)
            if not operation["confirmed"] or operation["operation"]["status"] != "queued":
                raise domain_error("META_INVALID", "An exact owner-confirmed preview is required")
            job.provider = "Meta"
            job.mode = self.app.state.settings.meta_mode
            job.max_calls = 12
            job.prompt_hashes = {}
        job.max_steps = (
            len(body.sizes) * 2
            if request.kind == "poster_batch"
            else len(body.languages)
            if request.kind == "generate"
            else 1
        )
        with self.db:
            self.db.execute(
                "INSERT INTO work_jobs VALUES(?,?,?,?,?,?)",
                (
                    job.id,
                    campaign_id,
                    request.idempotency_key,
                    hashed,
                    job.status,
                    job.model_dump_json(),
                ),
            )
        self.event(
            campaign_id,
            "queued",
            f"{job.kind.replace('_', ' ')} queued; "
            f"bounded to 480 seconds and {job.max_calls} calls.",
            job.id,
        )
        task = asyncio.create_task(self.execute(job.id, body, request.target_id))
        self.tasks[job.id] = task
        task.add_done_callback(lambda _: self.tasks.pop(job.id, None))
        return job

    def guard(self, job_id):
        job = self.get(job_id)
        calls = [c for c in self.app.state.store.calls() if c.work_id == job_id and c.sent]
        if (
            job.status != "running"
            or datetime.now(UTC) >= datetime.fromisoformat(job.deadline)
            or len(calls) >= job.max_calls
        ):
            raise domain_error("BUDGET_EXHAUSTED", "Job deadline or call budget reached")

    async def execute(self, job_id, body, target):
        job = self.get(job_id)
        tokens = (work_id.set(job_id), work_guard.set(lambda: self.guard(job_id)))
        try:
            seconds = max(
                0.001, (datetime.fromisoformat(job.deadline) - datetime.now(UTC)).total_seconds()
            )
            async with (
                asyncio.timeout(seconds),
                self.video_slots if job.kind in {"video", "local_video"} else self.slots,
            ):
                # Check after queue admission, before any operation starts.
                if self.campaigns.repo.get(job.campaign_id).revision != job.campaign_revision:
                    raise domain_error(
                        "REVISION_CONFLICT", "Queued work refers to an older revision"
                    )
                job.status, job.started_at = "running", utc_now()
                self.save(job, f"{job.kind.replace('_', ' ')} started.")
                result = await self.dispatch(job, body, target)
                if self.get(job.id).status in {"cancelled", "interrupted"}:
                    return
                if self.campaigns.repo.get(job.campaign_id).revision != result.get(
                    "revision", job.campaign_revision
                ):
                    raise domain_error("REVISION_CONFLICT", "Result belongs to an older revision")
                job.result = result
                if job.kind != "poster_batch":
                    job.completed_steps = 1
                job.status = (
                    result.get("status")
                    if result.get("status") in {"partial", "failed", "stale", "interrupted"}
                    else "completed"
                )
                job.error_code = result.get("error_code")
                if job.notices and job.status == "completed":
                    job.status = "partial"
                if result.get("status") in {"blocked", "uncertain", "BLOCKED", "PENDING"}:
                    job.status = "failed"
                    reasons = result.get("reasons") or result.get("findings")
                    if not reasons and result.get("checks"):
                        reasons = [
                            c.get("message", "Check failed")
                            for c in result["checks"]
                            if c.get("passed") is False
                        ]
                    job.error_code = (reasons or ["REVIEW_UNAVAILABLE"])[0]
                self.save(
                    job,
                    f"{job.kind.replace('_', ' ')} {job.status}. Review before approval.",
                )
        except asyncio.CancelledError:
            # Cancellation is a terminal decision; no late result may replace it.
            job = self.get(job_id)
            if job.status != "cancelled":
                job.status, job.error_code = "interrupted", "PROCESS_STOPPED"
                self.save(
                    job,
                    "Worker stopped. Outputs retained; uncertain submissions are not repeated.",
                )
            raise
        except (ProviderError, TimeoutError) as exc:
            if self.get(job.id).status == "cancelled":
                return
            job.status = (
                "stale"
                if isinstance(exc, ProviderError) and exc.body.code == "REVISION_CONFLICT"
                else "failed"
            )
            job.error_code = exc.body.code if isinstance(exc, ProviderError) else "WORK_TIMEOUT"
            if job.kind == "intent" and job.error_code == "INTENT_UNAVAILABLE":
                job.notices.append(
                    "The model could not interpret this brief. Edit and retry, or enter facts "
                    "manually. Existing facts have not changed."
                )
            if job.kind == "forms" and job.error_code == "SURFACES_UNAVAILABLE":
                job.notices.append(
                    "Canonical confirmation is saved. Review the current facts and retry "
                    "wording; unknown optional conditions do not need invented answers."
                )
            self.save(
                job, f"Work stopped: {job.error_code}. Saved outputs retained. Retry explicitly."
            )
        except Exception:
            if self.get(job.id).status == "cancelled":
                return
            job.status, job.error_code = "failed", "WORK_FAILED"
            self.save(job, "Work failed. Reload saved progress and retry explicitly.")
        finally:
            work_id.reset(tokens[0])
            work_guard.reset(tokens[1])

    async def dispatch(self, job, body, target):
        state, cid, rev, kind = self.app.state, job.campaign_id, job.campaign_revision, job.kind
        if kind == "meta_delivery":
            return await state.meta.execute(job, body)
        if kind == "video":
            return await state.video.execute(job, body)
        if kind == "local_video":
            return await state.video.execute_local(job, body)
        if kind == "intent":
            result = await self.campaigns.intent(cid, body)
        elif kind == "forms":
            result = await self.campaigns.surfaces(cid, body)
        elif kind == "strategy":
            if state.generation.repo.plan(cid, rev):
                job.cache_hits.append("Saved strategy and personas")
            result = await state.generation.strategy(cid, rev)
        elif kind in {"generate", "optimize"}:
            service = state.generation if kind == "generate" else state.optimization
            run = service.start(cid, body)
            job.native_run_id = run.id
            if kind == "optimize":
                job.max_steps = run.max_steps
            self.save(job, "Native run saved; progressive outputs and stop decisions are durable.")
            task = service.tasks.get(run.id)
            if task:
                await task
            result = service.repo.get(run.id)
        elif kind == "background":
            existing = {b.id for b in state.art.repo.snapshot(cid).backgrounds}
            result = await state.art.background(cid, body)
            if body.source == "provider" and result.provenance == "deterministic":
                job.notices.append(
                    "Provider image unavailable. Local artwork used; review before approval. "
                    + ", ".join(result.reasons)
                )
            if result.id in existing:
                job.cache_hits.append("Saved background · " + result.id)
        elif kind == "render":
            existing = {p.id for p in state.art.repo.snapshot(cid).posters}
            result = await state.art.render(cid, body)
            if result.id in existing:
                job.cache_hits.append("Saved poster pixels · " + result.id)
        elif kind == "poster_audit":
            poster = state.art.repo.poster(target)
            if poster.campaign_id != cid:
                raise domain_error("WORK_INVALID", "Poster belongs to another campaign")
            result = await state.optimization.audit_poster(target, rev)
        elif kind == "item_audit":
            result = await state.approvals.audit(cid, target, rev)
        elif kind == "change":
            result = await state.changes.propose(cid, body)
        elif kind == "red_team":
            if body.mode == "instruct_ai":
                proposal = await state.changes.propose(
                    cid,
                    ChangeRequest(
                        expected_revision=rev, text=body.text, idempotency_key=body.idempotency_key
                    ),
                )
                result = RedTeamResult(mode=body.mode, proposal=proposal)
            else:
                campaign = state.changes.ledger.locked(cid, rev)
                report = check(
                    campaign,
                    CheckRequest(
                        campaign_id=cid,
                        expected_revision=rev,
                        mode="fragment",
                        language=body.language,
                        channel="whatsapp",
                        template=TemplateContent(
                            headline="", body=body.text, cta="", hashtags=[], alt_text=""
                        ),
                    ),
                )
                result = RedTeamResult(mode=body.mode, report=report)
        elif kind == "change_forms":
            result = await state.changes.surfaces(
                cid, SimpleNamespace(expected_revision=rev, proposal_id=target)
            )
        else:
            if len(set(body.sizes)) != len(body.sizes):
                raise domain_error("WORK_INVALID", "Select each poster size once")
            posters = []
            for size in body.sizes:
                existing = state.art.repo.snapshot(cid)
                background = await state.art.background(
                    cid, BackgroundRequest(expected_revision=rev, size=size, source=body.source)
                )
                if background.id in {b.id for b in existing.backgrounds}:
                    job.cache_hits.append("Saved background · " + background.id)
                if body.source == "provider" and background.provenance == "deterministic":
                    job.notices.append(
                        f"{size}: Configured provider image unavailable. "
                        "Deterministic artwork used; review before approval. "
                        + ", ".join(background.reasons)
                    )
                job.completed_steps += 1
                if background.status == "blocked":
                    raise domain_error(
                        "ART_BLOCKED",
                        "Generated image saved, but image QA is unavailable. "
                        "Choose local artwork for an approvable poster.",
                    )
                self.save(job, f"{size} background saved. Preparing exact poster pixels.")
                poster = await state.art.render(
                    cid,
                    RenderRequest(
                        expected_revision=rev,
                        variant_id=body.variant_id,
                        size=size,
                        background_id=background.id,
                        logo_id=body.logo_id,
                    ),
                )
                posters.append(poster.model_dump())
                if poster.id in {p.id for p in existing.posters}:
                    job.cache_hits.append("Saved poster pixels · " + poster.id)
                job.completed_steps += 1
                self.save(job, f"{size} poster saved; approval pending.")
            return {"posters": posters}
        return result.model_dump()

    def retry(self, job_id, request):
        job = self.get(job_id)
        if job.kind == "video":
            raise domain_error(
                "RETRY_UNSAFE", "Inspect saved clip IDs before authorizing a new video job"
            )
        if job.kind == "meta_delivery":
            raise domain_error(
                "RETRY_UNSAFE",
                "Delivery is never retried through generic work. "
                "Inspect provider history and explicitly review a new preview.",
            )
        if job.status not in {"failed", "interrupted", "cancelled", "partial"}:
            raise domain_error("WORK_INVALID", "Only stopped or partial work can be retried")
        if (
            request.expected_revision != job.campaign_revision
            or self.campaigns.repo.get(job.campaign_id).revision != job.campaign_revision
        ):
            raise domain_error(
                "REVISION_CONFLICT", "Reload the changed facts and start a new reviewed operation"
            )
        media = [
            c
            for c in self.app.state.store.calls()
            if c.work_id == job.id and c.operation == "image" and c.sent
        ]
        if job.error_code == "SUBMISSION_UNCERTAIN" or any(
            c.status in {"submission_uncertain", "cancelled_uncertain"} for c in media
        ):
            raise domain_error(
                "RETRY_UNSAFE",
                "Media submission is uncertain. Inspect provider history; "
                "choose deterministic artwork to continue without resubmission.",
            )
        if not job.input:
            raise domain_error(
                "WORK_INVALID",
                "Legacy job input is unavailable. Review and start the matching action below.",
            )
        values = dict(job.input)
        if job.kind in {"generate", "optimize", "change"}:
            values["idempotency_key"] = request.idempotency_key
        if job.kind == "generate" and job.native_run_id:
            values["retry_source_run_id"] = job.native_run_id
        return self.start(
            job.campaign_id,
            WorkRequest(
                kind=job.kind,
                input=values,
                target_id=job.target_id,
                idempotency_key=request.idempotency_key,
            ),
        )

    async def cancel(self, job_id):
        job = self.get(job_id)
        if job.status not in ACTIVE:
            return job
        if job.kind == "meta_delivery":
            self.app.state.meta.cancel(job.input["operation_id"])
        job.status, job.error_code = "cancelled", "OWNER_CANCELLED"
        self.save(
            job,
            "Owner cancelled. Outputs retained; submitted media may still incur cost.",
        )
        if job.native_run_id and job.kind in {"generate", "optimize"}:
            service = (
                self.app.state.generation if job.kind == "generate" else self.app.state.optimization
            )
            service.repo.stop(job.native_run_id, "cancelled", "OWNER_CANCELLED")
        task = self.tasks.get(job_id)
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if job.native_run_id and job.kind in {"generate", "optimize"}:
            service = (
                self.app.state.generation if job.kind == "generate" else self.app.state.optimization
            )
            service.repo.stop(job.native_run_id, "cancelled", "OWNER_CANCELLED")
        return self.get(job_id)

    def snapshot(self, campaign_id, job_id=None):
        campaign = self.campaigns.repo.get(campaign_id)
        jobs = [
            WorkJob.model_validate_json(r[0])
            for r in self.db.execute(
                "SELECT payload FROM work_jobs WHERE campaign_id=? AND (? IS NULL OR id=?) "
                "ORDER BY rowid DESC LIMIT 50",
                (campaign_id, job_id, job_id),
            )
        ]
        all_active = self.db.execute(
            "SELECT id,status FROM work_jobs WHERE status IN ('queued','running') ORDER BY rowid"
        ).fetchall()
        queue = [i for i, s in all_active if s == "queued"]
        now = datetime.now(UTC)
        calls = self.app.state.store.calls()
        for job in jobs:
            if job.native_run_id:
                service = (
                    self.app.state.generation
                    if job.kind == "generate"
                    else self.app.state.optimization
                )
                native = service.repo.get(job.native_run_id)
                if job.kind == "optimize":
                    job.completed_steps = native.steps_used
                else:
                    job.completed_steps = sum(
                        all(
                            c.state not in {"queued", "running"}
                            for c in native.cells
                            if c.language == lang
                        )
                        for lang in native.request.languages
                    )
            own = [c for c in calls if c.work_id == job.id]
            job.calls = sum(c.sent for c in own)
            job.list_price_estimate_usd = sum(
                c.list_price_estimate_usd or 0 for c in own if c.mode == "live"
            )
            job.unknown_cost_calls = sum(
                c.sent and c.list_price_estimate_usd is None and c.mode == "live" for c in own
            )
            if job.kind == "meta_delivery":
                job.calls = self.db.execute(
                    "SELECT COUNT(*) FROM meta_attempts WHERE operation_id=?",
                    (job.input["operation_id"],),
                ).fetchone()[0]
                job.unknown_cost_calls = job.calls if job.mode == "live" else 0
            job.queue_position = queue.index(job.id) + 1 if job.id in queue else 0
            job.estimated_wait_seconds = job.queue_position * 30.0 + max(
                0, self.app.state.client.next_call["text"] - self.app.state.client.clock.now()
            )
            end = now if job.status in ACTIVE else datetime.fromisoformat(job.updated_at)
            job.elapsed_seconds = max(
                0, (end - datetime.fromisoformat(job.started_at or job.created_at)).total_seconds()
            )
            if job.campaign_revision != campaign.revision and job.kind not in {"intent", "forms"}:
                job.status = "stale"
        latest = self.db.execute(
            "SELECT COALESCE(MAX(id),0) FROM workflow_events WHERE campaign_id=?", (campaign_id,)
        ).fetchone()[0]
        return WorkSnapshot(
            jobs=jobs,
            active=sum(s == "running" for _, s in all_active),
            queued=len(queue),
            mode=self.app.state.settings.inference_mode,
            latest_event_id=latest,
        )
