import asyncio
import json

import httpx
import pytest
from pydantic import ValidationError

from backend.db import Store
from backend.errors import ProviderError
from backend.generation_models import GenerateRequest, StrategySuccess
from backend.generation_repository import GenerationRepository
from backend.generation_service import GenerationService
from backend.intent_rules import digest
from backend.mock import handler
from backend.mock_generation import strategy_fixture
from backend.tests import test_guardian


@pytest.fixture
def locked():
    campaign = test_guardian.campaign.__wrapped__()
    campaign.fact_hash = digest([f.model_dump() for f in campaign.facts])
    return campaign


def seed(client, campaign):
    with client.store.connection:
        client.store.connection.execute(
            "INSERT INTO campaigns VALUES(?,?,?,?)",
            (
                campaign.id,
                campaign.revision,
                campaign.status,
                campaign.model_dump_json(),
            ),
        )


def selection(campaign, plan, **changes):
    return GenerateRequest(
        **{
            "expected_revision": campaign.revision,
            "strategy_id": plan.id,
            "idempotency_key": "generation-test-key",
            "audience_ids": [a.id for a in plan.audiences],
            "languages": campaign.languages,
            "channels": ["instagram", "whatsapp", "facebook"],
            **changes,
        }
    )


async def finish(service, run):
    task = service.tasks.get(run.id)
    if task:
        await task
    return service.repo.get(run.id)


def inputs(request):
    payload = json.loads(request.content)
    return payload, json.loads(json.loads(payload["messages"][1]["content"])["input"])


def mutate_response(request, mutate):
    response = handler(request).json()
    function = response["choices"][0]["message"]["tool_calls"][0]["function"]
    result = json.loads(function["arguments"])
    mutate(result["result"])
    function["arguments"] = json.dumps(result)
    return httpx.Response(200, json=response)


async def test_full_matrix_persistence_stable_personas_rate_batches(factory, locked):
    captured = []

    def transport(request):
        captured.append(inputs(request))
        return handler(request)

    client = factory(transport)
    seed(client, locked)
    service = GenerationService(client.store, client)
    plan = await service.strategy(locked.id, locked.revision)
    assert len(plan.audiences) == 3 and len(plan.personas) == 5
    assert len({a.angle for a in plan.audiences}) == 3
    assert await service.strategy(locked.id, locked.revision) == plan
    run = service.start(locked.id, selection(locked, plan))
    assert len(run.cells) == 27 and all(c.variant is None for c in run.cells)
    assert service.start(locked.id, selection(locked, plan)).id == run.id
    run = await finish(service, run)
    assert run.status == "completed", [(c.language, c.reasons) for c in run.cells]
    assert run.calls_used == 3
    assert len(captured) == 4  # R3 plus one R4 batch/language, not per cell.
    assert [p[1].get("language") for p in captured[1:]] == ["en", "kn", "kn-Latn"]
    assert all(len(p[1]["combinations"]) == 9 for p in captured[1:])
    assert any(delay == 7.5 for delay in client.clock.sleeps)
    for cell in run.cells:
        variant = cell.variant
        assert cell.state == "ready" and variant.status == "pending"
        assert variant.mode == "mock" and variant.baseline
        assert "G14" in variant.report.missing_checks
        assert variant.slots_used == variant.report.rendered.slots_used
        assert variant.dependencies.facts["ELIGIBILITY"] == 1
        for span in variant.report.rendered.spans:
            assert (
                variant.report.rendered.fields[span.field][span.start : span.end]
                == span.approved_form
            )
    assert (
        client.store.connection.execute("SELECT count(*) FROM baseline_variants").fetchone()[0]
        == 27
    )
    snapshot = service.repo.matrix(locked.id)
    second = Store(client.settings.database_path)
    assert GenerationRepository(second).matrix(locked.id) == snapshot
    assert GenerationRepository(second).plan(locked.id, 1).personas == plan.personas
    second.close()
    await client.close()


