import base64
import io
import json
import struct
import zlib

import httpx
import pytest
from PIL import Image
from pydantic import ValidationError

from backend.art_context import font_manifest
from backend.art_models import BackgroundRequest, CanvasValidation, RenderRequest
from backend.art_service import ArtService, qa_passes
from backend.art_storage import ArtStorage, raster, sha
from backend.errors import ProviderError
from backend.generation_service import GenerationService
from backend.intent_rules import digest
from backend.mock import handler, mock_png
from backend.tests.test_generation import finish, seed, selection
from backend.tests.test_generation import locked as locked_fixture


@pytest.fixture
def locked():
    return locked_fixture.__wrapped__()


async def prepare(client, campaign):
    seed(client, campaign)
    service = GenerationService(client.store, client)
    plan = await service.strategy(campaign.id, campaign.revision)
    run = await finish(
        service, service.start(campaign.id, selection(campaign, plan, languages=["kn"]))
    )
    assert run.status == "completed"
    return run.cells[0].variant


async def fake_canvas(value, origin):
    safe = (
        [72, 200, value.width - 144, value.height - 440]
        if value.size == "story"
        else (
            [48, 48, value.width - 96, value.height - 96]
            if value.size == "landscape"
            else [64, 64, value.width - 128, value.height - 128]
        )
    )
    validation = CanvasValidation(
        passed=True,
        reasons=[],
        font_loaded=True,
        grapheme_engine=True,
        contrast=14,
        safe_area=safe,
        lines=[
            dict(
                field=k,
                text=v.replace("\n", ""),
                x=safe[0],
                y=safe[1],
                width=100,
                height=40,
                font_size=32,
            )
            for k, v in value.fields.items()
            if v and k != "alt_text"
        ],
        logo_bounds=[safe[0], safe[1], 64, 64] if value.logo_url else None,
        renderer_version=value.renderer_version,
    )
    raw = io.BytesIO()
    Image.new("RGB", (value.width, value.height), "#172B23").save(raw, "PNG")
    return raw.getvalue(), validation


@pytest.mark.parametrize(
    "size,ratio", [("feed", "1:1"), ("square", "1:1"), ("story", "9:16"), ("landscape", "16:9")]
)
async def test_background_native_ratios_safe_payload_qa_and_reuse(
    factory, locked, tmp_path, size, ratio
):
    seen = []

    def transport(request):
        if request.url.path.startswith("/v1/"):
            seen.append(json.loads(request.content))
        return handler(request)

    locked.brand.theme = "SECRET_VENUE luxury sofa free cake in Mysuru 25%"
    client = factory(transport, asset_path=tmp_path)
    seed(client, locked)
    service = ArtService(client.store, client, client.settings)
    request = BackgroundRequest(expected_revision=1, size=size)
    art = await service.background(locked.id, request)
    assert art.ratio == ratio and art.provenance == "mock" and qa_passes(art.qa)
    assert art.calls_used == 2
    assert await service.background(locked.id, request) == art
    assert len(seen) == 2
    assert seen[0]["size"] == {"1:1": "1024x1024", "9:16": "576x1024", "16:9": "1024x576"}[ratio]
    assert seen[0]["response_format"] == "url" and seen[0]["n"] == 1
    assert "extra_body" not in seen[0]
    assert "SECRET_VENUE" not in json.dumps(seen) and "25%" not in json.dumps(seen)
    assert "photorealistic café advertising" in seen[0]["prompt"]
    assert "Only the explicitly requested hero object" in seen[0]["prompt"]
    vision = seen[1]["messages"][1]["content"][1]["image_url"]["url"]
    assert sha(base64.b64decode(vision.split(",")[1])) == art.sha256
    assert service.storage.read(art.sha256)
    await client.close()


