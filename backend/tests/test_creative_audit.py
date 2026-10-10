import json

import pytest

from backend.art_context import art_brief, art_key, image_prompt
from backend.art_service import deterministic_background
from backend.errors import ProviderError
from backend.mock import handler
from backend.optimization_service import OptimizationService
from backend.semantic_audit import ground_reader, reader_spans
from backend.tests.test_generation import locked as locked_fixture
from backend.tests.test_optimization import altered, prepared


async def test_r7_exact_quote_offset_error_repaired_without_extra_provider_call(factory):
    captured = []

    def transport(req):
        body = json.loads(req.content)
        if "ROLE: R7" in body["messages"][0]["content"]:
            captured.append(body)

            def offset_error(data):
                cafe = next(e for e in data["expectations"] if e["key"] == "CAFE")
                for span in cafe["evidence"]:
                    span["start"] += 7
                    span["end"] += 7

            return altered(req, offset_error)
        return handler(req)

    client = factory(transport)
    campaign = locked_fixture.__wrapped__()
    _, variant = await prepared(client, campaign)
    service = OptimizationService(client.store, client)
    calls = []
    audit = await service.audit_report(
        campaign, variant.report, "en", "whatsapp", client.budget(calls=3, seconds=60), calls
    )
    assert audit.status == "PASS" and len(captured) == 1
    assert len(audit.call.call_ids) == 1
    data = json.loads(json.loads(captured[0]["messages"][1]["content"])["input"])
    assert "evidence_spans" in data and "canonical" not in data
    assert "scores" not in data and "provenance" not in data
    await client.close()


async def test_absent_or_duplicate_quote_never_fabricates_evidence(factory):
    client = factory()
    campaign = locked_fixture.__wrapped__()
    _, variant = await prepared(client, campaign)
    service = OptimizationService(client.store, client)
    audit = await service.audit_report(
        campaign, variant.report, "en", "whatsapp", client.budget(calls=3, seconds=60), []
    )
    for absent in (True, False):
        reader = audit.reader.model_copy(deep=True)
        cafe = next(e for e in reader.expectations if e.key == "CAFE")
        if absent:
            cafe.evidence = []
            fields = variant.report.rendered.fields
        else:
            span = cafe.evidence[0]
            span.start = span.end = 0
            fields = {**variant.report.rendered.fields, span.field: span.quote + " " + span.quote}
        with pytest.raises(ProviderError):
            ground_reader(reader, fields)
    await client.close()


def test_creative_coffee_category_and_local_fallback_are_safe():
    campaign = locked_fixture.__wrapped__()
    brief = art_brief(campaign, "1:1")
    assert brief["allowed_product_illustration"]
    assert "coffee mug" in image_prompt(brief)
    assert campaign.facts[0].canonical.value not in image_prompt(brief)
    before = art_key(campaign, "1:1", "deterministic")
    raw = deterministic_background("1:1", brief["palette"], coffee=True)
    assert raw != deterministic_background("1:1", brief["palette"], coffee=False)
    next(f for f in campaign.facts if f.key == "PRODUCT").canonical.value = "tea"
    assert not art_brief(campaign, "1:1")["allowed_product_illustration"]
    assert art_key(campaign, "1:1", "deterministic") != before
    assert reader_spans({"body": "ಕಾಫಿ\nNamma Cafe"})[1]["start"] == 5
