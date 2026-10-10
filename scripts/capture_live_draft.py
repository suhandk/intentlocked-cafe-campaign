"""Capture actual model proposals for the demo; never human sign-off."""

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
from backend.inference_client import InferenceClient
from backend.intent_rules import resolve_dates, today
from backend.schemas import CampaignCreate, DraftRequest, FactInput, IntentRequest, SurfaceRequest


async def main(manual=False):
    config = Settings(
        inference_mode="live",
        database_path=Path("data/b8-live-campaign.sqlite3"),
        asset_path=Path("data/b8-live-campaign-assets"),
        demo_fast=True,
        structured_strategy="json",
    )
    store = Store(config.database_path)
    client = InferenceClient(config, store)
    service = CampaignService(store, client, config)
    prior_call_ids = {c.id for c in store.calls()}
    report = {
        "mode": "live",
        "provider": "Configured provider",
        "captured_at": utc_now(),
        "scenario": "Hypothetical M0 broad-offer demo, not a real business assertion",
        "owner_lock": "PENDING",
        "native_review": "PENDING",
        "full_workflow": "PENDING",
        "structured_strategy": "json",
    }
    started = time.monotonic()
    try:
        campaign = service.repo.create(
            CampaignCreate(
                languages=["en", "kn", "kn-Latn"], channels=["instagram", "whatsapp", "facebook"]
            ),
            "live",
            today().isoformat(),
            False,
        )
        report["campaign_id"] = campaign.id
        brief = "Café name: Namma Cafe. Bengaluru alli coffee mele 20% off ee weekend. "
        brief += "Students ge focus maadona."
        if not manual:
            campaign = await service.intent(
                campaign.id, IntentRequest(expected_revision=campaign.revision, transcript=brief)
            )
        report["ambiguous_brief"] = brief
        report["clarification_questions"] = [q.model_dump() for q in campaign.clarifications]
        # The M0 broad scenario explicitly defines all-person eligibility and student targeting.
        clarified = (
            brief + " Offer ellarigu, open to all. Students are the initial marketing target, "
            "not an eligibility restriction."
        )
        if manual:
            dates = resolve_dates("ee weekend", today())
            supplied = {
                "CAFE": {"kind": "text", "value": "Namma Cafe"},
                "LOCATION": {"kind": "text", "value": "Bengaluru"},
                "PRODUCT": {"kind": "text", "value": "coffee"},
                "OFFER": {"kind": "percent_off", "value": 20},
                "ELIGIBILITY": {"kind": "eligibility", "scope": "all"},
                "DATES": dates.model_dump(),
            }
            campaign = service.draft(
                campaign.id,
                DraftRequest(
                    expected_revision=campaign.revision,
                    facts=[FactInput(key=k, canonical=v) for k, v in supplied.items()],
                    languages=campaign.languages,
                    channels=campaign.channels,
                    target_audiences=["students"],
                    brand=campaign.brand,
                ),
            )
            report["canonical_source"] = (
                "Explicit operator-entered M0 hypothetical facts; R1 did not supply these"
            )
            report["R1_acceptance"] = (
                "FAILED separately; manual editor fallback selected explicitly"
            )
        else:
            campaign = await service.intent(
                campaign.id,
                IntentRequest(expected_revision=campaign.revision, transcript=clarified),
            )
        report["clarified_brief"] = clarified
        expected = {
            f.key: f.canonical.model_dump() if f.canonical else None for f in campaign.facts
        }
        assert expected["CAFE"]["value"] == "Namma Cafe"
        assert expected["LOCATION"]["value"] == "Bengaluru"
        assert expected["PRODUCT"]["value"] == "coffee"
        assert expected["OFFER"]["kind"] == "percent_off" and expected["OFFER"]["value"] == 20
        assert expected["ELIGIBILITY"]["scope"] == "all"
        campaign = await service.surfaces(
            campaign.id, SurfaceRequest(expected_revision=campaign.revision, confirm_canonical=True)
        )
        report.update(
            status="PROPOSED_FOR_OWNER_REVIEW",
            campaign=campaign.model_dump(),
            final_owner_lock_performed=False,
        )
        text = [
            "# Genuine Configured provider demo proposal — owner review pending",
            "",
            "This is a hypothetical M0 demo. LIVE R1/R2 output; "
            "owner lock and native sign-off remain pending.",
            "",
            f"Campaign: `{campaign.id}` · revision {campaign.revision} · "
            f"captured {report['captured_at']}",
            "",
            "Confirm the café, location, 20% coffee offer, open-to-all eligibility, "
            "student targeting and dates, then review every form before lock.",
            "",
        ]
        for fact in campaign.facts:
            text += [
                f"## {fact.key}",
                "",
                json.dumps(
                    fact.canonical.model_dump() if fact.canonical else None, ensure_ascii=False
                ),
                "",
            ]
            for language, cases in fact.surface.items():
                text += [
                    f"- {language}: "
                    + "; ".join(
                        f"{case}: {' / '.join(words)}"
                        for case, words in cases.model_dump().items()
                        if words
                    )
                ]
            text.append("")
        Path("docs/LIVE_DEMO_OWNER_REVIEW.md").write_text("\n".join(text), encoding="utf-8")
    except ProviderError as exc:
        report.update(status="FAILED", code=exc.body.code)
    except AssertionError:
        report.update(
            status="NEEDS_CANONICAL_REVIEW",
            reason="Configured provider proposal differs from the explicit M0 demo facts",
        )
    finally:
        report["elapsed_seconds"] = round(time.monotonic() - started, 2)
        report["calls"] = [c.model_dump() for c in store.calls() if c.id not in prior_call_ids]
        Path("docs/evidence/b8-live-draft.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(
            json.dumps(
                {
                    k: v
                    for k, v in report.items()
                    if k not in {"campaign", "calls", "clarification_questions"}
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        await client.close()
        store.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--manual-demo-facts", action="store_true")
    asyncio.run(main(parser.parse_args().manual_demo_facts))
