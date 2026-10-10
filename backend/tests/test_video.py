import asyncio
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from pydantic import ValidationError

from backend.errors import ProviderError
from backend.tests.test_generation import locked as locked_fixture
from backend.tests.test_work import done, setup
from backend.video_service import VideoInput, VideoService
from backend.work_models import WorkRequest, WorkRetry


def body(campaign, **changes):
    return {
        "expected_revision": campaign.revision,
        "duration": 24,
        "generated_seconds": 18,
        "confirm_clip_count": True,
        "confirm_possible_charges": True,
        "confirm_video_access": True,
        **changes,
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"confirm_clip_count": False},
        {"confirm_possible_charges": False},
        {"confirm_video_access": False},
        {"generated_seconds": 24},
        {"duration": 12},
        {"prompt": "invent free cake"},
        {"model": "another-provider"},
    ],
)
def test_direct_video_input_cannot_bypass_confirmation_or_server_prompt(changes):
    with pytest.raises(ValidationError):
        VideoInput.model_validate(body(SimpleNamespace(revision=1), **changes))


async def configured(factory, tmp_path, monkeypatch, attack=None):
    campaign = locked_fixture.__wrapped__()
    submitted = []

    def transport(request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "disabled"}]})
        if request.method == "POST":
            payload = json.loads(request.content)
            assert payload["model"] == "disabled"
            submitted.append(payload)
            return httpx.Response(200, json={"video_id": f"unit-clip-{len(submitted)}"})
        assert request.url.params["model_name"] == "disabled"
        if attack == "failed" or (
            attack == "one_clip_failed" and request.url.params["video_id"] == "unit-clip-2"
        ):
            return httpx.Response(200, json={"status": "failed"})
        if attack == "timeout":
            return httpx.Response(200, json={"status": "processing"})
        return httpx.Response(200, json={"status": "completed", "url": "https://mock.invalid/clip"})

    client = factory(
        transport,
        enable_video=True,
        video_entitlement_verified=True,
        asset_path=tmp_path / "assets",
    )
    work = setup(client, campaign)
    work.app.state.settings = client.settings.model_copy(update={"inference_mode": "live"})
    work.app.state.work = work
    video = VideoService(work.app)
    video.client = client  # Explicit offline transport, never evidence of a live provider result.
    work.app.state.video = video
    monkeypatch.setattr("backend.video_service.binary", lambda name: name)

    async def download(url, destination, **kwargs):
        if attack in {"expired", "undownloadable"}:
            raise ProviderError("MEDIA_INVALID", "Expired URL")
        path = destination / (str(len(list(destination.glob("*.mp4")))) + ".mp4")
        path.write_bytes(b"UNIT TEST MOCK FOOTAGE; not a generated video")
        return {"filename": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    async def command(*args):
        if args[0] == "ffprobe":
            return json.dumps(
                {
                    "streams": [
                        {
                            "codec_type": "video",
                            "width": 1 if attack == "spec" else 720,
                            "height": 1280,
                            "codec_name": "h264",
                            "pix_fmt": "yuv420p",
                            "avg_frame_rate": "30/1",
                        },
                        {"codec_type": "audio", "codec_name": "aac"},
                    ],
                    "format": {"duration": "6" if Path(args[-1]).stem.isdigit() else "18"},
                }
            ).encode()
        Path(args[-1]).write_bytes(b"UNIT TEST MOCK COMPOSITION")
        return b""

    monkeypatch.setattr("backend.video_service.download_image", download)
    monkeypatch.setattr("backend.video_service.command", command)
    return client, work, campaign, submitted


async def test_video_job_persists_ids_bytes_specs_and_never_approves(
    factory, tmp_path, monkeypatch
):
    client, work, campaign, submitted = await configured(factory, tmp_path, monkeypatch)
    job = work.start(
        campaign.id,
        WorkRequest(kind="video", idempotency_key="video-test-key", input=body(campaign)),
    )
    saved = await done(work, job)
    assert saved.status == "completed"
    assert len(submitted) == 3
    value = work.app.state.video.get(job.id)
    assert value["approval"] == "UNAPPROVED" and value["qa"] == "NOT_VERIFIED"
    assert value["duration"] == 18 and "end card" in " ".join(value["reasons"])
    assert all(c["video_id"] and c["sha256"] for c in value["clips"])
    assert work.app.state.video.artifact(job.id).exists()
    assert work.campaigns.repo.get(campaign.id).fact_hash == campaign.fact_hash
    with pytest.raises(ProviderError):
        work.retry(
            job.id, WorkRetry(expected_revision=campaign.revision, idempotency_key="retry-key")
        )
    await work.close()
    await client.close()


@pytest.mark.parametrize(
    "attack", ["failed", "one_clip_failed", "timeout", "expired", "undownloadable", "spec"]
)
async def test_video_failures_do_not_change_core_or_expose_ready_file(
    factory, tmp_path, monkeypatch, attack
):
    client, work, campaign, _ = await configured(factory, tmp_path, monkeypatch, attack)
    job = work.start(
        campaign.id,
        WorkRequest(kind="video", idempotency_key="video-test-key", input=body(campaign)),
    )
    saved = await done(work, job)
    assert saved.status == "failed"
    assert work.campaigns.repo.get(campaign.id).revision == campaign.revision
    with pytest.raises(ProviderError):
        work.app.state.video.artifact(job.id)
    await work.close()
    await client.close()


async def test_cancelled_video_cannot_publish_late_bytes(factory, tmp_path, monkeypatch):
    client, work, campaign, _ = await configured(factory, tmp_path, monkeypatch)
    waiting = asyncio.Event()

    async def blocked(*args, **kwargs):
        waiting.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(work.app.state.video.client, "request", blocked)
    job = work.start(
        campaign.id,
        WorkRequest(kind="video", idempotency_key="video-test-key", input=body(campaign)),
    )
    await waiting.wait()
    await work.cancel(job.id)
    assert work.get(job.id).status == "cancelled"
    with pytest.raises(ProviderError):
        work.app.state.video.artifact(job.id)
    await work.close()
    await client.close()


async def test_video_download_rechecks_fact_revision_and_hash(factory, tmp_path, monkeypatch):
    client, work, campaign, _ = await configured(factory, tmp_path, monkeypatch)
    job = work.start(
        campaign.id,
        WorkRequest(kind="video", idempotency_key="video-test-key", input=body(campaign)),
    )
    await done(work, job)
    value = work.app.state.video.get(job.id)
    value["revision"] += 1
    work.app.state.video.save(value)
    with pytest.raises(ProviderError) as exc:
        work.app.state.video.artifact(job.id)
    assert exc.value.body.code == "REVISION_CONFLICT"
    await work.close()
    await client.close()


async def test_failed_video_pool_does_not_reserve_core_slots(factory, tmp_path, monkeypatch):
    client, work, campaign, _ = await configured(factory, tmp_path, monkeypatch)
    waiting = asyncio.Event()
    original = work.dispatch

    async def dispatch(job, body, target):
        if job.kind == "strategy":
            return {"revision": campaign.revision}
        return await original(job, body, target)

    async def blocked(*args, **kwargs):
        waiting.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(work, "dispatch", dispatch)
    monkeypatch.setattr(work.app.state.video.client, "request", blocked)
    job = work.start(
        campaign.id,
        WorkRequest(kind="video", idempotency_key="video-test-key", input=body(campaign)),
    )
    await waiting.wait()
    core = work.start(
        campaign.id,
        WorkRequest(
            kind="strategy",
            idempotency_key="core-test-key",
            input={"expected_revision": campaign.revision},
        ),
    )
    assert (await done(work, core)).status == "completed"
    await work.cancel(job.id)
    await work.close()
    await client.close()