@pytest.mark.parametrize(
    "flag",
    [
        "lettering_or_numbers",
        "logos_or_watermarks",
        "products_or_extra_items",
        "venue_features",
        "promotional_implications",
        "image_loaded",
        "inspected_all_regions",
        "recommendation",
    ],
)
async def test_r9_flags_fail_closed_bounded_retry_and_fallback(factory, locked, tmp_path, flag):
    def transport(request):
        if request.url.path == "/v1/chat/completions":
            response = handler(request).json()
            function = response["choices"][0]["message"]["tool_calls"][0]["function"]
            data = json.loads(function["arguments"])
            data[flag] = (
                "uncertain"
                if flag == "recommendation"
                else flag not in {"image_loaded", "inspected_all_regions"}
            )
            function["arguments"] = json.dumps(data)
            return httpx.Response(200, json=response)
        return handler(request)

    client = factory(transport, asset_path=tmp_path)
    seed(client, locked)
    service = ArtService(client.store, client, client.settings)
    art = await service.background(locked.id, BackgroundRequest(expected_revision=1, size="square"))
    assert art.provenance == "deterministic" and art.qa is None and art.status == "ready"
    assert art.calls_used == 4 and "R9_REJECTED_OR_UNCERTAIN" in art.reasons
    rejected = service.repo.snapshot(locked.id).backgrounds
    assert len(rejected) == 3 and sum(a.status == "blocked" for a in rejected) == 2
    with pytest.raises(ProviderError):
        service.bytes(rejected[0].id)
    await client.close()


@pytest.mark.parametrize(
    "kind",
    ["expired", "redirect", "mime", "qa_malformed", "qa_unavailable", "uncertain_submission"],
)
async def test_download_or_qa_failure_is_disclosed_no_blind_media_retry(
    factory, locked, tmp_path, kind
):
    def transport(request):
        if request.url.host == "mock.invalid":
            if kind == "expired":
                return httpx.Response(403)
            if kind == "redirect":
                return httpx.Response(302, headers={"location": "https://evil.test/a"})
            if kind == "mime":
                return httpx.Response(
                    200, content=mock_png(), headers={"content-type": "text/html"}
                )
        if request.url.path == "/v1/chat/completions":
            return (
                httpx.Response(401)
                if kind == "qa_unavailable"
                else httpx.Response(200, json={"choices": []})
            )
        if request.url.path == "/v1/images/generations" and kind == "uncertain_submission":
            return httpx.Response(500)
        return handler(request)

    client = factory(transport, asset_path=tmp_path)
    seed(client, locked)
    service = ArtService(client.store, client, client.settings)
    art = await service.background(locked.id, BackgroundRequest(expected_revision=1, size="square"))
    assert art.provenance == "deterministic" and art.reasons
    assert sum(c.model == client.settings.image_model for c in client.store.calls()) == 1
    assert art.calls_used <= 4
    await client.close()


async def test_deterministic_is_clean_and_has_zero_inference_calls(factory, locked, tmp_path):
    client = factory(asset_path=tmp_path)
    seed(client, locked)
    service = ArtService(client.store, client, client.settings)
    request = BackgroundRequest(expected_revision=1, size="story", source="deterministic")
    art = await service.background(locked.id, request)
    assert art.calls_used == 0 and not client.store.calls()
    assert art.generation_model is None and art.qa_model is None
    assert await service.background(locked.id, request) == art
    assert raster(service.bytes(art.id), "image/png")[1] == (576, 1024)
    await client.close()


