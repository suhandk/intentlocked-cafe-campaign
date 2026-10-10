# Requirements and acceptance evidence

<<<<<<< HEAD
## Website wizard recovery — 10 October 2026

| Observed requirement | Feature / invariant | Evidence |
|---|---|---|
| Optional incomplete hours must not trap navigation | Keep edits in memory, navigate freely, target the invalid step; invalid drafts cannot generate | Reproduced before fix; final browser recovery PASS |
| Keep edits through save failures | Bounded request, sequential latest-snapshot saving, Retry save; stale revision cannot overwrite current | HTTP 503 recovery, controlled delayed response/rapid edits, 409 unit handling; backend version tests PASS |
| Permit a deliberate exit | Keep editing or explicit discard and close; saved data is preserved | Browser incomplete-menu discard/reopen PASS |
| Preserve website generation and approval rules | Existing renderer, locked offer, Guardian, current ZIP, HTTPS/exact-hash hosting approval | Real browser website ZIP + MP4 integration PASS; live publication not performed |

[Current diagnosis](WEBSITE_RECOVERY_2026-10-10.md).

## Current hackathon workflow extension — 10 October 2026

| Source requirement | Actual implementation / invariant | Executed evidence / limit |
|---|---|---|
| Latest owner choice: OpenRouter Seedream images | Gateway config, shared server-only OpenRouter key for text/images/QA; raw capability checks before charged POST; exact model remains allowlisted | Public capabilities 200; one real image request 402 PAYMENT_REQUIRED, no retry; image bytes/vision NOT_TESTED; [switch evidence](SEEDREAM_SWITCH_2026-10-10.md) |
| Owner keeps GPT-4o mini text, requests direct OpenAI images | Config + one bounded client; separate keys/endpoints, no secret in frontend; missing key HTTP 422 before jobs/calls | Raw image/size/offline tests PASS; real text/tools PASS; real OpenAI image/vision NOT_TESTED |
| Fix approval without bypass | R7 independent typed extraction, audience/eligibility guidance, exact evidence/provenance comparison, source/hash approval unchanged | Four actual LIVE English audits and simulated test-owner export PASS; old failures retained |
| Keep copy repair finite and facts concealed | R4 closed expression feedback, safe date/disclosure grammar, full Guardian per attempt | Live 3/3 channels PASS; bounded retry/no hidden fact values regressions PASS |
| Real video without an AI video model | Persisted local_video jobs, checksum-verified encoder, exact poster pixels, independent review/hash approval, export rechecks | Genuine browser MP4/playback/download/reload PASS; cancellation, stale facts, source changes, tamper and forged approval blocked |
| Website generation remains usable | Complete valid rows before autosave; visible incomplete edits; existing version guard; static ZIP and optional hosting separation | Browser hours/menu completion and ZIP PASS; real hosting publication NOT_TESTED |
| Accurate traces/costs/modes | Provider/endpoint/report-fee data, strict token projection, actual worker provider labels, explicit local/MOCK/LIVE source | Current-profile MOCK smoke and network denial PASS; LIVE detailed usage PASS; invoice unknown |
| Recovery and persistence | Existing durable storage, finite budgets, SSE replay, idempotency, approvals and saved-mode rules | 635 backend / 26 browser PASS; production restart retains approved test MP4/website hashes |

[Diagnosis, raw contracts and run commands](HACKATHON_VERIFICATION_2026-10-10.md).

## Surface failure recovery — 10 October 2026

| Observed requirement | Feature / invariant | Evidence |
|---|---|---|
| SURFACES_UNAVAILABLE despite complete facts | Bound R2 fact/language/case wire contract; typed constraints; genuine failure remains possible | LIVE reproduction failed before fix; after-fix ten English forms PASS in one call |
| Optional questions must not force invented facts | Unknown conditions omitted; exact value/scope validation unchanged | Extra unknown form rejected; actual unknown conditions unchanged |
| Retry must use saved canonical-confirmation revision | Refresh on known failure; fresh operation/key; old generic retry still rejected | Two MOCK browser retry/explicit lock paths PASS |
| Concurrent edits require fresh review | Only unchanged facts retain confirmation; stale/cancelled results cannot commit | Changed 20%→15% browser confirmation case and existing stale/cancellation regressions PASS |
| Preserve approval boundaries | Proposed forms remain editable; exact owner-reviewed versions/forms still required | 610 backend tests, five MOCK browser checks PASS; real owner approval NOT_PERFORMED |

