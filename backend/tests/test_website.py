import asyncio
import base64
import io
import json
import zipfile

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import SecretStr, ValidationError

from backend.config import Settings
from backend.db import Store
from backend.main import create_app
from backend.tests import test_generation
from backend.tests.test_generation import seed
from backend.website_models import (
    ConnectionInput,
    DraftSave,
    GenerateWebsite,
    ImageUpload,
    PublishInput,
    WebsiteFields,
)
from backend.website_provider import HostingError, NetlifyProvider
from backend.website_service import WebsiteError, WebsiteService

TOKEN = "website-test-credential-never-persist-77ab"
locked_campaign = test_generation.locked


class Provider:
    def __init__(self):
        self.calls = []
        self.failure = None
        self.verified = asyncio.Event()
        self.proceed = asyncio.Event()
        self.proceed.set()

    async def test(self, token):
        self.calls.append("test")
        if self.failure:
            raise HostingError(self.failure)

    async def deploy(self, token, bundle):
        self.calls.append("deploy")
        return "site-123"

    async def ready_url(self, token, remote_id):
        return "https://website-test.netlify.app"

    async def verify(self, url, expected_html):
        self.calls.append("verify")
        self.verified.set()
        await self.proceed.wait()
        if self.failure:
            raise HostingError(self.failure)


@pytest.fixture
def website(factory, locked_campaign):
    locked = locked_campaign
    client = factory()
    seed(client, locked)
    provider = Provider()
    settings = client.settings.model_copy(
        update={
            "website_publish_enabled": True,
            "website_token_key": SecretStr(base64.b64encode(b"a" * 32).decode()),
        }
    )
    service = WebsiteService(client.store, settings, provider)
    draft = service.draft(locked.id)
    draft = service.save(
        draft["id"],
        DraftSave(
            expected_version=1, step=0, fields=WebsiteFields(name="Namma Cafe", area="Bengaluru")
        ),
    )
    return service, draft, provider


def generate(service, draft):
    return service.generate(draft["id"], GenerateWebsite(expected_version=draft["version"]))


def connect_input(bundle, **kwargs):
    return ConnectionInput(provider="netlify", token=TOKEN, bundle_hash=bundle["sha256"], **kwargs)


def publish_input(connection, bundle):
    return PublishInput(
        connection_id=connection["connection_id"],
        bundle_hash=bundle["sha256"],
        approve_exact_bundle=True,
    )


def test_draft_resume_and_generation_without_token(website):
    service, draft, provider = website
    result = generate(service, draft)
    assert result["report"]["missing_checks"] == ["G14"]
    assert result["report"]["approval_ready"] is False
    assert not provider.calls
    assert not service.receipts
    assert service.draft(draft["campaign_id"])["bundle_id"] == result["id"]
    fields = WebsiteFields(name="Namma Cafe", area="Bengaluru", description="Hello")
    saved = service.save(
        draft["id"], DraftSave(expected_version=draft["version"], step=3, fields=fields)
    )
    restarted = WebsiteService(service.store, service.settings, provider)
    assert service.get(draft["id"])["step"] == 3
    assert service.draft(draft["campaign_id"])["fields"] == saved["fields"]
    assert restarted.get(draft["id"])["fields"] == saved["fields"]


@pytest.mark.parametrize(
    "fields", [WebsiteFields(), WebsiteFields(name="Namma Cafe"), WebsiteFields(area="Bengaluru")]
)
def test_required_fields_block(website, fields):
    service, draft, _ = website
    saved = service.save(
        draft["id"], DraftSave(expected_version=draft["version"], step=0, fields=fields)
    )
    with pytest.raises(WebsiteError, match="required"):
        generate(service, saved)


