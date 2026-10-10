"""Current and compatible model adapters, protected error reporting, direct bypasses."""

import base64
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.errors import ProviderError
from backend.main import create_app
from backend.media import download_image
from backend.mock import handler, mock_png
from backend.tests import test_generation

locked = test_generation.locked


@pytest.mark.parametrize("status", [400, 404, 422])
async def test_provider_error_body_never_leaks_to_logs_disk_response_or_trace(
    factory, tmp_path, monkeypatch, capsys, caplog, status
):
    secret = "workflow-debug-private-value"
    monkeypatch.chdir(tmp_path)
    client = factory(lambda r: httpx.Response(status, json={"error": secret, "prompt": secret}))
    with pytest.raises(ProviderError) as exc:
        await client.text("A greeting", client.budget())
    assert exc.value.body.code == "INVALID_REQUEST"
    assert secret not in exc.value.body.model_dump_json()
    assert secret not in capsys.readouterr().out + caplog.text
    assert not (tmp_path / "error_log.txt").exists()
    assert secret not in json.dumps([c.model_dump() for c in client.store.calls()])
    await client.close()


@pytest.mark.parametrize("model", ["nb/nanobanana-flash", "bytedance-seed/seedream-5-0-flash"])
@pytest.mark.parametrize(
    "ratio,dims", [("1:1", (1024, 1024)), ("9:16", (576, 1024)), ("16:9", (1024, 576))]
)
async def test_both_image_adapters_preserve_native_ratio(factory, tmp_path, model, ratio, dims):
    seen = []

    def transport(request):
        if request.url.path.endswith("/images/generations"):
            seen.append(json.loads(request.content))
        return handler(request)

    client = factory(transport, image_model=model)
    url = await client.image("Abstract text-free art", client.budget(), ratio=ratio)
    saved = await download_image(url, tmp_path, mock_transport=client.mock_transport)
    assert (saved["width"], saved["height"]) == dims
    if model == "nb/nanobanana-flash":
        assert seen[0]["size"] == f"{dims[0]}x{dims[1]}" and "width" not in seen[0]
    else:
        assert (seen[0]["width"], seen[0]["height"]) == dims and "size" not in seen[0]
    await client.close()


async def test_base64_provider_response_uses_same_raster_validation(factory, tmp_path):
    encoded = base64.b64encode(mock_png()).decode()
    client = factory(lambda r: httpx.Response(200, json={"data": [{"b64_json": encoded}]}))
    output = await client.image("Text-free art", client.budget())
    assert output.startswith("data:image/png;base64,")
    saved = await download_image(output, tmp_path)
    assert saved["width"] == saved["height"] == 1024
    assert (tmp_path / saved["filename"]).read_bytes() == mock_png()
    await client.close()


@pytest.mark.parametrize(
    "value",
    [
        None,
        "data:image/png;base64,INVALID!",
        "data:image/svg+xml;base64,PHN2Zy8+",
        "data:image/png;base64,dGV4dA==",
    ],
)
async def test_unsafe_inline_media_rejected(tmp_path, value):
    with pytest.raises(ProviderError) as exc:
        await download_image(value, tmp_path)
    assert exc.value.body.code == "MEDIA_INVALID"
    assert not list(tmp_path.iterdir())


async def test_multiple_images_cannot_silently_choose_first(factory):
    client = factory(
        lambda r: httpx.Response(200, json={"data": [{"url": "https://mock.invalid/a"}] * 2})
    )
    with pytest.raises(ProviderError) as exc:
        await client.image("art", client.budget())
    assert exc.value.body.code == "INVALID_OUTPUT"
    await client.close()


def test_direct_video_job_cannot_bypass_disabled_frontend(tmp_path, locked):
    settings = Settings(_env_file=None, database_path=tmp_path / "db.sqlite3")
    with TestClient(create_app(settings)) as api:
        test_generation.seed(api.app.state.client, locked)
        response = api.post(
            f"/api/campaigns/{locked.id}/work",
            json={
                "kind": "video",
                "idempotency_key": "direct-video-bypass",
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
        assert api.get(f"/api/campaigns/{locked.id}/work").json()["jobs"] == []
        assert api.get("/api/health").status_code == 200
        assert api.get("/api/video/config").json()["price_verified"] is False


def test_isolated_test_storage_retries_windows_handle_release(monkeypatch):
    from pathlib import Path
    from tempfile import TemporaryDirectory

    from scripts import verify_workflow

    original = TemporaryDirectory.cleanup
    attempts = []
    sleeps = []

    def cleanup(temporary):
        attempts.append(temporary.name)
        if len(attempts) < 3:
            raise PermissionError("Controlled Windows handle contention")
        return original(temporary)

    monkeypatch.setattr(TemporaryDirectory, "cleanup", cleanup)
    monkeypatch.setattr(verify_workflow.time, "sleep", sleeps.append)
    with verify_workflow.test_workspace() as folder:
        (Path(folder) / "test.sqlite3").write_bytes(b"Explicit fixture")
    assert len(attempts) == 3 and sleeps == [0.5, 0.5]
    assert not Path(folder).exists()
