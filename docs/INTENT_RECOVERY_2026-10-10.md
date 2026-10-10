# Intent failure recovery — 10 October 2026

The screenshot refers to intent work `058fdfca20cb48958a6864372e7229d2`.
Its saved LIVE ledger records two completed HTTP 200 GPT-4o mini responses,
then `INTENT_UNAVAILABLE`. The campaign remained revision 1, draft; no lock
or approval occurred. This was a model result/contract failure, not a backend
connection error.

## Reproduction and cause

The saved private brief was replayed in a temporary isolated database using
the actual configured provider and model. Its text, credentials and raw
response bodies were not printed or added to evidence. The original database
was opened read only.

Before the fix, the first response proposed a `DATES` fact. The public shared
fact schema permits server/owner date values, but R1 is forbidden from deriving
dates. Its transport schema did not express that restriction. The unchanged
domain validator correctly rejected the response, and the repair returned
`error: unable_to_interpret`. The UI displayed only the generic work failure
and advised a reload that could discard the owner's unsaved brief.

[Before-fix LIVE replay](evidence/intent-recovery-before.json): failed,
two calls, 8.59 seconds. The historical response bodies themselves are not
persisted; this is an actual new reproduction, not a claim to have recovered them.

## Changes and boundaries

- R1 now receives an inlined, closed transport schema with ten permitted proposed
  fact keys, matching canonical types and required discriminator tags. `DATES`
  and `DAYS` are excluded from proposals. Date phrases still go to server code.
  Success, needs-input and failure outcomes all remain available.
- Prompt guidance explains how to repair contract errors while retaining
  evidence-linked proposals and clarification questions. Unspecified facts are
  omitted rather than represented as empty proposals. The existing two-repair
  limit, call budget, provider policy and strict Pydantic/domain checks remain.
- Genuine failures retain `INTENT_UNAVAILABLE` and an allowlisted reason. Durable
  jobs add a static, sanitized recovery notice. No rejected result changes facts.
- The owner sees explicit **Retry this brief** and **Enter facts manually** actions.
  A confirmed terminal failure uses a fresh durable key; uncertain requests still
  retain their original key. Editing/retrying preserves the visible brief.
- Manual entry uses the existing transactional draft route, with an optional
  `transcript` field. It saves the owner's source text without an R1 call or a
  successful-extraction claim. Changed source text clears obsolete evidence and
  proposed forms, resets review warnings, and leaves facts editable. Reload keeps
  the saved manual brief. Concurrent/stale saves still return revision conflicts.
- Manual facts still require complete canonical values, reviewed localized forms
  and explicit owner lock. A transcript cannot lock itself. Post-lock changes,
  Guardian, semantic audits, approved hashes and export authorization remain intact.

Two old tests corrupted only a unique quote's coordinates. Existing exact-quote
coordinate recovery already repairs that input locally. Their stimuli now use
absent source evidence and retain the required repair/rejection assertions;
additional regressions prove unique coordinate recovery and reject ambiguous
quotes within the original finite repair limit. No safety check was removed.

## Actual checks

[After-fix LIVE replay](evidence/intent-recovery-live.json): one call, 6.99 seconds,
valid evidence-linked proposals, unlocked draft. The date phrase still needs
owner clarification; dates were not fabricated. This was a temporary check,
not an update or approval of the owner's original campaign. Provider usage/list
price was unavailable and remains unknown.

[Targeted backend evidence](evidence/intent-recovery-targeted-tests.xml): 70 PASS.
[MOCK browser evidence](evidence/intent-recovery-browser-tests.xml): two PASS,
covering edited retry with a fresh key, manual entry without another R1 request,
brief persistence on reload, editable fields and absence of an owner lock.
Production frontend build, strict TypeScript and ESLint PASS.
[Full backend evidence](evidence/intent-recovery-backend-tests.xml): 602 PASS
(one existing AnyIO deprecation warning). Four previous MOCK approval/export,
copy/poster, prediction and disabled-video browser checks PASS again in
[browser evidence](evidence/screenshot-recovery-browser-tests.xml).
Ruff formatting/checks, source/build secret scans and diff whitespace checks PASS.

No final owner approval, export, native Kannada review or microphone sign-off
was performed for this fix. Normal backend/frontend services remain stopped;
the temporary browser test server is shut down after verification.

## Changed source

`backend/intent_context.py`, `backend/schemas.py`, `backend/campaign_service.py`,
`backend/prompts/R1.md`, `backend/work_service.py`,
`frontend/components/CampaignFlow.tsx`, `frontend/lib/work-api.ts`.
Regression coverage: `backend/tests/test_intent_recovery.py`,
`backend/tests/test_live_response_repairs.py`, `backend/tests/test_freeze.py`,
`frontend/e2e/intent-recovery.spec.ts`, `frontend/playwright.intent.config.ts`.
OpenAPI and frontend generated types include the optional manual transcript.