@pytest.mark.parametrize(
    "fields",
    [
        {"name": "x" * 121},
        {"phone": "123"},
        {"whatsapp": "abc"},
        {"social_links": ["javascript:alert(1)"]},
        {"social_links": ["https://user:pass@example.com"]},
        {"social_links": ["https://example.com:bad"]},
        {"colour": "red;script"},
        {"menu": [{"name": "Coffee", "price": "100"}]},
        {"menu": [{"name": "Coffee", "price": -1.0}]},
        {"menu": [{"name": "Coffee", "price": float("nan")}]},
        {"hours": [{"day": "MON", "open": "22:00", "close": "09:00"}]},
        {"hours": [{"day": "MON", "open": "25:00", "close": "26:00"}]},
        {"languages": ["en", "en"]},
        {"offer": "25%"},
    ],
)
def test_strict_server_input_validation(fields):
    with pytest.raises(ValidationError):
        WebsiteFields.model_validate(fields)


def test_read_only_offer_and_unlocked_block(website):
    service, draft, _ = website
    offer = service.offer(draft["id"])
    assert (
        offer["locked"]
        and next(f for f in offer["facts"] if f["key"] == "OFFER")["canonical"]["value"] == 20
    )
    campaign = service.repo.get(draft["campaign_id"])
    original = campaign.model_dump_json()
    with pytest.raises(ValidationError):
        DraftSave.model_validate({"expected_version": 2, "step": 1, "fields": {}, "offer": 25})
    assert service.repo.get(campaign.id).model_dump_json() == original
    campaign.status = "draft"
    service.db.execute(
        "UPDATE campaigns SET payload=?,status='draft' WHERE id=?",
        (campaign.model_dump_json(), campaign.id),
    )
    with pytest.raises(WebsiteError, match="Lock the offer"):
        generate(service, draft)


def test_optional_omission_xss_and_image_validation(website):
    service, draft, _ = website
    bundle = generate(service, draft)
    assert 'aria-label="Menu"' not in bundle["html"]
    assert 'aria-label="Visit info"' not in bundle["html"]
    fields = WebsiteFields(
        name="Namma Cafe",
        area="Bengaluru",
        address='<script>alert("x")</script>',
        menu=[{"name": "<img src=x onerror=alert(1)>", "price": 99.0}],
    )
    draft = service.save(
        draft["id"], DraftSave(expected_version=draft["version"], step=4, fields=fields)
    )
    bundle = generate(service, draft)
    assert "<script>" not in bundle["html"] and "&lt;script&gt;" in bundle["html"]
    with pytest.raises(WebsiteError):
        service.upload(
            draft["id"], ImageUpload(mime="image/png", base64=base64.b64encode(b"<svg/>").decode())
        )
    raw = io.BytesIO()
    Image.new("RGB", (10, 10), "red").save(raw, "PNG")
    image = service.upload(
        draft["id"], ImageUpload(mime="image/png", base64=base64.b64encode(raw.getvalue()).decode())
    )
    assert image["mime"] == "image/png"
    with pytest.raises(WebsiteError):
        service.upload(
            draft["id"],
            ImageUpload(mime="image/jpeg", base64=base64.b64encode(raw.getvalue()).decode()),
        )


@pytest.mark.parametrize(
    "description", ["25% off coffee", "free cake", "no ID needed", "best cafe in Bengaluru"]
)
def test_unsupported_description_blocked(website, description):
    service, draft, _ = website
    draft = service.save(
        draft["id"],
        DraftSave(
            expected_version=draft["version"],
            step=5,
            fields=WebsiteFields(name="Namma Cafe", area="Bengaluru", description=description),
        ),
    )
    with pytest.raises(WebsiteError, match="Guardian"):
        generate(service, draft)


@pytest.mark.parametrize(
    "status,code", [(401, "TOKEN_INVALID"), (403, "TOKEN_SCOPE"), (429, "PROVIDER_LIMIT")]
)
async def test_netlify_token_failures_do_not_retry_or_reflect(status, code, caplog):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(status, json={"message": TOKEN})

    provider = NetlifyProvider(httpx.MockTransport(handler))
    with pytest.raises(HostingError) as exc:
        await provider.test(SecretStr(TOKEN))
    assert exc.value.code == code and TOKEN not in str(exc.value)
    assert len(requests) == 1 and requests[0].method == "GET"
    assert TOKEN not in caplog.text


