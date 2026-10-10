# Website V2 implementation output

Source snapshot of the working implementation; no live Netlify deployment proof.


## 1. Assumptions

- This is the existing private, single-owner installation. `WEBSITE_OWNER_ID` is
  server-controlled; clients cannot select an owner. No public/multi-tenant access
  model is invented. Keep public hosting disabled until authentication exists.
- Name and city/area must match canonical Facts Lock identity. Offer values and
  approved forms are read-only; changing them requires Facts Lock.
- Website generation is deterministic, using owner inputs and approved forms.
  Description suggestion uses only the approved name/location; no AI calls or
  platform credentials are needed for website generation.
- Languages select approved offer/identity forms. Optional prose/menu/visit data
  remain as entered; translations and missing business facts are never invented.
- Menu prices are INR numbers. Opening hours are same-day; overnight hours are
  rejected rather than inferred. Images support PNG/JPEG/WebP, not SVG/animation.
- Publishing creates a new Netlify site from the approved ZIP; selecting or
  overwriting an existing site is outside this addendum.
- A successful read-only Netlify request does not prove write permission. PATs can
  be broader than deploy-only: use a dedicated account/team with minimal access.
  Permission rejection at deployment is terminal, without retrying.
- Website hash approval is distinct from campaign approval. Guardian diagnostics,
  missing G14 and pending native review are displayed, never upgraded to passed.

## 2. File/folder tree

```text
backend/website_models.py
backend/website_provider.py
backend/website_service.py
backend/website_routes.py
backend/migrations/011_merge_compat.sql
backend/migrations/012_websites.sql
frontend/lib/website-api.ts
frontend/components/WebsiteWizard.tsx
backend/config.py
backend/db.py
backend/main.py
backend/art_context.py
frontend/components/CampaignFlow.tsx
frontend/next.config.ts
pyproject.toml
backend/tests/test_website.py
frontend/tests/website-api.test.mjs
frontend/e2e/website.spec.ts
frontend/playwright.website.config.ts
scripts/verify_website_ui.py
scripts/website_ui_proxy.mjs
uv.lock (updated)
docs/openapi.json (regenerated)
frontend/lib/api.generated.ts (regenerated)
.env.example (safe disabled defaults)
README.md
docs/WEBSITE_V2_DESIGN.md
docs/WEBSITE_V2_IMPLEMENTATION.md
docs/evidence/website-v2-verification.json
docs/evidence/website-wizard-mock.png
```

## 3. Data model/schema

`WebsiteWizard` adds one optional entry point to `CampaignFlow`. Existing campaign,
matrix, rendering, approval and delivery services are not called to mutate facts.
Website draft/bundle/image/token/job tables are separate. Migration 11 repairs the
pre-existing version-9 social/video collision without dropping either table;
migration 12 introduces website tables. Existing planning migration 10 is retained.
Pre-existing merge markers were removed and API contracts regenerated. A verified
Windows prompt decoding failure was fixed by an explicit UTF-8 read in art_context.

Draft: UUID, server owner ID, campaign ID, content version, step 0–6, typed fields,
current bundle ID. Step navigation does not invalidate a generated bundle; content
edits do. Draft updates compare expected version. Progress is server persisted;
the hosting token is never a draft field or browser storage item.

Facts reference: bundle stores campaign revision and fact hash. All offer strings
come from approved slot forms. Guardian runs on the offer slots and description.
Structured visit/menu inputs are explicitly owner data, not inferred campaign
facts. Reports expose that scope and `G14=NOT_RUN`/native review pending.

Bundle: immutable ZIP BLOB, SHA-256, HTML, report, draft version and facts reference.
Every preview/download/publish rechecks current content/facts and byte hash. Preview
serves these same bundle files under a sandboxed frame marked DRAFT - NOT PUBLISHED.
All text/URLs are escaped, scripts absent, image metadata stripped, and CSP shipped.

Encrypted token: owner/provider primary key, random 12-byte nonce, AES-256-GCM
ciphertext, four-character suffix. Associated data binds owner/provider/version.
The 32-byte key comes only from server environment key management; no database
plaintext or generated in-repository key. Invalid/missing key disables remembering.
Backing up the SQLite database includes ciphertext; protect the key separately.

Connection receipt: server RAM only, one tested token bound to owner service,
draft and exact bundle hash, ten-minute expiry, at most ten receipts. A receipt is
consumed once. Expiry/disconnect/shutdown clears credentials; Python does not
guarantee cryptographic erasure of every transient immutable string allocation.

Publish job: UUID, owner/draft/hash, provider, state, fixed safe message, remote site
ID and verified URL. States queued → publishing → verifying → published, or
failed/stale/uncertain. Dispatch is persisted before POST. No automatic POST retry;
restart marks interrupted jobs uncertain. One job per owner runs with a 100-second
deadline. Credentials are not persisted in job inputs or traces. Disconnect cancels
active jobs and deletes remembered ciphertext; any uncertain remote side effect
must be checked in Netlify before attempting another publication.

## 4. API request/response shapes

All routes below use `/api`. Errors contain only code/message/status metadata;
validation errors contain field paths/types, not supplied values.

| Method/path | Input | Output |
| --- | --- | --- |
| GET `/website/config` | none | supported providers, enabled/remember flags, permission note |
| GET `/campaigns/{campaign}/website` | none | creates/resumes this owner's draft |
| PUT `/websites/{id}` | `{expected_version, step, fields}` | saved draft |
| GET `/websites/{id}/offer` | none | locked flag, revision, read-only facts, Facts Lock link |
| POST `/websites/{id}/suggest` | none | description from locked identity/location forms |
| POST `/websites/{id}/images` | `{mime, base64}` | re-encoded image ID/MIME/hash |
| POST `/websites/{id}/generate` | `{expected_version}` | bundle ID/hash/versions and Guardian diagnostic report |
| GET `/websites/{id}/bundle` | none | current bundle metadata/report, no credentials |
| GET `/websites/{id}/preview/{file}` | none | same immutable HTML/CSS/image bytes |
| GET `/websites/{id}/download.zip` | none | same immutable ZIP, hash header |
| POST `/websites/{id}/connection` | `{provider:"netlify", token:SECRET, remember:false, bundle_hash}` or `{provider, use_remembered:true, bundle_hash}` | read-only result, receipt ID, masked suffix, expiry; never token |
| POST `/websites/{id}/publish` | `{connection_id, bundle_hash, approve_exact_bundle:true}` | job metadata, HTTP 202 |
| GET `/website/jobs/{job}` | none | job status; URL only after exact page bytes verified |
| GET `/website/token` | none | remembered flag and masked suffix |
| DELETE `/website/token` | none | deleted status; cancels jobs and discards receipts |

No endpoint accepts editable offers, HTML, provider endpoints, owner IDs or approval
reports. A hosting token is the only secret-bearing user input, in the connection
POST body. Generation/download have no token parameter. Secret-bearing requests
require actual HTTPS, before body validation; forwarded-proto claims are not trusted.
Website origins are restricted to the private frontend, request bodies are bounded.

## 5. Code, file by file

### backend/website_models.py

```python
"""Website inputs are owner data; locked offer values have no editable input field."""

import re
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator

from backend.contracts import StrictModel
from backend.schemas import Lang


class Hours(StrictModel):
    day: Literal["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
    open: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    close: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")

    @model_validator(mode="after")
    def ordered(self):
        if self.close <= self.open:
            raise ValueError("Close must follow open on the same day")
        return self


class MenuItem(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    price: float = Field(ge=0, le=1_000_000, allow_inf_nan=False)


class WebsiteFields(StrictModel):
    name: str = Field(default="", max_length=120)
    area: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=1000)
    languages: list[Lang] = Field(default_factory=lambda: ["en"], min_length=1, max_length=3)
    address: str = Field(default="", max_length=500)
    hours: list[Hours] = Field(default_factory=list, max_length=7)
    phone: str = Field(default="", max_length=20)
    whatsapp: str = Field(default="", max_length=20)
    menu: list[MenuItem] = Field(default_factory=list, max_length=100)
    social_links: list[str] = Field(default_factory=list, max_length=5)
    logo_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    photo_ids: list[str] = Field(default_factory=list, max_length=5)
    style: Literal["simple", "warm", "modern"] = "simple"
    colour: str = Field(default="#43362d", pattern=r"^#[a-fA-F0-9]{6}$")

    @field_validator("name", "area", "description", "address")
    @classmethod
    def clean_text(cls, value):
        if any(ord(ch) < 32 and ch not in "\n\t" for ch in value):
            raise ValueError("Control characters are not permitted")
        return value.strip()

    @field_validator("phone", "whatsapp")
    @classmethod
    def phone_format(cls, value):
        if value and not re.fullmatch(r"\+?[1-9][0-9]{6,14}", value):
            raise ValueError("Use 7–15 digits with optional leading +")
        return value

    @field_validator("social_links")
    @classmethod
    def urls(cls, values):
        for value in values:
            parsed = urlsplit(value)
            if (
                len(value) > 500
                or parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.port not in {None, 443}
            ):
                raise ValueError("Social links must be HTTPS URLs without credentials")
        return values

    @model_validator(mode="after")
    def unique(self):
        for values in [self.languages, [h.day for h in self.hours], self.photo_ids]:
            if len(values) != len(set(values)):
                raise ValueError("Repeated languages, days or images are not permitted")
        return self


class DraftSave(StrictModel):
    expected_version: int = Field(ge=1)
    step: int = Field(ge=0, le=6)
    fields: WebsiteFields


class GenerateWebsite(StrictModel):
    expected_version: int = Field(ge=1)


class ImageUpload(StrictModel):
    mime: Literal["image/png", "image/jpeg", "image/webp"]
    base64: str = Field(min_length=1, max_length=7_000_000)


class ConnectionInput(StrictModel):
    provider: Literal["netlify"]
    token: SecretStr | None = None  # Secret; transient unless remember=True.
    remember: bool = False
    use_remembered: bool = False
    bundle_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def token_choice(self):
        if self.use_remembered == (self.token is not None):
            raise ValueError("Choose a new token or the remembered token")
        if self.token is not None:
            raw = self.token.get_secret_value()
            if not 8 <= len(raw) <= 512 or not re.fullmatch(r"[A-Za-z0-9_.-]+", raw):
                raise ValueError("Token format is invalid")
        return self


class PublishInput(StrictModel):
    connection_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    bundle_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    approve_exact_bundle: Literal[True]
```

### backend/website_provider.py

```python
"""Netlify only. Secrets never enter exception messages, redirects or AI clients."""

import asyncio
import re
from typing import Protocol

import httpx
from pydantic import SecretStr


class HostingError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


MESSAGES = {
    "TOKEN_INVALID": "The token is invalid or expired. Enter a new Netlify token.",
    "TOKEN_SCOPE": "This token does not have permission for this operation.",
    "PROVIDER_LIMIT": "Netlify rate limited this request. No automatic retry was made.",
    "PROVIDER_FAILED": "Netlify operation failed. Preview and zip remain available.",
    "PUBLISH_UNCERTAIN": "The publish outcome is uncertain. Check Netlify before submitting again.",
    "URL_UNVERIFIED": "The deployed website could not be verified. It is not marked Published.",
}


class HostingProvider(Protocol):
    async def test(self, token: SecretStr) -> None: ...
    async def deploy(self, token: SecretStr, bundle: bytes) -> str: ...
    async def ready_url(self, token: SecretStr, deploy_id: str) -> str: ...
    async def verify(self, url: str, expected_html: bytes) -> None: ...


class NetlifyProvider:
    API = "https://api.netlify.com/api/v1"

    def __init__(self, transport=None, sleep=asyncio.sleep):
        self.transport, self.sleep = transport, sleep

    async def call(self, method, path, token, **kwargs):
        try:
            async with httpx.AsyncClient(
                transport=self.transport, timeout=20, follow_redirects=False, trust_env=False
            ) as client:
                response = await client.request(
                    method,
                    self.API + path,
                    headers={
                        "Authorization": "Bearer " + token.get_secret_value(),
                        "Content-Type": "application/zip"
                        if method == "POST"
                        else "application/json",
                    },
                    **kwargs,
                )
                if response.status_code == 401:
                    raise HostingError("TOKEN_INVALID")
                if response.status_code == 403:
                    raise HostingError("TOKEN_SCOPE")
                if response.status_code == 429:
                    raise HostingError("PROVIDER_LIMIT")
                if not 200 <= response.status_code < 300:
                    raise HostingError("PROVIDER_FAILED")
                return response.json()
        except (httpx.HTTPError, ValueError):
            raise HostingError(
                "PUBLISH_UNCERTAIN" if method == "POST" else "PROVIDER_FAILED"
            ) from None

    async def test(self, token):
        # Read-only. Successful listing cannot establish deploy permission.
        value = await self.call("GET", "/sites?per_page=1&page=1", token)
        if not isinstance(value, list):
            raise HostingError("PROVIDER_FAILED")

    async def deploy(self, token, bundle):
        value = await self.call("POST", "/sites", token, content=bundle)
        site_id = value.get("id")
        if not isinstance(site_id, str) or not re.fullmatch(r"[a-zA-Z0-9-]{1,100}", site_id):
            raise HostingError("PUBLISH_UNCERTAIN")
        return site_id

    async def ready_url(self, token, site_id):
        for _ in range(12):
            value = await self.call("GET", f"/sites/{site_id}", token)
            deployed = value.get("published_deploy") or {}
            if deployed.get("state") == "ready":
                url = value.get("ssl_url")
                if isinstance(url, str) and re.fullmatch(
                    r"https://[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.netlify\.app/?", url
                ):
                    return url
                raise HostingError("URL_UNVERIFIED")
            if value.get("state") in {"error", "failed"}:
                raise HostingError("PROVIDER_FAILED")
            await self.sleep(2)
        raise HostingError("URL_UNVERIFIED")

    async def verify(self, url, expected_html):
        # Separate client: no Authorization header, redirects or owner-supplied URL.
        if not re.fullmatch(r"https://[a-z0-9-]+\.netlify\.app/?", url):
            raise HostingError("URL_UNVERIFIED")
        try:
            async with httpx.AsyncClient(
                transport=self.transport, timeout=20, follow_redirects=False, trust_env=False
            ) as client:
                async with client.stream("GET", url) as response:
                    if response.status_code != 200:
                        raise HostingError("URL_UNVERIFIED")
                    received = bytearray()
                    async for chunk in response.aiter_bytes():
                        received.extend(chunk)
                        if len(received) > 2_000_000:
                            raise HostingError("URL_UNVERIFIED")
                    if bytes(received) != expected_html:
                        raise HostingError("URL_UNVERIFIED")
        except httpx.HTTPError:
            raise HostingError("URL_UNVERIFIED") from None
```

