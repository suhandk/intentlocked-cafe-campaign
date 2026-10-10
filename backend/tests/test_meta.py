import asyncio
import hashlib
import hmac
import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.art_models import BackgroundRequest, RenderRequest
from backend.art_service import ArtService
from backend.config import Settings
from backend.errors import ProviderError
from backend.generation_service import GenerationService
from backend.main import create_app
from backend.meta_client import MetaClient, mock_handler
from backend.meta_models import MetaConfirm, MetaPreview
from backend.meta_service import MetaService
from backend.tests.conftest import FakeClock
from backend.tests.test_art import fake_canvas
from backend.tests.test_delivery import approval_request, setup
from backend.tests.test_generation import finish, selection
from backend.tests.test_generation import locked as locked_fixture
from backend.work_models import WorkRetry
from backend.work_service import WorkService


@pytest.fixture
async def social(factory):
    campaign = locked_fixture.__wrapped__()
    client = factory(
        meta_enabled=True,
        meta_owner_token="owner-" + "x" * 40,
        meta_app_secret="private-app-secret",
        meta_whatsapp_phone_id="123",
        meta_whatsapp_business_id="456",
    )
    changes, approvals, items, _ = await setup(client, campaign)
    await approvals.audit(campaign.id, items[0].id, campaign.revision)
    approvals.approve(campaign.id, approval_request(campaign, items))
    app = SimpleNamespace(
        state=SimpleNamespace(
            settings=client.settings,
            store=client.store,
            client=client,
            changes=changes,
            approvals=approvals,
        )
    )
    app.state.work = WorkService(app)
    app.state.meta = MetaService(app, client=MetaClient(client.settings, clock=FakeClock()))
    yield app, campaign, items[0]
    await app.state.work.close()
    await app.state.meta.close()
    await client.close()


def preview(campaign, item, **values):
    return MetaPreview(
        expected_revision=campaign.revision,
        platform="whatsapp",
        text_item_id=item.id,
        observed_hashes={item.id: item.snapshot_hash},
        recipient="+15555550123",
        recipient_consented=True,
        idempotency_key="social-preview-key",
        **values,
    )


def confirmation(op):
    return MetaConfirm(
        expected_revision=op.campaign_revision,
        preview_hash=op.preview_hash,
        confirmation_token=op.confirmation_token,
        owner_confirms_delivery=True,
    )


async def finished(app, op):
    task = app.state.work.tasks.get(op.job_id)
    if task:
        await task
    return app.state.meta.public(app.state.meta.load(op.id))


async def test_confirmed_mock_raw_message_replay_and_no_recipient_in_jobs(social):
    app, campaign, item = social
    captured = []

    def transport(req):
        captured.append(req)
        return mock_handler(req)

    await app.state.meta.client.close()
    app.state.meta.client = MetaClient(
        app.state.settings, clock=FakeClock(), mock_transport=httpx.MockTransport(transport)
    )
    op = app.state.meta.preview(campaign.id, preview(campaign, item))
    assert captured == []
    assert app.state.meta.preview(campaign.id, preview(campaign, item)).id == op.id
    first = app.state.meta.confirm(campaign.id, op.id, confirmation(op))
    assert app.state.meta.confirm(campaign.id, op.id, confirmation(op)).job_id == first.job_id
    result = await finished(app, first)
    assert result.status == "accepted" and result.provider_id.startswith("mock-wamid-")
    assert result.cost_status == "not_applicable_mock"
    assert len(captured) == 1
    assert captured[0].url.path == "/v25.0/123/messages"
    payload = json.loads(captured[0].content)
    assert payload["messaging_product"] == "whatsapp"
    assert payload["text"]["body"] == result.text and payload["type"] == "text"
    assert payload["to"] == "15555550123"
    job = app.state.work.get(first.job_id)
    assert "+15555550123" not in job.model_dump_json()
    assert "private-app-secret" not in job.model_dump_json()
    before = len(captured)
    app.state.work.events(campaign.id, 0)
    app.state.work.events(campaign.id, 0)
    assert len(captured) == before
    with pytest.raises(ProviderError, match="Delivery is never retried"):
        app.state.work.retry(
            job.id,
            WorkRetry(expected_revision=campaign.revision, idempotency_key="retry-social-key"),
        )