[Details and limitations](SURFACE_RECOVERY_2026-10-10.md).

## Intent failure recovery — 10 October 2026

| Observed requirement | Feature / invariant | Evidence |
|---|---|---|
| INTENT_UNAVAILABLE after a normal brief | R1 wire permits only evidence-linked proposal keys/types; server owns dates; finite repair | Actual LIVE reproduction failed before fix, then one-call draft after fix; date clarification remains explicit |
| Keep owner work after model failure | Retry retains visible input; explicit manual draft saves source without inference; reload persists it | Two MOCK browser regressions PASS |
| Manual fallback cannot grant approval | Unlocked owner facts, invalidated old evidence/forms, stale save rejection, normal form-review and lock | Targeted backend regressions PASS; no real owner approval performed |
| Evidence cannot be fabricated | Unique exact quotes can recover coordinates; ambiguous or absent quotes rejected | New recovery and strengthened freeze regressions PASS |

Details and verification limits: [INTENT_RECOVERY_2026-10-10.md](INTENT_RECOVERY_2026-10-10.md).

## Screenshot failure recovery — 10 October 2026

| Observed requirement | Feature / invariant | Evidence |
|---|---|---|
| Zero-channel prediction with non-selected hero | Explicit saved audience group; original baselines, single language/audience; no score without evidence | Non-hero API and browser PASS; mixed groups rejected |
| Poster waiting after failed copy | Exact approved disclosure slots, full Guardian check, focused repair feedback, explicit unfinished retry | Saved replay repaired G05-only draft; malformed/unknown ID/unsafe wording tests PASS |
| Repeated VIDEO_VALIDATOR_MISSING | No video capability advertised/admitted; old errors/history retained; no image-to-video substitution | Duplicate direct requests HTTP 422 before jobs/calls; browser controls disabled |
| Owner keeps GPT-4o mini and Flux Schnell | Actual model health; image dispatch blocked when no verified transport; explicit local illustration | Current public catalogues checked; LIVE copy partial; real local PNG hash/preview PASS |
| Keep audits/approval/export protected | Every new result remains draft; exact hashes and existing audit gates | 589 offline backend and four browser regressions PASS; actual PNG header pending |

Detailed limitations, changed files and primary sources:
[SCREENSHOT_RECOVERY_2026-10-10.md](SCREENSHOT_RECOVERY_2026-10-10.md).

=======
Website OpenRouter update: selected Qwen3 Coder Flash, public catalogue verified;
strict design schema and code-rendered facts retained. Fourteen added design tests,
597 full backend tests, nine client cases and two HTTPS browser cases pass. Optional
sections, images, multilingual rendering, mobile layout, ZIP and protected publish
flow are checked. Authenticated OpenRouter/Netlify and native review remain pending.
See [executed website evidence](WEBSITE_OPENROUTER.md).
>>>>>>> e1bceadbfb88804d229fe0898f7d41be4bd5116f

## Campaign / prediction / poster / video debug — 10 October 2026

Startup migrations/types, facts lock, 27-cell generation, prediction trajectory,
four native export sizes, long Kannada/font/logo/CORS cases, hash approval/export,
reload and cancellation/retry have current automated evidence: 583 backend tests,
21 MOCK browser cases, critical Guardian/slot branch coverage 100%. Tests do not
establish live provider support or native review. Video is explicitly unavailable
and direct attempts are rejected before dispatch. Live gateway is unreachable and
independent real-image QA remains unverified. See [debug evidence](WORKFLOW_DEBUG_2026-10-10.md).

## Owner model replacement — 2026-10-09

| Owner requirement | Implementation | Evidence |
|---|---|---|
| Image: `nb/nanobanana-flash` | Exact configuration allowlist; raw size/n/url image contract | Controlled HTTP/download tests and mock smoke PASS; real auth NOT_TESTED |
| Text and reasoning: `ollama/gpt-oss:120b` | All text roles share InferenceClient; JSON/Pydantic validation | 521 offline backend tests PASS; five MOCK browser tests PASS |
| Create key fields to fill later | Ignored .env and safe .env.example; server-only secret types; distinct gateway/upstream tokens | Private configuration regression PASS; frontend build secret scan PASS |
| Preserve truth and approvals | Unsupported visual QA blocked; no new video model; original saved provenance retained | Unsupported transport rejection, blocked image, tamper tests PASS |
| Preserve calendar and social flow | Existing /calendar, manual profile links, exact authorized export | Planning/social/approval browser regressions PASS |

