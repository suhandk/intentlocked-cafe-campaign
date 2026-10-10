import asyncio
import io
import json
import zipfile

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from backend.inference_client import InferenceClient
from backend.tests import test_generation, test_website
from backend.tests.conftest import FakeClock
from backend.website_design import WebsiteDesign, design_css
from backend.website_models import DraftSave, GenerateWebsite, WebsiteFields
from backend.website_service import WebsiteError

website = test_website.website
locked_campaign = test_generation.locked


def valid_plan():
    return {
        "layout": "editorial",
        "spacing": "airy",
        "heading_style": "bold",
        "sections": "cards",
        "photo_layout": "grid",
    }


def reply(value):
    return httpx.Response(
        200,
        json={
            "choices": [
                {
                    "message": {"content": json.dumps(value)},
                    "finish_reason": "stop",
                }
            ]
        },
    )


async def controlled(service, handler):
    await service.designer.client.close()
    settings = service.designer.client.settings
    service.designer.client = InferenceClient(
        settings, service.store, clock=FakeClock(), mock_transport=httpx.MockTransport(handler)
    )
    return service.designer.client


async def test_openrouter_model_payload_conceals_all_fact_values_and_secrets(website):
    service, draft, _ = website
    seen = []

    def handler(request):
        seen.append(request)
        return reply(valid_plan())

    client = await controlled(service, handler)
    # Live-header construction using only a controlled offline transport.
    key = "private-openrouter-credential"
    client.settings = client.settings.model_copy(
        update={
            "inference_mode": "live",
            "inference_api_key": SecretStr(key),
        }
    )
    result = await service.generate_with_ai(
        draft["id"], GenerateWebsite(expected_version=draft["version"])
    )
    assert len(seen) == 1
    request = seen[0]
    payload = json.loads(request.content)
    assert str(request.url) == "https://openrouter.ai/api/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer " + key
    assert payload["model"] == "qwen/qwen3-coder-flash"
    assert payload["response_format"] == {"type": "json_object"}
    serialized = request.content.decode()
    assert all(
        text not in serialized for text in ["Namma Cafe", "Bengaluru", "20%", "2026-10-10", key]
    )
    assert key not in json.dumps(result["report"])
    assert result["report"]["design"]["model"] == "qwen/qwen3-coder-flash"
    assert result["report"]["design"]["plan"] == valid_plan()
    assert result["report"]["missing_checks"] == ["G14"]
    assert result["report"]["reports"][0]["language"] == "en"
    with zipfile.ZipFile(io.BytesIO(result["bytes"])) as archive:
        assert b"max-width:840px" in archive.read("style.css")
        assert key.encode() not in b"".join(archive.read(name) for name in archive.namelist())
        assert b"20% off" in archive.read("index.html")
    await service.close()


async def test_real_mock_mode_generates_marked_layout_and_preserves_core(website):
    service, draft, _ = website
    original = service.repo.get(draft["campaign_id"]).model_dump_json()
    bundle = await service.generate_with_ai(
        draft["id"], GenerateWebsite(expected_version=draft["version"])
    )
    assert bundle["report"]["design"]["mode"] == "MOCK"
    assert bundle["report"]["design"]["calls"] == 1
    assert service.repo.get(draft["campaign_id"]).model_dump_json() == original
    # Disconnecting hosting credentials must not close the independent layout client.
    await service.disconnect()
    assert not service.designer.client.http.is_closed
    await service.close()


async def test_missing_live_key_does_not_call_or_replace_previous_bundle(website):
    service, draft, _ = website
    previous = service.generate(draft["id"], GenerateWebsite(expected_version=draft["version"]))
    service.settings.website_ai_mode = "live"
    with pytest.raises(WebsiteError, match="not configured"):
        await service.generate_with_ai(
            draft["id"], GenerateWebsite(expected_version=draft["version"])
        )
    assert service.bundle(draft["id"])["sha256"] == previous["sha256"]
    assert service.store.calls() == []
    await service.close()


