import asyncio
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest

from backend.approval_service import ApprovalService
from backend.art_service import ArtService
from backend.change_service import ChangeService
from backend.db import Store
from backend.errors import ProviderError
from backend.generation_service import GenerationService
from backend.intent_rules import digest
from backend.mock import handler
from backend.optimization_service import OptimizationService
from backend.tests.test_delivery import approval_request
from backend.tests.test_delivery import setup as delivery_setup
from backend.tests.test_generation import inputs, seed, selection
from backend.tests.test_generation import locked as locked_fixture
from backend.work_models import WorkRequest, WorkRetry
from backend.work_service import WorkService


@pytest.fixture
def locked():
    return locked_fixture.__wrapped__()


def setup(client, campaign, seed_campaign=True):
    if seed_campaign:
        seed(client, campaign)
    state = SimpleNamespace(store=client.store, client=client, settings=client.settings)
    state.generation = GenerationService(client.store, client)
    state.art = ArtService(client.store, client, client.settings)
    state.optimization = OptimizationService(client.store, client)
    state.changes = ChangeService(client.store, client)
    state.approvals = ApprovalService(client.store, client, state.optimization)
    work = WorkService(SimpleNamespace(state=state))
    client.store.work = work
    return work


def request(campaign, kind="strategy", key="durable-test-key", **input_values):
    return WorkRequest(
        kind=kind,
        idempotency_key=key,
        input={"expected_revision": campaign.revision, **input_values},
    )


async def done(work, job):
    task = work.tasks.get(job.id)
    if task:
        await task
    return work.get(job.id)


async def test_double_click_replay_persists_without_repeating_costs(factory, locked):
    client = factory()
    work = setup(client, locked)
    body = request(locked)
    first = work.start(locked.id, body)
    second = work.start(locked.id, body)
    assert first.id == second.id
    saved = await done(work, first)
    assert saved.status == "completed" and saved.prompt_hashes["R3"]
    before = len(client.store.calls())
    events = work.events(locked.id)
    assert [e.id for e in events] == sorted({e.id for e in events})
    assert work.events(locked.id, events[-1].id) == []
    assert work.events(locked.id, events[0].id)[0].id > events[0].id
    for _ in range(5):
        assert work.start(locked.id, body).id == first.id
        work.snapshot(locked.id)
    assert len(client.store.calls()) == before
    assert work.snapshot(locked.id).jobs[0].calls == before
    assert work.snapshot(locked.id).jobs[0].list_price_estimate_usd == 0
    reopened = WorkService(work.app)
    assert reopened.get(first.id).result == saved.result
    await client.close()


async def test_payload_bound_key_and_invalid_work_never_calls(factory, locked):
    client = factory()
    work = setup(client, locked)
    job = work.start(locked.id, request(locked))
    with pytest.raises(ProviderError, match="Job key"):
        work.start(locked.id, request(locked, kind="forms", confirm_canonical=True))
    with pytest.raises(ProviderError, match="schema"):
        work.start(locked.id, request(locked, key="invalid-schema", model="rogue"))
    await done(work, job)
    await client.close()


async def test_cancel_running_and_queued_preserves_terminal_state(factory, locked, monkeypatch):
    client = factory()
    work = setup(client, locked)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def blocked(*args):
        entered.set()
        await release.wait()
        return {"unexpected": True}

    monkeypatch.setattr(work, "dispatch", blocked)
    jobs = [work.start(locked.id, request(locked, key=f"cancel-key-{i}")) for i in range(3)]
    await entered.wait()
    assert work.snapshot(locked.id).active == 2
    assert work.snapshot(locked.id).queued == 1
    assert work.snapshot(locked.id).jobs[0].queue_position == 1
    for job in jobs:
        cancelled = await work.cancel(job.id)
        assert cancelled.status == "cancelled"
        assert (await work.cancel(job.id)).status == "cancelled"
    assert not client.store.calls()
    assert all(work.get(j.id).result is None for j in jobs)
    await client.close()


async def test_restart_marks_interrupted_and_retains_completed_strategy(factory, locked):
    client = factory()
    work = setup(client, locked)
    finished = await done(work, work.start(locked.id, request(locked)))
    interrupted = work.start(locked.id, request(locked, key="restart-job-key"))
    # Abrupt-process snapshot: the queued task has not executed.
    task = work.tasks[interrupted.id]
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    before = len(client.store.calls())
    reopened = Store(client.settings.database_path)
    original_store = client.store
    client.store = reopened
    recovered = setup(client, locked, False)
    assert recovered.get(interrupted.id).status == "interrupted"
    assert recovered.get(interrupted.id).error_code == "PROCESS_RESTARTED"
    assert recovered.get(finished.id).result == finished.result
    assert len(reopened.calls()) == before
    assert recovered.app.state.generation.repo.plan(locked.id, locked.revision)
    assert not recovered.tasks
    reopened.close()
    client.store = original_store
    await client.close()