Official source verification and all authenticated NOT_TESTED checks are detailed
in [the migration guide](MODEL_PROVIDER_MIGRATION.md). Historical reports below
must not be read as verification of the replacement models.


## Website V2 addendum

Wizard persistence/read-only facts/required and invalid inputs/token-free generation,
ZIP export, credential masking/storage exclusion, terminal invalid-token handling,
current hash approval, verified-before-Published, encrypted/delete token behavior
and campaign isolation have automated evidence. Backend website cases: 45; client
unit cases: 9; HTTPS wizard scenario: 1. Full backend regression: 553 passed.
Netlify transport is mocked; real provider/account publishing and native reader
review remain unverified. See [implementation and tests](WEBSITE_V2_IMPLEMENTATION.md)
and [verification record](evidence/website-v2-verification.json).

## Supplied calendar/planning references — 2026-10-09

| Owner requirement / source | Implementation and visible behaviour | Actual evidence |
|---|---|---|
| Plan campaigns before generation; calendar screenshot and page (1).tsx | `/calendar`, Plan ahead header link; real aligned months, saved briefs, upcoming/due, IST times | Planning browser navigation/save/reload/edit/mobile PASS; no invented events or analytics |
| Reuse saved campaign preferences; client.tsx | Planner.start loads tone/theme/colours/languages only; fresh draft opens Speak/Type | Locked-source facts remain unknown; no old approvals/must_say/offer copied; atomic interruption and duplicate start PASS |
| Continue after final approval; existing O1/O3 boundaries | DeliveryPanel exact selected items link to original or new plan; export service derives readiness | Audit/approval required; expiry and stale revision checks PASS; original future-plan attachment browser PASS |
| Manual social flow; existing owner instruction | Linked export/profile workflow, explicit owner-reported posted state | Pending direct-API posting rejected; 490 backend and four mock browser regressions PASS; real social posting NOT_TESTED |

Analysis, commands and limits: [CONTENT_CALENDAR.md](CONTENT_CALENDAR.md).

Latest [deployment verification](DEPLOYMENT_CHECK.md): local startup, migrations,
backup/restore, frontend checks and Guardian coverage pass. Clean installation,
public deployment and human/live release checks remain pending.

## Live response repairs — 2026-10-09

| Obligation | Evidence | Status |
|---|---|---|
| R1 exact source facts; R2 typed reviewed forms | Genuine live capture; bounded domain repairs; test_live_response_repairs and existing attack tests | R1/R2 authenticated PASS; human review pending |
| R3 eligible strategies, R4 stored matrix with no fixture substitution | Live campaign e0163b2ee5824f9aaeedcee02796168a, call records and timestamped reports | R3 PASS; matrix PARTIAL, 9/27 ready |
| Slot grammar remains a protection boundary | Connector roles, slot barriers, wrong-role/entity/wrapper positive/adversarial tests | 419 backend tests PASS, Ruff PASS |
| Native/G14/final live export/rehearsals | LIVE_REPAIR_VERIFICATION.md lists manual/live limits | PENDING; no production/hackathon readiness claim |

Details: [live repair verification](LIVE_REPAIR_VERIFICATION.md).
## Owner-requested optional API delivery — 2026-10-09

| Requirement source | Implementation | Verification |
|---|---|---|
| API_Inegration.md A/B: preserve architecture and modes | Separate Meta raw client; existing FastAPI/settings/SQLite; migration 008; disabled-by-default settings | Config validation, network-denying mock suite; live/documentation checks NOT_TESTED |
| C/D: exact approval and explicit owner confirmation | MetaPreview/MetaConfirm; ApprovalService.export reused before preview/attempt; account + preview hash binding | Forged approval/confirmation, stale revision, consent, audit, changed account, payload-key tests |
| E: supported initial adapters | WhatsApp text/image/static template; Facebook Page text/photo; Instagram Facebook Login feed container/poll/publish | Four raw HTTP shape/media tests; finite poll stop; authenticated shapes NOT_TESTED |
| F: no duplicate external side effects | Existing WorkService + dispatch journal; no generic delivery start/retry; unknown POST outcomes | Duplicate clicks, replay, queued fact change, timeout, restart, cancellation tests |
| G: media/webhook/security | Opaque expiring byte grants, exact JPEG preview/hash, signed/deduplicated callbacks, local owner authorization | Media expiry/hashes, webhook forgery/replay/order, owner route denial, secret redaction |
| H/J: deliberate usable flow and honest report | Minimal Optional API delivery panel; setup/report scripts; redacted evidence | Browser confirmation/reload/mobile verification; actual outcome in meta-browser.json when executed |

