# Interface contract baseline

## Hackathon media extension — 10 October 2026

All owner APIs retain `/api` and existing ErrorBody/status/revision conventions.
Health adds `image_provider` and `image_configuration_notice`, with actual image
dispatch and vision availability. Configuration availability does not claim live
verification. Direct OpenAI art uses the server-only `OPENAI_API_KEY`; ordinary
text continues to use the existing gateway key. MOCK uses only MockTransport.
CallRecord adds provider, transport_endpoint and provider_reported_cost_usd;
these are redacted transport/cost evidence, distinct from optional list-price estimates.

`POST /api/campaigns/{id}/work` accepts additive kind `local_video`, with input
`{expected_revision, poster_id, duration: 12|18|24}` and a normal work idempotency key.
It uses the existing durable job/cancellation/storage contracts, no inference call,
and bounded local encoding. `/api/video/config` reports local_enabled and
local_tools_available. The resulting video starts UNAPPROVED.

`POST /api/videos/{id}/approve` takes expected_revision, observed_hash,
owner_approves=true and idempotency_key. The source poster must already pass the
server's current audit/owner/export checks. GET `/api/videos/{id}/approved.mp4`
and `/manifest` repeat current fact/source/font/layout and exact-byte hash checks.
The manifest binds source poster, revision, facts, provenance and source export
manifest. GET `/draft.mp4` remains an explicitly unapproved download. Stale,
cancelled, tampered or unapproved output cannot gain an authorized export URL.
Approved MP4/manifest accept `saved_view=true` for CACHED labeling while preserving
source_mode, identical hashes and the same authorization checks. The source
export manifest also carries cached/source labels; the flag never grants approval.

R4 repair feedback adds only a closed vocabulary of rejected expressions; no
canonical business values or rendered findings enter R4. R7 keeps its blinded
input, exact evidence validation and independent canonical/provenance comparison.
The reader schema now rejects a canonical discriminator belonging to another key.
Prompt changes invalidate cache keys; historical blocked audits remain blocked.

## Surface recovery — 10 October 2026

Public DTOs and `/api` routes remain unchanged. Internal R2 wire guidance binds
specified keys to selected languages/cases and the existing typed form grammar.
Original Pydantic/domain validation remains authoritative. `SURFACES_UNAVAILABLE`
retains the canonical confirmation and reports an allowlisted reason/current
revision; no forms or approval are fabricated. Frontend retries start a new
reviewed forms job at the saved current revision, preserving canonical confirmation
only when its reviewed facts are unchanged. Generic work retry continues to reject
old revisions. All other lock/approval/export and warning rules are unchanged.

## Screenshot recovery contracts — 10 October 2026

The original API prefix, DTOs, approval rules and fact transactions remain.
Health adds `image_generation_enabled` and reports actual configured model IDs.
Unavailable image transport uses HTTP 422 IMAGE_TRANSPORT_UNVERIFIED; unavailable
video uses HTTP 422 VIDEO_DISABLED, both before new job/inference admission.
Generation's terminal all-blocked outcome records COPY_VALIDATION_FAILED.

B5 selection now accepts original ready baselines from one explicit saved audience
and language, not exclusively the suggested hero. `variant_ids` remains the wire
contract; the server derives and validates the group. All five saved personas and
the fixed original baseline remain frozen per run. Unscored IDs include ready
variants only. Mandatory disclosure references are appended before full Guardian
checks, and remain pending final audit/owner approval. Historical failed rows are
not rewritten as successful. See [recovery analysis](SCREENSHOT_RECOVERY_2026-10-10.md).


## Model migration — 2026-10-09

Current model configuration supersedes original Agnes-only contracts: text
`ollama/gpt-oss:120b`, image `nb/nanobanana-flash`; one OpenAI-compatible client.
`INFERENCE_*` replaces `AGNES_*`. Health reports the new models and unavailable
vision/video explicitly. The exact /api prefix and existing error/status,
revision, approval/export and job contracts remain. Blocked generated images
have a restricted unapproved preview, never authorized export. Migration 011
repairs both historical migration-009 variants without dropping saved records.
See [configuration and evidence](MODEL_PROVIDER_MIGRATION.md).