async def test_one_use_secret_absent_from_persistence_bundle_and_job(website, caplog):
    service, draft, provider = website
    bundle = generate(service, draft)
    connection = await service.connect(draft["id"], connect_input(bundle))
    assert TOKEN not in json.dumps(connection) and connection["masked_suffix"].endswith("77ab")
    job = service.publish(draft["id"], publish_input(connection, bundle))
    await asyncio.gather(*list(service.tasks.values()))
    assert service.job(job["id"])["status"] == "published"
    assert not service.receipts and not service.tasks
    assert not service.remembered()["remembered"]
    assert TOKEN not in caplog.text
    for table in [
        "website_drafts",
        "website_bundles",
        "website_publish_jobs",
        "api_calls",
        "trace_events",
    ]:
        assert TOKEN not in repr(service.db.execute(f"SELECT * FROM {table}").fetchall())
    with zipfile.ZipFile(io.BytesIO(bundle["bytes"])) as archive:
        assert all(TOKEN.encode() not in archive.read(path) for path in archive.namelist())
    assert provider.calls == ["test", "deploy", "verify"]


async def test_remember_is_encrypted_scoped_authenticated_and_deletable(website):
    service, draft, _ = website
    connection = await service.connect(
        draft["id"], connect_input(generate(service, draft), remember=True)
    )
    row = service.db.execute("SELECT * FROM website_tokens").fetchone()
    assert TOKEN.encode() not in row[3] and TOKEN not in repr(row)
    assert service.decrypt().get_secret_value() == TOKEN
    assert row[0] == service.owner and connection["remembered"]
    service.db.execute("UPDATE website_tokens SET owner_id='other-owner'")
    assert not service.remembered()["remembered"]
    service.db.execute("UPDATE website_tokens SET owner_id=?", (service.owner,))
    service.db.execute("UPDATE website_tokens SET ciphertext=?", (b"tampered",))
    with pytest.raises(WebsiteError, match="cannot be read"):
        service.decrypt()
    await service.disconnect()
    assert not service.receipts and not service.remembered()["remembered"]


async def test_approval_current_hash_and_connection_binding(website):
    service, draft, _ = website
    bundle = generate(service, draft)
    connection = await service.connect(draft["id"], connect_input(bundle))
    with pytest.raises(ValidationError):
        PublishInput(
            connection_id=connection["connection_id"],
            bundle_hash=bundle["sha256"],
            approve_exact_bundle=False,
        )
    with pytest.raises(WebsiteError):
        service.publish(draft["id"], publish_input(connection, {"sha256": "a" * 64}))
    service.save(
        draft["id"],
        DraftSave(
            expected_version=draft["version"],
            step=5,
            fields=WebsiteFields(name="Namma Cafe", area="Bengaluru", colour="#123456"),
        ),
    )
    with pytest.raises(WebsiteError):
        service.publish(draft["id"], publish_input(connection, bundle))


async def test_verified_before_published_and_failure_preserves_core(website):
    service, draft, provider = website
    original = service.repo.get(draft["campaign_id"]).model_dump_json()
    bundle = generate(service, draft)
    connection = await service.connect(draft["id"], connect_input(bundle))
    provider.proceed.clear()
    job = service.publish(draft["id"], publish_input(connection, bundle))
    await provider.verified.wait()
    assert service.job(job["id"])["status"] == "verifying"
    assert service.job(job["id"])["url"] is None
    provider.failure = "URL_UNVERIFIED"
    provider.proceed.set()
    await asyncio.gather(*list(service.tasks.values()))
    assert service.job(job["id"])["status"] == "failed"
    assert service.bundle(draft["id"])["sha256"] == bundle["sha256"]
    assert service.repo.get(draft["campaign_id"]).model_dump_json() == original


