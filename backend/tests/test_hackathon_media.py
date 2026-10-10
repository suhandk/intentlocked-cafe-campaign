import asyncio
import base64
import io
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend.art_models import BackgroundRequest, RenderRequest
from backend.config import Settings
from backend.contracts import SmokeResult
from backend.errors import ProviderError
from backend.local_video import LocalVideoApproval
from backend.main import create_app
from backend.mock import handler
from backend.tests.test_art import fake_canvas, prepare
from backend.tests.test_delivery import approval_request
from backend.tests.test_generation import locked as locked_fixture
from backend.tests.test_generation import seed
from backend.tests.test_work import done, setup
from backend.video_service import VideoService
from backend.work_models import WorkRequest


@pytest.fixture
def locked():
    return locked_fixture.__wrapped__()


def encoded_image(fmt="PNG"):
    output = io.BytesIO()
    Image.new("RGB", (1024, 1024), "#392519").save(output, fmt)
    return base64.b64encode(output.getvalue()).decode()


@pytest.mark.parametrize(
    "ratio,dimensions", [("1:1", (1024, 1024)), ("9:16", (864, 1536)), ("16:9", (1536, 864))]
)
async def test_current_openrouter_and_direct_openai_profile_is_fully_offline(
    factory, ratio, dimensions
):
    client = factory(
        inference_base_url="https://openrouter.ai/api/v1",
        text_model="openai/gpt-4o-mini",
        image_provider="openai",
        image_model="gpt-image-2.5-flare-2026-09-08",
    )
    assert (await client.text("Greeting", client.budget())).strip()
    assert (await client.structured("Greeting in message", SmokeResult, client.budget())).message
    url = await client.image("Coffee cup", client.budget(), ratio=ratio)
    raw = base64.b64decode(url.split(",", 1)[1])
    assert Image.open(io.BytesIO(raw)).size == dimensions
    assert all(c.mode == "mock" for c in client.store.calls())
    await client.close()


@pytest.mark.parametrize(
    "ratio,size", [("1:1", "1024x1024"), ("9:16", "864x1536"), ("16:9", "1536x864")]
)
async def test_direct_openai_raw_shape_and_secret_separation(factory, ratio, size):
    requests = []

    def transport(request):
        requests.append(request)
        return httpx.Response(200, json={"data": [{"b64_json": encoded_image()}]})

    client = factory(
        transport, image_provider="openai", image_model="gpt-image-2.5-flare-2026-09-08"
    )
    url = await client.image("Decorative coffee mug", client.budget(), ratio=ratio)
    assert url.startswith("data:image/png;base64,")
    request = requests[0]
    assert request.url == "https://api.openai.com/v1/images/generations"
    assert json.loads(request.content) == {
        "model": "gpt-image-2.5-flare-2026-09-08",
        "prompt": "Decorative coffee mug",
        "n": 1,
        "size": size,
        "quality": "medium",
        "output_format": "png",
    }
    assert "authorization" not in request.headers  # MOCK never uses either credential.
    await client.close()


async def test_openrouter_capabilities_raw_shape_and_actual_jpeg(factory):
    requests = []

    def transport(request):
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "id": "bytedance-seed/seedream-5-0-flash",
                    "endpoints": [
                        {
                            "supported_parameters": {
                                "resolution": {"type": "enum", "values": ["1K"]},
                                "aspect_ratio": {"type": "enum", "values": ["1:1"]},
                                "n": {"type": "range", "min": 1, "max": 1},
                            }
                        }
                    ],
                },
            )
        return httpx.Response(
            200, json={"data": [{"b64_json": encoded_image("JPEG")}], "usage": {"cost": 0.018}}
        )

    client = factory(
        transport,
        inference_base_url="https://openrouter.ai/api/v1",
        image_model="bytedance-seed/seedream-5-0-flash",
    )
    result = await client.image("Decorative mug", client.budget())
    assert result.startswith("data:image/jpeg;base64,")
    assert requests[1].url.path == "/api/v1/images"
    assert json.loads(requests[1].content)["resolution"] == "1K"
    assert client.store.calls()[0].provider_reported_cost_usd == 0.018
    with pytest.raises(ProviderError) as exc:
        await client.image("Decorative mug", client.budget(), ratio="9:16")
    assert exc.value.body.code == "IMAGE_PARAMETER_UNSUPPORTED"
    assert len(requests) == 2  # No unsupported charged POST.
    await client.close()