async def test_concealment_including_repair_and_brand(factory, locked):
    # Unique sentinel facts must never appear in R3/R4, including structured repair messages.
    for fact in locked.facts:
        if fact.key in {"CAFE", "LOCATION", "PRODUCT"}:
            fact.canonical.value = f"SECRET_{fact.key}_91273"
            for forms in fact.surface.values():
                forms.nom = [fact.canonical.value]
    locked.brand.tone = "SECRET_LOCATION_91273 25% on Monday"
    locked.brand.theme = "SECRET_PRODUCT_91273 2037-09-28"
    locked.brand.must_say = ["SECRET_CAFE_91273"]
    locked.brand.must_not_say = ["SECRET_LOCATION_91273"]
    locked.transcript = "SECRET_OFFER_25_PERCENT"
    seen = []

    def transport(request):
        payload, data = inputs(request)
        seen.append(request.content.decode())
        if "language" in data:
            return mutate_response(
                request, lambda result: result["entries"][0]["template"].update(body="25% off")
            )
        return handler(request)

    client = factory(transport)
    seed(client, locked)
    service = GenerationService(client.store, client)
    plan = await service.strategy(locked.id, 1)
    run = await finish(service, service.start(locked.id, selection(locked, plan, languages=["en"])))
    assert run.status == "failed" and run.calls_used == 3
    assert all("SECRET_" not in payload and "2037-09-28" not in payload for payload in seen)
    assert all("25%" not in payload for payload in seen)
    assert any("repair_codes" in payload and "G01" in payload for payload in seen)
    assert all(c.reasons for c in run.cells)
    await client.close()


@pytest.mark.parametrize(
    "kind",
    [
        "missing",
        "duplicate",
        "unknown",
        "malformed",
        "malformed_template",
        "wrong_language",
        "literal",
        "script",
        "duplicate_hook",
        "needs_input",
        "provider",
    ],
)
async def test_bad_language_preserves_other_work(factory, locked, kind):
    def transport(request):
        _, data = inputs(request)
        if data.get("language") != "kn":
            return handler(request)
        if kind == "provider":
            return httpx.Response(400, json={"error": "test failure"})

        def alter(result):
            entries = result["entries"]
            if kind == "missing":
                entries.clear()
            elif kind == "duplicate":
                result["entries"] = [entries[0], entries[0]]
            elif kind == "unknown":
                entries[0]["audience_id"] = "unselected"
            elif kind == "malformed":
                entries[0]["template"]["canonical"] = {"value": 25}
            elif kind == "malformed_template":
                for entry in entries:
                    entry["template"]["body"] = "{{OFFER"
            elif kind == "wrong_language":
                result["language"] = "en"
            elif kind == "literal":
                for entry in entries:
                    entry["template"]["body"] = "Free cake. 25% off"
            elif kind == "script":
                for entry in entries:
                    entry["template"]["headline"] = "A pause " * 50 + entry["audience_id"]
            elif kind == "duplicate_hook":
                for entry in entries:
                    entry["template"]["headline"] = "ಒಟ್ಟಾಗಿ ಬನ್ನಿ"
            else:
                result.clear()
                result.update(status="needs_input", questions=["Please clarify style"])

        return mutate_response(request, alter)

    client = factory(transport)
    seed(client, locked)
    service = GenerationService(client.store, client)
    plan = await service.strategy(locked.id, 1)
    run = await finish(service, service.start(locked.id, selection(locked, plan)))
    assert run.status == "partial"
    assert all(c.state == "ready" for c in run.cells if c.language != "kn")
    assert all(c.state == "blocked" and c.reasons for c in run.cells if c.language == "kn")
    assert run.calls_used <= 5
    await client.close()


async def test_bounded_repair_keeps_successful_cells(factory, locked):
    batches = []

    def transport(request):
        _, data = inputs(request)
        if "language" not in data:
            return handler(request)
        batches.append(data)
        if len(batches) == 1:
            return mutate_response(request, lambda result: result["entries"].pop())
        return handler(request)

    client = factory(transport)
    seed(client, locked)
    service = GenerationService(client.store, client)
    plan = await service.strategy(locked.id, 1)
    run = await finish(service, service.start(locked.id, selection(locked, plan, languages=["en"])))
    assert run.status == "completed"
    assert [len(b["combinations"]) for b in batches] == [9, 1]
    assert sorted(len(c.attempts) for c in run.cells) == [1] * 8 + [2]
    await client.close()


@pytest.mark.parametrize("exhaust", [False, True])
async def test_rate_limited_batch_retry_and_exhaustion(factory, locked, exhaust):
    batches = []

    def transport(request):
        _, data = inputs(request)
        if "language" in data:
            batches.append(data)
            if data["language"] == "en" and (exhaust or len(batches) == 1):
                return httpx.Response(429, headers={"Retry-After": "12"})
        return handler(request)

    client = factory(transport)
    seed(client, locked)
    service = GenerationService(client.store, client)
    plan = await service.strategy(locked.id, 1)
    run = await finish(service, service.start(locked.id, selection(locked, plan)))
    assert run.status == ("partial" if exhaust else "completed")
    assert run.calls_used == (5 if exhaust else 4)
    assert 12 in client.clock.sleeps
    assert all(len(batch["combinations"]) == 9 for batch in batches)
    assert all(c.state == "ready" for c in run.cells if c.language != "en")
    if exhaust:
        assert all(
            c.state == "blocked" and c.variant is None for c in run.cells if c.language == "en"
        )
    await client.close()


