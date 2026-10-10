"""Persist bounded progress, frozen inputs, audit evidence and exact-key role cache."""

import json

from backend.contracts import TraceEvent, utc_now
from backend.generation_repository import GenerationRepository
from backend.intent_rules import digest, domain_error
from backend.optimization_models import Audit, OptimizationRun, OptimizationSnapshot


class OptimizationRepository:
    def __init__(self, store):
        self.store = store
        self.db = store.connection
        self.generation = GenerationRepository(store)

    def get(self, run_id):
        row = self.db.execute(
            "SELECT payload FROM optimization_runs WHERE id=?", (run_id,)
        ).fetchone()
        if not row:
            raise domain_error("OPTIMIZATION_NOT_FOUND", "Optimization run not found")
        return OptimizationRun.model_validate_json(row[0])

    def current(self, run):
        campaign = self.generation.locked(run.campaign_id, run.campaign_revision)
        if digest(campaign.model_dump()) != run.context_hash:
            raise domain_error("REVISION_CONFLICT", "Optimization context changed; reload")
        return campaign

    def duplicate(self, campaign_id, request):
        row = self.db.execute(
            "SELECT request_hash,payload FROM optimization_runs "
            "WHERE campaign_id=? AND idempotency_key=?",
            (campaign_id, request.idempotency_key),
        ).fetchone()
        if row and row[0] != digest(request.model_dump()):
            raise domain_error("IDEMPOTENCY_CONFLICT", "Optimization key binds another request")
        return OptimizationRun.model_validate_json(row[1]) if row else None

    def create(self, run):
        with self.db:
            self.current(run)
            self.db.execute(
                "INSERT INTO optimization_runs VALUES(?,?,?,?,?,?)",
                (
                    run.id,
                    run.campaign_id,
                    run.request.idempotency_key,
                    digest(run.request.model_dump()),
                    run.status,
                    run.model_dump_json(),
                ),
            )

    def save(self, run, terminal=False):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            if not terminal:
                self.current(run)
            old = self.get(run.id)
            if not terminal and old.status in {"cancelled", "interrupted", "stale"}:
                raise domain_error("WORK_STOPPED", "Stopped optimization cannot commit late output")
            frozen = [
                "context_hash",
                "personas",
                "persona_hash",
                "baseline_hash",
                "prompt_hashes",
                "model",
                "max_rounds",
                "max_calls",
                "max_steps",
                "deadline_at",
                "request",
            ]
            if any(getattr(old, key) != getattr(run, key) for key in frozen) or [
                (g.baseline, g.baseline_score) for g in old.groups
            ] != [(g.baseline, g.baseline_score) for g in run.groups]:
                raise domain_error("REVISION_CONFLICT", "Frozen optimization inputs were modified")
            run.updated_at = utc_now()
            self.db.execute(
                "UPDATE optimization_runs SET status=?,payload=? WHERE id=?",
                (run.status, run.model_dump_json(), run.id),
            )
            if old.phase != run.phase or old.status != run.status:
                event = TraceEvent(
                    id=0,
                    trace_id=run.id,
                    run_id=run.id,
                    timestamp=utc_now(),
                    stage="B5",
                    campaign_id=run.campaign_id,
                    revision=run.campaign_revision,
                    event="optimization." + run.phase.replace(" ", "_"),
                    message=f"Optimization {run.phase}; status {run.status}.",
                )
                self.db.execute(
                    "INSERT INTO trace_events(run_id,payload) VALUES(?,?)",
                    (run.id, event.model_dump_json()),
                )
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

        if getattr(self.store, "work", None):
            self.store.work.event(
                run.campaign_id,
                "optimization",
                f"Optimization {run.phase}; {run.status}. Stop: {run.stop_reason or 'pending'}.",
                fingerprint=digest(
                    [run.id, run.phase, run.status, run.stop_reason, run.calls_used]
                ),
                run_id=run.id,
            )

    def stop(self, run_id, status, reason):
        run = self.get(run_id)  # discard any late, uncommitted async result
        run.status, run.stop_reason, run.phase = status, reason, "stopped"
        self.save(run, terminal=True)

    def recover(self):
        for (run_id,) in self.db.execute(
            "SELECT id FROM optimization_runs WHERE status IN ('queued','running')"
        ).fetchall():
            self.stop(run_id, "interrupted", "PROCESS_RESTARTED")

    def cache(self, key):
        row = self.db.execute(
            "SELECT payload FROM inference_cache WHERE cache_key=?", (key,)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def cache_save(self, key, payload):
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO inference_cache VALUES(?,?)", (key, json.dumps(payload))
            )

    def save_audit(self, audit):
        with self.db:
            self.generation.locked(audit.campaign_id, audit.campaign_revision)
            self.db.execute(
                "INSERT INTO semantic_audits VALUES(?,?,?,?)",
                (audit.id, audit.campaign_id, audit.content_hash, audit.model_dump_json()),
            )
        return audit

    def audit(self, audit_id):
        row = self.db.execute(
            "SELECT payload FROM semantic_audits WHERE id=?", (audit_id,)
        ).fetchone()
        if not row:
            raise domain_error("OPTIMIZATION_NOT_FOUND", "Audit not found")
        audit = Audit.model_validate_json(row[0])
        self.generation.locked(audit.campaign_id, audit.campaign_revision)
        return audit

    def snapshot(self, campaign_id):
        matrix = self.generation.matrix(campaign_id)
        runs = [
            OptimizationRun.model_validate_json(r[0])
            for r in self.db.execute(
                "SELECT payload FROM optimization_runs WHERE campaign_id=? "
                "ORDER BY rowid DESC LIMIT 10",
                (campaign_id,),
            )
        ]
        for run in runs:
            if run.campaign_revision != matrix.campaign_revision:
                run.status, run.stop_reason = "stale", "REVISION_CONFLICT"
        scored = {g.baseline.id for run in runs if run.status != "stale" for g in run.groups}
        variants = (
            [c.variant.id for c in matrix.run.cells if c.state == "ready" and c.variant]
            if matrix.run
            else []
        )
        return OptimizationSnapshot(
            runs=runs, unscored_variant_ids=[v for v in variants if v not in scored]
        )