@pytest.mark.parametrize(
    "ratio,dimensions", [("1:1", (1024, 1024)), ("9:16", (576, 1024)), ("16:9", (1024, 576))]
)
async def test_selected_seedream_mock_profile_stays_offline(factory, ratio, dimensions):
    requests = []

    def transport(request):
        requests.append(request)
        assert "authorization" not in request.headers
        return handler(request)

    client = factory(
        transport,
        inference_base_url="https://openrouter.ai/api/v1",
        text_model="openai/gpt-4o-mini",
        image_model="bytedance-seed/seedream-5-0-flash",
    )
    try:
        url = await client.image("MOCK coffee illustration", client.budget(), ratio=ratio)
        raw = base64.b64decode(url.split(",", 1)[1])
        assert Image.open(io.BytesIO(raw)).size == dimensions
        assert [(r.method, r.url.path) for r in requests] == [
            ("GET", "/api/v1/images/models/bytedance-seed/seedream-5-0-flash/endpoints"),
            ("POST", "/api/v1/images"),
        ]
        assert all(call.mode == "mock" for call in client.store.calls())
        assert client.store.calls()[0].provider_reported_cost_usd is None
    finally:
        await client.close()


@pytest.mark.parametrize(
    "status,body", [(402, {}), (429, {"error": {"code": "insufficient_quota"}})]
)
async def test_payment_error_has_no_retry_or_minute_sleep(factory, status, body):
    client = factory(lambda _: httpx.Response(status, json=body))
    with pytest.raises(ProviderError) as exc:
        await client.image("coffee", client.budget())
    assert exc.value.body.code == "PAYMENT_REQUIRED"
    assert len(client.store.calls()) == 1 and not any(client.clock.sleeps)
    await client.close()


@pytest.mark.parametrize("status", [200, 401])
async def test_token_usage_survives_provider_details_and_cost_without_storing_extras(
    factory, status
):
    def transport(request):
        data = handler(request).json()
        data["usage"] = {
            "prompt_tokens": 3,
            "completion_tokens": 2,
            "total_tokens": 5,
            "completion_tokens_details": {"reasoning_tokens": 1},
            "cost": 0.000123,
            "untrusted_extra": "DO_NOT_PERSIST_PROVIDER_EXTRA",
        }
        return httpx.Response(status, json=data)

    client = factory(transport)
    if status == 401:
        with pytest.raises(ProviderError):
            await client.text("Greeting", client.budget())
    else:
        await client.text("Greeting", client.budget())
    record = client.store.calls()[0]
    assert record.usage.model_dump() == {
        "prompt_tokens": 3,
        "completion_tokens": 2,
        "total_tokens": 5,
    }
    assert record.provider_reported_cost_usd == 0.000123
    assert "DO_NOT_PERSIST_PROVIDER_EXTRA" not in record.model_dump_json()
    await client.close()


def test_missing_direct_openai_key_is_actionable_422_before_job_or_network(tmp_path, locked):
    settings = Settings(
        _env_file=None,
        database_path=tmp_path / "missing-key.sqlite3",
        asset_path=tmp_path / "assets",
        inference_mode="live",
        image_provider="openai",
        image_model="gpt-image-2.5-flare-2026-09-08",
    )
    with TestClient(create_app(settings)) as api:
        seed(api.app.state.client, locked)
        health = api.get("/api/ready").json()
        assert (
            not health["image_generation_enabled"]
            and "OPENAI_API_KEY" in health["image_configuration_notice"]
        )
        body = {"expected_revision": 1, "size": "square", "source": "provider"}
        direct = api.post(f"/api/campaigns/{locked.id}/backgrounds", json=body)
        queued = api.post(
            f"/api/campaigns/{locked.id}/work",
            json={
                "kind": "background",
                "idempotency_key": "missing-key-no-job",
                "input": body,
            },
        )
        assert direct.status_code == queued.status_code == 422
        assert direct.json()["code"] == queued.json()["code"] == "IMAGE_KEY_MISSING"
        assert api.app.state.store.calls() == []
        assert (
            api.app.state.store.connection.execute("SELECT count(*) FROM work_jobs").fetchone()[0]
            == 0
        )