### backend/website_service.py

```python
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

from backend.guardian.report import CheckRequest
from backend.guardian.rules import check
from backend.guardian.slots import lookup
from backend.repository import CampaignRepository
from backend.schemas import TemplateContent
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

    async def close(self):
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.receipts.clear()

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

    def generate(self, draft_id, body):
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
            reports.append(report.model_dump())
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
            reports.append(report.model_dump())
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
        sections += [
            f'<img src="images/{asset_id}.png" alt="Owner-provided photo">'
            for asset_id in fields.photo_ids
        ]
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
        await self.close()
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
```

### backend/website_routes.py

```python
"""Secret-bearing requests require direct TLS and never enter the inference queue."""

import io
import zipfile

from fastapi import APIRouter, Request
from fastapi.responses import Response

from backend.website_models import (
    ConnectionInput,
    DraftSave,
    GenerateWebsite,
    ImageUpload,
    PublishInput,
)
from backend.website_service import WebsiteError

router = APIRouter(prefix="/api", tags=["website wizard"])


def service(request):
    return request.app.state.website


def public_bundle(value):
    return {key: item for key, item in value.items() if key not in {"bytes", "html"}}


@router.get("/website/config")
async def config(request: Request):
    settings = request.app.state.settings
    return {
        "providers": ["netlify"],
        "publish_enabled": settings.website_publish_enabled,
        "remember_available": bool(settings.website_token_key.get_secret_value()),
        "permissions_note": "Use a dedicated Netlify account/team with only needed site access. "
        "Personal access tokens may be broader than deploy-only; connection "
        "testing does not verify deploy permission.",
    }


@router.get("/campaigns/{campaign_id}/website")
async def draft(campaign_id: str, request: Request):
    return service(request).draft(campaign_id)


@router.put("/websites/{draft_id}")
async def save(draft_id: str, body: DraftSave, request: Request):
    return service(request).save(draft_id, body)


@router.get("/websites/{draft_id}/offer")
async def offer(draft_id: str, request: Request):
    return service(request).offer(draft_id)


@router.post("/websites/{draft_id}/suggest")
async def suggest(draft_id: str, request: Request):
    return service(request).suggest(draft_id)


@router.post("/websites/{draft_id}/images", status_code=201)
async def images(draft_id: str, body: ImageUpload, request: Request):
    return service(request).upload(draft_id, body)


@router.post("/websites/{draft_id}/generate")
async def generate(draft_id: str, body: GenerateWebsite, request: Request):
    return public_bundle(service(request).generate(draft_id, body))


@router.get("/websites/{draft_id}/bundle")
async def bundle(draft_id: str, request: Request):
    return public_bundle(service(request).bundle(draft_id))


@router.get("/websites/{draft_id}/download.zip")
async def download(draft_id: str, request: Request):
    value = service(request).bundle(draft_id)
    return Response(
        value["bytes"],
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="cafe-website.zip"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "X-Bundle-SHA256": value["sha256"],
        },
    )


@router.get("/websites/{draft_id}/preview/{filename:path}")
async def preview(draft_id: str, filename: str, request: Request):
    value = service(request).bundle(draft_id)
    with zipfile.ZipFile(io.BytesIO(value["bytes"])) as archive:
        if filename not in archive.namelist() or filename == "_headers":
            raise WebsiteError("NOT_FOUND", "Preview file not found", 404)
        raw = archive.read(filename)
    mime = (
        "text/html"
        if filename == "index.html"
        else "text/css"
        if filename == "style.css"
        else "image/png"
    )
    return Response(
        raw,
        media_type=mime,
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; img-src 'self'; style-src 'self'; "
            "base-uri 'none'; frame-ancestors 'self'",
        },
    )


@router.post("/websites/{draft_id}/connection")
async def connection(draft_id: str, body: ConnectionInput, request: Request):
    return await service(request).connect(draft_id, body)


@router.get("/website/token")
async def token_status(request: Request):
    return service(request).remembered()


@router.delete("/website/token")
async def disconnect(request: Request):
    return await service(request).disconnect()


@router.post("/websites/{draft_id}/publish", status_code=202)
async def publish(draft_id: str, body: PublishInput, request: Request):
    return service(request).publish(draft_id, body)


@router.get("/website/jobs/{job_id}")
async def job(job_id: str, request: Request):
    return service(request).job(job_id)
```

### backend/migrations/011_merge_compat.sql

```sql
CREATE TABLE IF NOT EXISTS social_profiles (
    id INTEGER PRIMARY KEY CHECK(id = 1), version INTEGER NOT NULL, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS campaign_videos (
    id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS campaign_videos_campaign ON campaign_videos(campaign_id);
```

### backend/migrations/012_websites.sql

```sql
CREATE TABLE website_drafts (
    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, campaign_id TEXT NOT NULL,
    version INTEGER NOT NULL, payload TEXT NOT NULL
);
CREATE UNIQUE INDEX website_owner_campaign ON website_drafts(owner_id, campaign_id);
CREATE TABLE website_bundles (
    id TEXT PRIMARY KEY, draft_id TEXT NOT NULL, owner_id TEXT NOT NULL,
    draft_version INTEGER NOT NULL, facts_revision INTEGER NOT NULL,
    facts_hash TEXT NOT NULL, sha256 TEXT NOT NULL, bytes BLOB NOT NULL,
    html TEXT NOT NULL, report TEXT NOT NULL
);
CREATE TABLE website_assets (
    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, draft_id TEXT NOT NULL,
    mime TEXT NOT NULL, sha256 TEXT NOT NULL, bytes BLOB NOT NULL
);
CREATE TABLE website_tokens (
    owner_id TEXT NOT NULL, provider TEXT NOT NULL, nonce BLOB NOT NULL,
    ciphertext BLOB NOT NULL, suffix TEXT NOT NULL,
    PRIMARY KEY(owner_id, provider)
);
CREATE TABLE website_publish_jobs (
    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, draft_id TEXT NOT NULL,
    bundle_hash TEXT NOT NULL, payload TEXT NOT NULL
);
```

### frontend/lib/website-api.ts

```typescript
export type WebsiteFields = {
  name: string; area: string; description: string; languages: ("en" | "kn" | "kn-Latn")[];
  address: string; hours: { day: "MON" | "TUE" | "WED" | "THU" | "FRI" | "SAT" | "SUN"; open: string; close: string }[];
  phone: string; whatsapp: string; menu: { name: string; price: number }[];
  social_links: string[]; logo_id: string | null; photo_ids: string[];
  style: "simple" | "warm" | "modern"; colour: string;
};
export type WebsiteDraft = { id: string; campaign_id: string; version: number; step: number; fields: WebsiteFields; bundle_id: string | null };
export type WebsiteBundle = { id: string; sha256: string; draft_version: number; facts_revision: number; report: {
  status: string; campaign_source: string; semantic_audit: string; native_review: string; scope: string; missing_checks: string[];
  reports: { language: string; status: string; rendered: { fields: Record<string, string> } | null }[];
} };
export type WebsiteJob = { id: string; status: string; message: string; url: string | null; bundle_hash: string };
export async function websiteApi<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  const response = await fetch(`/api${path}`, { method, cache: "no-store", headers: { "Content-Type": "application/json" },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
  const result = await response.json();
  if (!response.ok) throw new Error(result.message ?? "Website operation failed");
  return result as T;
}

// CSV uses exactly name,price. Quoted commas/newlines and escaped quotes supported.
export function parseMenuCsv(text: string): WebsiteFields["menu"] {
  if (text.length > 50_000) throw new Error("CSV is too large");
  const rows: string[][] = []; let row: string[] = []; let cell = ""; let quoted = false; let closed = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (quoted) { if (ch === '"' && text[i + 1] === '"') { cell += '"'; i++; }
      else if (ch === '"') { quoted = false; closed = true; } else cell += ch; continue; }
    if (ch === '"') { if (cell || closed) throw new Error("Malformed CSV quotes"); quoted = true; }
    else if (ch === ",") { row.push(cell); cell = ""; closed = false; }
    else if (ch === "\n" || ch === "\r") { if (ch === "\r" && text[i + 1] === "\n") i++;
      row.push(cell); if (row.some(v => v.trim())) rows.push(row); row = []; cell = ""; closed = false; }
    else { if (closed && ch.trim()) throw new Error("Malformed CSV quotes"); cell += ch; }
  }
  if (quoted) throw new Error("Unclosed CSV quote");
  row.push(cell); if (row.some(v => v.trim())) rows.push(row);
  if (rows[0]?.map(v => v.trim().toLowerCase()).join(",") === "name,price") rows.shift();
  if (rows.length > 100) throw new Error("Maximum 100 menu rows");
  return rows.map(r => { const name = r[0]?.trim(); const value = r[1]?.trim(); const price = Number(value);
    if (r.length !== 2 || !name || name.length > 100 || !value || !Number.isFinite(price) || price < 0 || price > 1_000_000)
      throw new Error("Each CSV row needs a name and a numeric INR price"); return { name, price }; });
}

export function websiteInputError(fields: WebsiteFields): string | null {
  if (!fields.name.trim() || !fields.area.trim()) return "Café name and city/area are required";
  if (fields.name.length > 120 || fields.area.length > 200) return "Name or city/area is too long";
  if ([fields.phone, fields.whatsapp].some(v => v && !/^\+?[1-9][0-9]{6,14}$/.test(v))) return "Phone needs 7–15 digits, optionally starting with +";
  if (fields.hours.some(h => !/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(h.open) || !/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(h.close) || h.close <= h.open)) return "Opening hours need valid same-day open and close times";
  if (fields.menu.some(m => !m.name.trim() || !Number.isFinite(m.price) || m.price < 0 || m.price > 1_000_000)) return "Menu prices must be valid numbers in INR";
  for (const link of fields.social_links) { try { const url = new URL(link); if (url.protocol !== "https:" || url.username || url.password) return "Social links must be HTTPS URLs"; } catch { return "Invalid social URL"; } }
  return null;
}
```

### frontend/components/WebsiteWizard.tsx