@pytest.mark.parametrize(
    "change", ["hash", "revision", "approval", "audit", "consent", "recipient"]
)
async def test_preview_cannot_bypass_existing_gate(social, change):
    app, campaign, item = social
    body = preview(campaign, item)
    if change == "hash":
        body.observed_hashes[item.id] = "f" * 64
    elif change == "revision":
        body.expected_revision += 1
    elif change == "approval":
        app.state.store.connection.execute("DELETE FROM item_approvals")
        app.state.store.connection.commit()
    elif change == "audit":
        app.state.approvals.ledger.db.execute("DELETE FROM delivery_audits")
        app.state.approvals.ledger.db.commit()
    elif change == "consent":
        body.recipient_consented = False
    else:
        body.recipient = type(body.recipient)("not-a-number")
    with pytest.raises((ProviderError, TypeError)):
        app.state.meta.preview(campaign.id, body)
    assert (
        app.state.store.connection.execute("SELECT COUNT(*) FROM meta_attempts").fetchone()[0] == 0
    )


async def test_forged_confirm_and_cancel_pending(social):
    app, campaign, item = social
    op = app.state.meta.preview(campaign.id, preview(campaign, item))
    body = confirmation(op)
    body.confirmation_token = type(body.confirmation_token)("forged")
    with pytest.raises(ProviderError):
        app.state.meta.confirm(campaign.id, op.id, body)
    assert app.state.meta.cancel(op.id).status == "cancelled"
    with pytest.raises(ProviderError):
        app.state.meta.confirm(campaign.id, op.id, confirmation(op))


async def test_configuration_changed_between_preview_and_confirmation(social):
    app, campaign, item = social
    op = app.state.meta.preview(campaign.id, preview(campaign, item))
    app.state.settings.meta_whatsapp_phone_id = "999"
    with pytest.raises(ProviderError, match="configuration changed"):
        app.state.meta.confirm(campaign.id, op.id, confirmation(op))


async def test_queued_fact_change_sends_nothing(social):
    app, campaign, item = social
    op = app.state.meta.preview(campaign.id, preview(campaign, item))
    confirmed = app.state.meta.confirm(campaign.id, op.id, confirmation(op))
    app.state.store.connection.execute(
        "UPDATE campaigns SET revision=revision+1 WHERE id=?", (campaign.id,)
    )
    # Repository reads payload; update its authoritative stored campaign too.
    row = app.state.store.connection.execute(
        "SELECT payload FROM campaigns WHERE id=?", (campaign.id,)
    ).fetchone()
    payload = json.loads(row[0])
    payload["revision"] += 1
    app.state.store.connection.execute(
        "UPDATE campaigns SET payload=? WHERE id=?", (json.dumps(payload), campaign.id)
    )
    app.state.store.connection.commit()
    await finished(app, confirmed)
    assert app.state.meta.public(app.state.meta.load(op.id)).status == "stale"
    assert (
        app.state.store.connection.execute("SELECT COUNT(*) FROM meta_attempts").fetchone()[0] == 0
    )


async def test_restart_never_repeats_unknown_submission(social):
    app, campaign, item = social
    op = app.state.meta.preview(campaign.id, preview(campaign, item))
    saved = app.state.meta.load(op.id)
    saved["operation"]["status"] = "submitting"
    app.state.meta.save(saved, "simulated persisted dispatch")
    restored = MetaService(app)
    assert restored.public(restored.load(op.id)).status == "delivery_unknown"
    await restored.close()
    assert (
        app.state.store.connection.execute("SELECT COUNT(*) FROM meta_attempts").fetchone()[0] == 0
    )


@pytest.mark.parametrize(
    "status,code", [(401, "META_AUTH"), (403, "META_PERMISSION"), (400, "META_REJECTED")]
)
async def test_error_redaction(status, code):
    client = MetaClient(
        Settings(_env_file=None),
        mock_transport=httpx.MockTransport(
            lambda _: httpx.Response(
                status, json={"error": {"message": "secret-token +15555550123"}}
            )
        ),
    )
    with pytest.raises(ProviderError) as caught:
        await client.request("facebook", "POST", "123", "feed", data={"message": "approved"})
    assert caught.value.body.code == code
    assert "secret-token" not in caught.value.body.model_dump_json()
    assert "15555550123" not in caught.value.body.model_dump_json()
    await client.close()