async def test_stale_during_publish_and_expired_receipt(website):
    service, draft, provider = website
    bundle = generate(service, draft)
    connection = await service.connect(draft["id"], connect_input(bundle))
    service.receipts[connection["connection_id"]].expires = 0
    with pytest.raises(WebsiteError, match="Test the connection"):
        service.publish(draft["id"], publish_input(connection, bundle))
    connection = await service.connect(draft["id"], connect_input(bundle))
    provider.proceed.clear()
    job = service.publish(draft["id"], publish_input(connection, bundle))
    await provider.verified.wait()
    service.save(
        draft["id"],
        DraftSave(
            expected_version=draft["version"],
            step=5,
            fields=WebsiteFields(name="Namma Cafe", area="Bengaluru", colour="#123456"),
        ),
    )
    provider.proceed.set()
    await asyncio.gather(*list(service.tasks.values()))
    assert service.job(job["id"])["status"] == "stale"


async def test_real_provider_zip_flow_no_token_on_live_get():
    seen = []

    def handler(request):
        seen.append(request)
        if request.url.host.endswith("netlify.app"):
            assert "authorization" not in request.headers
            return httpx.Response(200, content=b"exact-site")
        assert request.headers["authorization"] == "Bearer " + TOKEN
        if request.method == "POST":
            assert request.content == b"zip-bytes"
            return httpx.Response(201, json={"id": "site-123"})
        if request.url.path.endswith("site-123"):
            return httpx.Response(
                200,
                json={
                    "published_deploy": {"state": "ready"},
                    "ssl_url": "https://test.netlify.app",
                },
            )
        return httpx.Response(200, json=[])

    provider = NetlifyProvider(httpx.MockTransport(handler))
    await provider.test(SecretStr(TOKEN))
    remote_id = await provider.deploy(SecretStr(TOKEN), b"zip-bytes")
    url = await provider.ready_url(SecretStr(TOKEN), remote_id)
    await provider.verify(url, b"exact-site")
    assert len(seen) == 4


@pytest.mark.parametrize(
    "status,content", [(302, b"exact-site"), (404, b"exact-site"), (200, b"wrong-site")]
)
async def test_live_url_must_respond_with_exact_site(status, content):
    provider = NetlifyProvider(
        httpx.MockTransport(lambda r: httpx.Response(status, content=content))
    )
    with pytest.raises(HostingError, match="URL_UNVERIFIED"):
        await provider.verify("https://test.netlify.app", b"exact-site")


def test_https_enforcement_and_safe_validation_responses(tmp_path, locked_campaign):
    locked = locked_campaign
    settings = Settings(
        _env_file=None, database_path=tmp_path / "api.sqlite3", website_publish_enabled=True
    )
    with TestClient(create_app(settings), base_url="http://testserver") as api:
        seed(api.app.state.client, locked)
        draft = api.get(f"/api/campaigns/{locked.id}/website").json()
        response = api.post(f"/api/websites/{draft['id']}/connection", json={"token": TOKEN})
        assert response.status_code == 403 and response.json()["code"] == "HTTPS_REQUIRED"
        assert TOKEN not in response.text
    with TestClient(create_app(settings), base_url="https://testserver") as api:
        response = api.put(
            f"/api/websites/{draft['id']}",
            json={"expected_version": 1, "step": 0, "fields": {"phone": TOKEN}},
        )
        assert response.status_code == 422 and TOKEN not in response.text
        assert api.get("/api/health").status_code == 200
        assert api.get("/api/website/config").json()["providers"] == ["netlify"]


def test_migration_both_prior_version_nine_variants(tmp_path):
    # Both sides of the pre-existing migration-number merge conflict remain usable.
    for table in ["social_profiles", "campaign_videos"]:
        path = tmp_path / f"{table}.sqlite3"
        store = Store(path)
        store.connection.execute(f"DROP TABLE {table}")
        store.connection.execute("DELETE FROM migrations WHERE version=11")
        store.connection.commit()
        store.close()
        store = Store(path)
        assert store.connection.execute(f"SELECT count(*) FROM {table}").fetchone()
        assert store.connection.execute("SELECT 1 FROM migrations WHERE version=12").fetchone()
        store.close()