## Owner content planning — 2026-10-09

Migration 010 and `/api/plans` add a separate local-owner planning resource.
CreatePlan/UpdatePlan/PlanAction/FinishPlan, PlanView, CampaignChoice and
PlanningSnapshot are in generated OpenAPI/types. Plan version is distinct from
campaign fact revision; readiness is derived from existing server export checks.
Create/start/terminal actions are idempotent; editable updates require expected
version. Status is planned/cancelled/owner_posted (self-report, not verified).
Conflicts use 409, invalid input or unauthorized readiness uses 422, absent records
use 404. No new inference/job/provider transport. Internal transaction participation
preserves atomic draft creation and owner-posted verification. Existing HTTP DTOs
are unchanged. Full contracts and limits: [CONTENT_CALENDAR.md](CONTENT_CALENDAR.md).

Approval recovery extension (2026-10-09): DeliveryItem adds volatile
`audit_findings: string[]` and `approval_blockers: string[]`. GET delivery uses
approval's content/dependency/readiness verification to populate diagnostics.
These fields are excluded from `item_hash`; source/snapshot hashes are preserved.
Client owner/warning/native review binds to current item hashes and audit IDs.
Server approval/export remains authoritative. See APPROVAL_RECOVERY.md.

## Optional Meta delivery — 2026-10-09

Migration 008 and meta_models/client/service/routes extend B0–B7. `/api/meta/status`,
read-only connection checks, campaign `/meta/preview`, `/meta/{id}/confirm`, list,
cancel, reconcile and exact preview-image routes are documented in
[META_INTEGRATION.md](META_INTEGRATION.md). Owner routes require the separate
X-Owner-Delivery-Token header. `meta_delivery` wraps only a confirmed operation ID
and revision in existing durable work. Generic work-start rejects delivery and
generic retry always rejects it. Media grants and signed WhatsApp callbacks are
the only narrowly exposed HTTPS routes; existing owner routes remain local.
Safe ErrorBody conventions persist: owner/signature/disabled/unverified 403,
invalid delivery/media/window/template/configuration 422, missing operation 404,
revision/key conflicts 409, upstream provider failures 502. Unknown submission is
an explicit persisted state, never fabricated success. Generated OpenAPI is updated.

## Frontend redesign — 2026-10-09

API/schema contracts are unchanged. WorkspaceShell context contains presentation
navigation, campaign metadata, stage statuses scoped to campaign/revision,
trace visibility, actual job time/progress and connection/cost display. Existing
CampaignFlow/CampaignMatrix/DeliveryPanel remain the state owners. Hash history
preserves the campaign query parameter and browser back/forward. Hidden stage
content remains mounted; revision keys still reset obsolete approval state.
Saved previews can switch views/tabs, but inference and approvals are disabled.
BrandDraftEditor supplies existing BrandKit fields through DraftRequest before
locking. Logo/PNG/export paths and persisted artifact bytes are unchanged.
The generated OpenAPI TypeScript file is not modified. Details and evidence:
[FRONTEND_REDESIGN_REVIEW.md](FRONTEND_REDESIGN_REVIEW.md).

## B7 implemented contract — 2026-10-09

Health is B7/b7.1; existing B1–B6 routes/DTOs remain compatible. Migration 007 and
work_models/work_service/work_routes implement the durable admission contract in
[WORKFLOW_RECOVERY.md](WORKFLOW_RECOVERY.md). Generated OpenAPI/types are authority.

| Route, /api prefix | Actual shape |
|---|---|
| POST /campaigns/{id}/work | WorkRequest → 202 WorkJob; kind validates input using existing typed DTO |
| GET /campaigns/{id}/work; GET /work/{id} | Persisted status/result, steps/deadline, correlated call costs/timers/queue estimates |
| POST /work/{id}/cancel | Idempotent cancelled status; saved work retained; late native output rejected |
| POST /work/{id}/retry | WorkRetry → 202 new bounded job; ready generation cells reused; uncertain media blocked |
| GET /stream/{campaign_id} | Actual SSE: increasing IDs, Last-Event-ID/after replay, 5s heartbeats; read-only |
| GET /campaigns/{id}/saved-output | Actual completed render/generation capture or 404 SAVED_OUTPUT_MISSING |
| GET /campaigns/{id}/export[.zip]?saved_view=true | Same authorization; cached labels + original source/capture/prompt/approval/hash provenance |