```tsx
"use client";
import { useEffect, useRef, useState } from "react";
import { Button, Dialog } from "./ui";
import { parseMenuCsv, websiteApi, websiteInputError, type WebsiteBundle, type WebsiteDraft, type WebsiteFields, type WebsiteJob } from "@/lib/website-api";

const steps = ["Basics", "Offer", "Visit info", "Menu", "Look", "Review", "Publish"];
type Offer = { locked: boolean; edit_url: string; facts: { key: string; canonical: unknown }[]; revision: number };
type Config = { providers: string[]; publish_enabled: boolean; remember_available: boolean; permissions_note: string };
type Connection = { connection_id: string; masked_suffix: string; message: string; remembered: boolean };

export default function WebsiteWizard({ campaignId, readOnly = false }: { campaignId: string; readOnly?: boolean }) {
  const [open, setOpen] = useState(false); const [draft, setDraft] = useState<WebsiteDraft | null>(null);
  const [fields, setFields] = useState<WebsiteFields | null>(null); const [step, setStep] = useState(0);
  const [offer, setOffer] = useState<Offer | null>(null); const [config, setConfig] = useState<Config | null>(null);
  const [bundle, setBundle] = useState<WebsiteBundle | null>(null); const [error, setError] = useState("");
  const [busy, setBusy] = useState(false); const [saveStatus, setSaveStatus] = useState("");
  const [token, setToken] = useState(""); const [remember, setRemember] = useState(false);
  const [remembered, setRemembered] = useState(false); const [useRemembered, setUseRemembered] = useState(false);
  const [connection, setConnection] = useState<Connection | null>(null); const [approvedHash, setApprovedHash] = useState("");
  const [job, setJob] = useState<WebsiteJob | null>(null); const [csv, setCsv] = useState("");
  const [https, setHttps] = useState(false);
  const version = useRef(1); const saveQueue = useRef<Promise<unknown>>(Promise.resolve());
  const latest = useRef<{ fields: WebsiteFields; step: number } | null>(null);
  const savedJson = useRef("");
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    void Promise.all([websiteApi<WebsiteDraft>(`/campaigns/${campaignId}/website`), websiteApi<Config>("/website/config"),
      websiteApi<{ remembered: boolean }>("/website/token")]).then(async ([value, cfg, status]) => {
      if (cancelled) return; version.current = value.version; setDraft(value); setFields(value.fields); setStep(value.step);
      latest.current = { fields: value.fields, step: value.step }; savedJson.current = JSON.stringify(latest.current);
      setConfig(cfg); setRemembered(status.remembered); setSaveStatus("Draft saved");
      const currentOffer = await websiteApi<Offer>(`/websites/${value.id}/offer`); if (!cancelled) setOffer(currentOffer);
      if (value.bundle_id) { const result = await websiteApi<WebsiteBundle>(`/websites/${value.id}/bundle`);
        if (!cancelled) setBundle(result); }
    }).catch(() => { if (!cancelled) setError("Could not resume the website draft or bundle. Reload and review Facts Lock."); });
    return () => { cancelled = true; setToken(""); };
  }, [open, campaignId]);
  useEffect(() => {
    if (!job || !["queued", "publishing", "verifying"].includes(job.status)) return;
    const timer = setInterval(() => { void websiteApi<WebsiteJob>(`/website/jobs/${job.id}`).then(setJob).catch(() => setError("Publish status unavailable. Check Netlify before submitting again.")); }, 1500);
    return () => clearInterval(timer);
  }, [job]);
  function persist(snapshot: { fields: WebsiteFields; step: number }) {
    if (!draft) return Promise.resolve();
    const encoded = JSON.stringify(snapshot);
    const run = saveQueue.current.catch(() => undefined).then(async () => {
      if (savedJson.current === encoded) return;
      setSaveStatus("Saving draft…");
      const value = await websiteApi<WebsiteDraft>(`/websites/${draft.id}`, "PUT", { expected_version: version.current, ...snapshot });
      version.current = value.version; savedJson.current = encoded; setDraft(value); setSaveStatus("Draft saved");
    });
    saveQueue.current = run;
    return run;
  }
  // Owner fields only. Provider tokens are never part of this draft or any storage call.
  function update(next: WebsiteFields) {
    setFields(next); latest.current = { fields: next, step }; setBundle(null); setConnection(null); setApprovedHash("");
    void persist(latest.current).catch(() => { setSaveStatus("Draft not saved"); setError("Could not save the draft. Fix invalid inputs or reload after a conflict."); });
  }
  async function changeStep(next: number) {
    if (!fields) return; setBusy(true); setError("");
    try { await persist({ fields, step: next }); setStep(next); latest.current = { fields, step: next }; }
    catch { setError("Could not save this step. Review inputs and retry."); } finally { setBusy(false); }
  }
  async function close() { setBusy(true); try { if (latest.current) await persist(latest.current); setOpen(false); setToken(""); setConnection(null); setApprovedHash(""); }
    catch { setError("Draft could not be saved; keep this window open and retry."); } finally { setBusy(false); } }
  async function action(work: () => Promise<void>) { setBusy(true); setError(""); try { await work(); }
    catch (e) { setError(e instanceof Error ? e.message : "Website operation failed"); } finally { setBusy(false); } }
  async function generate() { if (!draft || !fields) return;
    const invalid = websiteInputError(fields); if (invalid) { setError(invalid); return; }
    if (!offer?.locked) { setError("Lock the offer in Facts Lock before generating"); return; }
    await action(async () => { await persist({ fields, step: 5 }); setStep(5);
      const result = await websiteApi<WebsiteBundle>(`/websites/${draft.id}/generate`, "POST", { expected_version: version.current });
      setBundle(result); setApprovedHash(""); setConnection(null); }); }
  async function upload(file: File, logo: boolean) {
    if (!draft || !fields) return;
    if (!["image/png", "image/jpeg", "image/webp"].includes(file.type) || file.size > 5_000_000) { setError("Images must be PNG, JPEG or WebP, up to 5 MB"); return; }
    await action(async () => { const encoded = await new Promise<string>((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result).split(",")[1]); reader.onerror = () => reject(new Error("Image could not be read")); reader.readAsDataURL(file); });
      const result = await websiteApi<{ id: string }>(`/websites/${draft.id}/images`, "POST", { mime: file.type, base64: encoded });
      update(logo ? { ...fields, logo_id: result.id } : { ...fields, photo_ids: [...fields.photo_ids, result.id] }); });
  }
  return <div className="card space-y-3">
    <Button variant="secondary" disabled={readOnly} onClick={() => { setError(""); setBundle(null); setHttps(window.location.protocol === "https:"); setOpen(true); }}>Create website</Button>
    <p className="hint">Optional website wizard. Your campaign stays unchanged.</p>
    <Dialog open={open} onClose={() => { if (!busy) void close(); }} title="Create website">
      <p role="status">{saveStatus}</p>{error && <p role="alert" className="callout danger">{error}</p>}
      <nav aria-label="Website wizard steps" className="flex flex-wrap gap-2">{steps.map((name, i) => <button key={name} className="field" aria-current={step === i ? "step" : undefined} disabled={busy || !draft} onClick={() => void changeStep(i)}>{i + 1}. {name}</button>)}</nav>
      {draft && fields && <fieldset disabled={busy} className="space-y-4 mt-4"><h3>{steps[step]}</h3>
        {step === 0 && <><label>Café name (required)<input className="field" required maxLength={120} value={fields.name} onChange={e => update({ ...fields, name: e.target.value })}/></label>
          <label>City/area (required)<input className="field" required maxLength={200} value={fields.area} onChange={e => update({ ...fields, area: e.target.value })}/></label>
          <p>Use the café name and city/area from Facts Lock.</p><label>Description (optional)<textarea className="field" maxLength={1000} value={fields.description} onChange={e => update({ ...fields, description: e.target.value })}/></label>
          <Button variant="secondary" onClick={() => void action(async () => { const result = await websiteApi<{ description: string }>(`/websites/${draft.id}/suggest`, "POST"); update({ ...fields, description: result.description }); })}>Suggest one</Button>
          <fieldset><legend>Languages (optional)</legend>{(["en", "kn", "kn-Latn"] as const).map(language => <label key={language}><input type="checkbox" checked={fields.languages.includes(language)} onChange={e => { const selected = e.target.checked ? [...fields.languages, language] : fields.languages.filter(v => v !== language); if (selected.length) update({ ...fields, languages: selected }); }}/>{language}</label>)}</fieldset></>}
        {step === 1 && <>{offer?.locked ? <><p>Read-only offer · Facts Lock revision {offer.revision}</p><dl>{offer.facts.map(f => <div key={f.key}><dt>{f.key}</dt><dd>{JSON.stringify(f.canonical)}</dd></div>)}</dl></> : <p role="alert">No facts are locked. Lock the offer before generation.</p>}
          <a className="underline" href={offer?.edit_url ?? `/?campaign=${campaignId}#facts-lock`} onClick={() => { setToken(""); }}>Edit in Facts Lock</a></>}
        {step === 2 && <><label>Address (optional)<textarea className="field" maxLength={500} value={fields.address} onChange={e => update({ ...fields, address: e.target.value })}/></label>
          {(["phone", "whatsapp"] as const).map(key => <label key={key}>{key === "phone" ? "Phone" : "WhatsApp"} (optional)<input className="field" type="tel" value={fields[key]} onChange={e => update({ ...fields, [key]: e.target.value })}/></label>)}
          <fieldset><legend>Opening hours (optional; same-day)</legend>{fields.hours.map((hours, i) => <div key={hours.day} className="flex gap-2"><span>{hours.day}</span>{(["open", "close"] as const).map(key => <label key={key}>{key}<input type="time" className="field" value={hours[key]} onChange={e => update({ ...fields, hours: fields.hours.map((h, n) => n === i ? { ...h, [key]: e.target.value } : h) })}/></label>)}<button onClick={() => update({ ...fields, hours: fields.hours.filter((_, n) => n !== i) })}>Remove day</button></div>)}
            <label>Add opening day<select className="field" value="" onChange={e => { if (e.target.value) update({ ...fields, hours: [...fields.hours, { day: e.target.value as WebsiteFields["hours"][number]["day"], open: "", close: "" }] }); }}><option value="">Choose day</option>{(["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"] as const).filter(day => !fields.hours.some(h => h.day === day)).map(day => <option key={day}>{day}</option>)}</select></label></fieldset>
          <label>Social links (optional, one HTTPS URL per line)<textarea className="field" value={fields.social_links.join("\n")} onChange={e => update({ ...fields, social_links: e.target.value.split("\n").filter(v => v.trim()) })}/></label></>}
        {step === 3 && <><p>Optional menu, prices in INR. Empty menu omits the section.</p>{fields.menu.map((item, i) => <div key={i} className="flex gap-2"><label>Menu item {i + 1}<input className="field" maxLength={100} value={item.name} onChange={e => update({ ...fields, menu: fields.menu.map((m, n) => n === i ? { ...m, name: e.target.value } : m) })}/></label><label>Price {i + 1}<input className="field" type="number" min="0" max="1000000" value={Number.isFinite(item.price) ? item.price : ""} onChange={e => update({ ...fields, menu: fields.menu.map((m, n) => n === i ? { ...m, price: e.target.value === "" ? NaN : Number(e.target.value) } : m) })}/></label><button onClick={() => update({ ...fields, menu: fields.menu.filter((_, n) => n !== i) })}>Remove item</button></div>)}
          <Button variant="secondary" disabled={fields.menu.length >= 100} onClick={() => update({ ...fields, menu: [...fields.menu, { name: "", price: NaN }] })}>Add menu row</Button>
          <label>CSV (name,price)<textarea className="field" value={csv} onChange={e => setCsv(e.target.value)}/></label><Button variant="secondary" onClick={() => { try { update({ ...fields, menu: parseMenuCsv(csv) }); } catch (e) { setError(e instanceof Error ? e.message : "Invalid CSV"); } }}>Import CSV</Button></>}
        {step === 4 && <><label>Style<select className="field" value={fields.style} onChange={e => update({ ...fields, style: e.target.value as WebsiteFields["style"] })}>{["simple", "warm", "modern"].map(style => <option key={style}>{style}</option>)}</select></label>
          <label>Colour<input type="color" value={fields.colour} onChange={e => update({ ...fields, colour: e.target.value })}/></label>
          <label>Logo (optional)<input type="file" accept="image/png,image/jpeg,image/webp" onChange={e => { const file = e.target.files?.[0]; if (file) void upload(file, true); }}/></label>{fields.logo_id && <button onClick={() => update({ ...fields, logo_id: null })}>Remove logo</button>}
          <label>Photo (optional, up to 5)<input type="file" disabled={fields.photo_ids.length >= 5} accept="image/png,image/jpeg,image/webp" onChange={e => { const file = e.target.files?.[0]; if (file) void upload(file, false); }}/></label>{fields.photo_ids.map((id, i) => <button key={id} onClick={() => update({ ...fields, photo_ids: fields.photo_ids.filter(v => v !== id) })}>Remove photo {i + 1}</button>)}</>}
        {step === 5 && <><p className="callout">DRAFT - NOT PUBLISHED</p><Button disabled={!offer?.locked || !!websiteInputError(fields)} onClick={() => void generate()}>Generate website</Button>{!offer?.locked && <p>Generation requires locked facts.</p>}{websiteInputError(fields) && <p>{websiteInputError(fields)}</p>}
          {bundle && <><h4>Guardian report</h4><p>Source: {bundle.report.campaign_source}</p><p>{bundle.report.scope}</p><p>Semantic audit: {bundle.report.semantic_audit} · native review: {bundle.report.native_review}. Missing checks: {bundle.report.missing_checks.join(", ")}. This does not approve a campaign.</p><ul>{bundle.report.reports.map((r, i) => <li key={i}>{r.language}: {r.status}</li>)}</ul>
            <iframe title="DRAFT - NOT PUBLISHED website preview" sandbox="" src={`/api/websites/${draft.id}/preview/index.html`} style={{ width: "100%", height: 420, border: "1px solid #bbb" }}/><p className="break-all">Bundle SHA-256: {bundle.sha256}</p></> }</>}
        {step === 6 && <><p>Publishing is optional. Zip download needs no hosting token.</p>{bundle ? <><p>Bundle source: {bundle.report.campaign_source}. Semantic/native review pending; website hash approval does not mark these checks passed.</p><a className="underline" href={`/api/websites/${draft.id}/download.zip`}>Download website (zip)</a></> : <p>Generate the current website in Review first.</p>}
          {!config?.publish_enabled && <p>Publishing is disabled by default. Zip export stays available.</p>}{!https && <p>Publishing credentials require HTTPS. Token entry is disabled here.</p>}
          <fieldset disabled={!https || !config?.publish_enabled || !bundle}><legend>Publish</legend><label>Hosting provider<select className="field"><option value="netlify">Netlify</option></select></label><p>{config?.permissions_note}</p>
            {remembered && <label><input type="checkbox" checked={useRemembered} onChange={e => { setUseRemembered(e.target.checked); setToken(""); setConnection(null); setApprovedHash(""); }}/>Use remembered Netlify token</label>}
            {!useRemembered && <label>Netlify API token<input className="field" type="password" autoComplete="off" spellCheck={false} value={token} onChange={e => { setToken(e.target.value); setConnection(null); setApprovedHash(""); }}/></label>}
            <label><input type="checkbox" disabled={!config?.remember_available || useRemembered} checked={remember} onChange={e => setRemember(e.target.checked)}/>Remember for next time (encrypted on server)</label>
            <Button variant="secondary" disabled={!token && !useRemembered} onClick={() => void action(async () => { if (!bundle) return; const entered = token; setToken(""); const result = await websiteApi<Connection>(`/websites/${draft.id}/connection`, "POST", { provider: "netlify", ...(useRemembered ? { use_remembered: true } : { token: entered }), remember, bundle_hash: bundle.sha256 }); setConnection(result); setRemembered(result.remembered); })}>Test connection</Button>
            {connection && <><p>{connection.message} · {connection.masked_suffix}</p><p className="break-all">Approve exact bundle SHA-256: {bundle?.sha256}</p><label><input type="checkbox" checked={!!bundle && approvedHash === bundle.sha256} onChange={e => setApprovedHash(e.target.checked && bundle ? bundle.sha256 : "")}/>I approve publication of this exact website bundle</label></>}
            <Button disabled={!connection || !bundle || approvedHash !== bundle.sha256 || !!job && ["queued", "publishing", "verifying"].includes(job.status)} onClick={() => void action(async () => { if (!bundle || !connection) return; const result = await websiteApi<WebsiteJob>(`/websites/${draft.id}/publish`, "POST", { connection_id: connection.connection_id, bundle_hash: bundle.sha256, approve_exact_bundle: true }); setJob(result); setConnection(null); setApprovedHash(""); setToken(""); })}>Publish</Button>
          </fieldset>
          {(remembered || connection) && <Button variant="secondary" disabled={!https} onClick={() => void action(async () => { await websiteApi("/website/token", "DELETE"); setRemembered(false); setUseRemembered(false); setConnection(null); setToken(""); setApprovedHash(""); })}>Disconnect / delete token</Button>}
          {job && <p role="status">{job.message}{job.status === "published" && job.url && <a className="underline" href={job.url} target="_blank" rel="noopener noreferrer"> Open verified website</a>}</p>}
        </>}
        <div className="flex flex-wrap gap-2"><Button variant="secondary" disabled={step === 0} onClick={() => void changeStep(step - 1)}>Back</Button>{step < 6 && <Button variant="secondary" onClick={() => void changeStep(step + 1)}>{[2, 3, 4].includes(step) ? "Skip / Next" : "Next"}</Button>}<Button variant="secondary" onClick={() => void close()}>Save and close</Button></div>
      </fieldset>}
    </Dialog>
  </div>;
}
```

### backend/config.py

```python
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)
    agnes_mode: Literal["mock", "live", "cached"] = "mock"
    agnes_api_key: SecretStr = SecretStr("")
    agnes_base_url: str = "https://apihub.agnes-ai.com/v1"
    text_model: Literal["agnes-3.0-flash"] = "agnes-3.0-flash"
    image_model: Literal["agnes-image-2.5-flash"] = "agnes-image-2.5-flash"
    video_model: Literal["agnes-video-2.5", "agnes-video-2.5-flash"] = "agnes-video-2.5-flash"
    enable_video: bool = False
    video_entitlement_verified: bool = False
    text_rpm: int = Field(default=8, ge=1, le=10)
    image_rpm: int = Field(default=8, ge=1, le=10)
    video_rpm: Literal[1] = 1
    structured_strategy: Literal["tools", "json"] = "tools"
    database_path: Path = Path("data/campaigns.sqlite3")
    asset_path: Path = Path("data/assets")
    render_origin: Literal["http://127.0.0.1:8000", "http://localhost:8000"] = (
        "http://127.0.0.1:8000"
    )
    today_override: str | None = None
    demo_fast: bool = False
    website_publish_enabled: bool = False
    website_owner_id: str = Field(default="local-owner", min_length=1, max_length=100)
    website_token_key: SecretStr = SecretStr("")
    # Separate non-inference delivery boundary. Never exposed to the browser.
    meta_enabled: bool = False
    meta_mode: Literal["mock", "live"] = "mock"
    meta_graph_version: str = Field(default="v25.0", pattern=r"^v[0-9]+\.0$")
    meta_verified_platforms: list[Literal["whatsapp", "facebook", "instagram"]] = Field(
        default_factory=list
    )
    meta_owner_token: SecretStr = SecretStr("")
    meta_app_secret: SecretStr = SecretStr("")
    meta_webhook_verify_token: SecretStr = SecretStr("")
    meta_whatsapp_phone_id: str = Field(default="", pattern=r"^[0-9]*$")
    meta_whatsapp_business_id: str = Field(default="", pattern=r"^[0-9]*$")
    meta_whatsapp_token: SecretStr = SecretStr("")
    meta_facebook_page_id: str = Field(default="", pattern=r"^[0-9]*$")
    meta_facebook_token: SecretStr = SecretStr("")
    meta_instagram_account_id: str = Field(default="", pattern=r"^[0-9]*$")
    meta_instagram_token: SecretStr = SecretStr("")
    meta_public_origin: str = ""
    meta_request_timeout: float = Field(default=20, ge=1, le=60)
    meta_max_attempts: int = Field(default=3, ge=1, le=3)
    meta_poll_limit: int = Field(default=6, ge=1, le=12)
    # Verified static, parameter-free template: name:language -> exact approved body SHA256.
    meta_whatsapp_templates: dict[str, str] = Field(default_factory=dict)
    frontend_origin: Literal["http://127.0.0.1:3000", "http://localhost:3000"] = (
        "http://127.0.0.1:3000"
    )

    @field_validator("video_rpm", mode="before")
    @classmethod
    def parse_video_rpm(cls, value):
        # Environment values are strings; retain the exact one-per-minute policy.
        return 1 if value == "1" else value

    @model_validator(mode="after")
    def enforce_policy(self):
        if self.meta_public_origin:
            from urllib.parse import urlparse

            origin = urlparse(self.meta_public_origin)
            if (
                origin.scheme != "https"
                or not origin.hostname
                or origin.username
                or origin.password
                or origin.query
                or origin.fragment
                or origin.path not in {"", "/"}
                or origin.hostname in {"localhost", "127.0.0.1", "::1"}
            ):
                raise ValueError("META_PUBLIC_ORIGIN must be a public HTTPS origin")
            self.meta_public_origin = self.meta_public_origin.rstrip("/")
        if self.meta_enabled and len(self.meta_owner_token.get_secret_value()) < 32:
            raise ValueError(
                "Enabled delivery requires a private META_OWNER_TOKEN of at least 32 characters"
            )
        if self.meta_enabled and self.meta_mode == "live":
            if self.agnes_mode != "live" or not self.meta_verified_platforms:
                raise ValueError(
                    "Live delivery requires live source mode and independently verified platforms"
                )
            if not self.meta_app_secret.get_secret_value():
                raise ValueError("Live delivery requires META_APP_SECRET for signing")
            for platform in self.meta_verified_platforms:
                identity, token = {
                    "whatsapp": (self.meta_whatsapp_phone_id, self.meta_whatsapp_token),
                    "facebook": (self.meta_facebook_page_id, self.meta_facebook_token),
                    "instagram": (self.meta_instagram_account_id, self.meta_instagram_token),
                }[platform]
                if not identity or not token.get_secret_value():
                    raise ValueError(
                        "Verified delivery platform is missing its account ID or token"
                    )
            if "whatsapp" in self.meta_verified_platforms and (
                not self.meta_whatsapp_business_id
                or not self.meta_webhook_verify_token.get_secret_value()
                or not self.meta_public_origin
            ):
                raise ValueError(
                    "Live WhatsApp requires business ID and public webhook configuration"
                )
            if "instagram" in self.meta_verified_platforms and not self.meta_public_origin:
                raise ValueError("Live Instagram requires a controlled public HTTPS media origin")
        if self.today_override:
            from datetime import date

            date.fromisoformat(self.today_override)
            if self.agnes_mode == "live":
                raise ValueError(
                    "TODAY_OVERRIDE is only permitted in visibly labeled mock/demo mode"
                )
        self.agnes_base_url = self.agnes_base_url.rstrip("/")
        if self.agnes_base_url != "https://apihub.agnes-ai.com/v1":
            raise ValueError("Only the official Agnes base URL is allowed")
        if self.agnes_mode == "live" and not self.agnes_api_key.get_secret_value():
            raise ValueError("Live mode requires a server-side AGNES_API_KEY")
        if self.enable_video and not self.video_entitlement_verified:
            raise ValueError("Video requires explicit entitlement verification")
        return self