async def test_fake_clock_retry_after_and_bounded_reads():
    calls = []

    def transport(req):
        calls.append(req)
        return (
            httpx.Response(429, headers={"Retry-After": "31"})
            if len(calls) == 1
            else httpx.Response(200, json={"id": "123"})
        )

    clock = FakeClock()
    client = MetaClient(
        Settings(_env_file=None), clock=clock, mock_transport=httpx.MockTransport(transport)
    )
    await client.request("facebook", "POST", "123", "feed", data={"message": "approved"})
    assert clock.sleeps == [31.0] and len(calls) == 2
    await client.close()
    calls.clear()

    def fail(req):
        calls.append(req)
        return httpx.Response(503)

    client = MetaClient(
        Settings(_env_file=None), clock=clock, mock_transport=httpx.MockTransport(fail)
    )
    with pytest.raises(ProviderError):
        await client.request("facebook", "GET", "123")
    assert len(calls) == 3
    calls.clear()
    with pytest.raises(ProviderError) as caught:
        await client.request("facebook", "POST", "123", "feed", data={"message": "approved"})
    assert len(calls) == 1 and caught.value.body.code == "META_DELIVERY_UNKNOWN"
    await client.close()


async def test_timeout_is_persisted_unknown_and_never_retried(social):
    app, campaign, item = social
    captured = []

    def transport(req):
        captured.append(req)
        raise httpx.ReadTimeout("private timeout details")

    await app.state.meta.client.close()
    app.state.meta.client = MetaClient(
        app.state.settings, mock_transport=httpx.MockTransport(transport)
    )
    op = app.state.meta.preview(campaign.id, preview(campaign, item))
    result = await finished(app, app.state.meta.confirm(campaign.id, op.id, confirmation(op)))
    assert result.status == "delivery_unknown" and len(captured) == 1
    assert (
        app.state.store.connection.execute("SELECT status FROM meta_attempts").fetchone()[0]
        == "unknown"
    )


def signed(settings, payload):
    raw = json.dumps(payload).encode()
    return raw, "sha256=" + hmac.new(
        settings.meta_app_secret.get_secret_value().encode(), raw, hashlib.sha256
    ).hexdigest()


async def test_verified_webhook_dedupe_out_of_order_and_unknown_ids(social):
    app, campaign, item = social
    op = app.state.meta.preview(campaign.id, preview(campaign, item))
    submitted = await finished(app, app.state.meta.confirm(campaign.id, op.id, confirmation(op)))
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "456",
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": "123"},
                            "statuses": [{"id": submitted.provider_id, "status": "read"}],
                        }
                    }
                ],
            }
        ],
    }
    raw, signature = signed(app.state.settings, payload)
    with pytest.raises(ProviderError):
        app.state.meta.webhook(raw, "forged")
    assert app.state.meta.webhook(raw, signature)["status"] == "processed"
    assert app.state.meta.webhook(raw, signature)["status"] == "duplicate"
    assert app.state.meta.public(app.state.meta.load(op.id)).status == "read"
    payload["entry"][0]["changes"][0]["value"]["statuses"] = [
        {"id": submitted.provider_id, "status": "sent"},
        {"id": "unmatched", "status": "failed"},
    ]
    app.state.meta.webhook(*signed(app.state.settings, payload))
    assert app.state.meta.public(app.state.meta.load(op.id)).status == "read"


async def test_templates_are_explicit_exact_static_bodies(social):
    app, campaign, item = social
    body = preview(campaign, item, template_name="cafe_offer", template_language="en")
    with pytest.raises(ProviderError):
        app.state.meta.preview(campaign.id, body)
    pack, _ = app.state.approvals.export(campaign.id, campaign.revision, [item.id])
    app.state.settings.meta_whatsapp_templates = {
        "cafe_offer:en": hashlib.sha256(pack.copy_text[item.id].encode()).hexdigest()
    }
    op = app.state.meta.preview(campaign.id, body)
    assert (
        await finished(app, app.state.meta.confirm(campaign.id, op.id, confirmation(op)))
    ).status == "accepted"