@pytest.mark.parametrize(
    "kind,source,endpoint,expected",
    [
        ("strategy", None, "https://openrouter.ai/api/v1", "OpenRouter"),
        ("strategy", None, "http://127.0.0.1:20128/v1", "Configured gateway"),
        ("background", "provider", "https://openrouter.ai/api/v1", "OpenAI"),
        ("background", "deterministic", "https://openrouter.ai/api/v1", "Local renderer"),
    ],
)
async def test_job_provenance_names_the_actual_selected_operation(
    factory, locked, kind, source, endpoint, expected
):
    client = factory(
        inference_base_url=endpoint,
        image_provider="openai",
        image_model="gpt-image-2.5-flare-2026-09-08",
    )
    work = setup(client, locked)
    job = work.start(
        locked.id,
        WorkRequest(
            kind=kind,
            idempotency_key="provider-label-test",
            input={
                "expected_revision": 1,
                **({"size": "square", "source": source} if source else {}),
            },
        ),
    )
    assert job.provider == expected
    await work.cancel(job.id)
    assert client.store.calls() == []
    await work.close()
    await client.close()


async def local_setup(factory, locked, tmp_path, monkeypatch, fail=None):
    client = factory(asset_path=tmp_path / "assets")
    variant = await prepare(client, locked)
    work = setup(client, locked, seed_campaign=False)
    work.app.state.work = work
    work.app.state.video = VideoService(work.app)
    work.app.state.art.renderer = fake_canvas
    background = await work.app.state.art.background(
        locked.id, BackgroundRequest(expected_revision=1, size="story", source="deterministic")
    )
    poster = await work.app.state.art.render(
        locked.id,
        RenderRequest(
            expected_revision=1, size="story", variant_id=variant.id, background_id=background.id
        ),
    )
    monkeypatch.setattr("backend.video_service.binary", lambda name: name)

    async def command(*args):
        if fail == "timeout":
            raise TimeoutError
        if args[0] == "ffprobe":
            return json.dumps(
                {
                    "streams": [
                        {
                            "codec_type": "video",
                            "codec_name": "h264",
                            "width": 720,
                            "height": 1280,
                            "pix_fmt": "yuv420p",
                            "avg_frame_rate": "30/1",
                        },
                        {"codec_type": "audio", "codec_name": "aac"},
                    ],
                    "format": {"duration": "12"},
                }
            ).encode()
        Path(args[-1]).write_bytes(b"UNIT TEST COMPOSITION; not a real MP4")
        return b""

    monkeypatch.setattr("backend.video_service.command", command)
    request = WorkRequest(
        kind="local_video",
        idempotency_key="local-animation-test",
        input={"expected_revision": 1, "poster_id": poster.id, "duration": 12},
    )
    return client, work, request, poster


