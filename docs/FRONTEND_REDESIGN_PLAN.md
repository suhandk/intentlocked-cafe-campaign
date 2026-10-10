# Frontend redesign: discovery and implementation plan

Status: **go received; implementation and frontend verification complete**.
Date: 2026-10-09. No product source changed during discovery; subsequent frontend
changes and executed verification are recorded in FRONTEND_REDESIGN_REVIEW.md.

## Scope and source instructions

Requested source: `C:/Users/Suhan/Downloads/CODEX_FRONTEND_REDESIGN_PROMPT.md`.
Its process ends with: “Start with step 1 (Discover) and step 2 (Plan) only.
Do not write code until I say "go".”

Read the actual project context at `docs/source/PROJECT_CONTEXT.md` and M0/B7
in `docs/AGNES_PROJECT_BUILD_PROMPTS.md`; neither is at the root location suggested
in the downloaded prompt. No AGENTS.md was found in the repository inventory.
The redesign is a newly authorized presentation scope after the earlier B8 freeze.
Backend, scripts, database, generated API schemas and service behavior are excluded.
No provider calls are necessary for discovery or the mock redesign walkthrough.

The working tree already contains B8 backend/script edits, test evidence and the
DeliveryPanel consent-race fix. Preserve these. Report redesign changes relative
to this starting snapshot; a whole-tree backend diff cannot truthfully be empty.
Do not revert prior authorized changes to make that check appear green.

## Discovery inventory: files and component ownership

The single route is `frontend/app/page.tsx`; `layout.tsx` supplies metadata and
`globals.css` imports Tailwind 4. `next.config.ts` proxies `/api` to local FastAPI.
There is no router, context store or existing hooks directory. React component
state plus persisted server snapshots are the existing workspace model.

