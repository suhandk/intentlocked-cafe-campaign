"""Finite persisted score → critique → authorize → verify → compare → select → stop."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from backend.art_repository import ArtRepository
from backend.campaign_service import prompt
from backend.contracts import utc_now
from backend.errors import ProviderError
from backend.generation_context import slot_inventory
from backend.guardian.report import CheckRequest
from backend.guardian.rules import check
from backend.guardian.slots import fields, parse
from backend.intent_rules import digest, domain_error
from backend.optimization_models import (
    CallEvidence,
    CritiqueResult,
    JudgeResult,
    OptimizationGroup,
    OptimizationRun,
    ReaderResult,
    Round,
)
from backend.optimization_repository import OptimizationRepository
from backend.scoring import acceptance, features, map_votes, score
from backend.semantic_audit import compare

EDIT_PATHS = ("template.headline", "template.body", "template.cta", "template.alt_text")


def apply_edits(template, critique):
    if critique.no_change and critique.edits:
        raise domain_error("EDIT_REJECTED", "no_change cannot contain edits")
    if len({e.target for e in critique.edits}) != len(critique.edits):
        raise domain_error("EDIT_REJECTED", "Duplicate edit targets")
    value = template.model_dump()
    for edit in critique.edits:
        if edit.target not in EDIT_PATHS:
            raise domain_error("EDIT_REJECTED", "Immutable or unsupported edit target")
        value[edit.target.split(".")[1]] = edit.value
    candidate = type(template).model_validate(value)

    def tokens(t):
        return {(s.key, s.case) for text in fields(t).values() for s in parse(text)}

    if tokens(candidate) != tokens(template):
        raise domain_error("EDIT_REJECTED", "Edits must preserve the approved slot/case inventory")
    return candidate


class OptimizationService:
    def __init__(self, store, client):
        self.store, self.client = store, client
        self.repo, self.art = OptimizationRepository(store), ArtRepository(store)
        self.tasks = {}

    async def close(self):
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def start(self, campaign_id, request):
        campaign = self.repo.generation.locked(campaign_id, request.expected_revision)
        duplicate = self.repo.duplicate(campaign_id, request)
        if duplicate:
            return duplicate
        if len(set(request.variant_ids)) != len(request.variant_ids):
            raise domain_error("OPTIMIZATION_SELECTION", "Select each variant once")
        if any(not task.done() for task in self.tasks.values()):
            raise domain_error("OPTIMIZATION_BUSY", "An optimization run is already active")
        if self.client.settings.inference_mode == "cached":
            raise domain_error("INFERENCE_DISABLED", "Saved-output mode cannot optimize")
        variants = [self.art.variant(campaign, v) for v in request.variant_ids]
        if any(not variant.baseline for variant in variants):
            raise domain_error(
                "OPTIMIZATION_SELECTION", "Select original baselines; charts never rebase"
            )
        plan = self.repo.generation.plan(campaign_id, campaign.revision)
        if plan is None or len(plan.personas) != 5:
            raise domain_error("OPTIMIZATION_SELECTION", "Five saved personas are required")
        allowed_audiences = {audience.id for audience in plan.audiences}
        if any(
            v.audience_id not in allowed_audiences
            or v.audience_id != variants[0].audience_id
            or v.language != variants[0].language
            for v in variants
        ):
            raise domain_error(
                "OPTIMIZATION_SELECTION", "Choose one language and one saved audience group"
            )
        groups = []
        for variant in variants:
            baseline_score = score(features(variant.report, variant.channel), baseline=True)
            groups.append(
                OptimizationGroup(
                    baseline=variant,
                    current_id=variant.id,
                    current_template=variant.template,
                    baseline_score=baseline_score,
                    current_score=baseline_score,
                )
            )
        stamp = utc_now()
        rounds = 2 if self.client.settings.demo_fast else 3
        run = OptimizationRun(
            id=uuid4().hex,
            campaign_id=campaign_id,
            campaign_revision=campaign.revision,
            context_hash=digest(campaign.model_dump()),
            request=request,
            personas=plan.personas,
            persona_hash=digest([p.model_dump() for p in plan.personas]),
            baseline_hash=digest([v.model_dump() for v in variants]),
            mode=campaign.mode,
            model=self.client.settings.text_model,
            prompt_hashes={r: digest(prompt(r)) for r in ["R5", "R6", "R7"]},
            status="queued",
            phase="queued",
            groups=groups,
            max_rounds=rounds,
            max_calls=48,
            max_steps=len(groups) * (1 + rounds * 4),
            deadline_at=(datetime.now(UTC) + timedelta(seconds=480)).isoformat(),
            created_at=stamp,
            updated_at=stamp,
        )
        self.repo.create(run)
        task = asyncio.create_task(self.execute(run.id), name=f"optimization-{run.id}")
        self.tasks[run.id] = task
        task.add_done_callback(lambda _: self.tasks.pop(run.id, None))
        return run

    def metrics(self, run, started=None):
        calls = [c for c in self.store.calls() if c.run_id == run.id and c.sent]
        run.calls_used = len(calls)
        run.mock_calls = sum(c.mode == "mock" for c in calls)
        run.known_cost_usd = sum(c.list_price_estimate_usd or 0 for c in calls if c.mode != "mock")
        run.unknown_cost_calls = sum(
            c.mode != "mock" and c.list_price_estimate_usd is None for c in calls
        )
        if started is not None:
            run.elapsed_ms = max(0.0, (self.client.clock.now() - started) * 1000)

    async def role(self, role, data, schema, budget, context, calls, run=None, validate=None):
        if run:
            if run.model != self.client.settings.text_model or run.prompt_hashes[role] != digest(
                prompt(role)
            ):
                raise domain_error("REVISION_CONFLICT", "Frozen role model or prompt changed")
            if run.steps_used >= run.max_steps:
                raise domain_error("BUDGET_EXHAUSTED", "Step budget exhausted")
            run.steps_used += 1
            self.repo.save(run)
        # Cache context is server-side only. R7 never receives facts/context hash as inputs.
        metadata = {
            "role": role,
            "input": data,
            "context_hash": context,
            "prompt": prompt(role),
            "model": self.client.settings.text_model,
            "provider_endpoint": self.client.settings.inference_base_url,
            "schema": schema.model_json_schema(),
            "mode": self.client.settings.inference_mode,
            "structured_strategy": self.client.settings.structured_strategy,
            "temperature": 0,
            "version": "b5.1",
        }
        key = digest(metadata)
        cached = self.repo.cache(key)
        started = self.client.clock.now()
        budget.check(started)  # even cached work cannot evade time/call bounds
        result, error = None, None
        stamp = utc_now()
        before = {c.id for c in self.store.calls() if c.run_id == budget.run_id}
        if cached:
            result = schema.model_validate_json(json.dumps(cached["output"]))
            if validate:
                validate(result)
            stamp = cached["captured_at"]
        else:
            try:
                result = await self.client.structured(
                    json.dumps(data, ensure_ascii=False),
                    schema,
                    budget,
                    system_prompt=prompt(role),
                    max_tokens=8192,
                    validate=validate,
                )
            except ProviderError as exc:
                error = exc.body.code
            if result:
                self.repo.cache_save(
                    key, {"metadata": metadata, "output": result.model_dump(), "captured_at": stamp}
                )
        records = [
            c.id for c in self.store.calls() if c.run_id == budget.run_id and c.id not in before
        ]
        evidence = CallEvidence(
            role=role,
            cache_key=key,
            provenance="cache" if cached else self.client.settings.inference_mode,
            source_mode=self.client.settings.inference_mode,
            captured_at=stamp,
            model=self.client.settings.text_model,
            prompt_hash=digest(prompt(role)),
            input_hash=digest(data),
            output_hash=digest(result.model_dump()) if result else None,
            call_ids=records,
            error_code=error,
            elapsed_ms=max(0.0, (self.client.clock.now() - started) * 1000),
        )
        calls.append(evidence)
        if run:
            self.metrics(run)
            self.repo.save(run)  # stale result rejected before audit/cache can authorize anything
        if error == "BUDGET_EXHAUSTED":
            raise domain_error(error, "Run call/time budget exhausted")
        return result, evidence

    async def audit_report(
        self,
        campaign,
        report,
        language,
        channel,
        budget,
        calls,
        run=None,
        artifact_hash=None,
        poster=None,
    ):
        data = {
            "language": language,
            "channel": channel,
            "fields": report.rendered.fields if report.rendered else {},
            "visual_description": None,
        }
        from backend.semantic_audit import ground_reader, reader_spans

        data["evidence_spans"] = reader_spans(data["fields"])
        reader, evidence = await self.role(
            "R7",
            data,
            ReaderResult,
            budget,
            digest([campaign.model_dump(), report.model_dump(), artifact_hash]),
            calls,
            run,
            validate=lambda result: ground_reader(result, data["fields"]),
        )
        audit = compare(campaign, report, reader, language, evidence, artifact_hash)
        if poster:
            audit.measured_features = features(audit.guardian, "poster", poster)
        if run:
            self.repo.current(run)
        self.repo.save_audit(audit)
        return audit

    def report(self, campaign, variant, template):
        plan = self.repo.generation.plan(campaign.id, campaign.revision)
        audience = next(a for a in plan.audiences if a.id == variant.audience_id)
        return check(
            campaign,
            CheckRequest(
                campaign_id=campaign.id,
                expected_revision=campaign.revision,
                mode="asset",
                language=variant.language,
                channel=variant.channel,
                template=template,
                audience=audience.segment,
            ),
        )

    async def execute(self, run_id):
        run = self.repo.get(run_id)
        started = self.client.clock.now()
        remaining = max(
            0.0,
            min(
                480.0, (datetime.fromisoformat(run.deadline_at) - datetime.now(UTC)).total_seconds()
            ),
        )
        budget = self.client.budget(calls=run.max_calls, seconds=remaining)
        budget.run_id = run.id
        try:
            async with asyncio.timeout(remaining):
                campaign = self.repo.current(run)
                run.status, run.phase = "running", "score baseline"
                self.repo.save(run)
                for group in run.groups:
                    await self.optimize_group(run, group, campaign, budget)
                run.status, run.phase, run.stop_reason = (
                    "completed",
                    "stopped",
                    "ALL_GROUPS_STOPPED",
                )
                self.metrics(run, started)
                self.repo.save(run)
        except asyncio.CancelledError:
            if self.repo.get(run_id).status != "cancelled":
                self.repo.stop(run_id, "interrupted", "CANCELLED")
            raise
        except (ProviderError, TimeoutError) as exc:
            code = exc.body.code if isinstance(exc, ProviderError) else "DEADLINE_EXCEEDED"
            if self.repo.get(run_id).status not in {"cancelled", "interrupted", "stale"}:
                self.repo.stop(run_id, "stale" if code == "REVISION_CONFLICT" else "failed", code)
        except Exception:
            self.repo.stop(run_id, "failed", "OPTIMIZATION_INTERNAL_ERROR")
        finally:
            saved = self.repo.get(run_id)
            self.metrics(saved, started)
            self.repo.save(saved, terminal=True)

    async def optimize_group(self, run, group, campaign, budget):
        baseline = group.baseline
        calls = []
        baseline_report = self.report(campaign, baseline, baseline.template)
        run.phase = "verify original baseline"
        self.repo.save(run)
        if baseline_report.status == "BLOCKED":
            group.stop_reason = "BASELINE_GUARDIAN_BLOCK"
            self.repo.save(run)
            return
        group.baseline_audit = await self.audit_report(
            campaign, baseline_report, baseline.language, baseline.channel, budget, calls, run
        )
        group.final_audit = group.baseline_audit
        self.repo.save(run)
        if group.baseline_audit.status != "PASS":
            group.stop_reason = "BASELINE_AUDIT_" + group.baseline_audit.status
            self.repo.save(run)
            return
        for number in range(1, run.max_rounds + 1):
            budget.check(self.client.clock.now())
            round_start = self.client.clock.now()
            item = Round(number=number, candidate_id=digest([run.id, baseline.id, number]))
            group.rounds.append(item)
            run.phase = "critique"
            data = {
                "template": group.current_template.model_dump(),
                "slots": slot_inventory(campaign, baseline.language),
                "allowed_paths": EDIT_PATHS,
                "language": baseline.language,
                "channel": baseline.channel,
                "features": [f.model_dump() for f in group.current_score.features],
                "persona_feedback": [
                    {"persona_id": v.persona_id, "outcome": v.outcome}
                    for v in group.current_score.votes
                ],
                "rejected_reasons": [r.reasons for r in group.rounds if not r.accepted],
                "remaining_rounds": run.max_rounds - number + 1,
            }
            plan = self.repo.generation.plan(campaign.id, campaign.revision)
            audience = next(a for a in plan.audiences if a.id == baseline.audience_id)
            data["preferences"] = {
                key: getattr(audience, key) for key in ["segment", "motivation", "angle", "tone"]
            }
            critique, _ = await self.role(
                "R6", data, CritiqueResult, budget, run.context_hash, item.calls, run
            )
            if not critique:
                item.reasons, group.stop_reason = ["CRITIQUE_UNAVAILABLE"], "CRITIQUE_UNAVAILABLE"
                item.elapsed_ms = max(0.0, (self.client.clock.now() - round_start) * 1000)
                self.repo.save(run)
                break
            item.critique, item.edits = critique.critique, critique.edits
            try:
                candidate = apply_edits(group.current_template, critique)
            except (ProviderError, ValueError):
                item.reasons, group.stop_reason = ["IMMUTABLE_OR_INVALID_EDIT"], "EDIT_REJECTED"
                item.elapsed_ms = max(0.0, (self.client.clock.now() - round_start) * 1000)
                self.repo.save(run)
                break
            item.candidate_template = candidate
            if critique.no_change or candidate == group.current_template:
                item.reasons, group.stop_reason = ["NO_CHANGE"], "NO_GAIN"
                item.elapsed_ms = max(0.0, (self.client.clock.now() - round_start) * 1000)
                self.repo.save(run)
                break
            run.phase = "verify permitted edit"
            report = self.report(campaign, baseline, candidate)
            item.guardian = report
            self.repo.save(run)
            if report.status == "BLOCKED":
                item.reasons, group.stop_reason = ["GUARDIAN_BLOCK"], "NO_GAIN"
                item.elapsed_ms = max(0.0, (self.client.clock.now() - round_start) * 1000)
                self.repo.save(run)
                break  # never spend judge calls on a deterministic block
            item.audit = await self.audit_report(
                campaign, report, baseline.language, baseline.channel, budget, item.calls, run
            )
            item.guardian = item.audit.guardian
            if item.audit.status != "PASS":
                item.reasons, group.stop_reason = ["AUDIT_" + item.audit.status], "NO_GAIN"
                item.elapsed_ms = max(0.0, (self.client.clock.now() - round_start) * 1000)
                self.repo.save(run)
                break
            run.phase = "compare against frozen baseline"
            votes = []
            for order in ["AB", "BA"]:
                baseline_fields = baseline_report.rendered.fields
                candidate_fields = report.rendered.fields
                data = {
                    "personas": [p.model_dump() for p in run.personas],
                    "language": baseline.language,
                    "channel": baseline.channel,
                    "X": baseline_fields if order == "AB" else candidate_fields,
                    "Y": candidate_fields if order == "AB" else baseline_fields,
                }
                judged, evidence = await self.role(
                    "R5",
                    data,
                    JudgeResult,
                    budget,
                    digest([run.context_hash, run.persona_hash, run.baseline_hash]),
                    item.calls,
                    run,
                )
                votes += map_votes(
                    judged, run.personas, order, baseline.id, item.candidate_id, evidence.error_code
                )
            item.score = score(features(item.audit.guardian, baseline.channel), votes)
            item.reasons = acceptance(group.current_score, item.score, item.guardian, item.audit)
            item.accepted = not item.reasons
            run.phase = "accept" if item.accepted else "reject"
            if item.accepted:
                group.current_id, group.current_template, group.current_score = (
                    item.candidate_id,
                    candidate,
                    item.score,
                )
                group.final_audit = item.audit
                item.reasons = ["SIX_WEIGHTED_WINS_FEATURE_DROP_LT3_STRICT_GAIN_ZERO_BLOCK"]
            else:
                group.stop_reason = "NO_GAIN"
            item.elapsed_ms = max(0.0, (self.client.clock.now() - round_start) * 1000)
            self.repo.save(run)
            if not item.accepted:
                break
        if group.stop_reason is None:
            group.stop_reason = "ROUND_LIMIT"
        self.repo.save(run)

    async def audit_poster(self, asset_id, revision):
        poster = self.art.poster(asset_id)
        campaign = self.repo.generation.locked(poster.campaign_id, revision)
        if poster.campaign_revision != revision or poster.status != "ready":
            raise domain_error("REVISION_CONFLICT", "Poster is stale")
        from backend.art_storage import ArtStorage

        ArtStorage(self.client.settings.asset_path).read(
            poster.sha256
        )  # actual persisted byte hash
        expected = poster.guardian.rendered.fields
        if poster.render_input.fields != expected:
            raise domain_error("ART_BLOCKED", "Rendered text differs from stored provenance")
        budget = self.client.budget(calls=3, seconds=90)
        audit = await self.audit_report(
            campaign,
            poster.guardian,
            poster.render_input.language,
            "poster",
            budget,
            [],
            artifact_hash=poster.sha256,
            poster=poster,
        )
        return audit
