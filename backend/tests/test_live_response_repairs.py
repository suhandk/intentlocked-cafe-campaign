import json
from types import SimpleNamespace

import httpx
import pytest

from backend.campaign_service import CampaignService
from backend.errors import ProviderError
from backend.guardian.claims import surface_numeric_valid
from backend.mock import handler
from backend.schemas import CampaignCreate, FactInput, IntentRequest, IntentResult, SurfaceRequest
from backend.surface_policy import surface_constraints


@pytest.mark.parametrize(
    "key,canonical",
    [
        ("OFFER", {"kind": "percent_off", "value": 20}),
        ("OFFER", {"kind": "amount_off", "amount": 50}),
        ("OFFER", {"kind": "buy_get", "buy": 2, "get": 1}),
        (
            "DATES",
            {
                "kind": "dates",
                "start": "2026-10-10",
                "end": "2026-10-11",
                "original_phrase": "ee weekend",
            },
        ),
        ("DAYS", {"kind": "days", "weekdays": ["SAT", "SUN"]}),
        ("ELIGIBILITY", {"kind": "eligibility", "scope": "all"}),
        ("ELIGIBILITY", {"kind": "eligibility", "scope": "students"}),
        ("ELIGIBILITY", {"kind": "eligibility", "scope": "custom", "description": "Members only"}),
        ("ID_RULE", {"kind": "id_rule", "required": True}),
        ("ID_RULE", {"kind": "id_rule", "required": False}),
        ("TIME_WINDOW", {"kind": "time_window", "start": "09:00", "end": "17:00"}),
        ("MIN_PURCHASE_RULE", {"kind": "minimum_purchase", "amount": 100}),
        ("DINE_IN_RULE", {"kind": "dine_in_rule", "scope": "both"}),
        ("DINE_IN_RULE", {"kind": "dine_in_rule", "scope": "dine_in_only"}),
        ("DINE_IN_RULE", {"kind": "dine_in_rule", "scope": "takeaway_only"}),
        ("COMBINE_RULE", {"kind": "combine_rule", "allowed": True}),
        ("COMBINE_RULE", {"kind": "combine_rule", "allowed": False}),
    ],
)
def test_typed_surface_constraints_match_guardian_in_every_language(key, canonical):
    value = FactInput(key=key, canonical=canonical)
    fact = SimpleNamespace(key=key, canonical=value.canonical)
    constraints = surface_constraints([fact], ["en", "kn", "kn-Latn"])
    for forms in constraints[key].values():
        assert surface_numeric_valid(fact, forms["nom"][0])
        assert not surface_numeric_valid(fact, forms["nom"][0] + " free cake")


@pytest.mark.parametrize("strategy", ["tools", "json"])
async def test_serialized_result_normalizes_once_and_preserves_schema(factory, strategy):
    def transport(request):
        payload = json.loads(request.content)
        response = handler(request).json()
        message = response["choices"][0]["message"]
        if "tools" in payload:
            function = message["tool_calls"][0]["function"]
            result = json.loads(function["arguments"])
            result["result"] = json.dumps(result["result"])
            function["arguments"] = json.dumps(result)
        else:
            result = json.loads(message["content"])
            result["result"] = json.dumps(result["result"])
            message["content"] = json.dumps(result)
        return httpx.Response(200, json=response)

    client = factory(transport, structured_strategy=strategy)
    service = CampaignService(client.store, client, client.settings)
    campaign = service.repo.create(CampaignCreate(), "mock", "2026-10-09", False)
    result = await service.intent(
        campaign.id,
        IntentRequest(expected_revision=1, transcript="Namma Cafe. 20% off coffee this weekend."),
    )
    assert next(f for f in result.facts if f.key == "OFFER").canonical.value == 20
    await client.close()


def test_surface_constraints_excludes_unknown_and_named_facts():
    facts = [
        SimpleNamespace(
            key="CAFE",
            canonical=FactInput(
                key="CAFE", canonical={"kind": "text", "value": "Owner Brand"}
            ).canonical,
        ),
        SimpleNamespace(key="ID_RULE", canonical=None),
    ]
    assert surface_constraints(facts, ["en", "kn"]) == {}


async def test_r1_bad_evidence_is_repaired_without_changing_the_source(factory):
    calls = 0

    def transport(request):
        nonlocal calls
        calls += 1
        response = handler(request).json()
        if calls == 1:
            function = response["choices"][0]["message"]["tool_calls"][0]["function"]
            parsed = json.loads(function["arguments"])
            parsed["result"]["facts"][0]["evidence"]["end"] += 1
            # A unique exact quote can have its coordinates repaired locally.
            # An absent quote still requires a new, evidence-valid provider result.
            parsed["result"]["facts"][0]["evidence"]["quote"] = "Absent source evidence"
            function["arguments"] = json.dumps(parsed)
        return httpx.Response(200, json=response)

    client = factory(transport)
    service = CampaignService(client.store, client, client.settings)
    campaign = service.repo.create(CampaignCreate(), "mock", "2026-10-09", False)
    brief = "Café name: Namma Cafe. Bengaluru. 20% off coffee this weekend. Open to all."
    result = await service.intent(campaign.id, IntentRequest(expected_revision=1, transcript=brief))
    assert calls == 2
    assert result.transcript == brief
    for fact in result.facts:
        if fact.source_span:
            assert brief[fact.source_span.start : fact.source_span.end] == fact.source_span.quote
    await client.close()