@pytest.mark.parametrize("error", ["AUTH_FAILED", "SUBMISSION_UNCERTAIN", "PROVIDER_UNAVAILABLE"])
async def test_failure_is_visible_and_not_retried_indefinitely(factory, locked, monkeypatch, error):
    client = factory()
    work = setup(client, locked)
    count = 0

    async def fail(*args):
        nonlocal count
        count += 1
        raise ProviderError(error, "Provider failed")

    monkeypatch.setattr(work, "dispatch", fail)
    job = await done(work, work.start(locked.id, request(locked)))
    assert job.status == "failed" and job.error_code == error and count == 1
    assert work.start(locked.id, request(locked)).id == job.id
    assert count == 1
    await client.close()


async def test_timeout_and_queued_revision_conflict(factory, locked, monkeypatch):
    client = factory()
    work = setup(client, locked)

    async def timeout(*args):
        raise TimeoutError

    monkeypatch.setattr(work, "dispatch", timeout)
    job = await done(work, work.start(locked.id, request(locked)))
    assert job.error_code == "WORK_TIMEOUT"
    stale = work.start(locked.id, request(locked, key="stale-queued-key"))
    locked.revision += 1
    with client.store.connection:
        client.store.connection.execute(
            "UPDATE campaigns SET revision=?,payload=? WHERE id=?",
            (locked.revision, locked.model_dump_json(), locked.id),
        )
    assert (await done(work, stale)).status == "stale"
    assert not client.store.calls()
    await client.close()


async def test_429_is_queued_with_fake_clock_and_accounted_once(factory, locked):
    count = 0

    def limited(req):
        nonlocal count
        count += 1
        return httpx.Response(429, headers={"Retry-After": "31"}) if count == 1 else handler(req)

    client = factory(limited)
    work = setup(client, locked)
    job = await done(work, work.start(locked.id, request(locked)))
    assert job.status == "completed" and count == 2
    assert 31 in client.clock.sleeps
    assert work.snapshot(locked.id).jobs[0].calls == 2
    assert any("Retry-After" in e.message for e in work.events(locked.id))
    for _ in range(5):
        work.events(locked.id)
    assert len(client.store.calls()) == 2
    await client.close()


async def test_partial_language_failure_retains_ready_work(factory, locked):
    failing = True

    def partial(req):
        if req.url.path.endswith("/chat/completions"):
            payload, data = inputs(req)
            if (
                failing
                and "R4" in payload["messages"][0]["content"]
                and data.get("language") == "kn"
            ):
                return httpx.Response(401)
        return handler(req)

    client = factory(partial)
    work = setup(client, locked)
    plan = await work.app.state.generation.strategy(locked.id, locked.revision)
    body = selection(locked, plan, languages=["en", "kn"], channels=["whatsapp"])
    job = await done(
        work,
        work.start(
            locked.id,
            WorkRequest(
                kind="generate", idempotency_key="partial-language-key", input=body.model_dump()
            ),
        ),
    )
    assert job.status == "partial"
    cells = job.result["cells"]
    assert any(c["state"] == "ready" and c["language"] == "en" for c in cells)
    assert all(c["state"] != "ready" for c in cells if c["language"] == "kn")
    recovered = WorkService(work.app)
    assert recovered.get(job.id).result == job.result
    failing = False
    before = len(client.store.calls())
    retried = await done(
        work,
        work.retry(
            job.id,
            WorkRetry(
                expected_revision=locked.revision, idempotency_key="retry-unfinished-language"
            ),
        ),
    )
    assert retried.status == "completed"
    assert len(client.store.calls()) == before + 1
    en_ids = [c["variant"]["id"] for c in job.result["cells"] if c["state"] == "ready"]
    assert all(any(c["variant"]["id"] == id for c in retried.result["cells"]) for id in en_ids)
    await client.close()


async def test_deadline_and_call_budget_fail_before_sending(factory, locked):
    client = factory()
    work = setup(client, locked)
    job = work.start(locked.id, request(locked))
    job.deadline = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    work.save(job, "Deadline reached.")
    assert (await done(work, job)).error_code == "BUDGET_EXHAUSTED"
    assert not client.store.calls()
    await client.close()


async def test_trace_and_job_metadata_do_not_expose_provider_secret(factory, locked):
    client = factory(inference_api_key="sentinel-provider-secret-b7")
    work = setup(client, locked)
    await done(work, work.start(locked.id, request(locked)))
    text = (
        json.dumps([e.model_dump() for e in work.events(locked.id)])
        + work.snapshot(locked.id).model_dump_json()
    )
    assert "sentinel-provider-secret-b7" not in text
    assert "internal reasoning" not in text
    await client.close()


async def test_image_timeout_is_uncertain_and_cannot_duplicate_submission(factory, locked):
    count = 0

    def timed(req):
        nonlocal count
        if req.url.path.endswith("/images/generations"):
            count += 1
            raise httpx.ReadTimeout("timed out")
        return handler(req)

    client = factory(timed)
    work = setup(client, locked)
    job = await done(
        work, work.start(locked.id, request(locked, "background", source="provider", size="square"))
    )
    assert count == 1
    assert job.status == "partial" and job.result["provenance"] == "deterministic"
    assert "Provider image unavailable" in job.notices[0]
    with pytest.raises(ProviderError, match="uncertain"):
        work.retry(
            job.id,
            WorkRetry(expected_revision=locked.revision, idempotency_key="unsafe-media-retry"),
        )
    assert count == 1
    await client.close()