| Existing component/file | Current responsibility | Proposed presentation |
|---|---|---|
| app/page.tsx (Workspace) | health, cost, traces, mode; large hero; CampaignFlow | compact persistent top bar, welcome state, trace overlay |
| CampaignFlow | campaign loading, transcript, facts/forms approval, workflow gate | state owner for Speak and Facts; hash navigation shell |
| VoiceInput + Readback | browser speech, editable interim/final text, TTS fallback | segmented speech language, mic states, counter; existing fallback/consent text |
| FactEditor + factNames | all 12 typed fact editors and evidence | required/condition card groups, clear editable/locked states, time unspecified control |
| CampaignMatrix | strategy, personas, selectors, matrix polling and previews | separate Strategy/Campaign stage views over the same controller |
| PosterPanel | persisted artwork/posters, PNG logo consent, sizes, audits | Poster tab and logo presentation using identical stored artifact URLs |
| PredictionPanel + Trajectory | frozen baseline, bounded optimization, actual scores/votes/audits | focused prediction stage, accessible SVG, KPI/band/timeline presentation |
| GuardianPanel | fragment vs complete-asset diagnostics, findings/provenance | focused diagnostic card with severity and span displays |
| DeliveryPanel | proposal/diff/form publication, red-team, history, exact approvals/export | Changes/Guardian/Approve sections over one retained state owner |
| WorkflowStatus | polling, SSE replay, cancellation/retry, explicit saved mode/export | persistent progress summary plus trace/work drawer |
| lib/campaign-api.ts | typed campaign API and ApiError | preserve request methods, bodies, revisions and routing |
| lib/work-api.ts | workRead, submitWork, routedWork, idempotency and progress events | preserve durable admission, polling, storage keys and routing |
| lib/api.generated.ts | OpenAPI-derived components | unchanged typed source of truth |
| public/renderer/canvas.js + scripts/render-poster.mjs | shared canvas artifact compositor and browser rendering entry | unchanged rendering boundary; UI only previews stored PNG bytes |
| public/fonts | local Noto Sans/Kannada, license files and manifest | retain fonts and licenses; use local faces for UI too |
| e2e/*.spec.ts (8 files) | foundation, facts, matrix, posters, optimization, Guardian, delivery, recovery | update navigation interactions; preserve semantic assertions |
| playwright.config.ts / playwright.freeze.config.ts | browser server and backup recording configuration | preserve existing workflows; isolated redesign screenshot/a11y coverage |

Types already used: Campaign, Fact, Canonical, Lang, Channel, DraftRequest,
LockRequest, Health, Cost, TraceEvent, WorkJob, WorkSnapshot, MatrixSnapshot,
StrategyPlan, GenerationRun, GenerateRequest, TemplateContent, GuardianReport,
ArtSnapshot, PosterArtifact, Audit, RenderRequest, OptimizationRun,
OptimizationSnapshot, DeliverySnapshot, Proposal, FactSurface, ExportPack,
RedTeamResult. Local aliases (Plan/Run/Snapshot/Selection/Group/Forms/etc.) remain
derived from these; no new request or response shapes are proposed.

## State and hook inventory (retain across stage switches)

All existing components use React built-in hooks, not independent custom hooks.
Setters stay paired with their state values; presentation-only state may be added.

| Owner | Every state value | Refs and hook behavior |
|---|---|---|
| Workspace | health, cost, traces, error, loading, saved | useCallback receive/fail; effects for mode and abortable 3-second snapshots/workflow-update |
| CampaignFlow | campaign, transcript, selectedLanguages, selectedChannels, facts, target, tone, forms, acks, canonicalConfirmed, formsConfirmed, dirty, busy, error, message, saved | lockKey, latestReview; receive callback; restore URL/localStorage; layout-effect review guard; workflow-update revision reload without clobbering edits |
| VoiceInput | language, listening, interim, notice | recognition, current; value sync; recognition abort cleanup |
| Readback | notice | speechSynthesis cancel cleanup |
| FactEditor | none (controlled fact/value) | typed onChange callbacks for every canonical kind |
| CampaignMatrix | snapshot, selection, language, channel, audience, busy, error, loaded, reload | pendingRequest, submitting; receive callback; workflow-update and abortable active-run poll |
| PosterPanel | art, variantId, chosen, source, logoId, file, reviewed, busy, error, refresh, audits | reload callback; workflow-update; abortable assets load |
| PredictionPanel | snapshot, language, error, busy, reload, posters | pending, submitting; workflow-update and stopped/active-run poll |
| GuardianPanel | template, mode, language, channel, report, error, busy | generation ref prevents stale reports after editor changes |
| DeliveryPanel | snapshot, proposal, text, mode, result, forms, confirmed, formsApproved, selected, warnings, native, owner, history, pack, busy, error, message | guarded, key; load callback; initial and workflow-update delivery reload |
| WorkflowStatus | snapshot, error, connected, events, capture, savedExport, reload | retryKeys, previousSignature; 2-second job polling, EventSource replay, deduplication and cleanup |

Preserve `intent-locked-campaign`, campaign query parameter, `intent-work-*`
request keys, and `intent-stream-*` cursor. Existing revision-dependent component
keys must still reset obsolete approvals/drafts when facts change. Hash navigation
must not replace query parameters or override unsaved state.

## Complete API/subscription reachability checklist

Prefix C = `/api/campaigns/{id}`. Existing calls remain behind existing helpers.
These are discovery entries, not claims of a fresh end-to-end pass.

| Surface | Existing operations that must remain reachable |
|---|---|
| Top bar / connection | GET `/api/ready`, `/api/cost`, `/api/traces`; manual refresh/retry and periodic refresh |
| Speak / Facts | POST `/api/campaigns`; GET C; POST C/intent; PUT C/facts/draft; POST C/facts/surface; POST C/facts/lock with reviewed versions/forms, acknowledgments and idempotency |
| Strategy / Matrix | GET C/matrix; POST C/strategy; POST C/generate; progressive polls; selection reset/idempotency and reload |
| Posters / logo | GET C/assets; POST C/logos with PNG bytes, revision and owner consent; poster_batch work for selected sizes/source/logo; GET `/api/assets/{id}` for exact preview/draft downloads; poster_audit work targeting exact poster |
| Prediction | GET C/optimization; POST C/optimize; active-run polls; poster_batch for retained square; actual trajectory, score formula, votes, sensitivity, rejection reasons and provenance |
| Guardian diagnostics | POST `/api/guardian/check` with fragment/asset mode, template, language, channel and revision; findings, missing G14 and fact-to-span provenance |
| Changes / versions | GET C/delivery; POST C/change; POST C/change/confirm for confirm and cancel; POST C/change/{proposal}/surface; POST C/change/publish; GET C after publication; saved proposals, versions and ledger from snapshot |
| Red-team | POST C/red-team in instruct_ai/edit_copy modes; returned proposal and Guardian report |
| Approval / export | POST C/delivery/{item}/audit; poster_batch for changed square; POST C/approve with observed hashes, warning/native/owner consent; GET C/export; GET C/export.zip; authorized poster URLs, clipboard and server-returned WhatsApp drafts |
| Work / recovery | GET C/work; POST C/work; GET `/api/work/{job}`; POST `/api/work/{job}/cancel`; POST `/api/work/{job}/retry`; GET C/saved-output; saved delivery read and authorized ZIP with saved_view=true |
| SSE and events | EventSource `/api/stream/{campaign}?after={cursor}`; workflow events/cursor replay; workflow-update polling/completion notifications; workspace-mode cached label notifications |
| Browser capabilities | microphone start/stop/abort, permission/unavailable fallback, editable interim words; TTS installed-voice check/readback; localStorage/sessionStorage; clipboard; approved external WhatsApp link |

Durable routing covers intent, forms, strategy, generate, optimize, background,
render, change, red_team, item_audit and change_forms. Preserve direct submitWork
poster_batch/poster_audit calls and capped failures; switching views never submits
work again. Cached inference/approval controls remain read-only; only existing
authorized saved-export paths remain usable.

## Baseline evidence

Launched the existing production Next build on loopback port 3000 against the
already running MOCK backend. Playwright Chrome captured the empty workspace;
no campaign generation or live inference was invoked. All captures are real.

| Viewport | Document width | Screenshot |
|---|---|---|
| 1440 × 960 | 1440 | [Desktop](evidence/redesign-baseline-1440.png) |
| 820 × 960 | 820 | [Tablet](evidence/redesign-baseline-820.png) |
| 390 × 960 | 390 | [Mobile](evidence/redesign-baseline-390.png) |

Capture metadata: [baseline JSON](evidence/redesign-baseline.json).
Desktop image visually inspected. Baseline covers the starting screen, not an
eight-stage walkthrough. Existing saved browser evidence remains separate.

## Proposed component tree and files

Workspace (health/cost/mode) → WorkspaceShell (top bar, stepper, sticky actions,
hash/keyboard navigation) → CampaignFlow (existing fact controller) → focused
stage containers. CampaignMatrix retains strategy/matrix controller and exposes
separate views; PosterPanel and PredictionPanel remain owned there. DeliveryPanel
retains change/red-team/approval controller and exposes its three views.
WorkflowStatus stays mounted to supply work state and replay, presented in the
trace/work drawer. Use context only for presentation navigation and metadata,
not a second store for canonical facts or approvals.

Retain controllers when stage content is hidden; avoid remounting on navigation.
For costly presentation pieces, lazy-load on first visit then preserve mounted
state. Facts revision changes retain the existing explicit key reset behavior.
Drawer/modal focus trapping, Escape, focus restoration and background inertness
must not disable saved-export links accidentally.

Create `components/workspace/` shell/navigation/stage/trace components,
`components/ui/` reusable primitives, and a small presentation navigation hook.
Modify page/layout/globals and the nine existing component files listed above.
Tailwind 4 theme tokens belong in CSS `@theme` plus semantic CSS variables; do not
introduce an unused Tailwind 3 config. Add only exact pinned permitted dependencies
needed for motion/icons; update package.json and package-lock together. Use local
Noto typography rather than a network font dependency. Gate UI-kit via `?uikit=1`
in development, with no additional route.

## Vertical slices and verification

1. Semantic cream/forest/terracotta tokens and reusable control/card/status/dialog
   kit; local fonts, focus rings and reduced-motion helper; dev-only UI kit.
2. Persistent shell, welcome, gated hash stepper, mobile chips/footer and trace
   drawer; keyboard navigation. Back/forward works without losing query or drafts.
3. Speak/Fact views: chips, mic states, ordered fact/condition cards, evidence,
   friendly unspecified time, truncated/copyable hash, language-tab form review.
4. Strategy/Matrix/Poster views: differentiated real strategies, grouped selectors,
   computed counts, missing/blocked combinations, device previews and provenance.
   Keep draft downloads distinct from server-authorized exports.
5. Prediction/Guardian/Changes/Approval: actual scores/bands/changelog, severity
   and span displays, immutable confirmation modal with exact diff/scope, preserved
   fields/history, live checklist and explicit disabled reasons, real export tiles.
6. Purposeful transition/motion pass, responsive/a11y pass, complete regression.

After each slice run frontend typecheck, lint and build; record real exit/output.
Add navigation-aware Playwright checks while preserving existing safety assertions.
Final screenshots: eight stages + immutable modal + trace at 1440/820/390. Verify
keyboard/focus, reduced-motion, overflow, local Kannada rendering, async partial
results, revision invalidation and blocked approval/export. Run full mock flow and
explicit saved read-only/export flow separately. Genuine cached/live provider
readiness is still limited by the previously recorded R1/R2 failures and native
review; the redesign cannot turn those into success.

Run bundle secret checks and a browser accessibility measurement where tooling
permits. Report Lighthouse's actual scores or “not measured”; do not substitute
unit tests for native Kannada observations. Update INTERFACES, PROGRESS and
DECISIONS with executed results and known gaps. Final report maps every inventory
entry to verified reachability or an explicit gap.

## Risks and interpretations

- Controls spanning shared owners must be split at render boundaries, not by
  copying service state. Hidden tabs do not auto-approve, auto-confirm or regenerate.
- BLOCK styling always says BLOCK with icon/text. Counts come from real reports.
  Missing semantic audits and native review remain blockers, not successful checks.
- Current diagnostic footer has obsolete B4/B5 wording. Correct only that UI copy
  to describe current audit readiness, without implying all audits passed.
- The prompt's cost wording “currently free” is not an account-verified billing
  fact. Preserve M0's list-price/actual-billing-unknown distinction.
- No invented campaign dropdown contents, uncertainty bands, integrity scores,
  progress estimates or arbitrary brand persistence endpoints. Use current schema
  data. Unknown optional metadata gets an honest empty state.
- Brand logo remains its existing reviewed PNG upload; canonical brand edits stay
  on existing fact-draft/change paths. Backend feature proposals are documented,
  never implemented as part of this frontend scope.
- English chips must reflect the existing selectable-language contract; do not
  silently force an additional language or mutate saved campaigns on navigation.
- Desktop 1.5-screen guidance is a layout goal. Long reviewable facts/forms/output
  collections may scroll within focused stages; do not hide evidence to meet it.
- Native Kannada and speech-device validation still require actual people/devices.
  No redesign screenshot is a human sign-off.

Executed outcomes are recorded in
[FRONTEND_REDESIGN_REVIEW.md](FRONTEND_REDESIGN_REVIEW.md).
