"""New provider boundaries, tested with controlled transports and no real account calls."""

import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from pydantic import ValidationError

from backend.art_models import BackgroundRequest
from backend.art_routes import unapproved_background
from backend.art_service import ArtService
from backend.config import Settings
from backend.contracts import SmokeResult
from backend.db import Store
from backend.errors import ProviderError
from backend.mock import FIXTURES, mock_png
from backend.tests.test_generation import locked as locked_fixture
from backend.tests.test_generation import seed


@pytest.mark.parametrize(
    "changes",
    [
        {"text_model": "agnes-3.0-flash"},
        {"image_model": "agnes-image-2.5-flash"},
        {"video_model": "agnes-video-2.5-flash"},
        {"enable_video": True},
        {"inference_base_url": "https://user:password@gateway.test/v1"},
        {"inference_base_url": "https://gateway.test/v1?token=secret"},
        {"inference_base_url": "http://gateway.test/v1"},
        {"inference_base_url": "https://apihub.agnes-ai.com/v1"},
    ],
)
def test_old_models_and_unsafe_gateway_configuration_rejected(changes):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **changes)


def test_credentials_load_from_private_env_without_disclosure(tmp_path):
    path = tmp_path / ".env"
    path.write_text(
        "INFERENCE_API_KEY=GATEWAY_TEST_ONLY\n"
        "NANOBANANA_API_KEY=IMAGE_TEST_ONLY\n"
        "OLLAMA_API_KEY=TEXT_TEST_ONLY\n"
        "TEXT_INPUT_PRICE_PER_MILLION=\n"
        "ENABLE_VIDEO=false\n",
        encoding="utf-8",
    )
    settings = Settings(_env_file=path)
    assert settings.inference_api_key.get_secret_value() == "GATEWAY_TEST_ONLY"
    assert settings.nanobanana_api_key.get_secret_value() == "IMAGE_TEST_ONLY"
    assert settings.ollama_api_key.get_secret_value() == "TEXT_TEST_ONLY"
    assert "TEST_ONLY" not in repr(settings)
    assert settings.text_input_price_per_million is None and not settings.enable_video


async def test_live_shape_uses_only_gateway_key_and_preserves_unknown_prices(factory):
    captured = []

    def handler(request):
        captured.append(request)
        return httpx.Response(200, json=json.loads((FIXTURES / "text.json").read_text()))

    client = factory(
        handler,
        inference_api_key="GATEWAY_ONLY",
        nanobanana_api_key="IMAGE_PRIVATE",
        ollama_api_key="TEXT_PRIVATE",
        text_input_price_per_million=None,
        text_output_price_per_million=None,
    )
    # Controlled transport remains offline; this exercises live header construction only.
    client.settings = client.settings.model_copy(update={"inference_mode": "live"})
    await client.text("A greeting", client.budget())
    assert captured[0].headers["Authorization"] == "Bearer GATEWAY_ONLY"
    assert json.loads(captured[0].content)["model"] == "ollama/gpt-oss:120b"
    assert "IMAGE_PRIVATE" not in str(captured) and "TEXT_PRIVATE" not in str(captured)
    assert client.store.calls()[0].usage is not None
    assert client.store.calls()[0].list_price_estimate_usd is None
    assert client.store.cost().unknown_cost_calls == 1
    await client.close()


async def test_live_vision_and_video_fail_before_any_transport_call(factory):
    captured = []

    def handler(request):
        captured.append(request)
        raise AssertionError("Unsupported capabilities must not reach transport")

    client = factory(handler)
    client.settings = client.settings.model_copy(update={"inference_mode": "live"})
    for operation in [
        client.text("inspect", client.budget(), image_url="https://image.test/x.png"),
        client.structured(
            "inspect", SmokeResult, client.budget(), vision_image="data:image/png;base64,AA=="
        ),
        client.request("video", {"model": "disabled"}, client.budget()),
    ]:
        with pytest.raises(ProviderError) as caught:
            await operation
        assert caught.value.body.code in {"VISION_UNSUPPORTED", "VIDEO_DISABLED"}
    assert captured == [] and client.store.calls() == []
    await client.close()


async def test_generated_image_retained_blocked_without_fabricated_vision(
    factory, tmp_path, monkeypatch
):
    client = factory(asset_path=tmp_path / "assets")
    campaign = locked_fixture.__wrapped__()
    seed(client, campaign)
    client.settings = client.settings.model_copy(update={"inference_mode": "live"})

    async def download(url, destination, **kwargs):
        path = Path(destination) / "controlled-fixture.png"
        path.write_bytes(mock_png())
        return {"filename": path.name, "mime": "image/png"}

    monkeypatch.setattr("backend.art_service.download_image", download)
    service = ArtService(client.store, client, client.settings)
    background = await service.background(
        campaign.id, BackgroundRequest(expected_revision=1, size="square")
    )
    assert background.status == "blocked" and background.qa is None
    assert background.generation_model == "nb/nanobanana-flash" and background.qa_model is None
    assert "IMAGE_QA_REQUIRED" in background.reasons
    assert service.storage.read(background.sha256)
    assert len(client.store.calls()) == 1 and client.store.calls()[0].operation == "image"
    with pytest.raises(ProviderError):
        service.bytes(background.id)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(art=service)))
    preview = await unapproved_background(background.id, request)
    assert preview.body == service.storage.read(background.sha256)
    assert preview.headers["X-Artifact-Approval"] == "blocked"
    service.storage.root.joinpath(f"{background.sha256}.png").write_bytes(b"tampered")
    with pytest.raises(ProviderError) as tampered:
        await unapproved_background(background.id, request)
    assert tampered.value.body.code == "ART_TAMPERED"
    await client.close()


def test_migration_collision_reconciles_both_branches_without_erasing_video(tmp_path):
    path = tmp_path / "db.sqlite3"
    store = Store(path)
    with store.connection:
        store.connection.execute("DELETE FROM migrations WHERE version=11")
        store.connection.execute("DROP TABLE social_profiles")
        store.connection.execute("INSERT INTO campaign_videos VALUES('historic','campaign','{}')")
    store.close()
    repaired = Store(path)
    assert repaired.connection.execute("SELECT id FROM campaign_videos").fetchone()[0] == "historic"
    assert repaired.connection.execute("SELECT count(*) FROM social_profiles").fetchone()[0] == 0
    assert repaired.connection.execute("SELECT count(*) FROM campaign_plans").fetchone()[0] == 0
    repaired.close()
