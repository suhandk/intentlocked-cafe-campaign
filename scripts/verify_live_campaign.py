"""Live integration evidence, with an explicitly simulated owner for test data only.

Never a human/native sign-off or approval of an actual business campaign.
"""

import argparse
import asyncio
import json
import time
from pathlib import Path

from backend.campaign_service import CampaignService
from backend.config import Settings
from backend.contracts import utc_now
from backend.db import Store
from backend.errors import ProviderError
from backend.generation_models import GenerateRequest
from backend.generation_service import GenerationService
from backend.inference_client import InferenceClient
from backend.intent_rules import today
from backend.schemas import (
    CampaignCreate,
    DraftRequest,
    FactSurface,
    IntentRequest,
    LockRequest,
    SurfaceRequest,
)


async def main(resume=None, matrix=False, strategy="tools", retry_run=None):
    settings = Settings(
        inference_mode="live",
        database_path=Path("data/b8-live-campaign.sqlite3"),
        asset_path=Path("data/b8-live-campaign-assets"),
        structured_strategy=strategy,
    )
    store = Store(settings.database_path)
    client = InferenceClient(settings, store)
    campaigns = CampaignService(store, client, settings)
    generation = GenerationService(store, client)
    prior = {c.id for c in store.calls()}
    started = time.monotonic()
    report = {
        "captured_at": utc_now(),
        "mode": "live",
        "provider": "Configured provider",
        "structured_strategy": strategy,
        "scenario": "Hypothetical integration test, not a real business campaign",
        "owner_actions": "SIMULATED_TEST_OPERATOR",
        "human_signoff": "PENDING",
        "native_review": "PENDING",
        "stages": {},
    }
    capture_id = str(time.time_ns())

    def save():
        report["elapsed_seconds"] = round(time.monotonic() - started, 2)
        report["calls"] = [c.model_dump() for c in store.calls() if c.id not in prior]
        encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        Path("docs/evidence/live-campaign-repair.json").write_text(encoded, encoding="utf-8")
        Path(f"docs/evidence/live-campaign-repair-{capture_id}.json").write_text(
            encoded, encoding="utf-8"
        )

    try:
        if resume:
            campaign = campaigns.repo.get(resume)
            report["R1_source"] = "Persisted genuine live proposal from earlier capture"
        else:
            campaign = campaigns.repo.create(
                CampaignCreate(
                    languages=["en", "kn", "kn-Latn"],
                    channels=["instagram", "whatsapp", "facebook"],
                ),
                "live",
                today().isoformat(),
                False,
            )
            brief = (
                "Café name: Namma Cafe. Bengaluru alli coffee mele 20% off ee weekend. "
                "Students ge focus maadona. Offer ellarigu, open to all. "
                "Students are the marketing target, not an eligibility restriction."
            )
            campaign = await campaigns.intent(
                campaign.id,
                IntentRequest(expected_revision=campaign.revision, transcript=brief),
            )
            report["R1_source"] = "Fresh genuine live proposal"
        report["campaign_id"] = campaign.id
        facts = {f.key: f.canonical for f in campaign.facts}
        assert facts["CAFE"].value == "Namma Cafe"
        assert facts["LOCATION"].value == "Bengaluru"
        assert facts["PRODUCT"].value == "coffee"
        assert facts["OFFER"].kind == "percent_off" and facts["OFFER"].value == 20
        assert facts["ELIGIBILITY"].scope == "all"
        report["stages"]["R1"] = "PASS"
        # Test operator explicitly checks the hypothetical canonical values above.
        # Use the same public draft/confirmation path as the UI, never skip a gate.
        if campaign.status == "draft":
            report["reviewed_test_warnings"] = [w.model_dump() for w in campaign.warnings]
            campaign = campaigns.draft(
                campaign.id,
                DraftRequest(
                    expected_revision=campaign.revision,
                    facts=[
                        {"key": f.key, "canonical": f.canonical}
                        for f in campaign.facts
                        if f.key != "DAYS"
                    ],
                    languages=campaign.languages,
                    channels=campaign.channels,
                    target_audiences=campaign.target_audiences,
                    brand=campaign.brand,
                    acknowledged_warning_ids=[w.id for w in campaign.warnings],
                ),
            )
        if campaign.status in {"draft", "canonical_confirmed"}:
            campaign = await campaigns.surfaces(
                campaign.id,
                SurfaceRequest(expected_revision=campaign.revision, confirm_canonical=True),
            )
        report["stages"]["R2"] = "PASS"
        report["campaign"] = campaign.model_dump()
        save()
        print("R1/R2 PASS; genuine live forms stored; human/native review pending", flush=True)
        if matrix:
            if campaign.status != "locked":
                campaign = campaigns.lock(
                    campaign.id,
                    LockRequest(
                        expected_revision=campaign.revision,
                        idempotency_key="live-integration-test-" + campaign.id,
                        reviewed_fact_versions={f.key: f.version for f in campaign.facts},
                        forms=[
                            FactSurface(key=f.key, surface=f.surface)
                            for f in campaign.facts
                            if f.canonical
                        ],
                        approve_canonical_and_forms=True,
                        acknowledged_warning_ids=[w.id for w in campaign.warnings],
                    ),
                )
            report["stages"]["test_lock"] = "PASS_SIMULATED_OWNER"
            report["campaign"] = campaign.model_dump()
            plan = await generation.strategy(campaign.id, campaign.revision)
            report["stages"]["R3"] = "PASS"
            save()
            run = generation.start(
                campaign.id,
                GenerateRequest(
                    expected_revision=campaign.revision,
                    strategy_id=plan.id,
                    idempotency_key="live-integration-matrix-" + str(time.time_ns()),
                    audience_ids=[a.id for a in plan.audiences],
                    languages=campaign.languages,
                    channels=campaign.channels,
                    retry_source_run_id=retry_run,
                ),
            )
            await generation.tasks[run.id]
            run = generation.repo.get(run.id)
            report["run"] = run.model_dump()
            report["stages"]["R4_matrix"] = {
                "status": run.status,
                "ready": sum(c.state == "ready" for c in run.cells),
                "total": len(run.cells),
            }
        report["status"] = "CAPTURED"
    except ProviderError as exc:
        report.update(status="BLOCKED", error=exc.body.model_dump())
    except (AssertionError, AttributeError):
        report.update(status="BLOCKED", error="Live canonical facts differ from test expectations")
    finally:
        save()
        print(
            json.dumps(
                {k: v for k, v in report.items() if k not in {"calls", "campaign", "run"}}, indent=2
            )
        )
        await generation.close()
        await client.close()
        store.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume")
    parser.add_argument("--matrix", action="store_true")
    parser.add_argument("--strategy", choices=["tools", "json"], default="tools")
    parser.add_argument("--retry-run")
    args = parser.parse_args()
    asyncio.run(main(args.resume, args.matrix, args.strategy, args.retry_run))
