"""Owner-confirmed delivery over existing approval/export and durable work boundaries."""

import asyncio
import hashlib
import hmac
import io
import json
import re
import secrets
import time
from uuid import uuid4

from PIL import Image

from backend.art_storage import sha
from backend.contracts import utc_now
from backend.errors import ProviderError
from backend.intent_rules import digest, domain_error
from backend.meta_client import MetaClient
from backend.meta_models import MetaOperation, MetaStatus
from backend.work_context import work_guard
from backend.work_models import WorkRequest

SUBMITTED = {"submitting", "processing", "accepted", "published", "delivered", "read"}


class MetaService:
    def __init__(self, app, *, client=None):
        self.app, self.settings = app, app.state.settings
        self.db = app.state.store.connection
        self.client = client or MetaClient(self.settings)
        for row in self.db.execute(
            "SELECT payload FROM meta_operations "
            "WHERE status IN ('queued','submitting','processing')"
        ).fetchall():
            saved = json.loads(row[0])
            submitted = saved["operation"]["status"] != "queued"
            saved["operation"]["status"] = "delivery_unknown" if submitted else "cancelled"
            saved["operation"]["error_code"] = "PROCESS_RESTARTED"
            self.save(saved, "Delivery interrupted; uncertain submissions are never repeated.")

    async def close(self):
        await self.client.close()

    def owner(self, request):
        expected = self.settings.meta_owner_token.get_secret_value()
        provided = request.headers.get("X-Owner-Delivery-Token", "")
        if not expected or not hmac.compare_digest(expected, provided):
            raise domain_error("META_OWNER_REQUIRED", "Owner delivery authorization is required")
        origin = request.headers.get("Origin")
        if origin and origin != self.settings.frontend_origin:
            raise domain_error("META_OWNER_REQUIRED", "Delivery origin is not authorized")

    def enabled(self, platform):
        if not self.settings.meta_enabled:
            raise domain_error(
                "META_DISABLED", "Enable optional Meta delivery in backend configuration"
            )
        if (
            self.settings.meta_mode == "live"
            and platform not in self.settings.meta_verified_platforms
        ):
            raise domain_error(
                "META_NOT_VERIFIED", "Live capability has not been independently verified"
            )

    def status(self):
        return MetaStatus(
            enabled=self.settings.meta_enabled,
            mode=self.settings.meta_mode,
            graph_version=self.settings.meta_graph_version,
            platforms={
                p: (
                    "disabled"
                    if not self.settings.meta_enabled
                    else "MOCK; no external delivery"
                    if self.settings.meta_mode == "mock"
                    else "live configured; check connection"
                    if p in self.settings.meta_verified_platforms
                    else "NOT_TESTED; live blocked"
                )
                for p in ("whatsapp", "facebook", "instagram")
            },
        )

    def load(self, operation_id, campaign_id=None):
        row = self.db.execute(
            "SELECT payload FROM meta_operations WHERE id=?", (operation_id,)
        ).fetchone()
        if not row:
            raise domain_error("META_NOT_FOUND", "Delivery operation is unavailable")
        saved = json.loads(row[0])
        if campaign_id and saved["operation"]["campaign_id"] != campaign_id:
            raise domain_error("META_NOT_FOUND", "Delivery operation is unavailable")
        return saved

    def public(self, saved):
        op = MetaOperation.model_validate(saved["operation"])
        current = self.app.state.work.campaigns.repo.get(op.campaign_id)
        if current.revision != op.campaign_revision:
            if op.status in SUBMITTED or op.status == "delivery_unknown":
                op.changed_after_submission = True
            elif op.status in {"pending_confirmation", "queued"}:
                op.status = "stale"
        return op

    def save(self, saved, message):
        op = saved["operation"]
        if op["platform"] == "whatsapp" and op["provider_id"]:
            status = self.db.execute(
                "SELECT status FROM meta_message_status WHERE provider_id=?", (op["provider_id"],)
            ).fetchone()
            if status and op["status"] not in {"read", "delivered"}:
                op["status"] = "accepted" if status[0] == "sent" else status[0]
        op["updated_at"] = utc_now()
        with self.db:
            self.db.execute(
                "UPDATE meta_operations SET status=?,payload=? WHERE id=?",
                (op["status"], json.dumps(saved), op["id"]),
            )
        self.app.state.work.event(op["campaign_id"], "delivery", message)

    def binding(self, platform):
        identity, token = self.client.credentials(platform)
        return digest(
            {
                "account": identity,
                "token": sha(token.get_secret_value().encode()),
                "version": self.settings.meta_graph_version,
                "mode": self.settings.meta_mode,
                "origin": self.settings.meta_public_origin,
            }
        )

    def material(self, campaign_id, body):
        ids = [body["text_item_id"]]
        if body.get("poster_item_id"):
            ids.append(body["poster_item_id"])
        if set(body["observed_hashes"]) != set(ids):
            raise domain_error(
                "META_INVALID", "Confirm hashes for exactly the selected delivery items"
            )
        pack, files = self.app.state.approvals.export(campaign_id, body["expected_revision"], ids)
        campaign = self.app.state.approvals.ledger.campaigns.get(campaign_id)
        for item_id in ids:
            item = self.app.state.approvals.current_item(campaign, item_id)
            if item.snapshot_hash != body["observed_hashes"][item_id]:
                raise domain_error(
                    "EXPORT_UNAUTHORIZED", "Delivery hash differs from owner approval"
                )
            if item.variant.channel != body["platform"]:
                raise domain_error(
                    "META_INVALID", "Select copy and media approved for this platform"
                )
        text_item = next(f for f in pack.files if f.item_id == body["text_item_id"])
        if text_item.filename.endswith("png"):
            raise domain_error(
                "META_INVALID", "A text item is required for the exact approved caption"
            )
        text = pack.copy_text[body["text_item_id"]]
        # Do not truncate, rewrite, or silently remove hashtags/alt text from approved copy.
        limit = (
            2200
            if body["platform"] == "instagram"
            else (1024 if body.get("poster_item_id") else 4096)
        )
        if len(text) > limit:
            raise domain_error(
                "META_INVALID", "Approved text exceeds this adapter's conservative limit"
            )
        media, mime = None, None
        if body.get("poster_item_id"):
            entry = next(f for f in pack.files if f.item_id == body["poster_item_id"])
            if not entry.filename.endswith("png") or entry.language != text_item.language:
                raise domain_error("META_INVALID", "Select a same-language approved poster")
            raw = files[entry.filename]
            with Image.open(io.BytesIO(raw)) as image:
                image.load()
                if image.format != "PNG" or image.width * image.height > 16_000_000:
                    raise domain_error("META_MEDIA", "Unsupported approved media")
                if body["platform"] == "instagram":
                    if (
                        not 0.8 <= image.width / image.height <= 1.91
                        or not 320 <= image.width <= 1440
                    ):
                        raise domain_error(
                            "META_MEDIA", "Instagram scope requires a feed-compatible image"
                        )
                    output = io.BytesIO()
                    image.convert("RGB").save(output, "JPEG", quality=95, subsampling=0)
                    media, mime = output.getvalue(), "image/jpeg"
                else:
                    media, mime = raw, "image/png"
            if len(media) > (5 if body["platform"] == "whatsapp" else 8) * 1024 * 1024:
                raise domain_error("META_MEDIA", "Approved media exceeds this adapter's byte limit")
        elif body["platform"] == "instagram":
            raise domain_error(
                "META_MEDIA", "Instagram single-image publishing requires an approved poster"
            )
        if self.settings.meta_mode == "live" and (
            pack.mode != "live"
            or any(f.mode != "live" or f.source_mode == "mock" for f in pack.files)
        ):
            raise domain_error(
                "META_INVALID", "Mock or saved demo output cannot be sent as live content"
            )
        return pack, text, media, mime

    def whatsapp_rules(self, body, text):
        recipient = body.get("recipient", "")
        if not re.fullmatch(r"\+[1-9][0-9]{7,14}", recipient) or not body.get(
            "recipient_consented"
        ):
            raise domain_error(
                "META_CONSENT", "WhatsApp requires an international recipient and recorded consent"
            )
        if body.get("template_name"):
            key = body["template_name"] + ":" + body["template_language"]
            if self.settings.meta_whatsapp_templates.get(key) != sha(text.encode()):
                raise domain_error(
                    "META_TEMPLATE", "Static template must exactly match its verified approved body"
                )
        elif self.settings.meta_mode == "live":
            row = self.db.execute(
                "SELECT received_at FROM meta_inbound WHERE recipient_hash=?",
                (sha(recipient.encode()),),
            ).fetchone()
            if not row or not 0 <= time.time() - row[0] < 24 * 3600:
                raise domain_error(
                    "META_WINDOW",
                    "A verified inbound service window or approved template is required",
                )

    def preview(self, campaign_id, request):
        self.enabled(request.platform)
        body = request.model_dump(exclude={"recipient"})
        body["recipient"] = request.recipient.get_secret_value()
        hashed = digest(body)
        row = self.db.execute(
            "SELECT request_hash,payload FROM meta_operations "
            "WHERE campaign_id=? AND idempotency_key=?",
            (campaign_id, request.idempotency_key),
        ).fetchone()
        if row:
            if row[0] != hashed:
                raise domain_error(
                    "IDEMPOTENCY_CONFLICT", "Delivery key already binds another payload"
                )
            saved = json.loads(row[1])
            result = self.public(saved)
            # Preview remains repeatable for browser recovery; no external work is started.
            if result.status == "pending_confirmation":
                result.confirmation_token = saved["confirmation_token"]
            return result
        pack, text, media, mime = self.material(campaign_id, body)
        if request.platform == "whatsapp":
            self.whatsapp_rules(body, text)
        if media and self.settings.meta_mode == "live" and not self.settings.meta_public_origin:
            raise domain_error(
                "META_CONFIGURATION", "Approved media requires a public HTTPS delivery origin"
            )
        binding = self.binding(request.platform)
        account_id, _ = self.client.credentials(request.platform)
        token, now = secrets.token_urlsafe(32), utc_now()
        artifacts = {f.item_id: f.sha256 for f in pack.files}
        preview_hash = digest(
            {
                "request": hashed,
                "artifacts": artifacts,
                "binding": binding,
                "media": sha(media) if media else None,
            }
        )
        op = MetaOperation(
            id=uuid4().hex,
            campaign_id=campaign_id,
            campaign_revision=request.expected_revision,
            platform=request.platform,
            status="pending_confirmation",
            mode=self.settings.meta_mode,
            source_mode=pack.mode,
            created_at=now,
            updated_at=now,
            destination_label="WhatsApp recipient ending " + body["recipient"][-2:]
            if request.platform == "whatsapp"
            else "Configured " + request.platform + " account " + (account_id or "MOCK account"),
            text=text,
            approved_hashes=request.observed_hashes,
            artifact_hashes=artifacts,
            delivery_media_hash=sha(media) if media else None,
            preview_hash=preview_hash,
            cached=any(f.mode == "cached" for f in pack.files),
            provenance={f.item_id: f.model_dump(exclude={"artifact_url"}) for f in pack.files},
            cost_status="not_applicable_mock"
            if self.settings.meta_mode == "mock"
            else "unknown_provider_charge",
        )
        saved = {
            "operation": op.model_dump(),
            "request": body,
            "binding": binding,
            "confirmation_token": token,
            "confirmed": False,
            "media_mime": mime,
        }
        with self.db:
            self.db.execute(
                "INSERT INTO meta_operations VALUES(?,?,?,?,?,?)",
                (
                    op.id,
                    campaign_id,
                    request.idempotency_key,
                    hashed,
                    op.status,
                    json.dumps(saved),
                ),
            )
        self.app.state.work.event(
            campaign_id, "delivery", "Exact approved delivery preview awaits owner confirmation."
        )
        return op.model_copy(update={"confirmation_token": token})

    def revalidate(self, saved):
        op, body = saved["operation"], saved["request"]
        self.enabled(op["platform"])
        if self.binding(op["platform"]) != saved["binding"]:
            raise domain_error(
                "META_INVALID", "Delivery account/configuration changed; create a new preview"
            )
        pack, text, media, mime = self.material(op["campaign_id"], body)
        if (
            text != op["text"]
            or {f.item_id: f.sha256 for f in pack.files} != op["artifact_hashes"]
            or (sha(media) if media else None) != op["delivery_media_hash"]
        ):
            raise domain_error("EXPORT_UNAUTHORIZED", "Approved delivery payload changed")
        if op["platform"] == "whatsapp":
            self.whatsapp_rules(body, text)
        return media, mime

    def confirm(self, campaign_id, operation_id, body):
        saved = self.load(operation_id, campaign_id)
        op = saved["operation"]
        if (
            body.preview_hash != op["preview_hash"]
            or body.expected_revision != op["campaign_revision"]
            or not hmac.compare_digest(
                body.confirmation_token.get_secret_value(), saved["confirmation_token"]
            )
        ):
            raise domain_error("META_INVALID", "Confirmation does not bind this exact preview")
        if op["job_id"]:
            return self.public(saved)  # safe double click, including completed historical work
        if op["status"] != "pending_confirmation":
            raise domain_error(
                "META_INVALID", "Create a new reviewed preview for this stopped operation"
            )
        self.revalidate(saved)
        saved["confirmed"], op["status"] = True, "queued"
        self.save(saved, "Owner confirmed exact destination, text and media; delivery queued.")
        try:
            job = self.app.state.work.start(
                campaign_id,
                WorkRequest(
                    kind="meta_delivery",
                    idempotency_key="meta-" + operation_id,
                    input={
                        "expected_revision": op["campaign_revision"],
                        "operation_id": operation_id,
                    },
                ),
            )
        except BaseException:
            saved["confirmed"], op["status"] = False, "pending_confirmation"
            self.save(saved, "Delivery was not admitted; review and confirm explicitly.")
            raise
        op["job_id"] = job.id
        self.save(saved, "Delivery linked to durable work; replay will not resubmit.")
        return self.public(saved)

    def attempt(self, operation_id, step, attempt):
        saved = self.load(operation_id)
        op = saved["operation"]
        if op["status"] == "cancelled" or op["attempts"] >= 12:
            raise domain_error("META_DEADLINE", "Delivery attempt budget exhausted or cancelled")
        self.revalidate(saved)
        op["attempts"] += 1
        identifier = uuid4().hex
        # Journal dispatch before awaiting HTTP. No recipients, tokens, payloads or signed URLs.
        with self.db:
            self.db.execute(
                "INSERT INTO meta_attempts VALUES(?,?,?,?,?,?,?)",
                (identifier, operation_id, step, attempt, utc_now(), "in_flight", None),
            )
        self.save(saved, f"Meta {step} dispatch recorded; attempt {op['attempts']} of 12.")
        return identifier

    def finish_attempt(self, attempt_id, status, http_status):
        with self.db:
            self.db.execute(
                "UPDATE meta_attempts SET status=?,http_status=? WHERE id=?",
                (status, http_status, attempt_id),
            )

    async def call(self, operation_id, method, node, edge="", **kwargs):
        saved = self.load(operation_id)
        return await self.client.request(
            saved["operation"]["platform"],
            method,
            node,
            edge,
            before=lambda n: self.attempt(operation_id, edge or "status", n),
            after=self.finish_attempt,
            guard=work_guard.get(),
            **kwargs,
        )

    @staticmethod
    def provider_id(result, *, whatsapp=False):
        try:
            value = result["messages"][0]["id"] if whatsapp else result["id"]
        except (KeyError, IndexError, TypeError):
            raise domain_error(
                "META_DELIVERY_UNKNOWN", "Provider accepted no verifiable operation identifier"
            ) from None
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,200}", value):
            raise domain_error("META_DELIVERY_UNKNOWN", "Provider identifier is malformed")
        return value

    def media_url(self, operation_id, raw, mime):
        token = secrets.token_urlsafe(32)
        with self.db:
            self.db.execute("DELETE FROM meta_media WHERE expires_at<?", (time.time(),))
            self.db.execute(
                "INSERT INTO meta_media VALUES(?,?,?,?,?,?)",
                (
                    sha(token.encode()),
                    operation_id,
                    time.time() + 1800,
                    mime,
                    sha(raw),
                    raw,
                ),
            )
        origin = self.settings.meta_public_origin or "https://mock.invalid"
        return origin + "/api/meta/media/" + token

    def read_media(self, token):
        row = self.db.execute(
            "SELECT operation_id,expires_at,mime,sha256,bytes FROM meta_media WHERE token_hash=?",
            (sha(token.encode()),),
        ).fetchone()
        if not row or row[1] <= time.time() or sha(row[4]) != row[3]:
            raise domain_error("META_NOT_FOUND", "Delivery media grant is unavailable")
        saved = self.load(row[0])
        if saved["operation"]["status"] in {"cancelled", "failed", "stale", "pending_confirmation"}:
            raise domain_error("META_NOT_FOUND", "Delivery media grant is unavailable")
        self.revalidate(saved)
        return row[4], row[2]

    async def execute(self, job, body):
        operation_id = body.operation_id
        saved = self.load(operation_id, job.campaign_id)
        op = saved["operation"]
        if not saved["confirmed"] or op["status"] != "queued" or op["job_id"] != job.id:
            raise domain_error(
                "META_INVALID", "Only the exact owner-confirmed delivery job can submit"
            )
        try:
            media, mime = self.revalidate(saved)
            op["status"] = "submitting"
            self.save(
                saved,
                "Delivery starting; cancellation cannot undo an accepted provider action.",
            )
            identity, _ = self.client.credentials(op["platform"])
            identity = identity or "mock-account"
            url = self.media_url(operation_id, media, mime) if media else None
            if op["platform"] == "whatsapp":
                payload = {"messaging_product": "whatsapp", "to": saved["request"]["recipient"][1:]}
                if saved["request"].get("template_name"):
                    payload.update(
                        type="template",
                        template={
                            "name": saved["request"]["template_name"],
                            "language": {"code": saved["request"]["template_language"]},
                        },
                    )
                elif url:
                    payload.update(type="image", image={"link": url, "caption": op["text"]})
                else:
                    payload.update(type="text", text={"body": op["text"], "preview_url": False})
                result = await self.call(operation_id, "POST", identity, "messages", data=payload)
                saved = self.load(operation_id)
                saved["operation"].update(
                    provider_id=self.provider_id(result, whatsapp=True), status="accepted"
                )
            elif op["platform"] == "facebook":
                result = await self.call(
                    operation_id,
                    "POST",
                    identity,
                    "photos" if url else "feed",
                    data={"url": url, "caption": op["text"], "published": "true"}
                    if url
                    else {"message": op["text"]},
                )
                saved = self.load(operation_id)
                saved["operation"].update(
                    provider_id=self.provider_id(
                        {"id": result["post_id"]} if result.get("post_id") else result
                    ),
                    status="published",
                    provider_media_id=self.provider_id(result) if url else None,
                )
            else:
                result = await self.call(
                    operation_id,
                    "POST",
                    identity,
                    "media",
                    data={"image_url": url, "caption": op["text"]},
                )
                container = self.provider_id(result)
                saved = self.load(operation_id)
                saved["operation"].update(container_id=container, status="processing")
                self.save(
                    saved, "Instagram container created; waiting within the finite polling budget."
                )
                for _ in range(self.settings.meta_poll_limit):
                    status = await self.call(
                        operation_id, "GET", container, params={"fields": "status_code"}
                    )
                    if status.get("status_code") == "FINISHED":
                        break
                    if status.get("status_code") in {"ERROR", "EXPIRED"}:
                        raise domain_error(
                            "META_CONTAINER", "Instagram media container failed or expired"
                        )
                    if status.get("status_code") not in {"IN_PROGRESS"}:
                        raise domain_error(
                            "META_PROTOCOL", "Instagram container state is unrecognized"
                        )
                    await self.client.clock.sleep(2)
                else:
                    raise domain_error(
                        "META_DELIVERY_UNKNOWN",
                        "Container is still processing; inspect before a new attempt",
                    )
                result = await self.call(
                    operation_id, "POST", identity, "media_publish", data={"creation_id": container}
                )
                saved = self.load(operation_id)
                saved["operation"].update(provider_id=self.provider_id(result), status="published")
            saved["operation"]["changed_after_submission"] = (
                self.app.state.work.campaigns.repo.get(job.campaign_id).revision
                != job.campaign_revision
            )
            self.save(
                saved,
                "MOCK delivery completed; nothing sent externally."
                if op["mode"] == "mock"
                else "Provider accepted delivery; review the recorded provider status.",
            )
        except asyncio.CancelledError:
            saved = self.load(operation_id)
            if saved["operation"]["status"] in SUBMITTED:
                saved["operation"].update(
                    status="delivery_unknown", error_code="META_DELIVERY_UNKNOWN"
                )
                self.save(
                    saved,
                    "Delivery interrupted after submission began; external outcome is unknown.",
                )
            raise
        except ProviderError as exc:
            saved = self.load(operation_id)
            state = (
                "delivery_unknown"
                if exc.body.code == "META_DELIVERY_UNKNOWN"
                else (
                    "stale"
                    if exc.body.code
                    in {"REVISION_CONFLICT", "EXPORT_UNAUTHORIZED", "APPROVAL_INVALID"}
                    else "failed"
                )
            )
            saved["operation"].update(status=state, error_code=exc.body.code)
            self.save(saved, "Delivery stopped: " + exc.body.code + ". No automatic resubmission.")
        except Exception:
            saved = self.load(operation_id)
            saved["operation"].update(status="delivery_unknown", error_code="META_DELIVERY_UNKNOWN")
            self.save(saved, "Delivery outcome could not be established; inspect provider history.")
        result = self.public(saved).model_dump()
        return {
            "operation": result,
            "status": "failed"
            if result["status"] in {"failed", "delivery_unknown", "stale", "cancelled"}
            else "completed",
            "error_code": result["error_code"],
            "revision": job.campaign_revision,
        }

    def cancel(self, operation_id):
        saved = self.load(operation_id)
        op = saved["operation"]
        if op["status"] in {"pending_confirmation", "queued"}:
            op["status"] = "cancelled"
        elif op["status"] in {"submitting", "processing"}:
            op.update(status="delivery_unknown", error_code="META_DELIVERY_UNKNOWN")
        self.save(
            saved, "Delivery cancellation recorded; accepted external actions are not rolled back."
        )
        return self.public(saved)

    async def check_connection(self, platform):
        self.enabled(platform)
        identity, _ = self.client.credentials(platform)
        data = await self.client.request(
            platform, "GET", identity or "mock-account", params={"fields": "id"}
        )
        self.provider_id(data)
        return {
            "platform": platform,
            "mode": self.settings.meta_mode,
            "status": "READ_CHECK_PASSED",
            "timestamp": utc_now(),
            "publishing_verified": False,
            "note": "Identity read does not prove publishing permissions or account entitlement.",
        }

    async def reconcile(self, campaign_id, operation_id):
        saved = self.load(operation_id, campaign_id)
        op = saved["operation"]
        self.enabled(op["platform"])
        if self.binding(op["platform"]) != saved["binding"]:
            raise domain_error(
                "META_INVALID", "Account configuration changed; inspect provider history"
            )
        if op["platform"] == "whatsapp":
            # WhatsApp has no invented message-history GET here. Signed callbacks only.
            self.save(saved, "WhatsApp reconciliation uses verified status callbacks; no resend.")
        elif op["platform"] == "instagram" and op["container_id"]:
            result = await self.client.request(
                "instagram", "GET", op["container_id"], params={"fields": "status_code"}
            )
            if result.get("status_code") == "PUBLISHED":
                op["status"], op["error_code"] = "published", None
            elif result.get("status_code") in {"ERROR", "EXPIRED"}:
                op["status"], op["error_code"] = "failed", "META_CONTAINER"
            # FINISHED means ready, not published; never submit from reconciliation.
            self.save(saved, "Instagram container read recorded; reconciliation never publishes.")
        elif op["provider_id"]:
            result = await self.client.request(
                op["platform"], "GET", op["provider_id"], params={"fields": "id"}
            )
            if self.provider_id(result) == op["provider_id"]:
                op["status"], op["error_code"] = "published", None
            self.save(saved, "Provider identity read recorded; no new post created.")
        return self.public(saved)

    def webhook(self, raw, signature):
        secret = self.settings.meta_app_secret.get_secret_value()
        expected = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
        if not secret or not hmac.compare_digest(expected, signature or ""):
            raise domain_error("META_SIGNATURE", "Webhook signature is invalid")
        if len(raw) > 256 * 1024:
            raise domain_error("META_INVALID", "Webhook is too large")
        try:
            body = json.loads(raw)
            if body.get("object") != "whatsapp_business_account":
                raise ValueError
            # Validate fully before beginning writes. Keep no raw payload.
            inbound, statuses = [], []
            for entry in body.get("entry", []):
                if entry.get("id") != self.settings.meta_whatsapp_business_id:
                    continue
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    if (
                        value.get("metadata", {}).get("phone_number_id")
                        != self.settings.meta_whatsapp_phone_id
                    ):
                        continue
                    for message in value.get("messages", []):
                        phone = "+" + message.get("from", "")
                        timestamp = float(message["timestamp"])
                        if (
                            re.fullmatch(r"\+[1-9][0-9]{7,14}", phone)
                            and 0 <= time.time() - timestamp < 86400
                        ):
                            inbound.append((sha(phone.encode()), timestamp))
                    for status in value.get("statuses", []):
                        if status.get("status") in {"sent", "delivered", "read", "failed"}:
                            statuses.append((str(status["id"]), status["status"]))
        except (ValueError, TypeError, KeyError, AttributeError):
            raise domain_error("META_INVALID", "Webhook schema is invalid") from None
        fingerprint = sha(raw)
        if self.db.execute(
            "SELECT 1 FROM meta_webhook_events WHERE fingerprint=?", (fingerprint,)
        ).fetchone():
            return {"status": "duplicate"}
        updated = []
        with self.db:
            self.db.execute("INSERT INTO meta_webhook_events VALUES(?)", (fingerprint,))
            for recipient_hash, timestamp in inbound:
                self.db.execute(
                    "INSERT INTO meta_inbound VALUES(?,?) ON CONFLICT(recipient_hash) "
                    "DO UPDATE SET received_at=MAX(received_at,excluded.received_at)",
                    (recipient_hash, timestamp),
                )
            for identifier, status in statuses:
                previous = self.db.execute(
                    "SELECT status FROM meta_message_status WHERE provider_id=?", (identifier,)
                ).fetchone()
                rank = {"sent": 1, "delivered": 2, "read": 3, "failed": 0}
                if not previous or rank[status] > rank[previous[0]]:
                    self.db.execute(
                        "INSERT INTO meta_message_status VALUES(?,?) ON CONFLICT(provider_id) "
                        "DO UPDATE SET status=excluded.status",
                        (identifier, status),
                    )
                for row in self.db.execute("SELECT payload FROM meta_operations").fetchall():
                    saved = json.loads(row[0])
                    op = saved["operation"]
                    if (
                        op["platform"] != "whatsapp"
                        or op["mode"] != self.settings.meta_mode
                        or op["provider_id"] != identifier
                    ):
                        continue
                    ranks = {"accepted": 0, "sent": 1, "delivered": 2, "read": 3}
                    # A late failure/sent event cannot erase delivered/read evidence.
                    if op["status"] in {"delivered", "read"} and (
                        status == "failed" or ranks.get(status, 0) <= ranks[op["status"]]
                    ):
                        continue
                    op["status"] = "accepted" if status == "sent" else status
                    if status == "failed":
                        op["error_code"] = "META_MESSAGE_FAILED"
                    op["updated_at"] = utc_now()
                    self.db.execute(
                        "UPDATE meta_operations SET status=?,payload=? WHERE id=?",
                        (op["status"], json.dumps(saved), op["id"]),
                    )
                    updated.append(op["campaign_id"])
        for cid in set(updated):
            self.app.state.work.event(cid, "delivery", "Verified WhatsApp status event recorded.")
        return {"status": "processed"}