def test_configuration_defaults_and_live_gate():
    assert not Settings(_env_file=None).meta_enabled
    with pytest.raises(ValidationError):
        Settings(_env_file=None, meta_enabled=True)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, meta_enabled=True, meta_mode="live", meta_owner_token="x" * 40)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, meta_public_origin="http://localhost:8000")
    for platform in ("whatsapp", "instagram"):
        with pytest.raises(ValidationError):
            Settings(
                _env_file=None,
                inference_mode="live",
                inference_api_key="fixture-only-not-a-real-key",
                meta_enabled=True,
                meta_mode="live",
                meta_owner_token="x" * 40,
                meta_app_secret="fixture-only",
                meta_verified_platforms=[platform],
                meta_whatsapp_phone_id="123",
                meta_whatsapp_token="fixture-only",
                meta_instagram_account_id="456",
                meta_instagram_token="fixture-only",
            )
    with pytest.raises(ValueError, match="isolated MockTransport"):
        MetaClient(Settings(_env_file=None), mock_transport=object())


def test_owner_route_and_generic_work_cannot_authorize(tmp_path):
    app = create_app(Settings(_env_file=None, database_path=tmp_path / "test.db"))
    with TestClient(app) as client:
        assert client.get("/api/meta/status").json()["enabled"] is False
        assert client.post("/api/meta/connections/facebook/check").status_code == 403
        response = client.post(
            "/api/campaigns/nonexistent/work",
            json={
                "kind": "meta_delivery",
                "idempotency_key": "forged-work-key",
                "input": {"expected_revision": 1, "operation_id": "forged"},
            },
        )
        assert response.status_code == 403
        assert client.get("/api/meta/media/missing").status_code == 404
        assert (
            client.get(
                "/api/meta/webhook?hub.mode=subscribe&hub.verify_token=forged&hub.challenge=1"
            ).status_code
            == 403
        )


async def platform_items(app, campaign, platform, *, with_image):
    generation = GenerationService(app.state.store, app.state.client)
    plan = generation.repo.plan(campaign.id, campaign.revision)
    run = await finish(
        generation,
        generation.start(
            campaign.id,
            selection(
                campaign,
                plan,
                languages=["en"],
                channels=[platform],
                audience_ids=[plan.hero_audience_id],
                idempotency_key="meta-" + platform,
            ),
        ),
    )
    variant = run.cells[0].variant
    items = app.state.changes.ledger.sync(campaign)
    text = next(i for i in items if i.source_id == variant.id and i.kind == "text")
    chosen = [text]
    poster = None
    if with_image:
        art = ArtService(app.state.store, app.state.client, app.state.settings)
        art.renderer = fake_canvas
        background = await art.background(
            campaign.id,
            BackgroundRequest(
                expected_revision=campaign.revision, size="square", source="deterministic"
            ),
        )
        rendered = await art.render(
            campaign.id,
            RenderRequest(
                expected_revision=campaign.revision,
                size="square",
                variant_id=variant.id,
                background_id=background.id,
            ),
        )
        poster = next(i for i in app.state.changes.ledger.sync(campaign) if i.id == rendered.id)
        chosen.append(poster)
    for item in chosen:
        await app.state.approvals.audit(campaign.id, item.id, campaign.revision)
    app.state.approvals.approve(
        campaign.id, approval_request(campaign, chosen, "approve-" + platform)
    )
    return text, poster