async def test_saved_manifest_keeps_mode_provenance_and_cannot_bypass_approval(factory, locked):
    client = factory()
    _, approvals, items, _ = await delivery_setup(client, locked)
    with pytest.raises(ProviderError):
        approvals.export(locked.id, locked.revision, [items[0].id], saved_view=True)
    await approvals.audit(locked.id, items[0].id, locked.revision)
    approvals.approve(locked.id, approval_request(locked, items))
    pack, _ = approvals.export(locked.id, locked.revision, [items[0].id], saved_view=True)
    assert pack.mode == "cached" and pack.source_mode == "mock"
    assert pack.files[0].mode == "cached" and pack.files[0].source_mode == "mock"
    assert "SAVED DEMO OUTPUT" in pack.view_label
    import io
    import zipfile

    raw = approvals.zip(locked.id, locked.revision, [items[0].id], saved_view=True)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    assert manifest["mode"] == "cached" and manifest["files"][0]["sha256"] == items[0].sha256
    await client.close()


async def test_dispatched_attempt_is_durable_and_cancel_blocks_late_native_output(factory, locked):
    entered = asyncio.Event()

    async def transport(req):
        payload, _ = inputs(req)
        if "R4" in payload["messages"][0]["content"]:
            entered.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                # Adversarial transport: returns a completed response after cancellation.
                return handler(req)
        return handler(req)

    client = factory(transport)
    work = setup(client, locked)
    plan = await work.app.state.generation.strategy(locked.id, locked.revision)
    body = selection(locked, plan, languages=["en"], channels=["whatsapp"])
    job = work.start(
        locked.id,
        WorkRequest(kind="generate", idempotency_key="late-cancel-native", input=body.model_dump()),
    )
    await entered.wait()
    own = [c for c in client.store.calls() if c.work_id == job.id]
    assert len(own) == 1 and own[0].status == "in_flight" and own[0].sent
    native_id = work.get(job.id).native_run_id
    await work.cancel(job.id)
    assert work.get(job.id).status == "cancelled"
    native = work.app.state.generation.repo.get(native_id)
    assert native.status == "cancelled" and not any(c.state == "ready" for c in native.cells)
    assert len([c for c in client.store.calls() if c.work_id == job.id]) == 1
    await client.close()


async def test_work_queue_capacity_is_finite(factory, locked, monkeypatch):
    client = factory()
    work = setup(client, locked)

    async def blocked(*args):
        await asyncio.Event().wait()

    monkeypatch.setattr(work, "dispatch", blocked)
    jobs = [work.start(locked.id, request(locked, key=f"bounded-queue-{i}")) for i in range(18)]
    await asyncio.sleep(0)
    snapshot = work.snapshot(locked.id)
    assert snapshot.active == 2 and snapshot.queued == 16
    with pytest.raises(ProviderError, match="Queue is full"):
        work.start(locked.id, request(locked, key="queue-over-capacity"))
    for job in jobs:
        await work.cancel(job.id)
    assert not client.store.calls()
    await client.close()


async def test_durable_red_team_modes_keep_their_distinct_outcomes(factory, locked):
    client = factory()
    work = setup(client, locked)
    instruction = request(
        locked,
        "red_team",
        key="durable-red-team-instruct",
        mode="instruct_ai",
        text="Make it 25%",
        idempotency_key="native-red-team-instruct",
    )
    proposed = await done(work, work.start(locked.id, instruction))
    assert proposed.result["proposal"]["classification"] == "immutable"
    assert proposed.result["proposal"]["status"] == "proposed"
    direct = request(
        locked,
        "red_team",
        key="durable-red-team-direct",
        mode="edit_copy",
        text="25% off",
        idempotency_key="native-red-team-direct",
    )
    checked = await done(work, work.start(locked.id, direct))
    assert checked.result["report"]["status"] == "BLOCKED"
    assert work.campaigns.repo.get(locked.id).revision == locked.revision
    await client.close()


async def test_pre_b7_native_key_replay_retains_old_request_binding(factory, locked):
    client = factory()
    work = setup(client, locked)
    native = work.app.state.generation
    plan = await native.strategy(locked.id, locked.revision)
    body = selection(locked, plan, languages=["en"], channels=["whatsapp"])
    run = native.start(locked.id, body)
    await native.tasks[run.id]
    before = len(client.store.calls())
    legacy_hash = digest(body.model_dump(exclude={"retry_source_run_id"}))
    with client.store.connection:
        client.store.connection.execute(
            "UPDATE generation_runs SET request_hash=? WHERE id=?", (legacy_hash, run.id)
        )
    assert native.start(locked.id, body).id == run.id
    with pytest.raises(ProviderError):
        native.start(locked.id, body.model_copy(update={"retry_source_run_id": run.id}))
    assert len(client.store.calls()) == before
    await client.close()
