# Frontend redesign review

Implementation date: 2026-10-09. Scope: Next.js presentation and navigation.
The user's explicit **go** authorized implementation after discovery.

## What changed

The long stacked page is now an eight-stage workspace with a welcome screen,
persistent mode/cost/work-time header, desktop stepper, mobile progress rail,
sticky Back/Continue controls, hash history and keyboard navigation. Controllers
remain mounted across stage switches. Revision keys still invalidate obsolete
edits and approvals. No additional page route, login or posting integration.

Facts have ordered required/condition cards, owner evidence, status/version
badges, clarification answers, explicit unspecified time, a readable hash with
copy/expand controls, and canonical/wording language tabs. Owner brand colors,
theme and restrictions use the existing editable-facts API before locking.
After lock, supported changes use the existing reviewed change pipeline.

Strategy shows actual hypothetical audiences/personas and selected combination
counts. The matrix has audience/language tiles, channel tabs, distinct returned
previews, fact-span highlights and explicitly labeled draft copy/downloads.
The Poster tab uses exact persisted PNGs and existing reviewed-logo upload.
Preview channel choice survives reload; previews stay browsable in saved mode.

Prediction uses actual baseline/retained scores, asymmetric or ± simulated
sensitivity, feature bars, trajectory and accepted/rejected rounds. Guardian
keeps fragment and complete-asset diagnostics separate, displays real severity
and source offsets, and never paints a BLOCK ring green. Editing red-team input
invalidates its old displayed verdict.

Immutable changes open a focus-trapped before/after modal with server-returned
affected-item counts. Approval explains missing audits, BLOCKs, native review,
warnings and owner consent; export still requires server authorization. Trace
and durable cancellation/retry live in a persistent drawer. API errors retain
returned codes/trace IDs; job failures show their actual work ID. Unknown IDs,
usage, billing and results are not invented.

## Verification status

Typecheck, lint and production build **PASS**. The full browser run passed all
**17 original regressions**; its extra screenshot case had a preview-label
mismatch. After correcting it, **3 targeted checks PASS in 1.2 minutes** (brand
draft, matrix recheck, full responsive/modal/trace/saved/reduced-motion review).
This verifies **19 unique browser cases across the runs**, not one fabricated
19-test run. Earlier failures remain preserved separately.

Lighthouse accessibility measured **100** on the welcome screen and **all eight
stages**. The initial welcome 93 and Facts 94 reports are retained; missing
button naming, contrast and heading order were fixed and remeasured. Screenshots
cover eight stages, modal and trace at 1440/820/390. Actual exported Kannada PNGs
were opened; native semantic review remains pending.

The final frontend build secret scan passed **142 files**; the scoped repository
scan passed **561 files**, including the actual configured-key check without
printing the key. The backend/scripts tracked diff is byte-for-byte unchanged
from redesign start. Machine-readable results and lock hashes:
[redesign-verification.json](evidence/redesign-verification.json).
 The clean lockfile install completed with **387 packages**;
install scripts were explicitly disabled. An upstream eslint deprecation remains.

The implementation is tested with Node **24.19.0**, npm **11.16.0**, Next
**16.4.0**, React **19.3.0**, TypeScript **5.9.3**, Tailwind **4.3.3**,
framer-motion **12.23.24**, lucide-react **0.468.0**. Motion transitive dependencies
are explicitly overridden to motion-dom **12.23.23** and motion-utils **12.23.6**
after the first production build exposed incompatible exports from a newer
transitive release. The lockfile records the actual resolved graph.

## Inventory reachability

The full pre-change inventory remains in
[FRONTEND_REDESIGN_PLAN.md](FRONTEND_REDESIGN_PLAN.md). Executed checks establish the following reachability:

| Inventory group | Evidence / verification |
|---|---|
| ✓ health/cost/global trace and retry | foundation regression + persistent trace drawer |
| speech/interim input/TTS fallback | facts and workflow permission/unavailable tests; real microphone/native speech remains manual |
| ✓ extraction/draft/forms/atomic lock | facts regression; brand preference and unsaved-navigation test |
| ✓ strategy/personas/selection/generation | 27-cell matrix regression; exact returned multilingual previews |
| ✓ assets/logo/background/render/audit | actual PNG dimension/hash/font/CORS/overflow/logo regressions |
| ✓ optimization/retention/scoring/audit | optimization regression, actual saved rounds and exact retained PNGs |
| ✓ fragment/asset Guardian and provenance | Guardian regression, pending G14, exact displayed Kannada |
| ✓ mutable/immutable proposals/forms/history | delivery regression, modal and atomic publication |
| ✓ owner/warning/native consent and authorized export | delivery regression and saved-mode disabled controls |
| durable work/poll/SSE/cancel/retry/idempotency | workflow regression, reconnect and page-close/reopen without new costs |
| ✓ saved output and captured-source labels | explicit saved-mode regression; original source remains MOCK where applicable |
| ✓ keyboard/focus/responsive/reduced motion | redesign browser review and screenshots |

## Running and reviewing

Start the existing FastAPI service on loopback port 8000 in the intended mode,
then from `frontend`:

```powershell
npm ci --ignore-scripts
npm run typecheck
npm run lint
npm run build
npm run start
npm run test:e2e -- --workers=1
```

`npm run dev` also enables the component gallery at `/?uikit=1`; production
does not render that gallery. No new route is created. Use `Ctrl/Cmd+K` for quick
navigation, `Ctrl/Cmd+J` for trace, `[`/`]` for stages outside editors, and Escape
to close dialogs. Campaign ID remains in the query string; active stage is in
the hash. Saved mode is read-only for inference/approvals. Authorized saved ZIP
downloads remain in the work drawer with captured-source metadata.

On this host npm is not on PATH. Commands were executed using Node's bundled
pnpm launcher with `dlx npm@11.16.0`; direct project CLI entry points were used
for TypeScript, ESLint, Next and Playwright. No compatibility claim depends on
the default Python 3.12 executable.

## Limits and manual gates

- All redesign workflow evidence is **MOCK**, or a saved view of explicitly
  labeled MOCK-origin outputs. This is not a genuine live Agnes campaign.
- Live R1/R2 campaign validation failures from the B8 audit remain unresolved by
  this frontend-only task. Five full live rehearsals have not been completed.
- Native Kannada/Kanglish lexicon, copy, posters and real speech/device review
  remain **PENDING**. Screenshots and font tests are not human sign-off.
- Cached mode deliberately prevents fresh inference or approval; it replays
  stored work and exports only already authorized outputs. It cannot execute
  the mutation steps of a live workflow.
- Logo upload remains in poster preparation, linked from Strategy once copy
  exists. No new asset-management or post-lock arbitrary-brand API was invented.
- Long facts/forms/history may exceed the 1.5-screen layout target; focused tabs
  and accordions preserve all reviewable content instead of removing evidence.
- Desktop/mobile Chrome are exercised. Safari/Firefox, real microphone hardware,
  team hotspot checks and production access controls are not claimed verified.
- No production/hackathon release readiness is asserted by visual polish.

## Backend boundary

The repository had existing B8 backend/script edits before redesign. Their exact
tracked diff was captured before/after and compared byte-for-byte: **unchanged**.
The redesigned frontend does not change routes, schemas, database migrations,
Guardian rules, renderer bytes, fonts/licenses, provider calls or approval gates.
See the final evidence record for lock hashes and executed checks.