@pytest.mark.parametrize(
    "size,dimensions",
    [
        ("feed", (1080, 1350)),
        ("square", (1080, 1080)),
        ("story", (1080, 1920)),
        ("landscape", (1200, 630)),
    ],
)
async def test_canonical_inputs_final_hashes_and_byte_identity(
    factory, locked, tmp_path, size, dimensions
):
    client = factory(asset_path=tmp_path)
    variant = await prepare(client, locked)
    service = ArtService(client.store, client, client.settings)
    service.renderer = fake_canvas  # Unit boundary only; real browser tests are mandatory evidence.
    art = await service.background(locked.id, BackgroundRequest(expected_revision=1, size=size))
    request = RenderRequest(
        expected_revision=1, size=size, variant_id=variant.id, background_id=art.id
    )
    poster = await service.render(locked.id, request)
    assert poster.validation.passed and poster.status == "ready" and not poster.approval_ready
    assert poster.render_input.fields == poster.guardian.rendered.fields
    assert not any(k.startswith("hashtags.") for k in poster.render_input.fields)
    assert "\n" in poster.render_input.fields["body"]
    assert poster.dependencies.font_hash == font_manifest()
    assert poster.render_input.background_url == f"/api/assets/{art.id}"
    raw = service.bytes(poster.id)
    assert sha(raw) == poster.sha256 and len(raw) == poster.byte_count
    assert raster(raw, "image/png")[1] == dimensions
    assert await service.render(locked.id, request) == poster
    assert "G14" in poster.guardian.missing_checks
    with pytest.raises(ProviderError, match="pending"):
        service.approved_bytes(poster.id)
    await client.close()


async def test_numeric_edit_reuses_art_and_invalidates_poster(factory, locked, tmp_path):
    client = factory(asset_path=tmp_path)
    variant = await prepare(client, locked)
    service = ArtService(client.store, client, client.settings)
    service.renderer = fake_canvas
    background = await service.background(
        locked.id, BackgroundRequest(expected_revision=1, size="square")
    )
    old = await service.render(
        locked.id,
        RenderRequest(
            expected_revision=1, size="square", variant_id=variant.id, background_id=background.id
        ),
    )
    images_before = sum(c.model == client.settings.image_model for c in client.store.calls())
    offer = next(f for f in locked.facts if f.key == "OFFER")
    offer.canonical.value = 15
    offer.version += 1
    for forms in offer.surface.values():
        forms.nom = [v.replace("20", "15") for v in forms.nom]
    locked.revision = 2
    locked.fact_hash = digest([f.model_dump() for f in locked.facts])
    with client.store.connection:
        client.store.connection.execute("DELETE FROM campaigns WHERE id=?", ("unused",))
        client.store.connection.execute(
            "UPDATE campaigns SET revision=2,payload=? WHERE id=?",
            (locked.model_dump_json(), locked.id),
        )
    generation = GenerationService(client.store, client)
    plan = await generation.strategy(locked.id, 2)
    run = await finish(
        generation,
        generation.start(
            locked.id,
            selection(locked, plan, languages=["kn"], idempotency_key="new-numeric-revision"),
        ),
    )
    assert run.status == "completed"
    assert (
        await service.background(locked.id, BackgroundRequest(expected_revision=2, size="square"))
    ).id == background.id
    new = await service.render(
        locked.id,
        RenderRequest(
            expected_revision=2,
            size="square",
            variant_id=run.cells[0].variant.id,
            background_id=background.id,
        ),
    )
    assert new.render_hash != old.render_hash and "15%" in new.render_input.fields["body"]
    assert (
        sum(c.model == client.settings.image_model for c in client.store.calls()) == images_before
    )
    assert service.repo.snapshot(locked.id).posters[0].status == "stale"
    await client.close()


@pytest.mark.parametrize(
    "kind", ["clipped", "dropped", "missing_font", "contrast", "nan", "safe_area", "logo"]
)
async def test_renderer_bad_metrics_cannot_persist_or_export(factory, locked, tmp_path, kind):
    client = factory(asset_path=tmp_path)
    variant = await prepare(client, locked)
    service = ArtService(client.store, client, client.settings)
    background = await service.background(
        locked.id, BackgroundRequest(expected_revision=1, size="square", source="deterministic")
    )

    async def invalid(value, origin):
        raw, report = await fake_canvas(value, origin)
        if kind == "clipped":
            report.lines[0].x = 2000
        if kind == "dropped":
            report.lines.clear()
        if kind == "missing_font":
            report.font_loaded = False
        if kind == "contrast":
            report.contrast = 1
        if kind == "nan":
            report.lines[0].x = float("nan")
        if kind == "safe_area":
            report.safe_area = [1, 1, 1079, 1079]
        if kind == "logo":
            report.logo_bounds = [64, 64, 64, 64]
        return raw, report

    service.renderer = invalid
    with pytest.raises(ProviderError):
        await service.render(
            locked.id,
            RenderRequest(
                expected_revision=1,
                size="square",
                variant_id=variant.id,
                background_id=background.id,
            ),
        )
    assert not service.repo.snapshot(locked.id).posters
    await client.close()