@pytest.mark.parametrize(
    "invalid",
    [
        {**valid_plan(), "html": "<script>steal()</script>"},
        {**valid_plan(), "spacing": "40px;background:url(https://evil.test)"},
        {**valid_plan(), "layout": "25% off"},
        {"layout": "editorial"},
    ],
)
async def test_malformed_designs_have_bounded_repairs_and_no_fixture_fallback(website, invalid):
    service, draft, _ = website
    previous = service.generate(draft["id"], GenerateWebsite(expected_version=draft["version"]))
    seen = []

    def handler(request):
        seen.append(request)
        return reply(invalid)

    await controlled(service, handler)
    with pytest.raises(WebsiteError, match="valid layout"):
        await service.generate_with_ai(
            draft["id"], GenerateWebsite(expected_version=draft["version"])
        )
    assert len(seen) == 2
    assert service.bundle(draft["id"])["sha256"] == previous["sha256"]
    assert not service.generating
    await service.close()


async def test_one_invalid_plan_can_be_repaired(website):
    service, draft, _ = website
    calls = []

    def handler(request):
        calls.append(request)
        return reply({"layout": "invalid"}) if len(calls) == 1 else reply(valid_plan())

    await controlled(service, handler)
    result = await service.generate_with_ai(
        draft["id"], GenerateWebsite(expected_version=draft["version"])
    )
    assert result["report"]["design"]["calls"] == 2
    await service.close()


@pytest.mark.parametrize("mutation", ["draft", "facts"])
async def test_revision_change_during_model_request_blocks_late_result(website, mutation):
    service, draft, _ = website

    async def handler(request):
        if mutation == "draft":
            service.save(
                draft["id"],
                DraftSave(
                    expected_version=draft["version"],
                    step=5,
                    fields=WebsiteFields(name="Namma Cafe", area="Bengaluru", colour="#123456"),
                ),
            )
        else:
            campaign = service.repo.get(draft["campaign_id"])
            campaign.revision += 1
            service.db.execute(
                "UPDATE campaigns SET revision=?,payload=? WHERE id=?",
                (campaign.revision, campaign.model_dump_json(), campaign.id),
            )
            service.db.commit()
        return reply(valid_plan())

    await controlled(service, handler)
    with pytest.raises(WebsiteError) as exc:
        await service.generate_with_ai(
            draft["id"], GenerateWebsite(expected_version=draft["version"])
        )
    assert exc.value.code in {"STALE_DRAFT", "STALE_BUNDLE"}
    assert service.get(draft["id"])["bundle_id"] is None
    await service.close()


async def test_required_fields_block_before_provider_request(website):
    service, draft, _ = website
    draft = service.save(
        draft["id"], DraftSave(expected_version=draft["version"], step=5, fields=WebsiteFields())
    )
    with pytest.raises(WebsiteError, match="required"):
        await service.generate_with_ai(
            draft["id"], GenerateWebsite(expected_version=draft["version"])
        )
    assert service.store.calls() == []
    await service.close()


async def test_duplicate_submission_and_cancellation_do_not_create_bundle(website):
    service, draft, _ = website
    entered = asyncio.Event()

    async def handler(request):
        entered.set()
        await asyncio.Event().wait()

    await controlled(service, handler)
    body = GenerateWebsite(expected_version=draft["version"])
    pending = asyncio.create_task(service.generate_with_ai(draft["id"], body))
    await entered.wait()
    with pytest.raises(WebsiteError, match="already running"):
        await service.generate_with_ai(draft["id"], body)
    pending.cancel()
    await asyncio.gather(pending, return_exceptions=True)
    assert not service.generating and service.get(draft["id"])["bundle_id"] is None
    await service.close()


@pytest.mark.parametrize(
    "bad",
    [{**valid_plan(), "heading_style": "<script>"}],
)
def test_direct_plan_construct_cannot_bypass_css_boundary(bad):
    with pytest.raises(ValidationError):
        design_css(WebsiteDesign.model_construct(**bad))


def test_extra_url_is_rejected_as_input_and_never_enters_css():
    bad = {**valid_plan(), "photos_url": "https://evil.test"}
    with pytest.raises(ValidationError):
        WebsiteDesign.model_validate(bad)
    # Pydantic's trusted construct discards forbidden extras rather than preserving them.
    assert "evil.test" not in design_css(WebsiteDesign.model_construct(**bad))
