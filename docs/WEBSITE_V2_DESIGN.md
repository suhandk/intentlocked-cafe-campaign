# Website V2 design note

10 October update: the website now has an isolated OpenRouter layout planner using
Qwen3 Coder Flash. The deterministic renderer still owns all factual content and
HTML/CSS. Platform and hosting tokens never enter model inputs. The historical
"no AI calls" description below applied before this requested model addition; see
[current model and functional evidence](WEBSITE_OPENROUTER.md).

## Assumptions

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

## Isolation and data

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

## API shapes

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

## Security checklist

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

## Running and evidence

```powershell
.venv\Scripts\python.exe -m uv sync --locked
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check backend scripts
node frontend/node_modules/typescript/bin/tsc --noEmit -p frontend/tsconfig.json
# From frontend:
node node_modules/eslint/bin/eslint.js . --max-warnings=0
node node_modules/next/dist/bin/next build
# From root; Node 24 for native TypeScript stripping:
node --experimental-strip-types --test frontend/tests/website-api.test.mjs
# Starts/stops isolated test servers; fake Netlify, never live proof:
.venv\Scripts\python.exe -m scripts.verify_website_ui
```

Default HTTP local demo supports draft/generate/preview/ZIP. Publishing is disabled
and token controls are unavailable. To enable private publishing, the operator must
provide `WEBSITE_PUBLISH_ENABLED=true`, actual trusted local TLS for frontend and
backend, and optional stable `WEBSITE_TOKEN_KEY` (base64 of 32 random bytes).
`BACKEND_ORIGIN=https://localhost:8000` configures the Next proxy for TLS; default
remains the previous HTTP loopback address. Use a trusted local CA with Node's
`NODE_EXTRA_CA_CERTS`, not disabled certificate validation. Backend Uvicorn supports
`--ssl-certfile`/`--ssl-keyfile`; local Next dev supports `--experimental-https` and
certificate/key flags. A public production profile is not introduced by this work.

No real Netlify token, account test or deploy was supplied/performed. Automated
hosting responses are explicit mocks. The browser screenshot is a MOCK HOSTING TEST,
not proof of a deployed café website. Native Kannada review remains pending.
Application servers are left stopped after verification, as requested.

Netlify integration follows the official [ZIP deployment API](https://docs.netlify.com/api-and-cli-guides/api-guides/get-started-with-api/).
Its read-only API cannot establish deploy-only permission; the UI states this limitation.