async def test_missing_logo_changed_art_and_direct_forgery(factory, locked, tmp_path):
    client = factory(asset_path=tmp_path)
    variant = await prepare(client, locked)
    service = ArtService(client.store, client, client.settings)
    background = await service.background(
        locked.id, BackgroundRequest(expected_revision=1, size="square", source="deterministic")
    )
    payload = dict(
        expected_revision=1, size="square", variant_id=variant.id, background_id=background.id
    )
    for key in ["fields", "png", "validation", "approved", "font_urls", "background_url"]:
        with pytest.raises(ValidationError):
            RenderRequest.model_validate({**payload, key: "forged"})
    with pytest.raises(ProviderError):
        await service.render(locked.id, RenderRequest(**payload, logo_id="missing"))
    locked.brand.colors = ["#FF0000"]
    with client.store.connection:
        client.store.connection.execute(
            "UPDATE campaigns SET payload=? WHERE id=?", (locked.model_dump_json(), locked.id)
        )
    with pytest.raises(ProviderError) as caught:
        await service.render(locked.id, RenderRequest(**payload))
    assert caught.value.body.code == "REVISION_CONFLICT"
    await client.close()


@pytest.mark.parametrize("kind", ["svg", "fake_mime", "oversized", "bomb", "animated"])
def test_unsafe_local_rasters_rejected(kind):
    raw, mime = mock_png(), "image/png"
    if kind == "svg":
        raw, mime = b'<svg onload="alert(1)"><image href="http://evil"/></svg>', "image/svg+xml"
    if kind == "fake_mime":
        mime = "image/jpeg"
    if kind == "oversized":
        raw = b"x" * (12 * 1024 * 1024 + 1)
    if kind == "bomb":
        # Huge dimensions in a tiny valid PNG header; rejection occurs before decompression.
        chunk = struct.pack(">IIBBBBB", 100000, 100000, 8, 2, 0, 0, 0)
        raw = (
            b"\x89PNG\r\n\x1a\n"
            + struct.pack(">I", 13)
            + b"IHDR"
            + chunk
            + struct.pack(">I", zlib.crc32(b"IHDR" + chunk))
        )
    if kind == "animated":
        output = io.BytesIO()
        Image.new("RGB", (10, 10), "red").save(
            output, "PNG", save_all=True, append_images=[Image.new("RGB", (10, 10), "blue")]
        )
        raw = output.getvalue()
    with pytest.raises(ProviderError):
        raster(raw, mime)


def test_storage_tamper_paths_and_font_integrity(tmp_path):
    storage = ArtStorage(tmp_path)
    key = storage.write(mock_png())
    assert key == sha(mock_png())
    (storage.root / f"{key}.png").write_bytes(b"tampered")
    with pytest.raises(ProviderError):
        storage.read(key)
    with pytest.raises(ProviderError):
        storage.read("../../etc/passwd")
    assert len(font_manifest()) == 64