WorkJob status includes queued/running/completed/partial/failed/cancelled/interrupted/
stale. Native generation/optimization add cancelled. GenerateRequest optionally
binds retry_source_run_id to the exact same current selection and carries ready
cells forward. CallRecord adds work_id, and dispatch/completion update one call ID.
WorkflowEvent includes campaign/revision/job/native run/time/action/message. Owner
request/result is private job data; raw input is not in event/trace payloads.

WORK_INVALID/RETRY_UNSAFE are 422, WORK_QUEUE_FULL is 409, missing jobs/captures 404;
revision/key conflicts keep 409 and the existing safe error envelope. No approval
or export boundary is relaxed for cached views.

## B6 implemented contract (2026-10-09)

Health is B6/b6.1. All B1–B5 APIs continue. Current generated OpenAPI/types
supersede older reserved DTOs. Migration 006 adds Proposal/DeliveryItem/AssetApproval/
Version/ExportPack storage with revision links and idempotent owner actions.

| Route (all /api) | Contract |
|---|---|
| POST /campaigns/{id}/change | ChangeRequest → Proposal; R8 typed operations, code classification/diff, no commit |
| POST /campaigns/{id}/change/confirm | ConfirmRequest → confirm/cancel, no partial mixed edit |
| POST /campaigns/{id}/change/{proposal_id}/surface | RevisionRequest → Proposal with editable forms |
| POST /campaigns/{id}/change/publish | PublishRequest → atomic revision after owner-reviewed forms |
| GET /campaigns/{id}/delivery | Current scoped items/statuses, proposals, versions and ledger |
| GET /campaigns/{id}/ledger; GET /campaigns/{id}/versions | Events; read-only current/historical snapshots |
| POST /campaigns/{id}/delivery/{item_id}/audit | RevisionRequest → persisted blinded R7 Audit |
| POST /campaigns/{id}/approve | ApprovalRequest → exact hash/warning/native attestation record |
| GET /campaigns/{id}/export | Required expected_revision, repeated item_ids → authorized ExportPack |
| GET /campaigns/{id}/export.zip; GET /campaigns/{id}/export/files/{item_id} | Repeat authorization, exact persisted bytes |
| POST /campaigns/{id}/red-team | R8 proposal (instruct_ai) or immediate Guardian (edit_copy) |

No client report/pass/content/bytes accepted for approval. 422: invalid proposals,
pending/blocked/unapproved exports or missing warnings; 409: revision/idempotency
conflicts; 404: absent delivery record. Existing error envelopes remain. Unchanged
lineage can carry only with identical dependencies/bytes and fresh code checks.
Manifest: current/source fact versions, original approval revision, SHA-256, mode
and separate poster URL. WhatsApp is a draft, not automatic delivery/attachment.
See DELIVERY_BOUNDARY.md. Job/release integration remains B7/B8.

## B5 implemented contract (2026-10-09)

Current health stage/schema: B5/b5.1. B1–B4 routes continue. Generated OpenAPI and
frontend types are authoritative; older stage labels below are historical.

| Route | Contract |
|---|---|
| POST /api/campaigns/{id}/optimize | OptimizeRequest: expected_revision, 1–3 original hero baseline variant_ids (one language), idempotency_key. 202 OptimizationRun with frozen inputs and finite budgets. |
| GET /api/campaigns/{id}/optimization | OptimizationSnapshot: saved runs and unscored current matrix IDs. Scores never populate other groups. |
| GET /api/optimization/jobs/{id} | Persisted phase/rounds, retained selection, counts/cost/timing, stop state and stale detection. |
| POST /api/assets/{id}/audit | RevisionRequest → immutable Audit after PNG byte/hash and exact render-text checks. R7 receives only text, language/channel. |
| GET /api/audits/{id} | Persisted Audit with extraction, evidence, report/warnings, hashes/provenance and measured poster features. Stale revision rejected. |