```

### backend/db.py

```python
import sqlite3
from pathlib import Path

from backend.contracts import CallRecord, Cost, TraceEvent


class Store:
    """Operational ledger and transactional campaign migrations."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA busy_timeout=5000")
        with self.connection:
            self.connection.executescript("""
                CREATE TABLE IF NOT EXISTS migrations(version INTEGER PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS api_calls(
                    id TEXT PRIMARY KEY, run_id TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS calls_run ON api_calls(run_id);
                CREATE TABLE IF NOT EXISTS trace_events(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS traces_run ON trace_events(run_id);
                INSERT OR IGNORE INTO migrations VALUES(1);
            """)
        self.migrate_campaigns()
        self.migrate_generation()
        self.migrate_art()
        self.migrate_optimization()
        if not self.connection.execute("SELECT 1 FROM migrations WHERE version=6").fetchone():
            sql = (Path(__file__).parent / "migrations/006_delivery.sql").read_text()
            try:
                self.connection.executescript(
                    "BEGIN IMMEDIATE;\n" + sql + "\nINSERT INTO migrations VALUES(6);\nCOMMIT;"
                )
            except Exception:
                self.connection.rollback()
                raise

        if not self.connection.execute("SELECT 1 FROM migrations WHERE version=7").fetchone():
            sql = (Path(__file__).parent / "migrations/007_work.sql").read_text(encoding="utf-8")
            try:
                self.connection.executescript(
                    "BEGIN IMMEDIATE;\n" + sql + "\nINSERT INTO migrations VALUES(7);\nCOMMIT;"
                )
            except Exception:
                self.connection.rollback()
                raise

        if not self.connection.execute("SELECT 1 FROM migrations WHERE version=8").fetchone():
            sql = (Path(__file__).parent / "migrations/008_meta.sql").read_text(encoding="utf-8")
            try:
                self.connection.executescript(
                    "BEGIN IMMEDIATE;\n" + sql + "\nINSERT INTO migrations VALUES(8);\nCOMMIT;"
                )
            except Exception:
                self.connection.rollback()
                raise

        for version, filename in [
            (9, "009_social_profiles.sql"),
            (10, "010_plans.sql"),
            (11, "011_merge_compat.sql"),
            (12, "012_websites.sql"),
        ]:
            if self.connection.execute(
                "SELECT 1 FROM migrations WHERE version=?", (version,)
            ).fetchone():
                continue
            sql = (Path(__file__).parent / "migrations" / filename).read_text(encoding="utf-8")
            try:
                self.connection.executescript(
                    "BEGIN IMMEDIATE;\n"
                    + sql
                    + f"\nINSERT INTO migrations VALUES({version});\nCOMMIT;"
                )
            except Exception:
                self.connection.rollback()
                raise

    def migrate_optimization(self):
        if not self.connection.execute("SELECT 1 FROM migrations WHERE version=5").fetchone():
            sql = (Path(__file__).parent / "migrations/005_optimization.sql").read_text()
            try:
                self.connection.executescript(
                    "BEGIN IMMEDIATE;\n" + sql + "\nINSERT INTO migrations VALUES(5);\nCOMMIT;"
                )
            except Exception:
                self.connection.rollback()
                raise
        from backend.optimization_repository import OptimizationRepository

        OptimizationRepository(self).recover()

    def migrate_art(self):
        if self.connection.execute("SELECT 1 FROM migrations WHERE version=4").fetchone():
            return
        sql = (Path(__file__).parent / "migrations/004_art.sql").read_text()
        try:
            self.connection.executescript(
                "BEGIN IMMEDIATE;\n" + sql + "\nINSERT INTO migrations VALUES(4);\nCOMMIT;"
            )
        except Exception:
            self.connection.rollback()
            raise

    def migrate_generation(self):
        if not self.connection.execute("SELECT 1 FROM migrations WHERE version=3").fetchone():
            sql = (Path(__file__).parent / "migrations/003_generation.sql").read_text()
            try:
                self.connection.executescript(
                    "BEGIN IMMEDIATE;\n" + sql + "\nINSERT INTO migrations VALUES(3);\nCOMMIT;"
                )
            except Exception:
                self.connection.rollback()
                raise
        # Single-worker profile. Restart never repeats an interrupted provider call.
        from backend.generation_repository import GenerationRepository

        GenerationRepository(self).recover()

    def migrate_campaigns(self):
        if self.connection.execute("SELECT 1 FROM migrations WHERE version=2").fetchone():
            return
        sql = (Path(__file__).parent / "migrations/002_campaigns.sql").read_text()
        try:
            self.connection.executescript(
                "BEGIN IMMEDIATE;\n" + sql + "\nINSERT INTO migrations VALUES(2);\nCOMMIT;"
            )
        except Exception:
            self.connection.rollback()
            raise

    def record(self, call: CallRecord):
        event = TraceEvent(
            id=0,
            trace_id=call.trace_id,
            run_id=call.run_id,
            timestamp=call.timestamp,
            event=call.status,
            message=f"{call.operation}: {call.status}",
        )
        with self.connection:
            self.connection.execute(
                "INSERT INTO api_calls VALUES(?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                (call.id, call.run_id, call.model_dump_json()),
            )
            self.connection.execute(
                "INSERT INTO trace_events(run_id,payload) VALUES(?,?)",
                (call.run_id, event.model_dump_json()),
            )

        if call.work_id and getattr(self, "work", None):
            job = self.work.get(call.work_id)
            decision = (
                "Rate limited; bounded Retry-After wait"
                if call.http_status == 429
                else f"{call.operation}: {call.status}"
            )
            self.work.event(job.campaign_id, "validation", decision, job.id)

    def calls(self) -> list[CallRecord]:
        return [
            CallRecord.model_validate_json(row[0])
            for row in self.connection.execute("SELECT payload FROM api_calls ORDER BY rowid")
        ]

    def traces(self) -> list[TraceEvent]:
        return [
            TraceEvent.model_validate_json(row[1]).model_copy(update={"id": row[0]})
            for row in self.connection.execute(
                "SELECT id,payload FROM trace_events ORDER BY id DESC LIMIT 50"
            )
        ]

    def cost(self) -> Cost:
        calls = [c for c in self.calls() if c.sent]
        live = [c for c in calls if c.mode == "live"]
        return Cost(
            calls=len(calls),
            mock_calls=sum(c.mode == "mock" for c in calls),
            known_list_price_estimate=sum(c.list_price_estimate_usd or 0 for c in live),
            unknown_cost_calls=sum(c.list_price_estimate_usd is None for c in live),
        )

    def close(self):
        self.connection.close()
```

### backend/main.py

```python
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from backend.agnes_client import AgnesClient
from backend.approval_service import ApprovalService
from backend.art_routes import router as art_router
from backend.art_service import ArtService
from backend.campaign_routes import router as campaign_router
from backend.change_service import ChangeService
from backend.config import Settings
from backend.contracts import Cost, ErrorBody, Health, TraceEvent
from backend.db import Store
from backend.delivery_routes import router as delivery_router
from backend.errors import AgnesError
from backend.future_contracts import BoundaryCatalog
from backend.generation_routes import router as generation_router
from backend.generation_service import GenerationService
from backend.guardian.routes import router as guardian_router
from backend.meta_routes import router as meta_router
from backend.meta_service import MetaService
from backend.optimization_routes import router as optimization_router
from backend.optimization_service import OptimizationService
from backend.planning import router as planning_router
from backend.social_profiles import router as social_router
from backend.video_routes import router as video_router
from backend.video_service import VideoService
from backend.website_routes import router as website_router
from backend.website_service import WebsiteError, WebsiteService
from backend.work_routes import router as work_router
from backend.work_service import WorkService


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings()
    from backend.meta_logging import install

    install()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store = Store(config.database_path)
        client = AgnesClient(config, store)
        app.state.store, app.state.client = store, client
        app.state.settings = config
        app.state.generation = GenerationService(store, client)
        app.state.art = ArtService(store, client, config)
        app.state.optimization = OptimizationService(store, client)
        app.state.changes = ChangeService(store, client)
        app.state.approvals = ApprovalService(store, client, app.state.optimization)
        app.state.work = WorkService(app)
        store.work = app.state.work
        app.state.meta = MetaService(app)
        app.state.video = VideoService(app)
        app.state.website = WebsiteService(store, config)
        try:
            yield
        finally:
            await app.state.website.close()
            await app.state.work.close()
            await app.state.meta.close()
            await app.state.video.close()
            await app.state.generation.close()
            await app.state.optimization.close()
            await client.close()
            store.close()

    app = FastAPI(
        title="Intent-Locked Campaigns",
        version="0.1.0",
        lifespan=lifespan,
        openapi_url="/api/openapi.json",
        docs_url="/api/docs",
        redoc_url=None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[config.frontend_origin, "https://127.0.0.1:3000", "https://localhost:3000"],
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", "X-Owner-Delivery-Token"],
    )

    def error(code, message, status=400, trace_id=None, retryable=False, details=None):
        return JSONResponse(
            status_code=status,
            content=ErrorBody(
                code=code,
                message=message,
                trace_id=trace_id or uuid4().hex,
                retryable=retryable,
                details=details or {},
            ).model_dump(),
        )

    @app.middleware("http")
    async def local_host_boundary(request: Request, call_next):
        from urllib.parse import urlparse

        # Only the signed webhook and opaque media grants may use the explicitly
        # configured public origin. Owner/work/export routes remain local-only.
        public_meta = (
            bool(config.meta_public_origin)
            and config.meta_enabled
            and request.url.scheme == "https"
            and request.url.hostname == urlparse(config.meta_public_origin).hostname
            and (
                request.url.path == "/api/meta/webhook"
                or request.url.path.startswith("/api/meta/media/")
            )
        )
        if request.url.hostname not in {"127.0.0.1", "localhost", "testserver"} and not public_meta:
            return error("HOST_REJECTED", "Only local hosts are allowed", 400)
        website = request.url.path.startswith(("/api/website/", "/api/websites/"))
        if website:
            secret_route = request.url.path.endswith(("/connection", "/publish")) or (
                request.url.path == "/api/website/token" and request.method == "DELETE"
            )
            if secret_route and request.url.scheme != "https":
                return error(
                    "HTTPS_REQUIRED",
                    "Publishing credentials require HTTPS; download zip instead",
                    403,
                )
            origin = request.headers.get("origin")
            allowed = {config.frontend_origin, "https://127.0.0.1:3000", "https://localhost:3000"}
            if origin and origin not in allowed:
                return error("ORIGIN_REJECTED", "Website request origin rejected", 403)
            if request.method in {"POST", "PUT"}:
                # Bound uploads and bodies before DTO validation or secret processing.
                try:
                    declared = int(request.headers.get("content-length", "0"))
                except ValueError:
                    return error("BODY_INVALID", "Invalid request size", 400)
                if declared > 7_100_000:
                    return error("BODY_TOO_LARGE", "Website request is too large", 413)
                received = bytearray()
                async for chunk in request.stream():
                    received.extend(chunk)
                    if len(received) > 7_100_000:
                        return error("BODY_TOO_LARGE", "Website request is too large", 413)
                request._body = bytes(received)
        return await call_next(request)

    @app.exception_handler(WebsiteError)
    async def website_error(_: Request, exc: WebsiteError):
        return error(exc.code, exc.message, exc.status)

    @app.exception_handler(Exception)
    async def unexpected_error(_: Request, exc: Exception):
        return error("INTERNAL_ERROR", "An internal operation failed", 500)

    @app.exception_handler(AgnesError)
    async def agnes_error(_: Request, exc: AgnesError):
        conflicts = {
            "REVISION_CONFLICT",
            "FACTS_LOCKED",
            "IDEMPOTENCY_CONFLICT",
            "GENERATION_BUSY",
            "OPTIMIZATION_BUSY",
            "WORK_QUEUE_FULL",
            "META_DEADLINE",
        }
        invalid = {
            "FACTS_INCOMPLETE",
            "REVIEW_REQUIRED",
            "FORMS_INVALID",
            "FORMS_NOT_READY",
            "DATE_DAY_CONFLICT",
            "DUPLICATE_FACT",
            "DUPLICATE_SELECTION",
            "GUARDIAN_SELECTION",
            "GENERATION_SELECTION",
            "ELIGIBILITY_UNRESOLVED",
            "ELIGIBILITY_CONFLICT",
            "STRATEGY_NEEDS_INPUT",
            "ART_INVALID",
            "ART_BLOCKED",
            "TEXT_OVERFLOW",
            "GRAPHEME_OVERFLOW",
            "APPROVAL_PENDING",
            "OPTIMIZATION_SELECTION",
            "EDIT_REJECTED",
            "CHANGE_INVALID",
            "APPROVAL_INVALID",
            "EXPORT_UNAUTHORIZED",
            "WORK_INVALID",
            "RETRY_UNSAFE",
            "META_INVALID",
            "META_MEDIA",
            "META_CONSENT",
            "META_TEMPLATE",
            "META_WINDOW",
            "META_CONFIGURATION",
            "META_CONTAINER",
        }
        status = (
            403
            if exc.body.code
            in {"META_OWNER_REQUIRED", "META_SIGNATURE", "META_DISABLED", "META_NOT_VERIFIED"}
            else 409
            if exc.body.code in conflicts
            else 422
            if exc.body.code in invalid
            else 404
            if exc.body.code
            in {
                "CAMPAIGN_NOT_FOUND",
                "GENERATION_NOT_FOUND",
                "ASSET_NOT_FOUND",
                "OPTIMIZATION_NOT_FOUND",
                "DELIVERY_NOT_FOUND",
                "WORK_NOT_FOUND",
                "SAVED_OUTPUT_MISSING",
                "META_NOT_FOUND",
            }
            else 502
        )
        return JSONResponse(status_code=status, content=exc.body.model_dump())

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        # Locations/types only: do not reflect untrusted values or validator context.
        fields = [
            ".".join(map(str, item["loc"])) + ": " + item["type"] for item in exc.errors()[:20]
        ]
        return error(
            "VALIDATION_ERROR",
            "Request does not match the API schema",
            422,
            details={"fields": fields},
        )

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException):
        return error(
            "NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR",
            "Route unavailable" if exc.status_code == 404 else "Request rejected",
            exc.status_code,
        )

    @app.get("/api/health", response_model=Health)
    async def health():
        return Health(
            mode={"mock": "MOCK", "live": "LIVE", "cached": "SAVED DEMO OUTPUT"}[config.agnes_mode],
            video_enabled=config.enable_video,
        )

    @app.get("/api/ready", response_model=Health, responses={503: {"model": ErrorBody}})
    async def ready(request: Request):
        try:
            request.app.state.store.connection.execute("SELECT 1").fetchone()
        except Exception:
            return error("STORAGE_UNAVAILABLE", "Storage is not ready", 503, retryable=True)
        return await health()

    @app.get("/api/cost", response_model=Cost)
    async def cost(request: Request):
        return request.app.state.store.cost()

    @app.get("/api/traces", response_model=list[TraceEvent])
    async def traces(request: Request):
        return request.app.state.store.traces()

    app.include_router(campaign_router)
    app.include_router(guardian_router)
    app.include_router(generation_router)
    app.include_router(art_router)
    app.include_router(optimization_router)
    app.include_router(delivery_router)
    app.include_router(work_router)
    app.include_router(meta_router)
    app.include_router(social_router)
    app.include_router(planning_router)
    app.include_router(video_router)
    app.include_router(website_router)
    original_openapi = app.openapi

    def contract_openapi():
        schema = original_openapi()
        definitions = BoundaryCatalog.model_json_schema(
            ref_template="#/components/schemas/{model}"
        )["$defs"]
        for name, definition in definitions.items():
            schema["components"]["schemas"].setdefault(name, definition)
        schema["info"]["x-reserved-boundaries"] = (
            "B8 release DTOs remain reserved; B1-B7 campaign workflows implemented"
        )
        return schema

    app.openapi = contract_openapi
    return app


app = create_app()
```

### backend/art_context.py

```python
"""Safe visual input projection and versioned art/font/layout dependencies."""

import json
from pathlib import Path

from backend.art_storage import sha
from backend.errors import AgnesError
from backend.intent_rules import digest

ROOT = Path(__file__).resolve().parents[1]

PUBLIC = ROOT / "frontend/public"

RENDERER_VERSION = "canvas-commercial-b1.0"

LAYOUT = {
    "version": "layout-commercial-b1.0",
    "copy": "poster-editorial-b1.0",
    "text_plate": "espresso_gold_campaign",
    "scrim": "#20150F",
    "text": "#FFF4DF",
    "min_contrast": 7,
    "square_margin": 64,
    "story_top": 200,
    "story_bottom": 240,
    "landscape_margin": 48,
    "min_font": {"feed": 26, "square": 26, "story": 30, "landscape": 24},
}


def font_manifest():
    try:
        manifest = json.loads((PUBLIC / "fonts/manifest.json").read_text())

        for item in manifest["files"]:
            if sha((PUBLIC / "fonts" / item["file"]).read_bytes()) != item["sha256"]:
                raise ValueError

        return digest(manifest)

    except (OSError, ValueError, KeyError):
        raise AgnesError(
            "FONT_UNAVAILABLE", "Bundled font or license is missing or altered"
        ) from None


def art_brief(campaign, ratio):
    # Project only a supported visual category, never brand/offer/date/venue literals.

    product = next((f.canonical for f in campaign.facts if f.key == "PRODUCT"), None)

    coffee = bool(
        product
        and product.kind == "text"
        and product.value.casefold().strip()
        in {
            "coffee",
            "ಕಾಫಿ",
            "kaapi",
            "kaafi",
            "kapi",
        }
    )

    return {
        "visual_subject": (
            "one unbranded ceramic coffee mug, visible coffee and subtle steam; "
            "photorealistic commercial beverage photography, rich reflections and depth; "
            "no extra food, gifts or unsupported menu items"
            if coffee
            else "warm amber studio lighting, rich espresso textures and "
            "abstract decorative shadows; no products"
        ),
        "palette": campaign.brand.colors or ["#20150F", "#FBC844", "#FFF4DF", "#A56A39"],
        "theme": {
            "1:1": "premium café advertising photograph with cinematic warm amber light",
            "9:16": "vertical café advertising photograph with dramatic depth and warm light",
            "16:9": "wide café advertising still life with cinematic directional light",
        }[ratio],
        "composition": "large coffee hero in the lower-right central region; "
        "anonymous dark studio backdrop, subtle amber bokeh and a plain wood-textured "
        "studio surface; keep the entire cup inside the central 70 percent; "
        "no paper-cut waves, collage, flat vector cartoon or blank gradient",
        "aspect_ratio": ratio,
        "text_safe_region": "dark upper and left negative space for code-rendered typography; "
        "a protected hero window keeps the coffee visible",
        "allowed_product_illustration": coffee,
        "visual_version": "commercial-cafe-b1.0",
    }


def art_key(campaign, ratio, source):
    return digest(
        {
            "brief": art_brief(campaign, ratio),
            "source": source,
            "mode": campaign.mode,
            "t1": sha((ROOT / "backend/prompts/T1.txt").read_bytes()),
            "qa": sha((ROOT / "backend/prompts/R9.md").read_bytes()),
        }
    )


def image_prompt(brief):
    return (
        (ROOT / "backend/prompts/T1.txt")
        .read_text(encoding="utf-8")
        .format(**{**brief, "palette": ", ".join(brief["palette"])})
    )


def renderer_hash():
    return sha((PUBLIC / "renderer/canvas.js").read_bytes())
```

### frontend/components/CampaignFlow.tsx

```tsx
"use client";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { campaignApi, type Campaign, type Canonical, type Channel, type DraftRequest, type Fact, type Lang, type LockRequest } from "@/lib/campaign-api";
import { FactEditor, factNames } from "./FactEditor";
import { Readback, VoiceInput } from "./VoiceInput";
import GuardianPanel from "./GuardianPanel";
import CampaignMatrix from "./CampaignMatrix";
import WebsiteWizard from "./WebsiteWizard";
import DeliveryPanel from "./DeliveryPanel";
import WorkflowStatus from "./WorkflowStatus";
import BrandDraftEditor from "./BrandDraftEditor";
import {workRead} from "@/lib/work-api";
import { Stage, useWorkspace } from "./workspace/WorkspaceShell";
import { Button, CopyButton, Dialog, Tabs, ToggleChip } from "./ui";
import { ArrowRight, AudioLines, FileCheck2, LockKeyhole, ShieldCheck } from "lucide-react";

const example = "Café name: Namma Cafe. Bengaluru. 20 percent off coffee this weekend for students.";
const languages: [Lang, string][] = [["en", "English"], ["kn", "Kannada"], ["kn-Latn", "Kanglish"]];
const channels: Channel[] = ["whatsapp", "instagram", "facebook", "poster"];
type FactMap = Partial<Record<Fact["key"], Canonical | null>>;

export default function CampaignFlow({ inferenceDisabled = false }: { inferenceDisabled?: boolean }) {
  const [campaign, setCampaign] = useState<Campaign | null>(null);
  const [transcript, setTranscript] = useState("");
  const [selectedLanguages, setLanguages] = useState<Lang[]>(["en"]);
  const [selectedChannels, setChannels] = useState<Channel[]>(["whatsapp"]);
  const [facts, setFacts] = useState<FactMap>({});
  const [target, setTarget] = useState("");
  const [tone, setTone] = useState("");
  const [brandDraft,setBrandDraft]=useState<Campaign["brand"]>({tone:"",theme:"",colors:[],must_say:[],must_not_say:[]});
  const [forms, setForms] = useState<LockRequest["forms"]>([]);
  const [acks, setAcks] = useState<string[]>([]);
  const [canonicalConfirmed, setCanonicalConfirmed] = useState(false);
  const [formsConfirmed, setFormsConfirmed] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [saved, setSaved] = useState(false);
  const lockKey = useRef("");
  const workspace = useWorkspace();
  const {setCampaign: publishCampaign, navigate, started, start, traceOpen, setTraceOpen, traces} = workspace;
  const [formLanguage, setFormLanguage] = useState<Lang>("en");
  const [factTab, setFactTab] = useState<"canonical" | "forms">("canonical");
  const [savedId, setSavedId] = useState("");
  const [advance, setAdvance] = useState<"facts-lock" | "brand-strategy" | null>(null);
  useEffect(() => { publishCampaign(campaign); }, [campaign, publishCampaign]);
  useEffect(() => { if (advance && workspace.campaign?.revision === campaign?.revision && workspace.campaign?.id === campaign?.id) { const timer = window.setTimeout(() => { navigate(advance); setAdvance(null); }, 0); return () => window.clearTimeout(timer); } }, [advance, campaign, workspace.campaign, navigate]);
  const receive = useCallback((next: Campaign) => {
    setCampaign(next); setTranscript(next.transcript); setLanguages(next.languages); setChannels(next.channels);
    setFacts(Object.fromEntries(next.facts.map((fact) => [fact.key, fact.canonical])));
    setTarget(next.target_audiences.join(", ")); setTone(next.brand.tone ?? ""); setBrandDraft(next.brand);
    setForms(next.facts.filter((fact) => fact.canonical).map((fact) => ({ key: fact.key, surface: fact.surface ?? {} })));
    setAcks(next.acknowledged_warning_ids); setDirty(false); setCanonicalConfirmed(false); setFormsConfirmed(false);
    localStorage.setItem("intent-locked-campaign", next.id);
    const url = new URL(window.location.href); url.searchParams.set("campaign", next.id); window.history.replaceState({}, "", url);
    lockKey.current = crypto.randomUUID();
  }, []);
  useEffect(() => {
    const id = new URL(window.location.href).searchParams.get("campaign") ?? localStorage.getItem("intent-locked-campaign");
    if (id) void campaignApi(`/${encodeURIComponent(id)}`).then(receive).catch(() => setError("Could not load the saved campaign. Retry loading or start a new draft."));
  }, [receive]);
  const locked = campaign?.status === "locked";
  const reviewBusy=!!busy || saved || inferenceDisabled;
  const transcriptChanged = !!campaign && transcript !== campaign.transcript;
  const latestReview = useRef({campaign, dirty, transcriptChanged, busy, saved});
  useLayoutEffect(() => { latestReview.current = {campaign, dirty, transcriptChanged, busy, saved}; }, [campaign, dirty, transcriptChanged, busy, saved]);
  useEffect(() => {
    const update = (raw: Event) => {
      const detail = (raw as CustomEvent).detail;
      if (!campaign || (detail?.source !== "poll" && detail?.event?.event !== "completed")) return;
      void campaignApi(`/${campaign.id}`).then(next => {
        const current = latestReview.current;
        if (current.saved || !current.campaign || next.id !== current.campaign.id || next.revision <= current.campaign.revision) return;
        if (current.dirty || current.transcriptChanged || current.busy) setMessage("Saved campaign changed. Your edits stay on screen; reload and review the current revision before continuing.");
        else receive(next);
      }).catch(() => { /* connection recovery is shown by Work and recovery */ });
    };
    window.addEventListener("workflow-update", update);
    return () => window.removeEventListener("workflow-update", update);
  }, [campaign, receive]);
  const changed = () => { setDirty(true); setCanonicalConfirmed(false); setFormsConfirmed(false); };
  const perform = async (label: string, action: () => Promise<Campaign>) => {
    setBusy(label); setError(""); setMessage("");
    try { const next = await action(); receive(next); if (label === "Proposing facts") setAdvance("facts-lock"); if (label === "Proposing localized forms") setFactTab("forms"); if (label === "Locking facts") setAdvance("brand-strategy"); setMessage(label === "Locking facts" ? "Facts and reviewed forms are locked together." : "Saved. Review the next step below."); }
    catch (failure) { setError(failure instanceof Error ? failure.message : "Request failed. Reload the saved draft before retrying."); }
    finally { setBusy(""); }
  };
  const draftBody = (current: Campaign): DraftRequest => ({
    expected_revision: current.revision,
    facts: current.facts.filter((fact) => fact.key !== "DAYS").map((fact) => ({ key: fact.key, canonical: facts[fact.key] ?? null })),
    languages: selectedLanguages, channels: selectedChannels,
    target_audiences: target.split(",").map((value) => value.trim()).filter(Boolean),
    brand: { ...brandDraft, tone }, acknowledged_warning_ids: acks,
  });
  const analyze = () => perform("Proposing facts", async () => {
    let current = campaign;
    if (!current) {
      current = await campaignApi("", "POST", { languages: selectedLanguages, channels: selectedChannels });
      // Keep the server-created id even if provider extraction fails.
      setCampaign(current); localStorage.setItem("intent-locked-campaign", current.id);
      const url = new URL(window.location.href); url.searchParams.set("campaign", current.id); window.history.replaceState({}, "", url);
    } else if (dirty) {
      current = await campaignApi(`/${current.id}/facts/draft`, "PUT", draftBody(current));
      setCampaign(current);
    }
    return campaignApi(`/${current.id}/intent`, "POST", { expected_revision: current.revision, transcript });
  });
  const save = () => campaign && perform("Saving draft", () => campaignApi(`/${campaign.id}/facts/draft`, "PUT", draftBody(campaign)));
  const newDraft = () => {
    setCampaign(null); setFactTab("canonical"); setFormLanguage("en"); setBrandDraft({tone:"",theme:"",colors:[],must_say:[],must_not_say:[]}); setTranscript(""); setFacts({}); setForms([]); setTarget(""); setTone(""); setAcks([]);
    setDirty(false); setCanonicalConfirmed(false); setFormsConfirmed(false); setError(""); setMessage("");
    localStorage.removeItem("intent-locked-campaign"); const url = new URL(window.location.href); url.searchParams.delete("campaign"); window.history.replaceState({}, "", url);
  };
  useEffect(() => {
    const reset = () => { if (busy || saved || inferenceDisabled) return; newDraft(); };
    window.addEventListener("workspace-new", reset);
    return () => window.removeEventListener("workspace-new", reset);
  });
  const canonicalText = campaign?.facts.filter((f) => f.canonical).map((f) => `${factNames[f.key]}: ${Object.entries(f.canonical!).filter(([key]) => !["kind", "original_phrase", "timezone"].includes(key)).map(([, value]) => Array.isArray(value) ? value.join(", ") : String(value)).join(" ")}`).join(". ") ?? "";
  const readyToPropose = campaign && !locked && !dirty && !transcriptChanged && canonicalConfirmed;
  return <section aria-label="Campaign workspace" className="space-y-6">
    {campaign && <WebsiteWizard key={campaign.id} campaignId={campaign.id} readOnly={saved || inferenceDisabled} />}
    {!campaign && !started && <>
      <div className="welcome-hero"><div><p className="eyebrow">THE OWNER-CONTROLLED CAMPAIGN WORKSPACE</p><h1>A campaign that<br/>keeps its word.</h1><p className="subtitle">Human controls truth. AI controls execution. Code enforces the boundary.</p><div className="welcome-actions"><Button onClick={start}>Start a campaign<ArrowRight size={17}/></Button><Button variant="secondary" onClick={()=>setTraceOpen(true)}>Load saved demo</Button></div><p className="hint mt-5">Speak in English, Kannada or Kanglish. Your approval makes the facts final.</p></div><div className="welcome-proof"><p className="eyebrow">A CLEAR BOUNDARY, AT EVERY STEP</p><h2>Creative freedom.<br/>Business truth.</h2><div className="proof-row"><span>Owner reviews the facts</span><LockKeyhole size={20}/></div><div className="proof-row"><span>Code checks every claim</span><ShieldCheck size={20}/></div><div className="proof-row"><span>You authorize the final export</span><FileCheck2 size={20}/></div><small>Real outputs, visible provenance, no silent approvals.</small></div></div>
      <div className="how-row">{[[AudioLines,"Speak your idea","An editable brief in your own words."],[LockKeyhole,"Lock the facts","Confirm names, numbers and conditions."],[FileCheck2,"Approve the campaign","Review the exact content before export."]].map(([Icon,title,text])=>{const Symbol=Icon as typeof AudioLines;return <div key={String(title)}><span className="how-icon"><Symbol size={20}/></span><div><strong>{String(title)}</strong><p>{String(text)}</p></div></div>;})}</div>
    </>}
    <Dialog drawer keepMounted open={traceOpen} onClose={()=>setTraceOpen(false)} title="Trace & saved work">
      {workspace.connection}
      {campaign ? <WorkflowStatus campaign={campaign.id} saved={saved} onSaved={value => { setSaved(value); if (!value) void campaignApi(`/${campaign.id}`).then(receive).catch(() => setError("Cannot reload the current workspace. Retry loading saved progress.")); window.dispatchEvent(new CustomEvent("workspace-mode", { detail: { saved: value } })); }} /> : <div className="space-y-4"><p>Load a persisted campaign by its ID. Saved output is explicitly labeled SAVED DEMO OUTPUT; no fixtures are silently substituted.</p>{error && <p role="alert" className="callout danger">{error}</p>}<label>Saved campaign ID<input className="field" value={savedId} onChange={e=>setSavedId(e.target.value)}/></label><Button disabled={!savedId.trim()} onClick={()=>void campaignApi(`/${encodeURIComponent(savedId.trim())}`).then(async next=>{await workRead(`/api/campaigns/${next.id}/saved-output`);receive(next);setSaved(true);window.dispatchEvent(new CustomEvent("workspace-mode",{detail:{saved:true}}));setTraceOpen(false);setAdvance("facts-lock");}).catch(()=>setError("No captured saved output is available for that campaign. Check the ID and backend connection."))}>Load SAVED DEMO OUTPUT</Button></div>}
      <details><summary>Global activity trace</summary><ol className="space-y-3">{traces.map(t=><li key={t.id} className="text-xs">#{t.id} · {t.message}</li>)}</ol></details>
    </Dialog>

    {inferenceDisabled && <p className="mode-banner">SAVED DEMO OUTPUT · Server inference is disabled. Saved facts and files remain readable.</p>}
    <fieldset hidden={!started && !campaign} data-saved={saved || inferenceDisabled} className="min-w-0 space-y-6"><legend className="sr-only">{saved || inferenceDisabled ? "Cached output. Inference and approvals disabled in this view." : "Current campaign workspace"}</legend>

    {campaign && <div className="fact-lock-banner text-sm" aria-live="polite"><strong><LockKeyhole size={16}/>{locked ? "Locked by owner" : campaign.status === "forms_review" ? "Forms awaiting owner approval" : "Editable draft"}</strong> · Revision {campaign.revision} · {campaign.mode.toUpperCase()}<p className="mt-1">Date reference: {campaign.reference_date} · {campaign.timezone}{campaign.demo_clock ? " · Explicit demo clock" : " · Server clock"}</p>{locked && <div className="hash-row mt-2"><span className="hint">Approved {campaign.approved_at}</span><code className="hash-chip" title={campaign.fact_hash ?? ""}>Fact hash {campaign.fact_hash}</code><CopyButton value={campaign.fact_hash ?? ""} label="Copy hash"/><details><summary>Full hash</summary><code className="break-all text-xs">{campaign.fact_hash}</code></details></div>}</div>}
    {error && <div role="alert" className="callout danger toast-error"><p>{error}</p><p className="mt-2 text-sm">Your edits remain on screen. Reload discards unsaved edits and fetches the current revision.</p></div>}
    {campaign && <button className="text-sm underline" disabled={reviewBusy} onClick={() => perform("Reloading", () => campaignApi(`/${campaign.id}`))}>Reload saved draft</button>}
    {(busy || message) && <p role="status" className="text-sm">{busy ? `${busy}…` : message}</p>}
    <Stage id="speak-type"><fieldset disabled={saved || inferenceDisabled}><div id="speak-type" className="card space-y-5">
      <h2 className="text-xl font-semibold">Speak or type, then review</h2>
      <VoiceInput value={transcript} disabled={reviewBusy || !!locked} onChange={(value) => { setTranscript(value); setCanonicalConfirmed(false); setFormsConfirmed(false); }} />
      {!locked && <button className="text-sm underline" disabled={reviewBusy} onClick={() => setTranscript(example)}>Load a labeled example brief</button>}
      <p className="text-xs text-[#576353]">The example explicitly supplies “Namma Cafe”. Empty drafts never assume a café identity. “This weekend” uses the date reference shown above after extraction.</p>
      <fieldset disabled={reviewBusy || !!locked} className="flex flex-wrap gap-5"><legend className="mb-2 font-semibold">Languages to review</legend>{languages.map(([lang, name]) => <ToggleChip key={lang} selected={selectedLanguages.includes(lang)} onClick={()=>{setLanguages(selectedLanguages.includes(lang) ? selectedLanguages.filter(l=>l!==lang) : [...selectedLanguages,lang]);changed();}}>{name}</ToggleChip>)}</fieldset>
      <fieldset disabled={reviewBusy || !!locked} className="flex flex-wrap gap-5"><legend className="mb-2 font-semibold">Future campaign channels</legend>{channels.map((channel) => <ToggleChip key={channel} selected={selectedChannels.includes(channel)} onClick={()=>{setChannels(selectedChannels.includes(channel) ? selectedChannels.filter(c=>c!==channel) : [...selectedChannels,channel]);changed();}}>{channel}</ToggleChip>)}</fieldset>
      {!locked && <><button className="primary" disabled={reviewBusy || !transcript.trim() || !selectedLanguages.length || !selectedChannels.length} onClick={analyze}>{campaign?.transcript ? "Re-propose facts from transcript" : "Propose facts from transcript"}</button><p className="text-xs">Proposing again replaces current fact proposals. Nothing in a transcript can approve or lock this campaign.</p></>}
      {transcriptChanged && <p className="text-sm font-semibold">Transcript edited. Re-propose facts, or reload to discard these transcript edits, before approving facts.</p>}
    </div>
    </fieldset></Stage><Stage id="facts-lock"><div>
    {campaign && <div className="mb-5"><Tabs label="Fact review section" value={factTab} onChange={setFactTab} options={[{value:"canonical",label:"Canonical facts"},{value:"forms",label:"Approved wording"}]}/></div>}
    {!campaign && <div id="facts-lock" className="card"><h2 className="font-semibold">◷ Facts Lock · waiting for your brief</h2><p>Propose facts above, then review their numbers, dates and localized forms.</p></div>}
      {campaign && campaign.warnings.length > 0 && <fieldset disabled={reviewBusy || !!locked} className="space-y-3 rounded-xl bg-[#f4ead7] p-4"><legend className="font-semibold">Review notes</legend>{campaign.warnings.map((warning) => <label key={warning.id} className="flex items-start gap-3 text-sm"><input className="mt-1" type="checkbox" checked={acks.includes(warning.id)} onChange={(e) => { setAcks(e.target.checked ? [...acks, warning.id] : acks.filter((id) => id !== warning.id)); setFormsConfirmed(false); }} /><span>{warning.message}</span></label>)}</fieldset>}
    {campaign && <div hidden={factTab!=="canonical"} id="facts-lock" className="card space-y-5">
      <div><p className="eyebrow">02 / Canonical facts</p><h2 className="mt-2 text-xl font-semibold">Resolve the details</h2><p className="mt-2 text-sm">Café name, location, product, offer, and dates are required. Unspecified conditions remain unknown.</p></div>
      {!locked && campaign.clarifications.length > 0 && <div className="rounded-xl bg-[#f4ead7] p-4"><h3 className="font-semibold">Clarifications</h3><ul className="mt-2 list-disc space-y-2 pl-5">{campaign.clarifications.map((question) => <li key={question.key} className="rounded-xl bg-white/70 p-4"><strong>{question.required ? "Required · needs your answer" : "Optional"}:</strong> {question.question}{question.key==="ELIGIBILITY" && <div className="mt-3 flex flex-wrap gap-2">{(["all","students"] as const).map(scope=><ToggleChip key={scope} disabled={reviewBusy} selected={facts.ELIGIBILITY?.kind==="eligibility" && facts.ELIGIBILITY.scope===scope} onClick={()=>{setFacts({...facts,ELIGIBILITY:{kind:"eligibility",scope,description:""}});changed();}}>{scope==="all" ? "Open to all" : "Students only"}</ToggleChip>)}</div>}{question.key==="ID_RULE" && <div className="mt-3 flex flex-wrap gap-2">{[true,false].map(required=><ToggleChip key={String(required)} disabled={reviewBusy} selected={facts.ID_RULE?.kind==="id_rule" && facts.ID_RULE.required===required} onClick={()=>{setFacts({...facts,ID_RULE:{kind:"id_rule",required}});changed();}}>{required ? "ID required" : "No ID required"}</ToggleChip>)}</div>}</li>)}</ul><p className="mt-3 text-sm">Answer in the matching fields below and save the draft.</p></div>}
      {!locked && !!campaign.agent_questions?.length && <ul className="list-disc pl-5">{campaign.agent_questions.map((q, i) => <li key={i}>{q}</li>)}</ul>}
      <fieldset disabled={reviewBusy || !!locked} className="grid gap-4 sm:grid-cols-2"><label>Target audiences (comma separated)<input className="field mt-2" value={target} onChange={(e) => { setTarget(e.target.value); changed(); }} /></label><label>Brand tone<input className="field mt-2" value={tone} onChange={(e) => { setTone(e.target.value); changed(); }} /></label></fieldset>
      <fieldset disabled={reviewBusy || !!locked}><BrandDraftEditor value={brandDraft} onChange={value=>{setBrandDraft(value);changed();}}/></fieldset>
      <div className="fact-grid">{campaign.facts.filter(f=>["CAFE","LOCATION","OFFER","PRODUCT","DAYS","DATES"].includes(f.key)).map((fact) => <FactEditor key={fact.key} fact={fact} value={facts[fact.key] ?? null} disabled={reviewBusy || !!locked} onChange={(value) => { setFacts({ ...facts, [fact.key]: value }); changed(); }} />)}</div>
      <h3 className="conditions-heading">Conditions <span className="hint font-normal">— unspecified stays unspecified</span></h3>
      <div className="fact-grid">{campaign.facts.filter(f=>!["CAFE","LOCATION","OFFER","PRODUCT","DAYS","DATES"].includes(f.key)).map(fact=><FactEditor key={fact.key} fact={fact} value={facts[fact.key] ?? null} disabled={reviewBusy || !!locked} onChange={value=>{setFacts({...facts,[fact.key]:value});changed();}}/>)}</div>
      <Readback text={canonicalText} />
      {!locked && <><div className="flex flex-wrap gap-3"><button className="secondary" disabled={reviewBusy || transcriptChanged} onClick={save}>Save editable facts</button>{dirty && <p className="self-center text-sm">Unsaved fact edits. Corresponding forms will be invalidated.</p>}</div><label className="flex items-start gap-3"><input type="checkbox" className="mt-1" checked={canonicalConfirmed} disabled={reviewBusy || dirty || transcriptChanged} onChange={(e) => setCanonicalConfirmed(e.target.checked)} /><span>I confirm the saved canonical facts, including names, numbers and dates.</span></label><button className="primary" disabled={reviewBusy || !readyToPropose} onClick={() => perform("Proposing localized forms", () => campaignApi(`/${campaign.id}/facts/surface`, "POST", { expected_revision: campaign.revision, confirm_canonical: true }))}>Propose localized forms</button></>}
    </div>}
    {campaign && factTab==="forms" && campaign.status!=="forms_review" && !locked && <p className="callout warning">Save and confirm canonical facts, then propose localized forms to review the wording.</p>}
    {campaign && (campaign.status === "forms_review" || locked) && <div hidden={factTab!=="forms"} className="card space-y-5">
      <div><p className="eyebrow">02 / Localized-form review</p><h2 className="mt-2 text-xl font-semibold">Approve the words that carry the facts</h2><p className="mt-2 text-sm">Review each language and case form. Separate alternatives with |. Kannada native review has not been performed. Mock forms are development fixtures.</p></div>
      <Tabs label="Surface-form language" options={selectedLanguages.map(value=>({value,label:languages.find(([id])=>id===value)?.[1] ?? value}))} value={selectedLanguages.includes(formLanguage) ? formLanguage : selectedLanguages[0]} onChange={setFormLanguage}/>
      <div className="grid gap-4 md:grid-cols-2">{forms.map((entry, index) => <fieldset key={entry.key} disabled={reviewBusy || !!locked || dirty || transcriptChanged} className="min-w-0 rounded-xl border border-[#d3d8cd] p-4"><legend className="font-semibold">{factNames[entry.key]}</legend>{selectedLanguages.map((lang) => <div key={lang} hidden={lang !== (selectedLanguages.includes(formLanguage) ? formLanguage : selectedLanguages[0])} className="mt-3 space-y-2"><p className="font-semibold">{languages.find(([id]) => id === lang)?.[1]}</p>{(["nom", "dat", "gen", "loc"] as const).filter((grammaticalCase) => grammaticalCase === "nom" || !!entry.surface[lang]?.[grammaticalCase]).map((grammaticalCase) => <label key={grammaticalCase} className="block text-xs">{grammaticalCase}<input lang={lang} className="field mt-1 text-base" aria-label={`${entry.key} ${lang} ${grammaticalCase}`} value={entry.surface[lang]?.[grammaticalCase]?.join(" | ") ?? ""} onChange={(e) => { setForms(forms.map((form, i) => i !== index ? form : { ...form, surface: { ...form.surface, [lang]: { ...form.surface[lang]!, [grammaticalCase]: e.target.value.split("|").map((v) => v.trim()) } } })); setFormsConfirmed(false); }} /></label>)}</div>)}</fieldset>)}</div>
      {selectedLanguages.includes("kn") && <Readback language="kn-IN" text={forms.map((form) => form.surface.kn?.nom.join(", ")).filter(Boolean).join(". ")} />}
      {!locked && <><label className="flex items-start gap-3"><input type="checkbox" className="mt-1" checked={formsConfirmed} disabled={reviewBusy || dirty || transcriptChanged} onChange={(e) => setFormsConfirmed(e.target.checked)} /><span>I approve these canonical facts and all displayed localized forms. Lock this exact revision.</span></label><button className="primary" disabled={reviewBusy || dirty || transcriptChanged || !formsConfirmed} onClick={() => perform("Locking facts", () => campaignApi(`/${campaign.id}/facts/lock`, "POST", { expected_revision: campaign.revision, idempotency_key: lockKey.current, reviewed_fact_versions: Object.fromEntries(campaign.facts.map((fact) => [fact.key, fact.version])), forms, approve_canonical_and_forms: true, acknowledged_warning_ids: acks } satisfies LockRequest))}>Lock approved facts</button><p className="text-xs">A lock stores all facts, forms, versions, and approval together. Locking enables strategy and generation below.</p></>}
    </div>}
    </div></Stage>
    {campaign && locked && <CampaignMatrix key={`matrix:${campaign.id}:${campaign.revision}`} campaign={campaign} readOnly={saved || inferenceDisabled} />}
    {campaign && locked && <Stage id="guardian"><GuardianPanel key={`${campaign.id}:${campaign.revision}`} campaign={campaign} /></Stage>}
    {campaign && locked && <DeliveryPanel key={`delivery-${campaign.id}-${campaign.revision}`} campaign={campaign} onPublished={receive} saved={saved || inferenceDisabled} />}

    </fieldset>
  </section>;
}
```

### frontend/next.config.ts

```typescript
import type { NextConfig } from "next";
const config: NextConfig = {
  async rewrites() {
    const backend = process.env.BACKEND_ORIGIN ?? "http://127.0.0.1:8000";
    if (!/^https?:\/\/(127\.0\.0\.1|localhost):8000$/.test(backend)) throw new Error("Invalid private backend origin");
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};
export default config;
```

### pyproject.toml

```toml
[project]
name = "intent-locked-campaigns"
version = "0.1.0"
requires-python = ">=3.11,<3.12"
dependencies = [
  "fastapi==0.115.12",
  "pydantic==2.11.4",
  "pydantic-settings==2.9.1",
  "httpx==0.28.1",
  "uvicorn==0.34.2",
  "pillow==11.2.1",
  "cryptography==46.0.3",
]

[dependency-groups]
dev = ["pytest==8.3.5", "pytest-asyncio==0.26.0", "pytest-cov==6.1.1", "ruff==0.11.9"]

[tool.pytest.ini_options]
testpaths = ["backend/tests"]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
pythonpath = ["."]

[tool.ruff]
target-version = "py311"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "ASYNC"]
```

## 6. Test code

Tests cover all requested items. Netlify operations are explicitly mocked.

- Draft resume, required fields, read-only offer and client convenience validation: HTTPS browser test + backend schema tests.
- Server invalid inputs, no-token generation, owner-scoped encrypted/delete behavior: backend tests.
- Tokens absent from logs/responses/storage/export: backend and browser tests; build scans.
- Invalid/expired/under-scoped tokens, no retry, approval hash, verified URL, failed/stale jobs and unchanged campaign: backend tests.

### backend/tests/test_website.py

```python
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
```

### frontend/tests/website-api.test.mjs

```javascript
import assert from "node:assert/strict";
import test from "node:test";
import { parseMenuCsv, websiteInputError } from "../lib/website-api.ts";

test("CSV supports headers, quoted commas, escaped quotes and numeric prices", () => {
  assert.deepEqual(parseMenuCsv('name,price\r\n"Coffee, large",100\r\n"Tea ""classic""",50'), [
    { name: "Coffee, large", price: 100 }, { name: 'Tea "classic"', price: 50 },
  ]);
});
for (const csv of ['Coffee,abc', 'Coffee,-1', 'Coffee,', 'Coffee,Infinity', '"Coffee,100', '"Coffee"bad,100', 'Coffee,10,20']) {
  test(`Malformed CSV rejected: ${csv}`, () => assert.throws(() => parseMenuCsv(csv)));
}
const fields = { name: "Namma Cafe", area: "Bengaluru", phone: "", whatsapp: "", hours: [], menu: [], social_links: [] };
test("Client convenience validation blocks required/invalid inputs", () => {
  assert.equal(websiteInputError(fields), null);
  assert.match(websiteInputError({ ...fields, name: "" }), /required/);
  assert.match(websiteInputError({ ...fields, phone: "1" }), /Phone/);
  assert.match(websiteInputError({ ...fields, social_links: ["javascript:alert(1)"] }), /HTTPS/);
  assert.match(websiteInputError({ ...fields, menu: [{ name: "Coffee", price: NaN }] }), /prices/);
  assert.match(websiteInputError({ ...fields, hours: [{ open: "22:00", close: "09:00" }] }), /hours/);
});
```

### frontend/e2e/website.spec.ts

```typescript
import { test, expect } from "@playwright/test";

