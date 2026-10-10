"""B3 bounded planning/copy execution. Saved drafts are never approved assets."""

import asyncio
import json
from collections import Counter
from uuid import uuid4

from backend.campaign_service import prompt
from backend.contracts import utc_now
from backend.errors import ProviderError
from backend.generation_context import (
    complete_disclosures,
    copy_input,
    dependency_hash,
    eligible_segments,
    strategy_input,
    validate_plan,
)
from backend.generation_models import (
    AudienceStrategy,
    BaselineVariant,
    CopyAttempt,
    CopyResult,
    GenerateRequest,
    GenerationRun,
    MatrixCell,
    PersonaProfile,
    StrategyPlan,
    StrategyResult,
)
from backend.generation_repository import GenerationRepository
from backend.guardian.normalize import normalize
from backend.guardian.policy import VERSION
from backend.guardian.report import CheckRequest
from backend.guardian.rules import check
from backend.guardian.slots import SlotError, fields, parse
from backend.inference_client import success_wire_schema
from backend.intent_rules import digest, domain_error
from backend.schemas import DependencyVersions


class GenerationService:
    def __init__(self, store, client):
        self.repo, self.client = GenerationRepository(store), client
        self.tasks: dict[str, asyncio.Task] = {}
        self.plan_lock = asyncio.Lock()

    async def close(self):
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def strategy(self, campaign_id, revision):
        async with self.plan_lock:
            campaign = self.repo.locked(campaign_id, revision)
            existing = self.repo.plan(campaign_id, revision)
            if existing:
                validate_plan(campaign, existing)
                return existing
            data = strategy_input(campaign)
            result = (
                await self.client.structured(
                    json.dumps(data),
                    StrategyResult,
                    self.client.budget(calls=3, seconds=120),
                    system_prompt=prompt("R3"),
                    max_tokens=4096,
                    wire_schema=success_wire_schema(StrategyResult, "StrategySuccess"),
                )
            ).result
            if result.status != "success":
                raise domain_error(
                    "STRATEGY_NEEDS_INPUT", "Three compatible strategies could not be planned"
                )
            allowed = eligible_segments(campaign)
            if any(a.segment not in allowed for a in result.audiences):
                raise domain_error("ELIGIBILITY_CONFLICT", "R3 proposed an ineligible audience")
            if any(a.preferred_channel not in data["channels"] for a in result.audiences):
                raise domain_error("GENERATION_SELECTION", "R3 proposed an unselected channel")
            if not set(result.message_hierarchy) <= set(data["available_slots"]):
                raise domain_error("FORMS_INVALID", "R3 referenced an unavailable fact")
            plan_id = uuid4().hex
            eligibility = next(f for f in campaign.facts if f.key == "ELIGIBILITY")
            audiences = [
                AudienceStrategy(
                    **a.model_dump(),
                    id=f"{plan_id}-a{i}",
                    name=f"{a.segment.title()} · {a.angle.replace('_', ' ')}",
                    eligibility_fact_version=eligibility.version,
                )
                for i, a in enumerate(result.audiences)
            ]
            plan = StrategyPlan(
                id=plan_id,
                campaign_id=campaign_id,
                campaign_revision=revision,
                dependency_hash=dependency_hash(campaign),
                audiences=audiences,
                personas=[
                    PersonaProfile(
                        **p.model_dump(),
                        id=f"{plan_id}-p{i}",
                        audience_id=audiences[p.audience_index].id,
                    )
                    for i, p in enumerate(result.personas)
                ],
                message_hierarchy=result.message_hierarchy,
                hero_audience_id=audiences[result.hero_index].id,
                mode=self.client.settings.inference_mode,
                notices=[
                    "Hypothetical strategy and personas, not market research.",
                    "Raw brand text and transcript withheld from copy generation; "
                    "brand rules still checked.",
                    "Native Kannada review and G14 semantic audit remain pending.",
                ],
            )
            return self.repo.save_plan(plan)

    def start(self, campaign_id, request: GenerateRequest):
        request = GenerateRequest.model_validate(request.model_dump())
        campaign = self.repo.locked(campaign_id, request.expected_revision)
        duplicate = self.repo.duplicate(campaign_id, request)
        if duplicate:
            return duplicate
        plan = self.repo.plan(campaign_id, request.expected_revision)
        if plan is None or plan.id != request.strategy_id:
            raise domain_error("GENERATION_SELECTION", "Select the current saved strategy")
        validate_plan(campaign, plan)
        if (
            not set(request.audience_ids) <= {a.id for a in plan.audiences}
            or not set(request.languages) <= set(campaign.languages)
            or not set(request.channels) <= set(campaign.channels)
        ):
            raise domain_error("GENERATION_SELECTION", "Selection is outside the locked campaign")
        if any(not task.done() for task in self.tasks.values()):
            raise domain_error(
                "GENERATION_BUSY", "Another generation is active; wait for completion"
            )
        if self.client.settings.inference_mode == "cached":
            raise domain_error("INFERENCE_DISABLED", "Saved-output mode cannot generate new copy")
        stamp = utc_now()
        run = GenerationRun(
            id=uuid4().hex,
            campaign_id=campaign_id,
            campaign_revision=campaign.revision,
            strategy_id=plan.id,
            mode=self.client.settings.inference_mode,
            status="queued",
            request=request,
            cells=[
                MatrixCell(audience_id=a, language=language, channel=c)
                for language in request.languages
                for a in request.audience_ids
                for c in request.channels
            ],
            created_at=stamp,
            updated_at=stamp,
        )
        if request.retry_source_run_id:
            source = self.repo.get(request.retry_source_run_id)
            if (
                source.campaign_id != campaign_id
                or source.campaign_revision != campaign.revision
                or source.strategy_id != plan.id
                or source.status in {"queued", "running"}
                or source.request.audience_ids != request.audience_ids
                or source.request.languages != request.languages
                or source.request.channels != request.channels
            ):
                raise domain_error(
                    "GENERATION_SELECTION",
                    "Retry must retain the exact source selection and current revision",
                )
            ready = {
                (c.audience_id, c.language, c.channel): c
                for c in source.cells
                if c.state == "ready"
            }
            run.cells = [
                ready.get((c.audience_id, c.language, c.channel), c).model_copy(deep=True)
                for c in run.cells
            ]
        self.repo.create(run)
        task = asyncio.create_task(self.execute(run.id), name=f"generation-{run.id}")
        self.tasks[run.id] = task
        task.add_done_callback(lambda _: self.tasks.pop(run.id, None))
        return run

    async def execute(self, run_id):
        try:
            run = self.repo.get(run_id)
            campaign = self.repo.locked(run.campaign_id, run.campaign_revision)
            plan = self.repo.plan(run.campaign_id, run.campaign_revision)
            run.status = "running"
            self.repo.save(run)
            for language in run.request.languages:
                await self.language(run, campaign, plan, language)
            ready = sum(c.state == "ready" for c in run.cells)
            run.status = (
                "completed" if ready == len(run.cells) else "partial" if ready else "failed"
            )
            if not ready:
                run.error_code = "COPY_VALIDATION_FAILED"
            self.repo.save(run)
        except asyncio.CancelledError:
            if self.repo.get(run_id).status != "cancelled":
                self.repo.stop(run_id, "interrupted", "GENERATION_CANCELLED")
            raise
        except ProviderError as exc:
            if self.repo.get(run_id).status in {"cancelled", "interrupted", "stale"}:
                return
            self.repo.stop(
                run_id, "stale" if exc.body.code == "REVISION_CONFLICT" else "failed", exc.body.code
            )
        except Exception:
            # Persist a truthful failure; no raw provider output or fixture substitution.
            self.repo.stop(run_id, "failed", "GENERATION_INTERNAL_ERROR")

    async def language(self, run, campaign, plan, language):
        cells = [c for c in run.cells if c.language == language and c.state != "ready"]
        if not cells:
            return
        for cell in cells:
            cell.state = "running"
        self.repo.save(run)
        budget = self.client.budget(calls=3, seconds=150)
        budget.run_id = run.id
        before_calls = run.calls_used
        for attempt in range(1, 4):
            pending = [c for c in cells if c.state != "ready"]
            if not pending:
                break
            codes = sorted({r for c in pending for r in c.reasons})
            try:
                response = (
                    await self.client.structured(
                        json.dumps(copy_input(campaign, plan, language, pending, codes)),
                        CopyResult,
                        budget,
                        system_prompt=prompt("R4"),
                        max_tokens=8192,
                        wire_schema=success_wire_schema(CopyResult, "CopySuccess"),
                    )
                ).result
                if response.status != "success":
                    raise domain_error("COPY_UNAVAILABLE", "R4 could not write this language")
                if response.language != language:
                    raise domain_error("COPY_LANGUAGE_MISMATCH", "R4 returned another language")
                self.evaluate(run, campaign, plan, pending, response.entries, attempt)
            except ProviderError as exc:
                for cell in pending:
                    cell.state, cell.reasons = "blocked", [exc.body.code]
                    cell.attempts.append(CopyAttempt(attempt=attempt, reasons=cell.reasons))
                run.calls_used = before_calls + budget.calls
                self.repo.save(run)
                break
            run.calls_used = before_calls + budget.calls
            self.repo.save(run)
        for cell in cells:
            if cell.state != "ready":
                cell.state = "blocked"
        self.repo.save(run)

    def evaluate(self, run, campaign, plan, pending, entries, attempt):
        counts = Counter((e.audience_id, e.channel) for e in entries)
        expected = {(c.audience_id, c.channel) for c in pending}
        unexpected = set(counts) - expected
        for cell in pending:
            key = (cell.audience_id, cell.channel)
            reasons = ["UNEXPECTED_COMBINATION"] if unexpected else []
            if counts[key] != 1:
                reasons.append(
                    "MISSING_COMBINATION" if not counts[key] else "DUPLICATE_COMBINATION"
                )
            if not reasons:
                entry = next(e for e in entries if (e.audience_id, e.channel) == key)
                template, added = complete_disclosures(campaign, entry.template)
                entry = entry.model_copy(update={"template": template})
                if added and getattr(self.client.store, "work", None):
                    self.client.store.work.event(
                        campaign.id,
                        "validation",
                        "Added approved disclosure slots: " + ", ".join(added) + "; checking copy",
                    )
                audience = next(a for a in plan.audiences if a.id == cell.audience_id)
                report = check(
                    campaign,
                    CheckRequest(
                        campaign_id=campaign.id,
                        expected_revision=campaign.revision,
                        mode="asset",
                        language=cell.language,
                        channel=cell.channel,
                        template=entry.template,
                        audience=audience.segment,
                    ),
                )
                reasons = [
                    c.rule
                    for c in report.checks
                    if c.passed is False and (c.severity == "BLOCK" or c.rule == "G11")
                ]
                hook = normalize(entry.template.headline).text.strip()
                if not hook:
                    reasons.append("MISSING_HOOK")
                comparisons = [e for e in entries if (e.audience_id, e.channel) != key]
                comparisons += [
                    c.variant
                    for c in run.cells
                    if c.state == "ready" and c.language == cell.language and c.variant
                ]
                for other in comparisons:
                    if (
                        other.channel == cell.channel
                        and normalize(other.template.headline).text.strip() == hook
                    ):
                        reasons.append("UNDIFFERENTIATED_HOOK")
                    if other.audience_id == cell.audience_id and other.template == entry.template:
                        reasons.append("DUPLICATED_CHANNEL_COPY")
                try:
                    used = sorted(
                        {
                            token.key
                            for text in fields(entry.template).values()
                            for token in parse(text)
                        }
                    )
                except SlotError:
                    used = []
                # Include all facts, including eligibility/unknown condition dependencies.
                cell.variant = BaselineVariant(
                    id=digest([run.id, cell.audience_id, cell.language, cell.channel]),
                    campaign_id=campaign.id,
                    campaign_revision=campaign.revision,
                    audience_id=cell.audience_id,
                    language=cell.language,
                    channel=cell.channel,
                    template=entry.template,
                    slots_used=used,
                    fact_hash=campaign.fact_hash or "",
                    dependency_hash=digest(
                        [report.dependency_hash, plan.dependency_hash, plan.id, "b3.1"]
                    ),
                    content_hash=report.content_hash,
                    render_hash=None,
                    status="blocked" if reasons else "pending",
                    parent_id=None,
                    dependencies=DependencyVersions(
                        facts={f.key: f.version for f in campaign.facts},
                        brand_revision=campaign.brand_revision,
                        prompt_version="b3.1",
                        policy_version=VERSION,
                    ),
                    report=report,
                    mode=run.mode,
                )
            cell.reasons = sorted(set(reasons))
            cell.state = "blocked" if reasons else "ready"
            cell.attempts.append(CopyAttempt(attempt=attempt, reasons=cell.reasons))