Migration 005 creates optimization_runs, inference_cache and semantic_audits.
OptimizationGroup contains immutable baseline/baseline_score plus current template,
score, audited reports and stored round history. R5 judges anonymous AB/BA texts;
code owns mappings and aggregates. R6 has at most four distinct permitted template
field edits. R7 canonical expectations are OUTPUTS; locked facts, earlier scores
and provenance labels are never its INPUTS. Missing judgments produce null scores,
missing audits remain PENDING, mismatches BLOCK.

OptimizedVariant retains VariantContract fields with baseline=false, parent ID,
pending status and exact report/dependencies. B4 render resolves completed B5 runs'
retained audited IDs, in addition to original baselines. CanvasInput carries server
derived approved offer_forms; canvas-b5.1 returns measured offer_area_ratio or null.
Renderer/font/layout/bytes remain dependency-bound.

TraceEvent supports stage=B5 with campaign_id/revision. Transactional phase decisions
have increasing IDs and no transcript/reasoning payload. Error envelopes remain
`{code,message,details,trace_id,retryable}`. Busy/stale/idempotency conflicts: 409;
invalid selection/edit: 422; absent run/audit: 404. See OPTIMIZATION_BOUNDARY.md for
features, exact acceptance/stop rules, caches, warnings and deadlines. Final owner
approval/export remain B6 and unavailable.

## B4 implemented contract (2026-10-09)

Health stage/schema: B4/b4.1. B3 strategy/matrix routes and schemas continue unchanged.

| Route | Contract |
|---|---|
| POST /api/campaigns/{id}/backgrounds | BackgroundRequest: expected_revision, size (square/story/landscape), source (agnes/deterministic). Returns Background with persisted QA/provenance/hash or disclosed deterministic fallback. |
| POST /api/campaigns/{id}/assets/render | RenderRequest: expected_revision, stored variant_id/background_id, size, optional stored logo_id. Returns PosterArtifact with canonical CanvasInput, pixel metrics, Guardian, exact bytes/hash and all dependencies. No client text/PNG/URL/validation accepted. |
| GET /api/campaigns/{id}/assets | ArtSnapshot: saved backgrounds, posters (stale on old revision), logo IDs. |
| POST /api/campaigns/{id}/logos | Raw PNG body (<=2MB), expected_revision and owner_approves_logo=true query. Returns server-owned logo ID. SVG/animation/MIME mismatch rejected. |
| GET /api/assets/{id} | Validated stored PNG bytes with hash ETag, nosniff and X-Artifact-Approval: pending. Same bytes for preview/draft download; blocked assets refused. |
| GET /api/assets/{id}/record | Typed persisted PosterArtifact metadata. |
| GET /api/render/worker, /api/render/canvas.js, /api/render/fonts/{filename} | Restricted local browser worker and allowlisted immutable source/font files. Font manifest/hash validation required. |

Migration 004 creates art_backgrounds, poster_artifacts and campaign_logos. Art
shares the same single AgnesClient limiter and never calls images per matrix cell.
Posters have status ready only after full text/byte/layout validation, but
approval_ready=false and G14 pending. Final approval/export routes remain B6.
See ART_BOUNDARY.md for budgets, hashes, native review and limitations.

## B3 implemented contract (2026-10-09)

Current health stage/schema are B3/b3.1. Generated OpenAPI and TypeScript are the
executable contract. Older stage descriptions below are historical where superseded.

| Route | Contract |
|---|---|
| POST /api/campaigns/{id}/strategy | RevisionRequest → StrategyPlan. R3 plans exactly three compatible hypothetical strategies and five persisted personas once per locked revision. |
| POST /api/campaigns/{id}/generate | GenerateRequest → 202 GenerationRun. Revision, plan ID, unique selected audience/language/channel lists and idempotency key only. |
| GET /api/campaigns/{id}/matrix | MatrixSnapshot: current strategy plus latest run, including queued/missing/blocked cells and typed server-rendered Guardian previews. |
| GET /api/jobs/{id} | Persisted GenerationRun; old revision becomes stale, never overwrites current campaign. |