def test_multilingual_and_suggestion_preserve_locked_forms(website):
    service, draft, _ = website
    suggestion = service.suggest(draft["id"])
    assert suggestion["description"] == "Namma Cafe · Bengaluru"
    draft = service.save(
        draft["id"],
        DraftSave(
            expected_version=draft["version"],
            step=5,
            fields=WebsiteFields(
                name="Namma Cafe",
                area="Bengaluru",
                languages=["en", "kn", "kn-Latn"],
                description=suggestion["description"],
            ),
        ),
    )
    bundle = generate(service, draft)
    assert 'lang="kn"' in bundle["html"] and 'lang="kn-Latn"' in bundle["html"]
    assert "೨೦" in bundle["html"] or "20%" in bundle["html"]


def test_step_navigation_keeps_current_bundle(website):
    service, draft, _ = website
    bundle = generate(service, draft)
    saved = service.save(
        draft["id"],
        DraftSave(
            expected_version=draft["version"],
            step=6,
            fields=WebsiteFields.model_validate(draft["fields"]),
        ),
    )
    assert saved["version"] == draft["version"]
    assert service.bundle(draft["id"])["sha256"] == bundle["sha256"]


async def test_saved_token_reuse_and_disconnect_during_job(website):
    service, draft, provider = website
    bundle = generate(service, draft)
    await service.connect(draft["id"], connect_input(bundle, remember=True))
    connection = await service.connect(
        draft["id"],
        ConnectionInput(
            provider="netlify",
            use_remembered=True,
            bundle_hash=bundle["sha256"],
        ),
    )
    provider.proceed.clear()
    job = service.publish(draft["id"], publish_input(connection, bundle))
    await provider.verified.wait()
    await service.disconnect()
    assert service.job(job["id"])["status"] == "uncertain"
    assert not service.tasks and not service.receipts and not service.remembered()["remembered"]


async def test_no_key_remember_fails_without_network_but_use_once_works(website):
    service, draft, provider = website
    bundle = generate(service, draft)
    service.settings.website_token_key = SecretStr("")
    with pytest.raises(WebsiteError, match="Remember token is unavailable"):
        await service.connect(draft["id"], connect_input(bundle, remember=True))
    assert not provider.calls
    result = await service.connect(draft["id"], connect_input(bundle))
    assert result["status"] == "CONNECTED"
    await service.close()


def test_publish_direct_construct_cannot_bypass_approval(website):
    service, draft, _ = website
    with pytest.raises(ValidationError):
        service.publish(
            draft["id"],
            PublishInput.model_construct(
                connection_id="a" * 32, bundle_hash="a" * 64, approve_exact_bundle=False
            ),
        )


async def test_under_scoped_deploy_fails_once_and_keeps_bundle(website):
    service, draft, _ = website
    seen = []

    def handler(request):
        seen.append(request.method)
        return (
            httpx.Response(200, json=[])
            if request.method == "GET"
            else httpx.Response(403, json={"message": TOKEN})
        )

    service.provider = NetlifyProvider(httpx.MockTransport(handler))
    bundle = generate(service, draft)
    connection = await service.connect(draft["id"], connect_input(bundle))
    job = service.publish(draft["id"], publish_input(connection, bundle))
    await asyncio.gather(*list(service.tasks.values()))
    saved = service.job(job["id"])
    assert saved["status"] == "failed" and "permission" in saved["message"]
    assert TOKEN not in json.dumps(saved)
    assert seen == ["GET", "POST"]
    assert service.bundle(draft["id"])["sha256"] == bundle["sha256"]


def test_menu_price_is_not_rounded_by_display_formatting(website):
    service, draft, _ = website
    draft = service.save(
        draft["id"],
        DraftSave(
            expected_version=draft["version"],
            step=3,
            fields=WebsiteFields(
                name="Namma Cafe",
                area="Bengaluru",
                menu=[{"name": "Owner item", "price": 123456.78}],
            ),
        ),
    )
    assert "₹123456.78" in generate(service, draft)["html"]