Live activation is blocked until actual platform/account checks pass. Mock evidence
does not certify current API versions, entitlements, permissions or public deployment.

## B7 source-to-feature evidence — 2026-10-09

| M0 / B7 obligation | Implementation and visible behavior | Actual evidence |
|---|---|---|
| Eight panels, owner workflow, responsive statuses | CampaignFlow navigation/empty prerequisites; existing matrix/prediction/Guardian/delivery; neutral CSS; optional drawers | workflow/facts browser paths, accessible skip/input, 390px screenshots |
| Durable work, cancellation, bounded admission/retries | migration 007; WorkService; original native runs; input/deadline/step/call persistence | test_work: duplicate keys, capacity 2+16, cancel running/queued/late response, fake-clock Retry-After, budget/deadline, timeout, stale revision |
| Reload / page close / restart / SSE replay | workflow-update read refresh; WorkSnapshot; raw stream journal | b7-browser-run.json; b7-recovery.json real killed backend / identical ready cells and asset bytes / Last-Event-ID / unchanged costs |
| Honest partial failure and media uncertainty | ready generation cells carried on retry; visible deterministic fallback notice; RETRY_UNSAFE | partial-language retry adds only one call; image timeout submits once; no fake live outcome |
| Current / mock / cached distinctions | explicit saved capture view, source/capture/hash metadata, cached export labels | missing-cache browser failure; cached authorized ZIP with source MOCK; test_work approval cannot be bypassed by cached export |
| Accessible voice/type and recovery errors | editable transcript/interim, permission denial guidance, Kannada TTS fallback, error/reconnect/retry controls | browser simulated mic denial / no Kannada voice / keyboard / backend outage; native review NOT_TESTED |
| Secrets / traces / costs | server-only client; private scan; persisted in-flight attempts updated by ID; action/validation traces | secret sentinel/redaction tests; production build scan; no transcripts or internal reasoning in events |

The three campaign objectives remain mapped to B3 generation, B5 prediction and
B1/B2/B6 intent/approval boundaries below. B7 connects their existing services.
Public release and authenticated/manual review remain B8 gates.

## B6 source-to-feature evidence, 2026-10-09

| Source requirement | Implementation and visible behavior | Evidence |
|---|---|---|
| M0 ledger + R8/B6 proposal classification | change.py/change_service.py, R8.md: mutable/immutable/mixed/rejected, diff, confirm/forms/publish | test_delivery.py: untrusted targets/values/evidence, mixed cancellation, conflict, rollback/idempotency |
| M0 dependencies and intent preservation | ledger.py, migration 006: policy conditions, eligibility, per-language forms, immutable history/current links | numeric/structural/tone/surface-language preservation and late optimizer tests |
| M0 Red-Team modes | delivery_routes.py + DeliveryPanel: instruction proposes, direct copy checks Guardian | direct API 25% outcomes and unsupported claims tests |
| M0 server approval + export | approval_service.py + DeliveryPanel: blinded audit, owner observed hash/warnings/native check, exact bytes/manifest/copy/draft/ZIP | forged/pending/stale/tampered/missing audit/font/layout/dangling source tests; real browser publication/approval/export/reload |
| M0 WhatsApp safety and provenance | ExportPack current/source versions, original approval, SHA-256, mode; separate poster URL | b6-browser-run.json timestamped authorized mock manifest; draft sends/attaches nothing |

Native Kannada/voice and authenticated R8 remain NOT_TESTED. Simulated reader
evidence is labeled MOCK. Public release/reconnect/cancel integration remains B7/B8.

## B5 evidence, 2026-10-09

