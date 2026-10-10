# Optional owner-confirmed Meta delivery

Implementation date: 2026-10-09. Requested source: `API_Inegration.md`.

This extension preserves B0–B7 and the frontend redesign. Export, clipboard copy,
poster download and `wa.me` drafts still send nothing. Meta is a separate,
non-inference transport; all AI inference remains Agnes-only. No login system,
multi-tenancy, personal-profile posting, scraping or unofficial API was added.

## Verification boundary

**MOCK implementation tests are not authenticated integration verification.**
Official Meta documentation requests on 2026-10-09 returned HTTP 429 or were
inaccessible. The official Meta Postman collection was reachable, but its loaded
page did not expose usable endpoint contracts. Consequently current permissions,
account entitlement, version availability/retirement dates, rate limits, token
lifecycle and raw live shapes remain **NOT_TESTED / DOCUMENTATION_UNAVAILABLE**.
No credentials were printed and no real message/post was submitted.

`v25.0` is a candidate mock fixture pin, **not a verified current-version claim**.
Before live enablement, the operator must verify support and retirement in the
official changelog, update the pin if necessary, verify account capabilities, and
record dated evidence. `META_VERIFIED_PLATFORMS=[]` blocks live startup. An identity
read alone does not qualify a platform as publishing-verified.

Official sources to complete verification:

