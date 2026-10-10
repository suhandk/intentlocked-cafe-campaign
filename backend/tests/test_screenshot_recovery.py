"""Regression boundaries for the three owner screenshots; no external inference."""

import json

import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.errors import ProviderError
from backend.generation_context import complete_disclosures
from backend.generation_service import GenerationService
from backend.guardian.slots import parse
from backend.main import create_app
from backend.optimization_models import OptimizeRequest
from backend.optimization_service import OptimizationService
from backend.schemas import TemplateContent
from backend.tests.test_generation import finish, inputs, mutate_response, seed, selection
from backend.tests.test_generation import locked as locked_fixture
from backend.tests.test_optimization import completed


@pytest.fixture
def locked():
    return locked_fixture.__wrapped__()


def test_disclosures_add_only_missing_approved_facts_and_leave_unknown_id_unknown(locked):
    template = TemplateContent(
        headline="A warm pause",
        body="{{CAFE}} · {{OFFER}} · {{PRODUCT}} · {{DATES}} · {{DAYS}}",
        cta="Join us",
        hashtags=[],
        alt_text="{{CAFE}} · {{PRODUCT}}",
    )
    result, inserted = complete_disclosures(locked, template)
    assert inserted == ["ELIGIBILITY", "LOCATION"]
    assert result.body.startswith(template.body)
    assert "{{ID_RULE}}" not in result.body
    assert complete_disclosures(locked, result) == (result, [])
    malformed = template.model_copy(update={"body": "{{OFFER"})
    assert complete_disclosures(locked, malformed) == (malformed, [])


async def test_missing_disclosures_become_valid_in_one_bounded_copy_batch(factory, locked):
    def transport(request):
        _, value = inputs(request)
        if "language" not in value:
            from backend.mock import handler

            return handler(request)

        def omit(result):
            for entry in result["entries"]:
                for key in ["LOCATION", "ELIGIBILITY"]:
                    entry["template"]["body"] = entry["template"]["body"].replace(
                        "{{" + key + "}}", ""
                    )

        return mutate_response(request, omit)

    client = factory(transport)
    seed(client, locked)
    service = GenerationService(client.store, client)
    plan = await service.strategy(locked.id, locked.revision)
    run = await finish(
        service,
        service.start(
            locked.id,
            selection(
                locked,
                plan,
                languages=["en"],
                channels=["instagram"],
            ),
        ),
    )
    assert run.status == "completed" and run.calls_used == 1
    for cell in run.cells:
        assert cell.state == "ready" and not cell.reasons
        assert {"LOCATION", "ELIGIBILITY"} <= {
            token.key for token in parse(cell.variant.template.body)
        }
        assert cell.variant.report.status != "BLOCKED" and cell.variant.status == "pending"
    await client.close()


async def test_unsupported_claims_still_block_and_repair_feedback_contains_no_fact_values(
    factory,
    locked,
):
    batches = []

    def transport(request):
        _, value = inputs(request)
        if "language" not in value:
            from backend.mock import handler

            return handler(request)
        batches.append(value)

        def corrupt(result):
            for entry in result["entries"]:
                entry["template"]["body"] = "Free cake today. {{CAFE}}"

        return mutate_response(request, corrupt)

    client = factory(transport)
    seed(client, locked)
    service = GenerationService(client.store, client)
    plan = await service.strategy(locked.id, locked.revision)
    run = await finish(
        service,
        service.start(
            locked.id,
            selection(
                locked,
                plan,
                languages=["en"],
                channels=["instagram"],
            ),
        ),
    )
    assert run.status == "failed" and run.error_code == "COPY_VALIDATION_FAILED"
    assert run.calls_used == 3 and all(cell.state == "blocked" for cell in run.cells)
    assert all("G08" in cell.reasons for cell in run.cells)
    assert batches[1]["repair_feedback"][0]["violations"]
    assert "Namma Cafe" not in json.dumps(batches) and "Bengaluru" not in json.dumps(batches)
    assert service.repo.matrix(locked.id).run.id == run.id
    await client.close()