| Requirement | Actual implementation/UI | Evidence |
|---|---|---|
| Honest rules and scores | scoring.py; PredictionPanel feature details, fixed chart, null missing judgments | Threshold/mask, AB/BA mapping, ties, all-identical/order disagreement, missing/invalid batches |
| Frozen comparison | optimization models/repository/service; original baseline and five saved personas | Stable remapping; accepted second-round comparison keeps original; no-rebase guard; full cache keys |
| Finite decisions | R6 + code edits, Guardian then R7 then R5, 48 calls/480 seconds/2 or 3 rounds | Immutable edits, Guardian-before-judge, 429 accounting, deadline, no-gain, exact cap, cancellation/restart/stale cases |
| Retain accurate selection | Transactional accepted/rejected rounds and OptimizedVariant | Real MOCK browser score→critique→edit→verify→compare→accept→no-change stop; duplicate start/reload |
| Blinded semantic evidence | R7 text-only payload and code comparison | Payload excludes facts/scores; forged evidence, missing/ambiguous/unknown facts, mismatch, unavailable audit, warnings |
| Actual image-text provenance | PNG hash + render-input equality, canvas glyph bounds, poster audit | Three real retained PNG sizes hash-matched; audits persisted; contrast/offer measurements; tamper blocks |
| Transparent incomplete scope | Unscored IDs, MOCK/cache labels, native/vision/approval flags | Two non-hero variants remain unscored; native/remote vision NOT_TESTED; no owner-approved export |

G5 is explicitly mock-verified. Text comparison scores are not poster/customer/CTR
performance. Native Kannada and authenticated Agnes remain pending. B6 must bind
owner approvals and warning acknowledgments to current audits/artifacts.

## B4 evidence, 2026-10-09

| Requirement | Implementation / visible behavior | Evidence |
|---|---|---|
| Text-free faithful art | art_context/service + T1/R9; abstract-only allowed brief | Safe payload, all QA flags, uncertain/malformed QA, bounded candidate/fallback tests |
| Reuse and provenance | Art-key cache, native ratios, persisted backgrounds and costs | No per-cell image calls, second audience costs unchanged, numeric edit reuse test |
| Safe persistence | media.py + art_storage, hash-addressed PNGs, restricted routes | MIME/redirect/expired URL, bomb/size/SVG/animation/tamper and API forgery tests |
| Actual Kannada posters | shared canvas renderer, bundled licensed Noto, measured grapheme wrapping | Real PNGs at 1080×1080, 1080×1920, 1200×630 opened for inspection; long café/Kannada and offer forms |
| Layout failures block | Font loading/deadline, ink bounds, safe areas, contrast, reserved logo space | Actual slow/missing font and overflow browser checks; bad metrics/bytes block persistence |
| Exact preview/file identity | Server renders and validates final bytes; UI uses asset ID directly | SHA-256 and dimensions matched; same-origin canvas pixel access; reload persistence |
| Honest pending release | G14/approval_ready=false, B4_VISUAL_REVIEW.md native section | Native observations remain PENDING; no approved export or live QA claimed |

## B3 evidence, 2026-10-09

| Requirement | Implementation / visible behavior | Evidence |
|---|---|---|
| Eligible hypothetical strategy | generation_models/context/service; three distinct angles/motivations, five persisted personas | Student-only, custom/unknown, invalid R3, stable IDs/reload tests |
| Concealed fact values | Closed R4 projection, slot-only grammar, safe repair codes | Sentinels in facts/brand/transcript absent from captured payloads, including repairs |
| Stored differentiated full matrix | Migration 003, append-only baselines, parsed slots, typed Guardian previews | 27 cells, three languages/channels, distinct audience hooks; reload and restart tests |
| Honest partial failures | Persist queued/running/blocked states and reasons; language-local budgets | Malformed/duplicate/missing/script/literal failures, 429 retry/exhaustion, later-language success |
| Server boundary and races | Current locked snapshot, idempotency, revision/dependency checks | Direct forged API inputs rejected; pending R3/R4 revision races cannot commit late results |
| Visible returned copy | CampaignMatrix selectors and social previews | Browser asserts all 27 headlines against returned stored data, mobile width and reload equality |

G3 is offline/mock-verified. No live-provider, native-language, performance or final
approval claim is made. G14 and the Kannada release gate remain pending.

## B2 evidence, 2026-10-09

