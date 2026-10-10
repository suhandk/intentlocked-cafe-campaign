import json

import httpx
import pytest

from backend.campaign_service import CampaignService
from backend.errors import ProviderError
from backend.mock import handler
from backend.schemas import CampaignCreate, IntentRequest, SurfaceRequest
from backend.surface_policy import surface_wire_schema
from backend.tests.test_work import done, request, setup
from backend.work_models import WorkRetry

BRIEF = "Café name: Namma Cafe. Bengaluru. 20% off coffee this weekend. Open to all."


async def draft(client, languages=None):
    service = CampaignService(client.store, client, client.settings)
    campaign = service.repo.create(
        CampaignCreate(languages=languages or ["en"]), "mock", "2026-10-10", True
    )
    campaign = await service.intent(
        campaign.id, IntentRequest(expected_revision=1, transcript=BRIEF)
    )
    return service, campaign


def mutate_surface(req, mutate):
    value = handler(req).json()
    choice = value["choices"][0]
    if "tools" in json.loads(req.content):
        target = choice["message"]["tool_calls"][0]["function"]
        parsed = json.loads(target["arguments"])
        mutate(parsed["result"])
        target["arguments"] = json.dumps(parsed)
    else:
        parsed = json.loads(choice["message"]["content"])
        mutate(parsed["result"])
        choice["message"]["content"] = json.dumps(parsed)
    return httpx.Response(200, json=value)


async def test_surface_wire_binds_selected_languages_known_facts_cases_and_typed_values(factory):
    client = factory()
    _, campaign = await draft(client, ["en", "kn", "kn-Latn"])
    wire = surface_wire_schema(campaign)
    assert "$ref" not in json.dumps(wire) and "$defs" not in json.dumps(wire)
    outcomes = wire["properties"]["result"]["oneOf"]
    assert {v["properties"]["status"]["const"] for v in outcomes} == {
        "success",
        "needs_input",
        "error",
    }
    forms = outcomes[0]["properties"]["forms"]
    variants = forms["items"]["oneOf"]
    assert (
        forms["minItems"]
        == forms["maxItems"]
        == sum(f.canonical is not None for f in campaign.facts)
    )
    assert {v["properties"]["key"]["const"] for v in variants} == {
        f.key for f in campaign.facts if f.canonical
    }
    for variant in variants:
        surface = variant["properties"]["surface"]
        assert set(surface["properties"]) == set(surface["required"]) == set(campaign.languages)
        assert surface["additionalProperties"] is False
        assert "dat" not in surface["properties"]
        if variant["properties"]["key"]["const"] in {"CAFE", "PRODUCT", "LOCATION"}:
            assert surface["properties"]["en"]["required"] == ["nom"]
            assert surface["properties"]["kn"]["required"] == ["nom", "dat", "gen", "loc"]
            assert surface["properties"]["kn"]["properties"]["dat"]["type"] == "array"
    offer = next(v for v in variants if v["properties"]["key"]["const"] == "OFFER")
    assert offer["properties"]["surface"]["properties"]["en"]["properties"]["nom"]["const"] == [
        "20% off"
    ]
    await client.close()


@pytest.mark.parametrize("strategy", ["json", "tools"])
async def test_wrong_surface_nesting_is_repaired_before_forms_persist(factory, strategy):
    surfaces = 0
    captured = []

    def transport(req):
        nonlocal surfaces
        body = json.loads(req.content)
        if "ROLE: R2" in body["messages"][0]["content"]:
            surfaces += 1
            captured.append(body)
            if surfaces == 1:
                return mutate_surface(
                    req, lambda result: result["forms"][0]["surface"].update(dat=[], gen=[], loc=[])
                )
        return handler(req)

    client = factory(transport, structured_strategy=strategy)
    service, campaign = await draft(client)
    result = await service.surfaces(
        campaign.id, SurfaceRequest(expected_revision=campaign.revision, confirm_canonical=True)
    )
    assert surfaces == 2
    assert result.revision == campaign.revision + 2 and result.status == "forms_review"
    assert all(set(f.surface) == {"en"} for f in result.facts if f.canonical)
    assert next(f for f in result.facts if f.key == "ID_RULE").canonical is None
    repair = json.loads(captured[1]["messages"][-1]["content"])
    assert repair["validation_errors"] and "20%" not in json.dumps(repair)
    assert client.store.connection.execute("SELECT COUNT(*) FROM approvals").fetchone()[0] == 0
    await client.close()


async def test_true_failure_preserves_confirmed_facts_and_stale_generic_retry_is_rejected(factory):
    def transport(req):
        if "ROLE: R2" not in json.loads(req.content)["messages"][0]["content"]:
            return handler(req)
        return mutate_surface(
            req,
            lambda result: (
                result.clear(),
                result.update(status="error", reason="uncertain_forms"),
            ),
        )

    client = factory(transport)
    service, campaign = await draft(client)
    work = setup(client, campaign, seed_campaign=False)
    job = await done(
        work, work.start(campaign.id, request(campaign, "forms", confirm_canonical=True))
    )
    assert job.status == "failed" and job.error_code == "SURFACES_UNAVAILABLE"
    assert "Canonical confirmation is saved" in job.notices[0]
    current = service.repo.get(campaign.id)
    assert current.revision == campaign.revision + 1 and current.status == "canonical_confirmed"
    assert current.facts == campaign.facts
    assert all(not f.surface for f in current.facts)
    before = len(client.store.calls())
    with pytest.raises(ProviderError) as caught:
        work.retry(
            job.id,
            WorkRetry(
                expected_revision=job.campaign_revision, idempotency_key="must-review-new-revision"
            ),
        )
    assert caught.value.body.code == "REVISION_CONFLICT"
    assert len(client.store.calls()) == before
    await client.close()


@pytest.mark.parametrize("attack", ["missing_kn", "extra_unknown", "wrong_offer", "lock"])
async def test_invalid_wording_never_locks_and_stops_after_two_repairs(factory, attack):
    def transport(req):
        if "ROLE: R2" not in json.loads(req.content)["messages"][0]["content"]:
            return handler(req)

        def corrupt(result):
            if attack == "missing_kn":
                del result["forms"][0]["surface"]["kn"]
            elif attack == "extra_unknown":
                result["forms"].append(
                    {
                        "key": "ID_RULE",
                        "surface": {
                            "en": {"nom": ["No ID required"]},
                            "kn": {"nom": ["No ID required"]},
                        },
                    }
                )
            elif attack == "wrong_offer":
                next(f for f in result["forms"] if f["key"] == "OFFER")["surface"]["en"]["nom"] = [
                    "25% off"
                ]
            else:
                result["status"] = "locked"

        return mutate_surface(req, corrupt)

    client = factory(transport)
    service, campaign = await draft(client, ["en", "kn"])
    before = len(client.store.calls())
    with pytest.raises(ProviderError) as caught:
        await service.surfaces(
            campaign.id, SurfaceRequest(expected_revision=campaign.revision, confirm_canonical=True)
        )
    assert caught.value.body.code in {"FORMS_INVALID", "SCHEMA_INVALID"}
    assert len(client.store.calls()) == before + 3
    current = service.repo.get(campaign.id)
    assert current.status == "canonical_confirmed" and current.facts == campaign.facts
    assert client.store.connection.execute("SELECT COUNT(*) FROM approvals").fetchone()[0] == 0
    await client.close()