async def test_progress_and_revision_race(factory, locked):
    started, release = asyncio.Event(), asyncio.Event()

    async def transport(request):
        _, data = inputs(request)
        if data.get("language") == "kn":
            started.set()
            await release.wait()
        return handler(request)

    client = factory(transport)
    seed(client, locked)
    service = GenerationService(client.store, client)
    plan = await service.strategy(locked.id, 1)
    run = service.start(locked.id, selection(locked, plan))
    await started.wait()
    snapshot = service.repo.matrix(locked.id)
    assert sum(c.state == "ready" for c in snapshot.run.cells) == 9
    with pytest.raises(ProviderError, match="active"):
        service.start(locked.id, selection(locked, plan, idempotency_key="new-busy-key"))
    locked.revision = 2
    with client.store.connection:
        client.store.connection.execute(
            "UPDATE campaigns SET revision=2,payload=? WHERE id=?",
            (locked.model_dump_json(), locked.id),
        )
    release.set()
    run = await finish(service, run)
    assert run.status == "stale" and all(c.state == "stale" for c in run.cells)
    assert sum(c.variant is not None for c in run.cells) == 9
    assert (
        client.store.connection.execute("SELECT count(*) FROM baseline_variants").fetchone()[0] == 9
    )
    await client.close()


@pytest.mark.parametrize(
    "scope,target,expected",
    [
        ("students", "students", None),
        ("students", "families", "ELIGIBILITY_CONFLICT"),
        ("custom", "members", "ELIGIBILITY_UNRESOLVED"),
        ("unknown", "students", "ELIGIBILITY_UNRESOLVED"),
    ],
)
async def test_eligibility(factory, locked, scope, target, expected):
    fact = next(f for f in locked.facts if f.key == "ELIGIBILITY")
    if scope == "unknown":
        fact.canonical, fact.status = None, "not_specified"
    else:
        fact.canonical.scope = scope
        fact.canonical.description = "members" if scope == "custom" else ""
    if scope == "students":
        for language, form in [
            ("en", "Students only"),
            ("kn", "ವಿದ್ಯಾರ್ಥಿಗಳಿಗೆ ಮಾತ್ರ"),
            ("kn-Latn", "Students maatra"),
        ]:
            fact.surface[language].nom = [form]
    locked.target_audiences = [target]
    client = factory()
    seed(client, locked)
    service = GenerationService(client.store, client)
    if expected:
        with pytest.raises(ProviderError) as caught:
            await service.strategy(locked.id, 1)
        assert caught.value.body.code == expected
        assert not client.store.calls()
    else:
        plan = await service.strategy(locked.id, 1)
        assert {a.segment for a in plan.audiences} == {"students"}
        assert len({a.angle for a in plan.audiences}) == 3
        run = await finish(service, service.start(locked.id, selection(locked, plan)))
        assert run.status == "completed"
    await client.close()


async def test_cancellation_restart_and_idempotency(factory, locked):
    started = asyncio.Event()

    async def transport(request):
        _, data = inputs(request)
        if "language" in data:
            started.set()
            await asyncio.Event().wait()
        return handler(request)

    client = factory(transport)
    seed(client, locked)
    service = GenerationService(client.store, client)
    plan = await service.strategy(locked.id, 1)
    request = selection(locked, plan)
    run = service.start(locked.id, request)
    await started.wait()
    with pytest.raises(ProviderError) as caught:
        service.start(locked.id, request.model_copy(update={"languages": ["en"]}))
    assert caught.value.body.code == "IDEMPOTENCY_CONFLICT"
    await service.close()
    assert service.repo.get(run.id).status == "interrupted"
    # Simulate a process dying without executing its finally/cancellation handler.
    saved = service.repo.get(run.id)
    saved.status = "running"
    with pytest.raises(ProviderError) as stopped:
        service.repo.save(saved)
    assert stopped.value.body.code == "WORK_STOPPED"
    # Fault injection bypasses the terminal-state guard to represent a hard crash.
    with client.store.connection:
        client.store.connection.execute(
            "UPDATE generation_runs SET status=?,payload=? WHERE id=?",
            (saved.status, saved.model_dump_json(), saved.id),
        )
    service.repo.recover()
    assert service.repo.get(run.id).error_code == "PROCESS_RESTARTED"
    assert service.start(locked.id, request).status == "interrupted"
    assert not service.tasks
    await client.close()