async def test_local_video_duplicate_persistence_approval_and_export(
    factory, locked, tmp_path, monkeypatch
):
    client, work, request, poster = await local_setup(factory, locked, tmp_path, monkeypatch)
    before = len(client.store.calls())
    job = work.start(locked.id, request)
    assert work.start(locked.id, request).id == job.id
    assert (await done(work, job)).status == "completed"
    assert len(client.store.calls()) == before
    video = work.app.state.video
    value = video.get(job.id)
    assert value["source"] == "local_animation" and value["approval"] == "UNAPPROVED"
    assert video.artifact(job.id).exists()
    body = LocalVideoApproval(
        expected_revision=1,
        observed_hash=value["sha256"],
        owner_approves=True,
        idempotency_key="approve-animation-test",
    )
    with pytest.raises(ProviderError):
        video.approve_local(job.id, body)  # Source approval cannot be bypassed.
    with pytest.raises(ProviderError):
        video.local_manifest(job.id, saved_view=True)
    item = next(
        i for i in work.app.state.approvals.ledger.active(locked) if i.poster_id == poster.id
    )
    audit = await work.app.state.approvals.audit(locked.id, item.id, 1)
    owner_request = approval_request(locked, [item], native_review_confirmed=True)
    owner_request.acknowledged_warning_ids = audit.warning_ids
    work.app.state.approvals.approve(locked.id, owner_request)
    assert video.approve_local(job.id, body)["approval"] == "APPROVED"
    assert video.approve_local(job.id, body)["approved_hash"] == value["sha256"]
    assert video.local_manifest(job.id)["source_provenance"] == "mock"
    cached = video.local_manifest(job.id, saved_view=True)
    assert cached["mode"] == cached["source_manifest"]["mode"] == "cached"
    assert cached["source_mode"] == cached["source_manifest"]["source_mode"] == "mock"
    assert cached["approved_hash"] == value["sha256"]
    restored = VideoService(work.app)
    assert restored.artifact(job.id).read_bytes() == video.artifact(job.id).read_bytes()
    video.artifact(job.id).write_bytes(b"TAMPERED")
    with pytest.raises(ProviderError):
        video.local_manifest(job.id)
    await work.close()
    await client.close()


@pytest.mark.parametrize("failure", ["timeout", "stale", "cancelled", "source_changed"])
async def test_local_video_stops_and_rejects_changed_dependencies(
    factory, locked, tmp_path, monkeypatch, failure
):
    client, work, request, poster = await local_setup(
        factory, locked, tmp_path, monkeypatch, "timeout" if failure == "timeout" else None
    )
    job = work.start(locked.id, request)
    await done(work, job)
    if failure == "stale":
        locked.revision = 2
        work.db.execute(
            "UPDATE campaigns SET revision=2,payload=? WHERE id=?",
            (locked.model_dump_json(), locked.id),
        )
        work.db.commit()
    elif failure == "cancelled":
        saved = work.get(job.id)
        saved.status = "cancelled"
        work.save(saved, "test cancellation")
    elif failure == "source_changed":
        poster.render_input.renderer_hash = "tampered"
        work.db.execute(
            "UPDATE poster_artifacts SET payload=? WHERE id=?",
            (poster.model_dump_json(), poster.id),
        )
        work.db.commit()
    with pytest.raises(ProviderError):
        work.app.state.video.artifact(job.id)
    await work.close()
    await client.close()


@pytest.mark.parametrize("interruption", ["cancel", "fact_change"])
async def test_in_progress_encoder_cannot_commit_after_cancellation_or_fact_edit(
    factory, locked, tmp_path, monkeypatch, interruption
):
    client, work, request, _ = await local_setup(factory, locked, tmp_path, monkeypatch)
    from backend import video_service

    original_command = video_service.command
    entered, release = asyncio.Event(), asyncio.Event()

    async def held_command(*args):
        if args[0] == "ffmpeg":
            entered.set()
            await release.wait()
        return await original_command(*args)

    monkeypatch.setattr(video_service, "command", held_command)
    job = work.start(locked.id, request)
    await asyncio.wait_for(entered.wait(), 2)
    assert work.get(job.id).status == "running"
    if interruption == "cancel":
        await work.cancel(job.id)
        assert work.get(job.id).status == "cancelled"
        assert work.app.state.video.get(job.id)["status"] == "cancelled"
    else:
        locked.revision = 2
        with work.db:
            work.db.execute(
                "UPDATE campaigns SET revision=2,payload=? WHERE id=?",
                (locked.model_dump_json(), locked.id),
            )
        release.set()
        assert (await done(work, job)).status == "stale"
        assert work.app.state.video.get(job.id)["status"] == "failed"
    with pytest.raises(ProviderError):
        work.app.state.video.local_manifest(job.id)
    assert work.app.state.video.get(job.id)["approval"] == "UNAPPROVED"
    await work.close()
    await client.close()
