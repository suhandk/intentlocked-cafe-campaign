# Surface wording recovery — 10 October 2026

Screenshot work: `9b8bd9d2730d4020a1ba1fa39d15cae2`, LIVE GPT-4o mini.
The saved job began at campaign revision 5 and failed with `SURFACES_UNAVAILABLE`
after two HTTP 200 responses. Canonical confirmation had already committed
revision 6; no proposed forms or owner approval were saved. Daily time and
offer-combination rules were unspecified, not required missing facts.

## Reproduction and root cause

The actual current canonical snapshot was read from the original database in
read-only mode and copied into a temporary database. A bounded LIVE replay
reproduced the failure: R2 returned all ten fact keys, but placed `dat`, `gen`
and `loc` beside language keys inside `surface`. These names were interpreted
as unsupported languages rather than cases inside the `en` object. Strict
Pydantic validation rejected them; the repair then returned `uncertain_forms`.

[Before-fix evidence](evidence/surface-recovery-before.json): FAILED, two calls,
9.10 seconds. This is a new actual reproduction; historical raw model response
bodies are not stored and were not fabricated. No credentials, private fact
values, raw source text or response bodies are included in evidence.

A separate recovery defect existed: the failed request had advanced the saved
revision from 5 to 6, while the UI still submitted revision 5 on retry. Generic
durable retry also binds the original job revision. That conflict was correctly
rejected by the server but left the owner without a useful retry flow.

## Fix

- R2's inlined transport schema binds each specified fact to exactly the selected
  languages. Case arrays are inside their language object. Named Kannada and
  Kanglish nouns require all four nonempty case arrays. English nom retains the
  canonical owner spelling; typed nom arrays use the existing code grammar.
- The wire hint retains success, needs-input and failure outcomes. It is JSON
  prompt/tool guidance, not a claim that the provider enforces a native schema.
  The original strict parsing, domain validation and two-repair limit still run.
  Wrong values, missing languages and invented unknown conditions remain errors.
- R2 instructions explicitly distinguish optional unknown conditions from a
  missing required fact, and describe nesting/repair without inventing support.
- Real failures keep `SURFACES_UNAVAILABLE`, an allowlisted reason/current revision,
  and a static sanitized durable notice. Canonical confirmation is preserved;
  no error is presented as a successful proposal, lock, audit or approval.
- On a known forms failure, the UI reloads the saved campaign revision. It carries
  forward the owner's canonical confirmation only when the original confirmation
  advanced one revision and the facts, selected languages, brand, audiences and
  warnings are unchanged. Changed facts require a fresh confirmation. Local
  unsaved facts/transcripts are not overwritten by this recovery path.
- **Retry wording** submits a new reviewed operation and fresh durable key against
  the current revision. The trace drawer's stopped forms entry navigates to fact
  review instead of submitting an obsolete generic retry. Generic API revision
  rejection is unchanged. Cancellation and late-result checks remain intact.
- Proposed forms remain editable and unapproved. **Lock approved facts** still
  requires exact reviewed versions/forms, warning review and the owner checkbox.

## Actual verification

[After-fix isolated LIVE check](evidence/surface-recovery-live.json): PASS,
one call, 3.48 seconds, all ten English forms validated, canonical values unchanged,
unknown conditions unchanged. Status `forms_review`, owner approval PENDING.
Usage/list-price data was unavailable and remains unknown. The original campaign
was not updated or approved by either replay.

- [Backend suite](evidence/surface-recovery-backend-tests.xml): 610 PASS; one existing
  AnyIO deprecation warning.
- [Targeted cases](evidence/surface-recovery-targeted-tests.xml): 61 PASS, including
  JSON/tool malformed nesting, wrong offer, absent Kannada, extra unknown condition,
  forged lock outcome, genuine failure, bounded repairs and stale generic retry.
- [MOCK browser checks](evidence/surface-recovery-browser-tests.xml): five PASS.
  Both forms recovery paths go through retry and explicit simulated owner lock;
  one rejects carried confirmation after a concurrent 20%→15% edit. The previous
  intent recovery and final approval/export recovery checks pass again.
- Production frontend build, strict TypeScript, ESLint and Ruff PASS.
- Source/build credential scans and diff whitespace checks PASS. The scans cover
  known configured credentials and defined patterns, not every possible secret.

The owner had restarted normal services. After confirming zero active durable jobs
and this worktree's process identity, only the idle backend was restarted to load
the fix. The existing frontend uses automatic development reload. Persistent
campaigns/history/approvals were preserved; the temporary browser test server exits.

[Read-only runtime check](evidence/surface-recovery-runtime.json): backend and
frontend `/api/ready` both HTTP 200, LIVE/OpenRouter/GPT-4o mini. Original campaign
remains revision 6, canonical_confirmed, unapproved; zero active durable jobs.
The readiness check made zero inference requests.

LIVE Kannada/Kanglish, native language review, microphone checks and final live
owner approval/export were not performed for this fix. Browser approvals above
are explicitly MOCK test actions, not a real owner attestation.

Changed source: `backend/surface_policy.py`, `backend/campaign_service.py`,
`backend/prompts/R2.md`, `backend/work_service.py`,
`frontend/components/CampaignFlow.tsx`, `frontend/lib/work-api.ts`,
`frontend/components/WorkflowStatus.tsx`. Added backend/browser surface regressions
and `frontend/playwright.surface.config.ts`. Public request/result DTOs are unchanged.