def test_strategy_and_request_schema_rejects_duplicate_profiles():
    data = strategy_fixture({"eligible_segments": ["students"], "channels": ["whatsapp"]})["result"]
    data["audiences"][1] = data["audiences"][0]
    with pytest.raises(ValidationError):
        StrategySuccess.model_validate(data)


@pytest.mark.parametrize(
    "kind", ["ineligible", "channel", "slot", "needs_input", "duplicate_persona"]
)
async def test_r3_rejects_invalid_plans(factory, locked, kind):
    eligibility = next(f for f in locked.facts if f.key == "ELIGIBILITY")
    eligibility.canonical.scope = "students"
    locked.channels = ["whatsapp"]

    def transport(request):
        def alter(result):
            if kind == "ineligible":
                result["audiences"][0]["segment"] = "families"
            elif kind == "channel":
                result["audiences"][0]["preferred_channel"] = "facebook"
            elif kind == "slot":
                result["message_hierarchy"].append("ID_RULE")
            elif kind == "duplicate_persona":
                result["personas"][1] = result["personas"][0]
            else:
                result.clear()
                result.update(status="needs_input", questions=["Clarify eligible audiences"])

        return mutate_response(request, alter)

    client = factory(transport)
    seed(client, locked)
    service = GenerationService(client.store, client)
    with pytest.raises(ProviderError):
        await service.strategy(locked.id, 1)
    assert service.repo.plan(locked.id, 1) is None
    assert len(client.store.calls()) <= 3
    await client.close()


async def test_r3_revision_race(factory, locked):
    started, release = asyncio.Event(), asyncio.Event()

    async def transport(request):
        started.set()
        await release.wait()
        return handler(request)

    client = factory(transport)
    seed(client, locked)
    service = GenerationService(client.store, client)
    task = asyncio.create_task(service.strategy(locked.id, 1))
    await started.wait()
    locked.revision += 1
    with client.store.connection:
        client.store.connection.execute(
            "UPDATE campaigns SET revision=2,payload=? WHERE id=?",
            (locked.model_dump_json(), locked.id),
        )
    release.set()
    with pytest.raises(ProviderError) as caught:
        await task
    assert caught.value.body.code == "REVISION_CONFLICT"
    assert service.repo.plan(locked.id, 1) is None
    await client.close()


def test_direct_api_boundary_and_reload(tmp_path, locked):
    import time

    from fastapi.testclient import TestClient

    from backend.config import Settings
    from backend.main import create_app
    from backend.tests.conftest import FakeClock

    config = Settings(_env_file=None, database_path=tmp_path / "api.sqlite")
    app = create_app(config)
    with TestClient(app) as api:
        app.state.client.clock = FakeClock()
        seed(app.state.client, locked)
        base = f"/api/campaigns/{locked.id}"
        assert api.get(base + "/matrix").json()["run"] is None
        assert api.post(base + "/strategy", json={"expected_revision": 99}).status_code == 409
        response = api.post(base + "/strategy", json={"expected_revision": 1})
        assert response.status_code == 200, response.text
        plan = app.state.generation.repo.plan(locked.id, 1)
        payload = selection(locked, plan, languages=["en"], channels=["whatsapp"]).model_dump()
        for field in ["facts", "slots_used", "approved", "report"]:
            assert api.post(base + "/generate", json={**payload, field: True}).status_code == 422
        assert (
            api.post(base + "/generate", json={**payload, "channels": ["poster"]}).status_code
            == 422
        )
        assert (
            api.post(base + "/generate", json={**payload, "audience_ids": ["forged"]}).status_code
            == 422
        )
        assert (
            api.post(base + "/generate", json={**payload, "languages": ["en", "en"]}).status_code
            == 422
        )
        response = api.post(base + "/generate", json=payload)
        assert response.status_code == 202
        run_id = response.json()["id"]
        for _ in range(100):
            result = api.get(f"/api/jobs/{run_id}").json()
            if result["status"] not in {"queued", "running"}:
                break
            time.sleep(0.01)
        assert result["status"] == "completed"
        assert api.post(base + "/generate", json=payload).json()["id"] == run_id
        assert api.get("/api/jobs/absent").status_code == 404
        assert api.get("/api/campaigns/absent/matrix").status_code == 404
    with TestClient(create_app(config)) as api:
        snapshot = api.get(base + "/matrix").json()
        assert snapshot["run"] == result
        assert len(snapshot["strategy"]["personas"]) == 5