Request selections must be subsets of the locked campaign and saved strategy.
Duplicate idempotency keys return the original run; changed requests return 409.
One active copy run is permitted; another returns GENERATION_BUSY (409). Invalid
eligibility/selection returns 422, stale revisions 409, absent IDs 404. Canonical
facts, templates, reports, approvals and slots_used cannot be injected into generate.

Migration 003 adds strategy_plans, generation_runs and baseline_variants. Existing
VariantContract is extended with actual GuardianReport, explicit mode and baseline
marker. Templates, parsed slots_used, fact/dependency/content hashes and fact/brand/
prompt/policy versions are stored. Ready matrix cells still have variant status
pending and report approval_ready=false. The matrix polls saved progress at 1.5s;
there is no B3 SSE, public cancellation endpoint or automatic restart replay.

R3/R4 use strict extra-forbidden models with success/needs_input/error envelopes.
R4 gets one language and up to nine combinations, closed creative enums, slot
shapes/cases and policy; never raw fact values, brand text, transcript, examples or
repair findings. See GENERATION_BOUNDARY.md for budgets and failure semantics.

## B2 implemented contract (2026-10-09)

`POST /api/guardian/check` accepts strict `CheckRequest`: campaign_id,
expected_revision, mode (`fragment|asset`), language, channel, TemplateContent
(headline/body/cta/hashtags/alt_text), optional audience and optional displayed copy.
Facts/forms/provenance/policy/audit results are never accepted from clients.
The repository supplies the authoritative locked snapshot; stale revisions return
409, unlocked facts and unselected language/channel return 422, unknown ID 404.

Diagnostics return `GuardianReport` (`guardian-report-2.1`) with
`guardian-policy-2.1`, content/dependency hashes, original field-local spans,
rendered fields and derived slots, all 15 checks, missing checks and warning IDs.
Rule failure is a 200 diagnostic with status BLOCKED, not a successful approval.
All offsets count Unicode code points, with half-open [start,end) bounds.

Fragments skip G05 completeness and G14 semantic audit but cannot approve/export.
Assets require all core facts and specified conditions in visible fields. G14 is
mandatory and incomplete until B5; poster pixel overflow is incomplete until B4.
Every B2 report has approval_ready=false. The future boundary registry also uses
GuardianReport; the old unused GuardianContract is historical. Approval
and export routes remain absent. See GUARDIAN_BOUNDARY.md for precise policy,
G14 evidence requirements, conservative grammars and lexical limitations.

`frontend/components/GuardianPanel.tsx` exposes both diagnostic modes on locked
campaigns; edits clear prior results and in-flight stale results are discarded.
It renders untrusted copy through React text nodes and never normalizes display.

Status: **B0 contract b0.1 implemented**. `openapi.json` is generated by `python -m scripts.export_openapi`; `frontend/lib/api.generated.ts` is generated by `npm --prefix frontend run api:types`. Strict frontend types use those generated schemas.

## Executable B0 surface

| Route | Current response / behavior |
|---|---|
| GET /api/health | Health: status=ok, stage=B0, mode, Agnes provider, live_contract=NOT_TESTED, schema_version=b0.1, video_enabled |
| GET /api/ready | Same health payload after SELECT 1; typed 503 if storage unavailable. Does not claim provider account readiness. |
| GET /api/cost | Cost: recorded sent attempts, mock_calls, known_list_price_estimate, unknown_cost_calls, USD, actual_billing=unknown |
| GET /api/traces | Last 50 TraceEvent records, newest first; increasing persisted IDs. This snapshot is not SSE. |
| GET /api/openapi.json; GET /api/docs | Generated contract and development API documentation |

All campaign/job/asset/export routes in the future route table below remain **unimplemented** and return typed 404; no placeholder success handlers. Schema definitions live in `backend/contracts.py`. Unexpected errors, HTTP errors, input validation and rejected Host headers use `{code,message,details,trace_id,retryable}`. CORS preflight is framework middleware behavior; application errors use the envelope. Current error status mapping: 400 HOST_REJECTED, 404 NOT_FOUND, 422 VALIDATION_ERROR, 500 INTERNAL_ERROR, 502 provider errors, 503 STORAGE_UNAVAILABLE. Future campaign revision conflicts will use 409.

