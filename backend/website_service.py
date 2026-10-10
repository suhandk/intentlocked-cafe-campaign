"""Isolated website drafts, immutable bundles and owner-scoped publishing."""

import asyncio
import base64
import hashlib
import html
import io
import json
import secrets
import time
import warnings
import zipfile
from dataclasses import dataclass
from uuid import uuid4

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from PIL import Image
from pydantic import SecretStr

from backend.errors import ProviderError
from backend.guardian.report import CheckRequest
from backend.guardian.rules import check
from backend.guardian.slots import lookup
from backend.repository import CampaignRepository
from backend.schemas import TemplateContent
from backend.website_design import WebsiteDesigner, design_css
from backend.website_models import ConnectionInput, PublishInput, WebsiteFields
from backend.website_provider import MESSAGES, HostingError, NetlifyProvider


class WebsiteError(Exception):
    def __init__(self, code, message, status=422):
        self.code, self.message, self.status = code, message, status
        super().__init__(message)


@dataclass
class Receipt:
    draft_id: str
    bundle_hash: str
    token: SecretStr
    expires: float


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class WebsiteService:
    def __init__(self, store, settings, provider=None):
        self.store = store
        self.db, self.repo, self.settings = store.connection, CampaignRepository(store), settings
        self.owner = settings.website_owner_id
        self.provider = provider or NetlifyProvider()
        self.designer = WebsiteDesigner(settings, store)
        self.generating = set()
        self.receipts: dict[str, Receipt] = {}
        self.tasks: dict[str, asyncio.Task] = {}
        # Unknown prior dispatches must never be automatically replayed on restart.
        with self.db:
            for row in self.db.execute(
                "SELECT id,payload FROM website_publish_jobs WHERE owner_id=?", (self.owner,)
            ).fetchall():
                job = json.loads(row[1])
                if job["status"] in {"queued", "publishing", "verifying"}:
                    job.update(status="uncertain", message=MESSAGES["PUBLISH_UNCERTAIN"])
                    self.db.execute(
                        "UPDATE website_publish_jobs SET payload=? WHERE id=?",
                        (json.dumps(job), row[0]),
                    )

    async def close(self, *, close_designer=True):
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.receipts.clear()
        if close_designer:
            await self.designer.close()

    def draft(self, campaign_id):
        self.repo.get(campaign_id)
        row = self.db.execute(
            "SELECT payload FROM website_drafts WHERE owner_id=? AND campaign_id=?",
            (self.owner, campaign_id),
        ).fetchone()
        if row:
            return json.loads(row[0])
        value = dict(
            id=uuid4().hex,
            campaign_id=campaign_id,
            version=1,
            step=0,
            fields=WebsiteFields().model_dump(),
            bundle_id=None,
        )
        with self.db:
            self.db.execute(
                "INSERT INTO website_drafts VALUES(?,?,?,?,?)",
                (value["id"], self.owner, campaign_id, 1, json.dumps(value)),
            )
        return value

    def get(self, draft_id):
        row = self.db.execute(
            "SELECT payload FROM website_drafts WHERE id=? AND owner_id=?", (draft_id, self.owner)
        ).fetchone()
        if not row:
            raise WebsiteError("NOT_FOUND", "Website draft not found", 404)
        return json.loads(row[0])

    def save(self, draft_id, body):
        value = self.get(draft_id)
        if value["version"] != body.expected_version:
            raise WebsiteError("STALE_DRAFT", "Reload the current website draft", 409)
        next_fields = body.fields.model_dump()
        changed = next_fields != value["fields"]
        value.update(
            version=value["version"] + int(changed),
            step=body.step,
            fields=next_fields,
            bundle_id=None if changed else value["bundle_id"],
        )
        with self.db:
            self.db.execute(
                "UPDATE website_drafts SET version=?,payload=? WHERE id=? AND owner_id=?",
                (value["version"], json.dumps(value), draft_id, self.owner),
            )
        # No awaits between revision validation and the SQLite update.
        return value

    def locked(self, draft):
        campaign = self.repo.get(draft["campaign_id"])
        if campaign.status != "locked":
            raise WebsiteError("FACTS_UNLOCKED", "Lock the offer in Facts Lock before generating")
        return campaign

    def offer(self, draft_id):
        draft = self.get(draft_id)
        campaign = self.repo.get(draft["campaign_id"])
        return {
            "locked": campaign.status == "locked",
            "revision": campaign.revision,
            "facts": [f.model_dump() for f in campaign.facts if f.canonical],
            "edit_url": f"/?campaign={campaign.id}#facts-lock",
        }

    def suggest(self, draft_id):
        campaign = self.locked(self.get(draft_id))
        language = self.get(draft_id)["fields"]["languages"][0]
        try:
            name, _ = lookup(campaign, "CAFE", language, "nom")
            area, _ = lookup(campaign, "LOCATION", language, "nom")
        except ValueError:
            raise WebsiteError(
                "FORMS_MISSING", "Approve the selected language forms in Facts Lock"
            ) from None
        return {"description": f"{name} · {area}", "source": "locked forms; no invented claims"}

    def upload(self, draft_id, body):
        self.get(draft_id)
        try:
            raw = base64.b64decode(body.base64, validate=True)
            if len(raw) > 5_000_000:
                raise ValueError
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(raw)) as image:
                    expected = {"image/png": "PNG", "image/jpeg": "JPEG", "image/webp": "WEBP"}
                    if (
                        image.format != expected[body.mime]
                        or getattr(image, "n_frames", 1) != 1
                        or image.width * image.height > 12_000_000
                    ):
                        raise ValueError
                    image.load()
                    clean = io.BytesIO()
                    image.convert("RGBA").save(clean, format="PNG")
                    raw = clean.getvalue()
                    if len(raw) > 8_000_000:
                        raise ValueError
        except (ValueError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise WebsiteError(
                "IMAGE_INVALID", "Use a valid PNG, JPEG or WebP up to 5 MB and 12 megapixels"
            ) from None
        asset_id = uuid4().hex
        with self.db:
            self.db.execute(
                "INSERT INTO website_assets VALUES(?,?,?,?,?,?)",
                (asset_id, self.owner, draft_id, "image/png", sha(raw), raw),
            )
        return {"id": asset_id, "mime": "image/png", "sha256": sha(raw)}

    def assets(self, draft_id, fields):
        files = {}
        for asset_id in ([fields.logo_id] if fields.logo_id else []) + fields.photo_ids:
            row = self.db.execute(
                "SELECT bytes,sha256 FROM website_assets WHERE id=? AND owner_id=? AND draft_id=?",
                (asset_id, self.owner, draft_id),
            ).fetchone()
            if not row or sha(row[0]) != row[1]:
                raise WebsiteError("IMAGE_INVALID", "A selected website image is unavailable")
            files[f"images/{asset_id}.png"] = row[0]
        return files

    async def generate_with_ai(self, draft_id, body):
        if draft_id in self.generating:
            raise WebsiteError("GENERATION_BUSY", "Website generation is already running", 409)
        draft = self.get(draft_id)
        campaign = self.locked(draft)
        if self.settings.inference_mode == "cached" or campaign.mode == "cached":
            raise WebsiteError(
                "INFERENCE_DISABLED", "Saved-output mode cannot generate a new design", 403
            )
        # Validate the full deterministic output before sending any model request,
        # without storing a speculative or fallback bundle.
        self.generate(draft_id, body, validate_only=True)
        if (
            self.settings.website_ai_mode == "live"
            and not self.settings.openrouter_api_key.get_secret_value()
        ):
            raise WebsiteError(
                "DESIGN_UNAVAILABLE", "Website design service is not configured on the server", 503
            )
        self.generating.add(draft_id)
        try:
            async with asyncio.timeout(90):
                plan, provenance = await self.designer.generate(
                    WebsiteFields.model_validate(draft["fields"])
                )
            current = self.locked(self.get(draft_id))
            if current.revision != campaign.revision or current.fact_hash != campaign.fact_hash:
                raise WebsiteError(
                    "STALE_BUNDLE", "Facts changed during generation; review and retry", 409
                )
            return self.generate(draft_id, body, design=plan, design_provenance=provenance)
        except ProviderError:
            raise WebsiteError(
                "DESIGN_FAILED",
                "Website model could not return a valid layout. Previous work is preserved",
                502,
            ) from None
        except TimeoutError:
            raise WebsiteError(
                "DESIGN_TIMEOUT", "Website design timed out. Previous work is preserved", 504
            ) from None
        finally:
            self.generating.discard(draft_id)

    def generate(self, draft_id, body, *, design=None, design_provenance=None, validate_only=False):
        draft = self.get(draft_id)
        if body.expected_version != draft["version"]:
            raise WebsiteError("STALE_DRAFT", "Reload the current website draft", 409)
        fields = WebsiteFields.model_validate(draft["fields"])
        if not fields.name or not fields.area:
            raise WebsiteError("FIELDS_REQUIRED", "Café name and city/area are required")
        campaign = self.locked(draft)
        # Identity is a locked fact too: website inputs may not silently override it.
        canonical = {f.key: f.canonical for f in campaign.facts if f.canonical}
        if fields.name != canonical["CAFE"].value or fields.area != canonical["LOCATION"].value:
            raise WebsiteError(
                "FACT_CONFLICT", "Name and city/area must match Facts Lock; edit them there first"
            )
        files = self.assets(draft_id, fields)
        esc = html.escape
        sections, reports = [], []
        keys = [f.key for f in campaign.facts if f.canonical and f.status == "locked"]
        for language in fields.languages:
            if language not in campaign.languages:
                raise WebsiteError("FORMS_MISSING", "Select a language approved in Facts Lock")
            channel = campaign.channels[0]
            # Reuse Guardian; no AI output or arbitrary offer string enters the site.
            template = TemplateContent(
                headline="{{CAFE}}",
                body=" · ".join("{{" + key + "}}" for key in keys if key != "CAFE"),
                cta="",
                hashtags=[],
                alt_text="",
            )
            try:
                report = check(
                    campaign,
                    CheckRequest(
                        campaign_id=campaign.id,
                        expected_revision=campaign.revision,
                        mode="fragment",
                        language=language,
                        channel=channel,
                        template=template,
                    ),
                )
            except ValueError:
                raise WebsiteError(
                    "FORMS_MISSING", "Approve all selected language forms in Facts Lock"
                ) from None
            if report.status == "BLOCKED" or report.rendered is None:
                raise WebsiteError("GUARDIAN_BLOCKED", "Guardian blocked the locked offer forms")
            reports.append({"language": language, **report.model_dump()})
            sections.append(
                f'<section lang="{language}"><h1>{esc(report.rendered.fields["headline"])}</h1>'
                f'<p class="offer">{esc(report.rendered.fields["body"])}</p></section>'
            )
        if fields.description:
            # Check literal prose for unapproved offer/eligibility/claims as well.
            description_template = fields.description
            if fields.description == self.suggest(draft_id)["description"]:
                description_template = "{{CAFE}} · {{LOCATION}}"
            report = check(
                campaign,
                CheckRequest(
                    campaign_id=campaign.id,
                    expected_revision=campaign.revision,
                    mode="fragment",
                    language=fields.languages[0],
                    channel=campaign.channels[0],
                    template=TemplateContent(
                        headline="", body=description_template, cta="", hashtags=[], alt_text=""
                    ),
                    displayed=TemplateContent(
                        headline="", body=fields.description, cta="", hashtags=[], alt_text=""
                    ),
                ),
            )
            if report.status == "BLOCKED":
                raise WebsiteError(
                    "GUARDIAN_BLOCKED", "Guardian blocked a claim in the description"
                )
            reports.append({"language": fields.languages[0], **report.model_dump()})
            sections.append(f"<section><p>{esc(fields.description)}</p></section>")
        if fields.address or fields.hours or fields.phone or fields.whatsapp:
            visit = f"<p>{esc(fields.address)}</p>" if fields.address else ""
            visit += "".join(f"<p>{h.day}: {h.open}–{h.close}</p>" for h in fields.hours)
            if fields.phone:
                visit += f'<p><a href="tel:{fields.phone}">{fields.phone}</a></p>'
            if fields.whatsapp:
                visit += (
                    f'<p><a href="https://wa.me/{fields.whatsapp.lstrip("+")}">'
                    f"WhatsApp {fields.whatsapp}</a></p>"
                )
            sections.append(f'<section aria-label="Visit info">{visit}</section>')
        if fields.menu:
            rows = "".join(
                f"<li>{esc(item.name)} <span>₹{str(item.price).removesuffix('.0')}</span></li>"
                for item in fields.menu
            )
            sections.append(f'<section aria-label="Menu"><ul>{rows}</ul></section>')
        if fields.social_links:
            sections.append(
                '<nav aria-label="Social links">'
                + " ".join(
                    f'<a href="{esc(url, quote=True)}" rel="noopener noreferrer">{esc(url)}</a>'
                    for url in fields.social_links
                )
                + "</nav>"
            )
        if fields.logo_id:
            sections.insert(0, f'<img class="logo" src="images/{fields.logo_id}.png" alt="Logo">')
        if fields.photo_ids:
            sections.append(
                '<div class="website-photos">'
                + "".join(
                    f'<img src="images/{asset_id}.png" alt="Owner-provided photo">'
                    for asset_id in fields.photo_ids
                )
                + "</div>"
            )
        css = (
            f":root{{color-scheme:light;--accent:{fields.colour}}}"
            "body{margin:0;font-family:system-ui,sans-serif;background:#faf8f3;color:#242424;line-height:1.6}"
            "main{max-width:960px;margin:auto;padding:32px}"
            "section{padding:20px 0;border-bottom:1px solid #ddd}"
            "h1{color:var(--accent);overflow-wrap:anywhere}a{color:var(--accent)}"
            "img{max-width:100%;height:auto}.logo{max-height:120px}"
            "li{display:flex;justify-content:space-between;gap:20px}"
        )
        if fields.style == "warm":
            css += "body{background:#fff3df}section{border-radius:12px}"
        if fields.style == "modern":
            css += "body{background:#fff}h1{font-size:clamp(2rem,6vw,4rem)}"
        if design is not None:
            css += design_css(design)
        rendered = (
            '<!doctype html><html><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{esc(fields.name)}</title><link rel="stylesheet" href="style.css">'
            "</head><body><main>" + "".join(sections) + "</main></body></html>"
        )
        files.update(
            {
                "index.html": rendered.encode(),
                "style.css": css.encode(),
                "_headers": (
                    b"/*\n  X-Content-Type-Options: nosniff\n"
                    b"  Content-Security-Policy: default-src 'none'; img-src 'self'; "
                    b"style-src 'self'; base-uri 'none'; frame-ancestors 'none'\n"
                ),
            }
        )
        report = {
            "status": "DIAGNOSTIC",
            "campaign_source": campaign.mode.upper(),
            "design": design_provenance or {"mode": "BASIC", "provider": None, "model": None},
            "reports": reports,
            "semantic_audit": "NOT_RUN",
            "native_review": "PENDING",
            "scope": "Locked offer and description checked; visit/menu supplied by owner.",
            "approval_ready": False,
            "missing_checks": ["G14"],
            "optional_translation": "Owner text kept as entered; locked forms are multilingual.",
        }
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, raw in sorted(files.items()):
                entry = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(entry, raw)
        raw = buffer.getvalue()
        if validate_only:
            return None
        bundle_id = uuid4().hex
        with self.db:
            self.db.execute(
                "INSERT INTO website_bundles VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    bundle_id,
                    draft_id,
                    self.owner,
                    draft["version"],
                    campaign.revision,
                    campaign.fact_hash,
                    sha(raw),
                    raw,
                    rendered,
                    json.dumps(report),
                ),
            )
            draft["bundle_id"] = bundle_id
            self.db.execute(
                "UPDATE website_drafts SET payload=? WHERE id=? AND owner_id=?",
                (json.dumps(draft), draft_id, self.owner),
            )
        return self.bundle(draft_id)

    def bundle(self, draft_id, expected_hash=None):
        draft = self.get(draft_id)
        campaign = self.locked(draft)
        row = self.db.execute(
            "SELECT * FROM website_bundles WHERE id=? AND draft_id=? AND owner_id=?",
            (draft["bundle_id"], draft_id, self.owner),
        ).fetchone()
        if (
            not row
            or row[3] != draft["version"]
            or row[4] != campaign.revision
            or row[5] != campaign.fact_hash
            or sha(row[7]) != row[6]
            or (expected_hash and expected_hash != row[6])
        ):
            raise WebsiteError(
                "STALE_BUNDLE", "Generate and approve the current website bundle", 409
            )
        with zipfile.ZipFile(io.BytesIO(row[7])) as archive:
            if archive.read("index.html") != row[8].encode():
                raise WebsiteError("STALE_BUNDLE", "Stored website bytes do not match", 409)
        return {
            "id": row[0],
            "sha256": row[6],
            "bytes": row[7],
            "html": row[8],
            "report": json.loads(row[9]),
            "draft_version": row[3],
            "facts_revision": row[4],
        }

    def aes(self):
        try:
            key = base64.b64decode(
                self.settings.website_token_key.get_secret_value(), validate=True
            )
            if len(key) != 32:
                raise ValueError
            return AESGCM(key)
        except ValueError:
            raise WebsiteError(
                "KEY_UNAVAILABLE", "Remember token is unavailable; use it once instead"
            ) from None

    def remembered(self):
        row = self.db.execute(
            "SELECT suffix FROM website_tokens WHERE owner_id=? AND provider='netlify'",
            (self.owner,),
        ).fetchone()
        return {"remembered": bool(row), "masked_suffix": "••••" + row[0] if row else None}

    def decrypt(self):
        row = self.db.execute(
            "SELECT nonce,ciphertext FROM website_tokens WHERE owner_id=? AND provider='netlify'",
            (self.owner,),
        ).fetchone()
        if not row:
            raise WebsiteError("TOKEN_MISSING", "Enter a Netlify token")
        try:
            return SecretStr(
                self.aes().decrypt(row[0], row[1], f"{self.owner}:netlify:v1".encode()).decode()
            )
        except WebsiteError:
            raise
        except Exception:
            raise WebsiteError(
                "TOKEN_UNAVAILABLE",
                "The saved token cannot be read; disconnect and enter a new token",
            ) from None

    async def connect(self, draft_id, body):
        body = ConnectionInput.model_validate(body.model_dump())
        if not self.settings.website_publish_enabled:
            raise WebsiteError(
                "PUBLISH_DISABLED", "Publishing is disabled; download the website zip instead", 403
            )
        bundle = self.bundle(draft_id, body.bundle_hash)
        token = self.decrypt() if body.use_remembered else body.token
        # Verify encryption configuration before making even a read-only request.
        cipher = self.aes() if body.remember else None
        try:
            await self.provider.test(token)
        except HostingError as error:
            raise WebsiteError(error.code, MESSAGES[error.code]) from None
        # The draft may change while the read-only request is pending.
        self.bundle(draft_id, body.bundle_hash)
        raw = token.get_secret_value()
        with zipfile.ZipFile(io.BytesIO(bundle["bytes"])) as archive:
            if any(raw.encode() in archive.read(name) for name in archive.namelist()):
                raise WebsiteError(
                    "SECRET_IN_CONTENT", "Remove credential-like text from website inputs"
                )
        if body.remember:
            nonce = secrets.token_bytes(12)
            encrypted = cipher.encrypt(nonce, raw.encode(), f"{self.owner}:netlify:v1".encode())
            with self.db:
                self.db.execute(
                    "INSERT OR REPLACE INTO website_tokens VALUES(?,?,?,?,?)",
                    (self.owner, "netlify", nonce, encrypted, raw[-4:]),
                )
        # Bounded TTL and count; token exists only in server RAM until use/expiry.
        now = time.monotonic()
        self.receipts = {k: v for k, v in self.receipts.items() if v.expires > now}
        for receipt_id, receipt in list(self.receipts.items()):
            if receipt.draft_id == draft_id:
                del self.receipts[receipt_id]
        if len(self.receipts) >= 10:
            raise WebsiteError(
                "CONNECTION_LIMIT", "Finish or disconnect a pending connection first"
            )
        connection_id = uuid4().hex
        self.receipts[connection_id] = Receipt(draft_id, body.bundle_hash, token, now + 600)
        asyncio.get_running_loop().call_later(600, self.receipts.pop, connection_id, None)
        return {
            "connection_id": connection_id,
            "status": "CONNECTED",
            "message": "Read-only connection passed. Deploy permissions checked when publishing.",
            "masked_suffix": "••••" + raw[-4:],
            "expires_in": 600,
            "remembered": self.remembered()["remembered"],
        }

    async def disconnect(self):
        self.receipts.clear()
        with self.db:
            self.db.execute(
                "DELETE FROM website_tokens WHERE owner_id=? AND provider='netlify'", (self.owner,)
            )
        # Cancel any job holding a decrypted remembered or one-use token.
        await self.close(close_designer=False)
        return {"remembered": False, "masked_suffix": None}

    def job(self, job_id):
        row = self.db.execute(
            "SELECT payload FROM website_publish_jobs WHERE id=? AND owner_id=?",
            (job_id, self.owner),
        ).fetchone()
        if not row:
            raise WebsiteError("NOT_FOUND", "Publish job not found", 404)
        return json.loads(row[0])

    def persist_job(self, job):
        with self.db:
            self.db.execute(
                "UPDATE website_publish_jobs SET payload=? WHERE id=? AND owner_id=?",
                (json.dumps(job), job["id"], self.owner),
            )

    def publish(self, draft_id, body):
        body = PublishInput.model_validate(body.model_dump())
        if not self.settings.website_publish_enabled:
            raise WebsiteError(
                "PUBLISH_DISABLED", "Publishing is disabled; download the website zip instead", 403
            )
        # DTO approval and immutable bytes are independently checked server-side.
        bundle = self.bundle(draft_id, body.bundle_hash)
        receipt = self.receipts.get(body.connection_id)
        if (
            not receipt
            or receipt.expires <= time.monotonic()
            or receipt.draft_id != draft_id
            or receipt.bundle_hash != bundle["sha256"]
        ):
            self.receipts.pop(body.connection_id, None)
            raise WebsiteError(
                "CONNECTION_REQUIRED", "Test the connection for this exact bundle first", 409
            )
        if any(not task.done() for task in self.tasks.values()):
            raise WebsiteError("PUBLISH_BUSY", "A publish job is already running", 409)
        del self.receipts[body.connection_id]
        job = dict(
            id=uuid4().hex,
            draft_id=draft_id,
            bundle_hash=bundle["sha256"],
            status="queued",
            message="Exact bundle approved; waiting to publish",
            provider="netlify",
            remote_id=None,
            url=None,
        )
        with self.db:
            self.db.execute(
                "INSERT INTO website_publish_jobs VALUES(?,?,?,?,?)",
                (job["id"], self.owner, draft_id, bundle["sha256"], json.dumps(job)),
            )
        self.tasks[job["id"]] = asyncio.create_task(self.execute(job, receipt.token, bundle))
        return job

    async def execute(self, job, token, bundle):
        try:
            async with asyncio.timeout(100):
                self.bundle(job["draft_id"], job["bundle_hash"])
                job.update(status="publishing", message="Submitting the approved bundle")
                self.persist_job(
                    job
                )  # Dispatch record before a side effect; never auto retry POST.
                job["remote_id"] = await self.provider.deploy(token, bundle["bytes"])
                job.update(status="verifying", message="Verifying the live website")
                self.persist_job(job)
                url = await self.provider.ready_url(token, job["remote_id"])
                await self.provider.verify(url, bundle["html"].encode())
                self.bundle(job["draft_id"], job["bundle_hash"])
                job.update(status="published", message="Published and live URL verified", url=url)
                if getattr(self.provider, "verification_only", False):
                    job["message"] = "MOCK HOSTING TEST · " + job["message"]
        except WebsiteError:
            job.update(
                status="stale",
                message="Inputs changed during publish. Check Netlify; draft is not Published.",
            )
        except HostingError as error:
            job.update(
                status="uncertain" if error.code == "PUBLISH_UNCERTAIN" else "failed",
                message=MESSAGES[error.code],
            )
        except (TimeoutError, asyncio.CancelledError):
            job.update(status="uncertain", message=MESSAGES["PUBLISH_UNCERTAIN"])
        except Exception:
            job.update(status="failed", message=MESSAGES["PROVIDER_FAILED"])
        finally:
            token = None  # No persisted plaintext or replay input.
            self.persist_job(job)
            self.tasks.pop(job["id"], None)