test.skip(process.env.WEBSITE_UI_TEST !== "isolated-mock", "Use the isolated HTTPS website verification harness");
test("website wizard resumes, keeps offer read-only, exports without token, and handles encrypted publishing", async ({ page, request }) => {
  test.setTimeout(120000);
  const token = "website-browser-credential-88cd";
  const consoleText: string[] = []; page.on("console", message => consoleText.push(message.text()));
  const urls: string[] = []; page.on("request", r => urls.push(r.url()));
  const responseBodies: string[] = [];
  page.on("response", r => { if (r.url().includes("/api/")) void r.text().then(t => responseBodies.push(t)).catch(() => undefined); });
  await page.goto("/?campaign=test-campaign");
  await page.getByRole("button", { name: "Create website", exact: true }).click();
  let wizard = page.getByRole("dialog", { name: "Create website", exact: true });
  await expect(wizard.getByLabel("Café name (required)")).toHaveValue("");
  await wizard.getByRole("button", { name: "6. Review", exact: true }).click();
  await expect(wizard.getByRole("button", { name: "Generate website", exact: true })).toBeDisabled();
  await wizard.getByRole("button", { name: "1. Basics", exact: true }).click();
  await wizard.getByLabel("Café name (required)").fill("Namma Cafe");
  await wizard.getByLabel("City/area (required)").fill("Bengaluru");
  await wizard.getByRole("button", { name: "Save and close", exact: true }).click();
  await expect(wizard).not.toBeVisible();
  await page.reload(); await page.getByRole("button", { name: "Create website", exact: true }).click();
  wizard = page.getByRole("dialog", { name: "Create website", exact: true });
  await expect(wizard.getByLabel("Café name (required)")).toHaveValue("Namma Cafe");
  await wizard.getByRole("button", { name: "2. Offer", exact: true }).click();
  await expect(wizard.getByText(/Read-only offer/)).toBeVisible();
  await expect(wizard.locator("input,textarea")).toHaveCount(0);
  await expect(wizard.getByRole("link", { name: "Edit in Facts Lock" })).toHaveAttribute("href", /facts-lock/);
  await wizard.getByRole("button", { name: "6. Review", exact: true }).click();
  await wizard.getByRole("button", { name: "Generate website", exact: true }).click();
  await expect(wizard.getByText(/Bundle SHA-256/)).toBeVisible();
  await expect(wizard.getByText("DRAFT - NOT PUBLISHED", { exact: true })).toBeVisible();
  await expect(wizard.locator("iframe")).toHaveAttribute("sandbox", "");
  await wizard.getByRole("button", { name: "7. Publish", exact: true }).click();
  const href = await wizard.getByRole("link", { name: "Download website (zip)" }).getAttribute("href");
  const zip = await request.get(href!); expect(zip.status()).toBe(200);
  expect((await zip.body()).includes(Buffer.from(token))).toBeFalsy();
  await wizard.getByLabel("Netlify API token").fill("expired-token-example");
  await wizard.getByRole("button", { name: "Test connection", exact: true }).click();
  await expect(wizard.getByRole("alert")).toContainText("invalid or expired");
  await expect(wizard.getByLabel("Netlify API token")).toHaveValue("");
  await wizard.getByLabel("Netlify API token").fill(token);
  await wizard.getByLabel("Remember for next time (encrypted on server)").check();
  await wizard.getByRole("button", { name: "Test connection", exact: true }).click();
  await expect(wizard.getByText(/Read-only connection passed/)).toBeVisible();
  await expect(wizard.getByRole("button", { name: "Publish", exact: true })).toBeDisabled();
  await wizard.getByLabel("I approve publication of this exact website bundle").check();
  await wizard.getByRole("button", { name: "Publish", exact: true }).click();
  await expect(wizard.getByText(/Published and live URL verified/)).toBeVisible({ timeout: 15000 });
  await wizard.getByRole("button", { name: "Disconnect / delete token", exact: true }).click();
  await expect(wizard.getByLabel("Use remembered Netlify token")).toHaveCount(0);
  const stored = await page.evaluate(() => ({ local: JSON.stringify(localStorage), session: JSON.stringify(sessionStorage), cookie: document.cookie }));
  expect(JSON.stringify(stored)).not.toContain(token);
  expect(consoleText.join("\n")).not.toContain(token);
  expect(urls.join("\n")).not.toContain(token);
  expect(responseBodies.join("\n")).not.toContain(token);
  const core = await request.get("/api/campaigns/test-campaign"); expect(core.status()).toBe(200);
  expect((await core.json()).facts.find((f: { key: string }) => f.key === "OFFER").canonical.value).toBe(20);
  await page.screenshot({ path: "../docs/evidence/website-wizard-mock.png", fullPage: true });
});
```

### frontend/playwright.website.config.ts

```typescript
import { defineConfig } from "@playwright/test";
// Started only by the isolated verification harness; never targets a user's live server.
export default defineConfig({
  testDir: "./e2e", testMatch: /website\.spec\.ts/, workers: 1,
  use: { baseURL: "https://localhost:3000", ignoreHTTPSErrors: true, channel: "chrome" },
});
```

### scripts/verify_website_ui.py

```python
"""Isolated HTTPS wizard check with explicitly fake hosting; stop every owned process."""