Operational migration 1 creates `migrations`, `api_calls` and `trace_events`, with indexes, WAL, foreign keys and busy timeout. Campaign tables remain B1+. CallRecord persists `sent`, attempt and repair numbers, redacted status, run/trace IDs, model, mode, HTTP status, queue/duration, optional usage and estimate. Cancelled unsent entries retain trace evidence but do not count as sent/billed calls. Failed-call returned usage is retained; absent usage stays unknown. An HTTP-completed trace does not assert successful schema validation.

One client serializes requests and prioritizes interactive work with background service after at most three interactive calls. Fake clocks make tests immediate. Transport attempts are capped at three; schema repairs at two; the shared Budget also caps total calls and deadline. Raw JSON is sent with httpx, and mock mode always installs an in-memory MockTransport. Cached mode rejects inference. No thinking mode or implicit structured-strategy/provider fallback is enabled.

The client currently has no campaign run persistence, distributed limiter or job/SSE API; those remain later stages. CLI invocations and server processes do not coordinate quotas. B0 live-readiness status remains conservative NOT_TESTED; smoke evidence must be reviewed before a later stage changes this status.

## Cross-stage design (not yet implemented unless listed above)

## Runtime and trust boundary

Python 3.11, FastAPI, Pydantic v2 with extra fields forbidden, SQLite WAL/foreign keys/busy timeout/versioned migrations; Next.js/React strict TypeScript/Tailwind. One server worker, bounded active runs. All inference through one Agnes httpx client. Browser speech is the only separate speech exception. No public unauthenticated write deployment.

Modes: config `live|mock|cached` displayed as LIVE/MOCK/SAVED DEMO OUTPUT. Server time zone Asia/Kolkata; normal live mode must not inherit a demo clock. Text/vision model `agnes-3.0-flash`; image `agnes-image-2.5-flash`; video disabled until entitlement checked.

## Domain invariants

- Fact keys: CAFE, LOCATION, OFFER, PRODUCT, DAYS, DATES, ELIGIBILITY, ID_RULE, TIME_WINDOW, DINE_IN_RULE, MIN_PURCHASE_RULE, COMBINE_RULE. Tagged canonical types, status proposed/locked/not_specified, source spans, append-only version, approval provenance. DAYS derives from DATES.
- Languages en/kn/kn-Latn; cases nom/dat/gen/loc. Forms map language -> case -> nonempty approved string list. Canonical confirmation is distinct from final atomic form/fact lock.
- Variant status approved/stale/pending/blocked. Store template, derived slots_used, fact/dependency/content/render hashes, exact dependency versions, parent, changelog and versioned scores/reports.
- Planned tables: campaigns, fact_versions, brand_kits, audiences, variants, assets, scores, ledger_events, campaign_versions, approvals, trace_events, api_calls, jobs, migrations.
- Every mutable commit checks expected campaign/fact revision transactionally. Idempotency keys bind request payload and operation, not just a button. Old async results never overwrite newer revisions.
- Jobs persist run_id, revision, status, deadline, budgets, idempotency key and outputs. Terminal outcomes distinguish completed, failed, cancelled, interrupted and uncertain operations. Concrete transition graph will be tested in implementation; uncertain media must not be auto-resubmitted.
- Guardian reports carry per-check applicability/completion/pass state, original spans, severity, missing checks and warning IDs. Incomplete mandatory checks mean INCOMPLETE. Required semantic audit cannot be skipped on approval.

## Required routes (all prefixed `/api`)

| Method and path | Purpose / constraint |
|---|---|
| POST /campaigns; GET /campaigns/{id} | Create and reload campaign with authoritative revisions and mode |
| POST /campaigns/{id}/intent | Propose editable facts; cap transcript at 2,000 chars |
| POST /campaigns/{id}/facts/surface | Confirm canonical draft and request proposed forms against its exact revision |
| POST /campaigns/{id}/facts/lock | Owner approves forms and locks canonical/forms atomically |
| POST /campaigns/{id}/generate | Idempotent bounded job, progressive persisted outputs |
| POST /campaigns/{id}/optimize | Bounded job against frozen baseline and current revision |
| POST /guardian/check | Typed fragment or full-asset mode; fragments cannot authorize exports |
| POST /campaigns/{id}/change | Parse proposal; code classifies targets |
| POST /campaigns/{id}/change/confirm | Before/after expected-revision confirmation; new form review still required |
| GET /campaigns/{id}/ledger; GET /campaigns/{id}/versions | Current/historical distinctions and dependency consequences |
| POST /campaigns/{id}/approve | Transactional readiness, reports, hashes, artifacts and warning acknowledgments |
| GET /campaigns/{id}/export | Current authorized persisted bytes/manifest only |
| GET /stream/{id} | Proposed interpretation: campaign event stream, each event includes run_id; increasing IDs, Last-Event-ID replay and heartbeat |
| GET /cost; GET /health | Measured usage/estimated cost; process health and documented readiness semantics |