@pytest.mark.parametrize(
    "platform,image",
    [("facebook", False), ("facebook", True), ("instagram", True), ("whatsapp", True)],
)
async def test_platform_raw_shapes_and_authorized_media(social, platform, image):
    from urllib.parse import parse_qs

    app, campaign, _ = social
    text, poster = await platform_items(app, campaign, platform, with_image=image)
    captured = []

    def handler(req):
        captured.append(req)
        return mock_handler(req)

    await app.state.meta.client.close()
    app.state.meta.client = MetaClient(
        app.state.settings, clock=FakeClock(), mock_transport=httpx.MockTransport(handler)
    )
    body = MetaPreview(
        expected_revision=campaign.revision,
        platform=platform,
        text_item_id=text.id,
        poster_item_id=poster.id if poster else None,
        observed_hashes={i.id: i.snapshot_hash for i in [text, poster] if i},
        idempotency_key="platform-preview-key",
        **(
            {"recipient": "+15555550123", "recipient_consented": True}
            if platform == "whatsapp"
            else {}
        ),
    )
    op = app.state.meta.preview(campaign.id, body)
    final = await finished(app, app.state.meta.confirm(campaign.id, op.id, confirmation(op)))
    assert final.status == ("accepted" if platform == "whatsapp" else "published"), final.error_code
    if platform == "instagram":
        assert [r.url.path.rsplit("/", 1)[-1] for r in captured if r.method == "POST"] == [
            "media",
            "media_publish",
        ]
        first = parse_qs(captured[0].content.decode())
        assert first["caption"] == [op.text] and "image_url" in first
        assert final.container_id.startswith("mock-") and final.provider_id.startswith("mock-")
    elif platform == "facebook":
        form = parse_qs(captured[0].content.decode())
        assert form["caption" if image else "message"] == [op.text]
        assert captured[0].url.path.endswith("/photos" if image else "/feed")
    else:
        assert json.loads(captured[0].content)["image"]["caption"] == op.text
    if image:
        row = app.state.store.connection.execute(
            "SELECT mime,sha256,bytes FROM meta_media"
        ).fetchone()
        assert row[0] == ("image/jpeg" if platform == "instagram" else "image/png")
        assert hashlib.sha256(row[2]).hexdigest() == op.delivery_media_hash == row[1]
        url = (
            (
                parse_qs(captured[0].content.decode()).get("image_url")
                or parse_qs(captured[0].content.decode()).get("url")
            )[0]
            if platform != "whatsapp"
            else json.loads(captured[0].content)["image"]["link"]
        )
        token = url.rsplit("/", 1)[-1]
        assert app.state.meta.read_media(token)[0] == row[2]
        app.state.store.connection.execute("UPDATE meta_media SET expires_at=0")
        app.state.store.connection.commit()
        with pytest.raises(ProviderError):
            app.state.meta.read_media(token)


async def test_instagram_polling_has_finite_stop(social):
    app, campaign, _ = social
    text, poster = await platform_items(app, campaign, "instagram", with_image=True)
    captured = []

    def handler(req):
        captured.append(req)
        return (
            httpx.Response(200, json={"status_code": "IN_PROGRESS"})
            if req.method == "GET"
            else mock_handler(req)
        )

    await app.state.meta.client.close()
    app.state.meta.client = MetaClient(
        app.state.settings, clock=FakeClock(), mock_transport=httpx.MockTransport(handler)
    )
    op = app.state.meta.preview(
        campaign.id,
        MetaPreview(
            expected_revision=campaign.revision,
            platform="instagram",
            text_item_id=text.id,
            poster_item_id=poster.id,
            observed_hashes={text.id: text.snapshot_hash, poster.id: poster.snapshot_hash},
            idempotency_key="instagram-poll-preview",
        ),
    )
    final = await finished(app, app.state.meta.confirm(campaign.id, op.id, confirmation(op)))
    assert final.status == "delivery_unknown" and final.container_id
    assert len(captured) == 1 + app.state.settings.meta_poll_limit
    assert all(not r.url.path.endswith("/media_publish") for r in captured)


async def test_cancel_during_submission_is_unknown_and_attempt_is_retained(social):
    app, campaign, item = social
    started = asyncio.Event()

    async def handler(req):
        started.set()
        await asyncio.Event().wait()

    await app.state.meta.client.close()
    app.state.meta.client = MetaClient(
        app.state.settings, mock_transport=httpx.MockTransport(handler)
    )
    op = app.state.meta.preview(campaign.id, preview(campaign, item))
    confirmed = app.state.meta.confirm(campaign.id, op.id, confirmation(op))
    await started.wait()
    await app.state.work.cancel(confirmed.job_id)
    result = app.state.meta.public(app.state.meta.load(op.id))
    assert result.status == "delivery_unknown"
    assert (
        app.state.store.connection.execute("SELECT COUNT(*) FROM meta_attempts").fetchone()[0] == 1
    )


async def test_idempotency_payload_conflict(social):
    app, campaign, item = social
    body = preview(campaign, item)
    app.state.meta.preview(campaign.id, body)
    body.recipient = type(body.recipient)("+15555550124")
    with pytest.raises(ProviderError) as caught:
        app.state.meta.preview(campaign.id, body)
    assert caught.value.body.code == "IDEMPOTENCY_CONFLICT"