async def test_explicit_non_hero_group_can_optimize_without_rebasing_or_mixing_audiences(
    factory,
    locked,
):
    client = factory(demo_fast=True)
    seed(client, locked)
    generation = GenerationService(client.store, client)
    plan = await generation.strategy(locked.id, locked.revision)
    audience = next(a.id for a in plan.audiences if a.id != plan.hero_audience_id)
    matrix = await finish(
        generation,
        generation.start(
            locked.id,
            selection(
                locked,
                plan,
                audience_ids=[audience, plan.hero_audience_id],
                languages=["en"],
                channels=["instagram"],
            ),
        ),
    )
    service = OptimizationService(client.store, client)
    ids = [cell.variant.id for cell in matrix.cells if cell.audience_id == audience]
    run = await completed(
        service,
        service.start(
            locked.id,
            OptimizeRequest(
                expected_revision=locked.revision,
                variant_ids=ids,
                idempotency_key="non-hero-group",
            ),
        ),
    )
    assert run.groups[0].baseline.audience_id == audience
    assert run.groups[0].baseline.id == ids[0]
    assert run.personas == plan.personas and run.max_rounds == 2
    with pytest.raises(ProviderError) as mixed:
        service.start(
            locked.id,
            OptimizeRequest(
                expected_revision=locked.revision,
                variant_ids=[cell.variant.id for cell in matrix.cells],
                idempotency_key="mixed-group",
            ),
        )
    assert mixed.value.body.code == "OPTIMIZATION_SELECTION"
    await service.close()
    await client.close()


def test_health_reports_actual_models_and_video_is_rejected_before_job_creation(tmp_path, locked):
    settings = Settings(
        _env_file=None,
        database_path=tmp_path / "db.sqlite3",
        asset_path=tmp_path / "assets",
        inference_mode="live",
        inference_api_key="offline-test-key",
        inference_base_url="https://openrouter.ai/api/v1",
    )
    with TestClient(create_app(settings)) as api:
        seed(api.app.state.client, locked)
        health = api.get("/api/ready").json()
        assert health["text_model"] == "openai/gpt-4o-mini"
        assert health["image_model"] == "black-forest-labs/flux-schnell"
        assert not health["video_enabled"] and not health["image_generation_enabled"]
        for index in range(2):
            response = api.post(
                f"/api/campaigns/{locked.id}/work",
                json={
                    "kind": "video",
                    "idempotency_key": f"reject-video-{index}",
                    "input": {
                        "expected_revision": locked.revision,
                        "duration": 24,
                        "generated_seconds": 18,
                        "confirm_clip_count": True,
                        "confirm_possible_charges": True,
                        "confirm_video_access": True,
                    },
                },
            )
            assert response.status_code == 422 and response.json()["code"] == "VIDEO_DISABLED"
        for index in range(2):
            response = api.post(
                f"/api/campaigns/{locked.id}/work",
                json={
                    "kind": "background",
                    "idempotency_key": f"reject-image-{index}",
                    "input": {"expected_revision": locked.revision, "size": "square"},
                },
            )
            assert response.status_code == 422
            assert response.json()["code"] == "IMAGE_TRANSPORT_UNVERIFIED"
        direct = api.post(
            f"/api/campaigns/{locked.id}/backgrounds",
            json={"expected_revision": locked.revision, "size": "square"},
        )
        assert direct.status_code == 422
        assert direct.json()["code"] == "IMAGE_TRANSPORT_UNVERIFIED"
        assert (
            api.app.state.store.connection.execute("SELECT count(*) FROM work_jobs").fetchone()[0]
            == 0
        )
        assert api.app.state.store.calls() == []


async def test_unverified_image_endpoint_cannot_spend_a_provider_call(factory):
    def forbidden(request):
        raise AssertionError("Unverified image transport must not dispatch")

    client = factory(
        forbidden,
        image_model="black-forest-labs/flux-schnell",
        inference_base_url="https://openrouter.ai/api/v1",
    )
    client.settings = client.settings.model_copy(update={"inference_mode": "live"})
    with pytest.raises(ProviderError) as error:
        await client.image("Café art", client.budget())
    assert error.value.body.code == "IMAGE_TRANSPORT_UNVERIFIED"
    assert client.store.calls() == []
    await client.close()