@pytest.mark.parametrize("tokens,seconds,expected", [(256, 90, 30), (8192, 90, 60), (8192, 15, 15)])
async def test_large_batch_timeout_never_extends_absolute_budget(
    factory, tokens, seconds, expected
):
    observed = []

    def transport(request):
        observed.append(request.extensions["timeout"]["read"])
        return httpx.Response(200, json={"choices": []})

    client = factory(transport)
    await client.request(
        "text",
        {
            "model": client.settings.text_model,
            "max_tokens": tokens,
        },
        client.budget(calls=1, seconds=seconds),
    )
    assert observed == [expected]
    await client.close()


async def test_string_field_named_result_is_not_coerced(factory):
    from backend.contracts import StrictModel

    class StringResult(StrictModel):
        result: str

    client = factory(
        lambda _: httpx.Response(
            200,
            json={
                "choices": [
                    {"finish_reason": "stop", "message": {"content": '{"result":"plain"}'}}
                ],
            },
        )
    )
    value = await client.structured("hello", StringResult, client.budget(), strategy="json")
    assert value.result == "plain"
    await client.close()


def test_success_wire_contract_is_inlined_closed_and_contains_no_campaign_values():
    from backend.generation_models import CopyResult
    from backend.inference_client import success_wire_schema

    wire = success_wire_schema(CopyResult, "CopySuccess")
    encoded = json.dumps(wire)
    assert "$ref" not in encoded and "$defs" not in encoded
    assert "Namma Cafe" not in encoded and "20%" not in encoded
    assert wire["additionalProperties"] is False
    result = wire["properties"]["result"]
    assert result["additionalProperties"] is False
    assert result["properties"]["status"]["const"] == "success"
    assert "status" in result["required"]
    entry = result["properties"]["entries"]["items"]
    assert entry["properties"]["template"]["additionalProperties"] is False


@pytest.mark.parametrize(
    "inner",
    [
        "[]",
        '"{\\"status\\":\\"success\\"}"',
        '{"status":"needs_input","status":"success","questions":["x"]}',
        '{"status":"needs_input","questions":["x"],"lock":true}',
    ],
)
async def test_result_envelope_rejects_recursive_duplicate_and_extra_values(factory, inner):
    client = factory(
        lambda _: httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps({"result": inner}),
                        },
                    }
                ],
            },
        )
    )
    with pytest.raises(ProviderError) as caught:
        await client.structured("untrusted", IntentResult, client.budget(), strategy="json")
    assert caught.value.body.code == "SCHEMA_INVALID"
    assert len(client.store.calls()) == 3
    await client.close()


async def test_surface_domain_failure_repaired_before_any_forms_persist(factory):
    surface_calls = 0
    captured = []

    def transport(request):
        nonlocal surface_calls
        payload = json.loads(request.content)
        response = handler(request).json()
        if "ROLE: R2" in payload["messages"][0]["content"]:
            surface_calls += 1
            captured.append(payload)
            if surface_calls == 1:
                function = response["choices"][0]["message"]["tool_calls"][0]["function"]
                parsed = json.loads(function["arguments"])
                offer = next(f for f in parsed["result"]["forms"] if f["key"] == "OFFER")
                offer["surface"]["en"]["nom"] = ["25% off"]
                function["arguments"] = json.dumps(parsed)
        return httpx.Response(200, json=response)

    client = factory(transport)
    service = CampaignService(client.store, client, client.settings)
    campaign = service.repo.create(CampaignCreate(), "mock", "2026-10-09", False)
    campaign = await service.intent(
        campaign.id,
        IntentRequest(
            expected_revision=1,
            transcript=(
                "Café name: Namma Cafe. Bengaluru. 20% off coffee this weekend. Open to all."
            ),
        ),
    )
    campaign = await service.surfaces(
        campaign.id,
        SurfaceRequest(
            expected_revision=campaign.revision,
            confirm_canonical=True,
        ),
    )
    assert surface_calls == 2
    assert next(f for f in campaign.facts if f.key == "OFFER").surface["en"].nom == ["20% off"]
    assert "25%" not in json.dumps(captured)
    assert campaign.status == "forms_review"
    await client.close()