- [Graph API changelog](https://developers.facebook.com/docs/graph-api/changelog/)
- [Pages posts](https://developers.facebook.com/docs/pages-api/posts/)
- [Instagram Facebook Login publishing](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-facebook-login/content-publishing/)
- [WhatsApp messages](https://developers.facebook.com/docs/whatsapp/cloud-api/reference/messages/)
- [WhatsApp send-message guide](https://developers.facebook.com/docs/whatsapp/cloud-api/guides/send-messages/)
- [WhatsApp webhook guide](https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks/)
- [Webhook payload verification](https://developers.facebook.com/docs/graph-api/webhooks/getting-started/)
- [Access tokens](https://developers.facebook.com/docs/facebook-login/guides/access-tokens/)
- [App review](https://developers.facebook.com/docs/app-review/)
- [Official Meta Postman collection](https://www.postman.com/meta/whatsapp-business-platform/documentation/wlk6lh4/whatsapp-cloud-api)

These are verification references; failed retrieval is not represented as a
successful review. See `evidence/meta-contract.json` and `evidence/meta-tests.xml`.

## Implemented initial scope

| Platform | Implemented adapter | Deliberate limitations |
|---|---|---|
| WhatsApp | Exact approved text; approved PNG image + exact caption; static approved text template; signed status/inbound webhook | Consent required. Live free-form needs an actual signed inbound event in the preceding 24 hours. No broadcast/contact discovery, arbitrary components, dynamic templates or invented conversation access |
| Facebook | Configured Page text or single approved image | No personal profile, scheduling, video, ads or groups. Photo/media ID and returned post ID are distinguished |
| Instagram | Facebook Login flow; single-image feed; create container → bounded status polling → publish | Professional account setup must be verified; do not use Instagram Login tokens. No personal accounts, Reels, Stories, carousels or silent image cropping |

Operator checklist for the selected Facebook Login flow: verify the linked Page /
professional-account relationship and current requirements for `instagram_basic`,
`instagram_content_publish`, `pages_read_engagement` and Page discovery. Verify
`pages_manage_posts` for Facebook and `whatsapp_business_messaging` for WhatsApp,
plus management permissions needed by the actual setup. This checklist is **not**
a freshly verified permission inventory. App review, advanced access and business
verification depend on the deployment/account and must be checked in Meta's app.

Tokens are server-managed environment secrets. There is no OAuth onboarding or
automatic token refresh in this single-owner extension. Follow the verified token
lifecycle for the selected account, rotate before expiry, restart, perform the
read-only check and create a new preview. A changed token/account/version/media
origin invalidates an outstanding preview.

## Configure quickly in mock mode

Use the existing root `.env`, privately, following `.env.example`. Never overwrite
an existing populated file, commit it, or place these fields in `NEXT_PUBLIC_*`.

Set `META_ENABLED=true`, `META_MODE=mock` and a random `META_OWNER_TOKEN` of at least
32 characters. Keep `META_VERIFIED_PLATFORMS=[]`. Mock needs no Meta access token,
public origin or external account. The owner token is a separate authorization
credential, **not** any platform access token. The owner enters it into the
delivery panel; it is retained in page memory only and cleared on reload.

Production inference and social modes are separate. Live delivery requires live
Agnes source mode and separately verified platform configuration. Mock/saved demo
content cannot be submitted as live content. Ordinary cached Agnes role evidence
is retained in the approved artifact provenance; it does not confer approval.

Windows PowerShell, from the repository root:

```powershell
if (-not (Test-Path -LiteralPath .env)) { Copy-Item -LiteralPath .env.example -Destination .env }
# Edit .env privately; set META_ENABLED, META_MODE and META_OWNER_TOKEN as above.
.venv/Scripts/python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --no-access-log
# Separate terminal:
Set-Location frontend
npm.cmd run build
npm.cmd run start
```

bash:

```bash
test -f .env || cp .env.example .env
# Edit .env privately as above.
.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --no-access-log
# Separate terminal:
cd frontend
npm run build
npm run start
```

After existing final approval, open **Approve + Export → Optional API delivery**,
enter owner authorization, choose platform and approved copy/poster, enter a
WhatsApp recipient/consent if applicable, preview, and separately confirm.
The mode and status are explicit. Static templates are available through the API;
the minimal UI uses the free-form flow and explains its live window requirement.

## Backend settings

| Setting | Meaning |
|---|---|
| META_ENABLED / META_MODE | Disabled by default; explicit mock/live |
| META_GRAPH_VERSION | Version in every Graph URL; verify before live use |
| META_VERIFIED_PLATFORMS | JSON array of independently verified platform names; empty by default |
| META_OWNER_TOKEN | Private authorization for preview, confirm, list, cancel, reconcile and connection checks |
| META_APP_SECRET | App-secret proof and webhook HMAC verification |
| META_WEBHOOK_VERIFY_TOKEN | Private webhook handshake credential |
| META_WHATSAPP_PHONE_ID / META_WHATSAPP_BUSINESS_ID / META_WHATSAPP_TOKEN | Configured sender/business and appropriate server access token |
| META_FACEBOOK_PAGE_ID / META_FACEBOOK_TOKEN | Configured authorized Page and Page token |
| META_INSTAGRAM_ACCOUNT_ID / META_INSTAGRAM_TOKEN | Professional account and token compatible with Facebook Login |
| META_PUBLIC_ORIGIN | Controlled public HTTPS origin for approved media and signed webhook routes only |
| META_REQUEST_TIMEOUT / META_MAX_ATTEMPTS / META_POLL_LIMIT | Defaults 20 seconds / 3 attempts / 6 polls, bounded by validation |
| META_WHATSAPP_TEMPLATES | JSON object: `name:language` → SHA256 of verified exact static template body |

For templates, independently check approval status/language/category and the exact
parameter-free body in Meta. The configured body hash must equal the exact current
authorized text export; arbitrary template content/components are not accepted.
Client text or audience targeting is never a contact list or consent evidence.

## API contracts and raw transport fixtures

Owner routes require `X-Owner-Delivery-Token`. Browser Origin, when present, must
match the configured local frontend origin. Secrets and raw recipients never
appear in operation responses, generic work inputs/results, SSE events or logs.

| Route under /api | Behavior |
|---|---|
| GET /meta/status | Safe enabled/mode/capability status; no credentials |
| POST /meta/connections/{platform}/check | Read configured identity only; does not prove publication |
| POST /campaigns/{id}/meta/preview | Recheck authorized export; persist immutable exact preview; no external action |
| GET /campaigns/{id}/meta | Latest operations, masked destination, actual recorded states |
| GET /campaigns/{id}/meta/{op}/preview-image | Owner-authorized exact delivery bytes, including JPEG derivative |
| POST /campaigns/{id}/meta/{op}/confirm | Exact preview hash + confirmation token + explicit owner confirmation → 202 |
| POST /campaigns/{id}/meta/{op}/cancel | Cancel unsubmitted work; preserve uncertainty/accepted external actions |
| POST /campaigns/{id}/meta/{op}/reconcile | Bounded read-only check; never sends or publishes |
| GET /meta/media/{opaque-token} | Approved media only, 30-minute grant, hash/current approval checks |
| GET /meta/webhook | Verified numeric challenge |
| POST /meta/webhook | HMAC-verified WhatsApp inbound/status events; deduplicated, size bounded |

Preview request, redacted example:

```json
{
  "expected_revision": 6,
  "platform": "facebook",
  "text_item_id": "approved-text-id",
  "poster_item_id": null,
  "observed_hashes": {"approved-text-id": "<current approved snapshot SHA256>"},
  "idempotency_key": "owner-reviewed-delivery-key"
}
```

Confirmation request:

```json
{
  "expected_revision": 6,
  "preview_hash": "<server preview SHA256>",
  "confirmation_token": "<private token returned by authenticated preview>",
  "owner_confirms_delivery": true
}
```

Raw request fixtures, with Bearer token/app-secret proof/recipient/media grant
redacted. These shapes are **tested against MockTransport, NOT authenticated Meta**:

```text
POST /v25.0/[phone-id]/messages             application/json
{"messaging_product":"whatsapp","to":"[REDACTED]","type":"text",
 "text":{"body":"[exact approved export]","preview_url":false}}
response fixture: {"messages":[{"id":"mock-wamid-[unique]"}]}

POST /v25.0/[page-id]/feed                 application/x-www-form-urlencoded
message=[exact approved export]
response fixture: {"id":"mock-feed-[unique]"}

POST /v25.0/[page-id]/photos               application/x-www-form-urlencoded
url=[opaque HTTPS grant]&caption=[exact approved export]&published=true

POST /v25.0/[ig-id]/media                  application/x-www-form-urlencoded
image_url=[opaque HTTPS JPEG grant]&caption=[exact approved export]
response fixture: {"id":"mock-media-[unique]"}
GET /v25.0/[container-id]?fields=status_code
response fixture: {"status_code":"FINISHED"}
POST /v25.0/[ig-id]/media_publish          application/x-www-form-urlencoded
creation_id=[recorded container-id]
response fixture: {"id":"mock-media_publish-[unique]"}
```

The runtime signs with `appsecret_proof` and uses server-only Bearer authorization.
No SDK merging assumptions are used. Redirects, environment proxies and arbitrary
provider URLs are disabled. These adapter payloads are candidate raw contracts;
the live gate requires actual response evidence before they are called verified.

## Persistence, approval and recovery

Migration 008 extends the same SQLite database with operations, byte grants,
dispatch attempts and sanitized webhook/status/inbound records. It does not alter
fact or artifact approval schemas. Preview binds the current revision, exact
snapshot/byte hashes, destination/request, selected account/configuration and
derived-media bytes. Source provenance includes the authorized export metadata.

Preview and every provider attempt reuse `ApprovalService.export`: audits,
warnings, hidden eligibility dependencies, layout/font, source hashes and bytes
cannot be bypassed. Work kind `meta_delivery` contains only operation ID/revision;
generic work-start cannot authorize it. Generic retry always rejects delivery.
Two existing worker slots, 16 queued jobs, 480-second deadline, 12 total attempts,
maximum 3 per request and finite Instagram polling bound the operation.

Confirmation and job admission are short persisted steps. A crash between them
is recovered conservatively; it never implies exactly-once external delivery.
Queued operations are cancelled on restart. Submission/processing becomes
`delivery_unknown`. Each network attempt is journaled before awaiting HTTP.
Only explicit 429 rejection may repeat POST with bounded Retry-After. POST 5xx,
timeout, transport loss or malformed success is unknown and never blindly replayed.
GET 5xx has bounded retries. SSE/reload/list operations do not submit or add costs.

`accepted` is WhatsApp provider acceptance, not delivery. `delivered` / `read`
require verified callbacks. `published` records publication response or a verified
read-only published-container result. `delivery_unknown` requires inspection;
reconciliation never republishes a ready Instagram container. A fact edit while
queued prevents submission. A fact edit after dispatch is shown as
`changed_after_submission`; already accepted external work is not claimed undone.

Meta charges remain `unknown_provider_charge` in live operation records. They are
not folded into Agnes inference price estimates or invented as zero. Mock records
say `not_applicable_mock`. Work snapshots count actual Meta dispatch attempts.

The local database contains private recipient/consent data in operation input.
Keep DB/backups owner-only and apply a deployment retention policy. Public routes
never return raw webhook messages/contacts. Message identifiers/statuses and
hashed inbound recipient timestamps are retained to handle callbacks arriving
before the initial HTTP response is persisted.

## Media and deployment boundary

WhatsApp/Facebook use approved PNG bytes without modification. Instagram uses a
deterministic JPEG derivative (quality 95, no crop/layout/text changes); its exact
bytes are shown in the owner-only preview and bound by a separate delivery hash.
Conservative checks: WhatsApp image ≤5 MB, Facebook/Instagram ≤8 MB; Instagram
feed ratio 0.8–1.91 and width 320–1440. Verify current platform limits before live
enablement; these local bounds are not claims of current Meta documentation.

Expose only `/api/meta/webhook` and `/api/meta/media/*` through a controlled HTTPS
reverse proxy using the configured public origin. Owner/work/export routes retain
the existing local Host restriction. Do not expose the whole app/asset directory.
Configure the proxy to suppress/redact webhook query strings and opaque grants;
use `--no-access-log`. The application also redacts Meta routes in Uvicorn access
records. Do not enable HTTP debug logging containing credentials or signatures.

This remains a single-owner local application with a private delivery credential,
not a public multi-user authorization system. Do not deploy it as SaaS.

## Local checks

PowerShell:

```powershell
.venv/Scripts/python.exe -m pytest backend/tests/test_meta.py -q
.venv/Scripts/python.exe -m scripts.check_meta_connection whatsapp
.venv/Scripts/python.exe -m scripts.check_meta_connection facebook
.venv/Scripts/python.exe -m scripts.check_meta_connection instagram
.venv/Scripts/python.exe -m scripts.check_frontend_secrets
```

bash uses `.venv/bin/python` with the same arguments. Connection commands use the
private server configuration and redact identifiers/secrets. They are read-only.
If integration is disabled, they return NOT_TESTED. Mock mode cannot contact Meta.

Authenticated connection/send/publication, public-media fetch and webhook callback
checks remain **NOT_TESTED**. Real delivery testing needs explicit approval for the
exact recipient/Page/account/content. No script in this change performs a live send.