| Requirement | Implementation / visible behavior | Evidence |
|---|---|---|
| Preserve approved facts | guardian/slots.py, normalize.py, claims.py, rules.py; Guardian panel | Parameterized adversarial/positive cases, exact offsets, typed role/unit checks |
| Fragment versus complete asset | guardian/policy.py and report.py; mode selector | Missing disclosures block G05; complete text remains INCOMPLETE without G14 |
| Direct backend enforcement | guardian/routes.py loads current locked repository snapshot | Forged fields rejected, stale revisions 409, absent approval/export 404 |
| Honest semantic readiness | Mandatory G14 pending B5; approval_ready always false | Absent/missing G14 cannot authorize approval; B5 contract in GUARDIAN_BOUNDARY.md |
| Native language review | KANNADA_NATIVE_REVIEW.md and visible pending notice | PENDING; no human sign-off |

G2 automated results and commands are in PROGRESS.md and docs/evidence/g2-*. B2
does not complete campaign generation or prediction objectives; those remain later stages.

B0, 2026-10-08. The three product-objective implementations/tests below remain PLANNED. No full campaign objective has passed. B0 supplies the tested foundation listed separately here. Organizer source: `source/HR26_Problem_Statements_Agnes.pdf`, marketing objectives on page 3, model/rules on pages 1 and 4.

## B0 evidence

| Requirement | Implementation / visible behavior | Evidence |
|---|---|---|
| Provider-only/offline policy | backend/config.py, agnes_client.py, mock.py; mode and provider shown by frontend/app/page.tsx | backend/tests/test_client.py: model/base URL rejection, offline network-denied fixtures, cached inference rejection, disabled video |
| Bounded failures and accounting | Agnes client/Queue/Budget, db.py/contracts.py; frontend real cost and trace | 58 total B0 pytest cases including 401/403, 429, 5xx, timeout, cancellation, repair limits, usage unknown/failed-call retention, raw image shape; provider report distinguishes mocks |
| Reproducible foundation and typed API | pyproject/uv.lock; frontend package-lock; main.py; docs/openapi.json; generated frontend types | Backend startup, ruff, strict TS, lint and production build pass; lockfile dependency sync passed |
| Connected basic workspace | frontend/app/page.tsx | Two real-backend browser tests pass, including failure/retry and mobile overflow; screenshots visually inspected |

X01 is implemented and mock-tested; authenticated provider verification remains pending. X02 has client-level implementation/tests; campaign jobs/restart/cross-process coordination are not claimed. X03-X12 remain future or manual gates as individually described below.

## Three required objectives

| ID | Objective | Planned implementation | Visible UI behavior | Acceptance test and gate |
|---|---|---|---|---|
| O1 | Coherent campaign across audiences, languages and channels | `backend/agents/strategy.py`, `backend/agents/copy.py`, `backend/guardian/slots.py`; `frontend/components/CampaignMatrix.tsx` | Three distinct eligible strategies; owner-selected en/kn/kn-Latn and Instagram/WhatsApp/Facebook matrix, plus posters; exact approved facts retained | `backend/tests/test_campaign_matrix.py` and `frontend/e2e/campaign.spec.ts`: 27 selected copy combinations, no duplicate/missing cells, differentiated hooks, correct facts, no unselected channels/languages; reload and partial failure. G3/G4/G7. |
| O2 | Predict relative effectiveness and autonomously optimize | `backend/agents/scoring.py`, `backend/agents/optimizer.py`, `backend/orchestrator.py`; `frontend/components/PredictionPanel.tsx` | Explicit simulated-preference label; real feature/tournament scores, fixed-baseline chart, accepted/rejected edits and stop reasons; unscored groups labeled | `backend/tests/test_optimizer.py`: five fixed paired AB/BA personas, label remapping, ties/missing votes, identical masks, >=6 weighted wins, <3 feature decrease, strict overall gain, BLOCK rejection, best retained/no-gain stop, budgets; UI E2E follows same evidence. G5/G7. |
| O3 | Preserve approved intent through cultural/linguistic adaptation | `backend/schemas.py`, `backend/guardian/`, `backend/agents/reader.py`, `backend/change.py`, `backend/ledger.py`, `backend/approvals.py`; FactsLock/Guardian/Changes/ApproveExport components | Canonical/form approval; case-aware slots; deterministic blocks and blind audit; explicit fact diffs; current vs historical approvals; export gate | `backend/tests/test_slots.py`, `test_guardian.py`, `test_changes.py`, `test_approval_export.py`: >=40 adversarial cases + positive controls; >=90% branch coverage critical logic; 20->15 confirmation/forms; 25% direct-copy block; eligibility conflict; unrelated approvals preserved; stale jobs and export bypass rejected. G1/G2/G5/G6/G7 plus human Kannada review. |