async def test_background_revision_race_does_not_commit(factory, locked, tmp_path):
    import asyncio

    started, release = asyncio.Event(), asyncio.Event()

    async def transport(request):
        if request.url.path == "/v1/images/generations":
            started.set()
            await release.wait()
        return handler(request)

    client = factory(transport, asset_path=tmp_path)
    seed(client, locked)
    service = ArtService(client.store, client, client.settings)
    task = asyncio.create_task(
        service.background(locked.id, BackgroundRequest(expected_revision=1, size="square"))
    )
    await started.wait()
    locked.revision = 2
    with client.store.connection:
        client.store.connection.execute(
            "UPDATE campaigns SET revision=2,payload=? WHERE id=?",
            (locked.model_dump_json(), locked.id),
        )
    release.set()
    with pytest.raises(ProviderError):
        await task
    assert not service.repo.snapshot(locked.id).backgrounds
    await client.close()


async def test_canvas_worker_preserves_utf8_metrics(monkeypatch):
    from pathlib import Path

    from backend.art_models import CanvasInput
    from backend.canvas_worker import render_canvas

    value = CanvasInput(
        width=1080,
        height=1080,
        size="square",
        language="kn",
        fields={"body": "ಕನ್ನಡ ಕಾಫಿಗೆ ವಿರಾಮ"},
        background_url="/api/assets/test",
        logo_url=None,
        font_urls={},
        font_hash="hash",
        renderer_version="canvas-b4.1",
        renderer_hash="hash",
        background_hash="hash",
        logo_hash=None,
        layout_hash="hash",
    )

    async def process(*args, **kwargs):
        raw, validation = await fake_canvas(value, "http://127.0.0.1:8000")
        Path(args[3]).write_text(validation.model_dump_json(), encoding="utf-8")
        Path(args[4]).write_bytes(raw)

        class Completed:
            returncode = 0

            async def wait(self):
                return 0

        return Completed()

    monkeypatch.setattr("backend.canvas_worker.shutil.which", lambda _: "node")
    monkeypatch.setattr("backend.canvas_worker.asyncio.create_subprocess_exec", process)
    raw, validation = await render_canvas(value, "http://127.0.0.1:8000")
    assert validation.lines[0].text == value.fields["body"]
    assert raster(raw, "image/png")[1] == (1080, 1080)


def test_art_http_boundary_and_logo_bytes(tmp_path, locked):
    from fastapi.testclient import TestClient

    from backend.config import Settings
    from backend.main import create_app

    app = create_app(
        Settings(
            _env_file=None, database_path=tmp_path / "api.sqlite", asset_path=tmp_path / "assets"
        )
    )
    with TestClient(app) as api:
        seed(app.state.client, locked)
        base = f"/api/campaigns/{locked.id}"
        response = api.post(
            base + "/backgrounds",
            json={"expected_revision": 1, "size": "square", "source": "deterministic"},
        )
        assert response.status_code == 200
        background = response.json()
        fetched = api.get(f"/api/assets/{background['id']}")
        assert sha(fetched.content) == background["sha256"]
        assert fetched.headers["x-artifact-approval"] == "pending"
        assert (
            api.post(
                base + "/assets/render",
                json={
                    "expected_revision": 1,
                    "size": "square",
                    "variant_id": "forged",
                    "background_id": background["id"],
                    "fields": {"body": "Free cake"},
                },
            ).status_code
            == 422
        )
        query = "?expected_revision=1&owner_approves_logo=true"
        assert (
            api.post(
                base + "/logos" + query,
                content=b"<svg/>",
                headers={"content-type": "image/svg+xml"},
            ).status_code
            == 422
        )
        logo = api.post(
            base + "/logos" + query, content=mock_png(), headers={"content-type": "image/png"}
        )
        assert logo.status_code == 200
        assert api.get(f"/api/assets/{logo.json()}").status_code == 200
        assert (
            api.post(
                base + "/logos?expected_revision=1&owner_approves_logo=false",
                content=mock_png(),
                headers={"content-type": "image/png"},
            ).status_code
            == 422
        )
        assert api.get("/api/render/fonts/missing.ttf").status_code == 422
        assert api.get("/api/assets/../../etc/passwd").status_code == 404
        missing_revision = api.get(base + "/export")
        assert missing_revision.status_code == 422
        assert missing_revision.json()["code"] == "VALIDATION_ERROR"