import base64
import os
import socket
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

ROOT = Path(__file__).resolve().parents[1]


def create_app():
    # Uvicorn factory used only in this test script, never backend.main production.
    from backend.config import Settings
    from backend.main import create_app as main_app
    from backend.tests.test_generation import locked, seed
    from backend.tests.test_website import Provider
    from backend.website_provider import HostingError

    class FakeHosting(Provider):
        verification_only = True

        async def test(self, token):
            if token.get_secret_value().startswith("expired"):
                raise HostingError("TOKEN_INVALID")

    app = main_app(
        Settings(
            _env_file=None,
            agnes_mode="mock",
            database_path=Path(os.environ["WEBSITE_TEST_DB"]),
            website_publish_enabled=True,
            website_token_key=os.environ["WEBSITE_TEST_KEY"],
        )
    )
    original = app.router.lifespan_context
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(app):
        async with original(app):
            seed(app.state.client, locked.__wrapped__())
            app.state.website.provider = FakeHosting()
            yield

    app.router.lifespan_context = lifespan
    return app


def main():
    for port in [3000, 3001, 8000]:
        with socket.socket() as probe:
            assert probe.connect_ex(("127.0.0.1", port)) != 0, "Stop existing app servers first"
    processes = []
    with tempfile.TemporaryDirectory(prefix="website-ui-") as folder:
        root = Path(folder)
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
        cert = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(UTC) - timedelta(minutes=1))
            .not_valid_after(datetime.now(UTC) + timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), False)
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), True)
            .sign(key, hashes.SHA256())
        )
        cert_path, key_path = root / "cert.pem", root / "tls-key.pem"
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        key_path.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        env = dict(
            os.environ,
            WEBSITE_TEST_DB=str(root / "test.sqlite3"),
            WEBSITE_TEST_KEY=base64.b64encode(os.urandom(32)).decode(),
            AGNES_MODE="mock",
            ENABLE_VIDEO="false",
            AGNES_API_KEY="",
            WEBSITE_UI_TEST="isolated-mock",
        )
        try:
            processes.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        "scripts.verify_website_ui:create_app",
                        "--factory",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        "8000",
                        "--ssl-certfile",
                        str(cert_path),
                        "--ssl-keyfile",
                        str(key_path),
                        "--no-access-log",
                    ],
                    cwd=ROOT,
                    env=env,
                )
            )
            processes.append(
                subprocess.Popen(
                    [
                        "node",
                        "node_modules/next/dist/bin/next",
                        "start",
                        "--hostname",
                        "127.0.0.1",
                        "--port",
                        "3001",
                    ],
                    cwd=ROOT / "frontend",
                    env=env,
                )
            )
            processes.append(
                subprocess.Popen(
                    ["node", "scripts/website_ui_proxy.mjs", str(cert_path), str(key_path)],
                    cwd=ROOT,
                    env=env,
                )
            )
            deadline = time.monotonic() + 30
            with httpx.Client(verify=str(cert_path), trust_env=False) as client:
                while True:
                    try:
                        if client.get("https://localhost:3000/api/ready").status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    assert time.monotonic() < deadline, "Verification server startup timed out"
                    time.sleep(0.2)
            result = subprocess.run(
                [
                    "node",
                    "node_modules/@playwright/test/cli.js",
                    "test",
                    "--config",
                    "playwright.website.config.ts",
                    "--reporter=line",
                ],
                cwd=ROOT / "frontend",
                env=env,
                timeout=150,
            )
            if result.returncode:
                raise SystemExit(result.returncode)
        finally:
            for process in reversed(processes):
                process.terminate()
            for process in processes:
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)


