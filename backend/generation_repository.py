"""Short synchronous transactions; asynchronous results compare revisions at commit."""

from backend.contracts import utc_now
from backend.generation_context import dependency_hash
from backend.generation_models import GenerationRun, MatrixSnapshot, StrategyPlan
from backend.intent_rules import digest, domain_error
from backend.repository import CampaignRepository


class GenerationRepository:
    def __init__(self, store):
        self.store = store
        self.db = store.connection
        self.campaigns = CampaignRepository(store)

    def locked(self, campaign_id, revision):
        campaign = self.campaigns.get(campaign_id)
        if campaign.revision != revision:
            raise domain_error("REVISION_CONFLICT", "Campaign changed; reload before generating")
        if campaign.status != "locked":
            raise domain_error(
                "FACTS_INCOMPLETE", "Lock facts and reviewed forms before generating"
            )
        return campaign

    def plan(self, campaign_id, revision):
        row = self.db.execute(
            "SELECT payload FROM strategy_plans WHERE campaign_id=? AND campaign_revision=?",
            (campaign_id, revision),
        ).fetchone()
        return StrategyPlan.model_validate_json(row[0]) if row else None

    def save_plan(self, plan):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            campaign = self.locked(plan.campaign_id, plan.campaign_revision)
            if dependency_hash(campaign) != plan.dependency_hash:
                raise domain_error("REVISION_CONFLICT", "Strategy dependencies changed")
            self.db.execute(
                "INSERT OR IGNORE INTO strategy_plans VALUES(?,?,?,?)",
                (plan.id, plan.campaign_id, plan.campaign_revision, plan.model_dump_json()),
            )
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise
        return self.plan(plan.campaign_id, plan.campaign_revision)

    def duplicate(self, campaign_id, request):
        row = self.db.execute(
            "SELECT request_hash,payload FROM generation_runs "
            "WHERE campaign_id=? AND idempotency_key=?",
            (campaign_id, request.idempotency_key),
        ).fetchone()
        if not row:
            return None
        accepted_hashes = {digest(request.model_dump())}
        if request.retry_source_run_id is None:
            # Pre-B7 keys did not contain this optional field. Preserve their binding.
            accepted_hashes.add(digest(request.model_dump(exclude={"retry_source_run_id"})))
        if row[0] not in accepted_hashes:
            raise domain_error(
                "IDEMPOTENCY_CONFLICT", "Generation key already binds another selection"
            )
        return GenerationRun.model_validate_json(row[1])

    def create(self, run):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self.locked(run.campaign_id, run.campaign_revision)
            self.db.execute(
                "INSERT INTO generation_runs VALUES(?,?,?,?,?,?)",
                (
                    run.id,
                    run.campaign_id,
                    run.request.idempotency_key,
                    digest(run.request.model_dump()),
                    run.status,
                    run.model_dump_json(),
                ),
            )
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def get(self, run_id):
        row = self.db.execute(
            "SELECT payload FROM generation_runs WHERE id=?", (run_id,)
        ).fetchone()
        if not row:
            raise domain_error("GENERATION_NOT_FOUND", "Generation run not found")
        return GenerationRun.model_validate_json(row[0])

    def save(self, run, *, terminal=False):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            if not terminal:
                if self.get(run.id).status in {"cancelled", "interrupted", "stale"}:
                    raise domain_error(
                        "WORK_STOPPED", "Stopped generation cannot commit late output"
                    )
                campaign = self.locked(run.campaign_id, run.campaign_revision)
                plan = self.plan(run.campaign_id, run.campaign_revision)
                if plan is None or dependency_hash(campaign) != plan.dependency_hash:
                    raise domain_error("REVISION_CONFLICT", "Generation dependencies changed")
            run.updated_at = utc_now()
            for cell in run.cells:
                if cell.variant and (cell.state == "ready" or run.status in {"partial", "failed"}):
                    self.db.execute(
                        "INSERT OR IGNORE INTO baseline_variants VALUES(?,?,?,?,?,?)",
                        (
                            cell.variant.id,
                            run.id,
                            cell.audience_id,
                            cell.language,
                            cell.channel,
                            cell.variant.model_dump_json(),
                        ),
                    )
            self.db.execute(
                "UPDATE generation_runs SET status=?,payload=? WHERE id=?",
                (run.status, run.model_dump_json(), run.id),
            )
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

        if getattr(self.store, "work", None):
            ready = sum(c.state == "ready" for c in run.cells)
            message = f"Generation {run.status}: {ready}/{len(run.cells)} drafts saved."
            if run.error_code:
                message += f" Stop: {run.error_code}."
            self.store.work.event(
                run.campaign_id,
                "generation",
                message,
                fingerprint=digest([run.id, run.status, ready, run.calls_used, run.error_code]),
                run_id=run.id,
            )

    def stop(self, run_id, status, code):
        # Reload persisted progress, discarding any late uncommitted provider result.
        run = self.get(run_id)
        run.status, run.error_code = status, code
        for cell in run.cells:
            if status == "stale":
                cell.state = "stale"
                if cell.variant:
                    cell.variant.status = "stale"
            elif cell.state in {"queued", "running"}:
                cell.state = "blocked"
            if cell.state != "ready":
                cell.reasons = [code]
        self.save(run, terminal=True)

    def recover(self):
        ids = [
            r[0]
            for r in self.db.execute(
                "SELECT id FROM generation_runs WHERE status IN ('queued','running')"
            )
        ]
        for run_id in ids:
            self.stop(run_id, "interrupted", "PROCESS_RESTARTED")

    def matrix(self, campaign_id):
        campaign = self.campaigns.get(campaign_id)
        row = self.db.execute(
            "SELECT payload FROM generation_runs WHERE campaign_id=? ORDER BY rowid DESC LIMIT 1",
            (campaign_id,),
        ).fetchone()
        run = GenerationRun.model_validate_json(row[0]) if row else None
        if run and run.campaign_revision != campaign.revision:
            run.status = "stale"
            for cell in run.cells:
                cell.state = "stale"
                if cell.variant:
                    cell.variant.status = "stale"
        return MatrixSnapshot(
            campaign_id=campaign_id,
            campaign_revision=campaign.revision,
            strategy=self.plan(campaign_id, campaign.revision),
            run=run,
        )
