"""No await inside transactions. Compare revision again after every provider call."""

from collections.abc import Callable
from contextlib import nullcontext
from uuid import uuid4

from backend.contracts import utc_now
from backend.db import Store
from backend.intent_rules import digest, domain_error, prerequisites
from backend.schemas import KEYS, BrandKit, Campaign, CampaignCreate, Fact


class CampaignRepository:
    def __init__(self, store: Store):
        self.db = store.connection

    def get(self, campaign_id: str) -> Campaign:
        row = self.db.execute("SELECT payload FROM campaigns WHERE id=?", (campaign_id,)).fetchone()
        if not row:
            raise domain_error("CAMPAIGN_NOT_FOUND", "Campaign not found")
        return Campaign.model_validate_json(row[0])

    def create(
        self,
        request: CampaignCreate,
        mode: str,
        reference: str,
        demo: bool,
        *,
        transaction_owned: bool = False,
    ) -> Campaign:
        if len(set(request.languages)) != len(request.languages) or len(
            set(request.channels)
        ) != len(request.channels):
            raise domain_error("DUPLICATE_SELECTION", "Languages and channels must be unique")
        campaign = Campaign(
            id=uuid4().hex,
            revision=1,
            status="draft",
            mode=mode,
            languages=request.languages,
            channels=request.channels,
            target_audiences=[],
            transcript="",
            facts=[
                Fact(
                    key=key,
                    canonical=None,
                    version=1,
                    status="not_specified",
                    source="unspecified",
                    canonical_hash=digest(None),
                )
                for key in KEYS
            ],
            brand=BrandKit(),
            brand_revision=1,
            warnings=[],
            clarifications=[],
            acknowledged_warning_ids=[],
            reference_date=reference,
            demo_clock=demo,
        )
        campaign.clarifications = prerequisites(campaign)
        with nullcontext() if transaction_owned else self.db:
            self.db.execute(
                "INSERT INTO campaigns VALUES(?,?,?,?)",
                (campaign.id, 1, "draft", campaign.model_dump_json()),
            )
            self.write_facts(campaign, [])
            self.db.execute(
                "INSERT INTO brand_kits VALUES(?,?,?)",
                (campaign.id, 1, campaign.brand.model_dump_json()),
            )
        return campaign

    def write_facts(self, campaign: Campaign, previous: list[Fact]):
        old = {f.key: f for f in previous}
        for fact in campaign.facts:
            if fact.key not in old or fact.version != old[fact.key].version:
                self.db.execute(
                    "INSERT INTO fact_versions VALUES(?,?,?,?)",
                    (campaign.id, fact.key, fact.version, fact.model_dump_json()),
                )

    def check(self, campaign: Campaign, revision: int):
        if campaign.revision != revision:
            raise domain_error(
                "REVISION_CONFLICT",
                "This draft changed. Reload and review the latest revision.",
                expected_revision=revision,
                current_revision=campaign.revision,
            )
        if campaign.status == "locked":
            raise domain_error(
                "FACTS_LOCKED", "Locked facts require the later confirmed change workflow"
            )

    def commit(
        self,
        campaign_id: str,
        revision: int,
        edit: Callable[[Campaign], None],
        *,
        lock_key: str | None = None,
        request_hash: str | None = None,
    ) -> Campaign:
        self.db.execute("BEGIN IMMEDIATE")
        try:
            if lock_key:
                old = self.db.execute(
                    "SELECT request_hash,snapshot FROM approvals "
                    "WHERE campaign_id=? AND idempotency_key=?",
                    (campaign_id, lock_key),
                ).fetchone()
                if old:
                    if old[0] != request_hash:
                        raise domain_error(
                            "IDEMPOTENCY_CONFLICT", "This lock key was used with different content"
                        )
                    self.db.commit()
                    return Campaign.model_validate_json(old[1])
            campaign = self.get(campaign_id)
            self.check(campaign, revision)
            previous = campaign.model_copy(deep=True)
            edit(campaign)
            campaign.revision += 1
            campaign.clarifications = prerequisites(campaign)
            # Validate mutations before writing, not only the original request.
            campaign = Campaign.model_validate_json(campaign.model_dump_json())
            self.write_facts(campaign, previous.facts)
            if previous.brand != campaign.brand:
                campaign.brand_revision += 1
                self.db.execute(
                    "INSERT INTO brand_kits VALUES(?,?,?)",
                    (campaign.id, campaign.brand_revision, campaign.brand.model_dump_json()),
                )
            self.db.execute(
                "UPDATE campaigns SET revision=?,status=?,payload=? WHERE id=? AND revision=?",
                (
                    campaign.revision,
                    campaign.status,
                    campaign.model_dump_json(),
                    campaign.id,
                    revision,
                ),
            )
            if lock_key:
                self.db.execute(
                    "INSERT INTO approvals VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        campaign.facts[0].approval_id,
                        campaign.id,
                        campaign.revision,
                        "fact_lock",
                        lock_key,
                        request_hash,
                        campaign.fact_hash,
                        campaign.approved_at,
                        campaign.model_dump_json(),
                    ),
                )
            self.db.commit()
            return campaign
        except BaseException:
            self.db.rollback()
            raise


def revise_fact(fact: Fact, **changes) -> Fact:
    return Fact.model_validate_json(
        fact.model_copy(update={**changes, "version": fact.version + 1}).model_dump_json()
    )


def approval_stamp() -> tuple[str, str]:
    return uuid4().hex, utc_now()