if __name__ == "__main__":
    main()
```

### scripts/website_ui_proxy.mjs

```javascript
// Verification-only local TLS proxy. Never used as a production hosting profile.
import https from "node:https";
import http from "node:http";
import fs from "node:fs";
const [cert, key] = process.argv.slice(2);
https.createServer({ cert: fs.readFileSync(cert), key: fs.readFileSync(key) }, (req, res) => {
  const api = req.url.startsWith("/api/");
  const upstream = (api ? https : http).request({ hostname: "localhost", port: api ? 8000 : 3001,
    path: req.url, method: req.method, headers: { ...req.headers, host: `localhost:${api ? 8000 : 3001}` },
    ...(api ? { ca: fs.readFileSync(cert) } : {}) }, response => { res.writeHead(response.statusCode, response.headers); response.pipe(res); });
  upstream.on("error", () => { res.writeHead(502); res.end("Verification upstream unavailable"); });
  req.pipe(upstream);
}).listen(3000, "localhost");
```

## 7. Security checklist

| Token handling rule | Enforcement |
| --- | --- |
| Client sends only to own HTTPS server | Wizard checks page protocol; main middleware rejects HTTP connection/publish/delete before parsing; same-origin fetch |
| No localStorage/cookies/URLs/logging | Token in masked component state, cleared on submission/close; no storage/log calls; receipt only in server RAM |
| Use once/discard | Receipt consumed once, explicit TTL, job `finally`, disconnect and shutdown; no job credential input |
| Remember only with opt-in/encryption | `ConnectionInput.remember=false`; `WebsiteService.aes/connect/decrypt`, AES-GCM with owner/provider associated data |
| Scope to owner/delete visibly | SQL filters use server owner; Wizard Disconnect; token row deletion, receipts cleared, jobs cancelled |
| Mask only, never return raw | SecretStr input; response allowlists include only last-four suffix; public bundle excludes bytes/HTML from JSON metadata |
| Never send token to AI | Standalone HostingProvider; no Agnes/client/work/inference call in website generation/publishing |
| Redact errors/traces | Fixed HostingError codes/messages; global validation handler strips values; no raw HTTP exception/body persisted |
| Invalid/expired/under-scoped stop | 401/403 mapped to fixed plain-language messages; 429 no automatic retry; POST never retried |
| Failures preserve preview/ZIP/core | Separate tables; publish reads immutable bundle and facts; failed jobs do not edit drafts/campaigns |
| Exact hash approved | Revalidated PublishInput; receipt bound to bundle hash; current draft/facts/bytes rechecked before dispatch and final success |
| Verify before Published | Netlify state polling, strict Netlify HTTPS URL allowlist, no redirects, unauthenticated bounded GET, exact HTML byte comparison |
| Secrets absent from bundle/build | No provider credentials used during generation; uncompressed ZIP checked against submitted token; repository/build scans and tests |

See [short design/run note](WEBSITE_V2_DESIGN.md) and [executed evidence](evidence/website-v2-verification.json).