## Cross-cutting requirements

| ID | Requirement / planned location | Required evidence | Status |
|---|---|---|---|
| X01 | Agnes-only allowlist, httpx client, offline mock; `agnes_client.py`, config | Unknown models/startup rejected; mock zero external inference; account report separate | B0 MOCK PASSED; LIVE NOT_TESTED |
| X02 | Queue, retry/repair budgets, redaction, usage/cost; client/jobs | Fake-clock 429/Retry-After, auth no retry, capped 5xx, uncertain media no resubmit, unknown cost represented | B0 CLIENT PASSED; campaign jobs pending |
| X03 | Typed append-only facts, timezone, approval provenance; schemas/db | Missing core blocks; unspecified conditions remain unknown; canonical edits invalidate forms; date-derived weekdays | NOT_IMPLEMENTED |
| X04 | Persisted state, revisions, idempotency, SSE; orchestrator/jobs | Replay increasing IDs/heartbeats; disconnect/restart never duplicates side effects; old revision commit 409 | NOT_IMPLEMENTED |
| X05 | Shared renderer, same-origin media, exact PNG hashes | 1080x1080, 1080x1920 with 250px exclusions, 1200x630; grapheme/font/overflow visual checks; QA fail fallback | NOT_IMPLEMENTED |
| X06 | Full dependency hashes; ledger/approvals/export | Font/layout/surface/policy edits invalidate relevant approvals; transactions and byte-tamper rejection | NOT_IMPLEMENTED |
| X07 | Blinded G14, applicable mandatory checks, warnings | Missing/failed audit cannot display 100% or approve; acknowledgments bound to current warning IDs | NOT_IMPLEMENTED |
| X08 | Browser speech, typed fallback, accessibility | Actual en-IN/kn-IN tests, interim/final editing, mic denied/unavailable, no TTS auto-confirm; keyboard/mobile | NOT_TESTED |
| X09 | LIVE/MOCK/SAVED DEMO OUTPUT distinction | Visible transitions; genuine cached provenance including capture/prompt/fact/artifacts; no fallback concealed | NOT_IMPLEMENTED |
| X10 | Owner-only operations and storage; security/runbook | Loopback/access control, secrets, upload/SSRF/path checks, backup+restore, retention, graceful shutdown | NOT_IMPLEMENTED |
| X11 | Native Kannada review | Named reviewer/date, exact lexicon/forms/posters, findings and corrections; AI back-translation is insufficient | NOT_TESTED |
| X12 | Optional video | Disabled by default; verified enabled model and final playable bytes before success | NOT_IMPLEMENTED; deferred V1 |

At each gate replace planned references with actual paths and evidence. Keep failed, skipped, mock, live and manual results distinct.

| F1 final output recovery / photographic café post | DeliveryPanel, delivery_routes, art_context, T1/R9, canvas.js | Approval shows authorized output; explicit reload retrieval; 4:5 photographic draft | approval-recovery.spec.ts; test_art.py; commercial-canvas-results.json; live poster/audit evidence | PASS implementation/checks; real owner sign-off pending |

| Manual social publishing | social_profiles.py, migration 009, ManualPublishingPanel, DeliveryPanel | Save profile links; authorized poster/description download/copy; explicitly open accounts | test_social_profiles.py; e2e/meta.spec.ts; manual-social-browser.json | PASS offline; real account actions NOT_TESTED |

| Modern café reference style | art_context.py, T1.txt, art_service.py, canvas.js, PosterPanel, ledger.py | Cream/green/gold layout; exact current approved facts; supported coffee subject; versioned historical assets | test_pinterest_posters.py, test_art.py, test_hackathon_media.py; e2e/posters.spec.ts, optimization.spec.ts, hackathon-media.spec.ts; MODERN_CAFE_POSTERS_2026-10-10.md | 74 focused backend and 8 mock-inference browser cases PASS; live new-prompt image/QA NOT_TESTED (last provider POST 402) |