Proposed additions to finalize in B0/B4/B7: GET `/jobs/{run_id}`, POST `/jobs/{run_id}/cancel`, POST `/campaigns/{id}/assets/render`, GET `/assets/{asset_id}`, GET `/ready`. Render accepts server-owned variant/layout references and expected revision, never arbitrary URLs or executable content. Asset retrieval uses server-generated IDs, validated paths and the current deployment's access boundary. Optional video routes exist only when explicitly enabled.

## Errors, traces, costs and artifacts

Error envelope: `{code,message,details,trace_id,retryable}`. Validation errors are typed/redacted; revision conflict returns 409 with expected/current revision and recovery information. Exact code enum and success DTOs will come from Pydantic/OpenAPI in B0/B1.

Trace contract must include increasing event ID, run/campaign IDs, revision, timestamp, stage, event type and short redacted decision. Never expose internal reasoning, credentials, raw transcripts by default, or signed media URLs. Disconnect only stops delivery, not the job.

API call records distinguish transport attempts from schema repairs and include model, trace, queue wait, duration, retries, status, returned usage and unknown usage. Estimate USD from the supplied list-price schedule; actual billing/entitlement remains separate. Configured dated FX is required for INR.

Export manifest includes safe filenames, campaign/fact revisions, language/channel, SHA-256 bytes, fact/dependency/content/render hashes, renderer/font/prompt versions, mode, and artifact provenance. Saved outputs additionally identify original provider/capture time. Final approval references persisted bytes, not client-reported render hashes.

B0 health/error/trace/cost schema version is b0.1; app version 0.1.0. Campaign prompt/schema/scoring/renderer versions remain unimplemented. Source guide is preserved byte-for-byte.
# Frontend redesign planning note — 2026-10-09

No API/schema changes are proposed. Existing client operations, revision guards,
work admission, idempotency keys, polling, SSE replay and export authorization
are inventoried in [FRONTEND_REDESIGN_PLAN.md](FRONTEND_REDESIGN_PLAN.md).
The planned hash stage navigation preserves the campaign query parameter and
component state. Implementation is pending the supplied prompt's explicit “go”.


F1: `feed` is an additive 1080×1350 poster size using supported 1:1 background generation. Poster batches remain at most three formats. Active renderer is canvas-commercial-b1.0; old renders remain historical and cannot inherit approval. Individual authorized file export accepts saved_view (default false). Approval retrieves the exact selected export; retrieving previously approved output is explicit.

Manual social publishing: GET/PUT /api/social-profiles stores optional validated Instagram/Facebook/WhatsApp URLs with an independent optimistic settings version. Migration 009 is single-owner/global across campaigns. No fact/hash invalidation or provider call. Meta UI is removed. Profile buttons require a current authorized export pack; existing draft and file export contracts stay intact.

## Intent recovery addition — 10 October 2026

`PUT /api/campaigns/{id}/facts/draft` accepts optional `transcript` (1–2000
characters) for explicit owner manual entry. Existing payloads remain valid.
This saves an editable draft without inference or automatic approval. A changed
transcript invalidates proposed forms and obsolete source spans; facts become
owner-entered/derived, warnings require fresh review. Revision and post-lock
guards remain. Genuine R1 failures keep `INTENT_UNAVAILABLE`, with an allowlisted
reason in the error details and a sanitized durable recovery notice. R1's internal
transport contract excludes code-derived date/day proposals while retaining all
three outcomes; the public canonical fact interfaces continue to contain dates.
