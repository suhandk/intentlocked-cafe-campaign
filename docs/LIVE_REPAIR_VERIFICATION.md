# Live response repairs — 2026-10-09

R1/R2/R3 have passed genuine authenticated Agnes calls. These results do not prove
a complete live approved campaign. The latest completed matrix capture is partial:
9/27 combinations ready (Kanglish); 18 blocked. Human/native review, full live
semantic audit, posters and approval/export are not signed off by this capture.

## Implemented acceptance fixes

- Decode a serialized JSON `result` object once, only for an object-result schema.
  Retain strict types, discriminators, extra-field and duplicate-key rejection.
- Give repairs schema-owned field paths and static domain error codes, without
  echoing rejected text/values. R1 evidence and R2 factual forms enter bounded
  repair before committing any proposal. Exhausted failures remain blocked.
- Supply R2 Guardian-compatible constraints for numeric/date/day/eligibility and
  condition forms. Agnes still returns the complete result; no result is replaced
  with deterministic/mock forms. Named forms still require owner/native review.
- Apply the same R2 validation to changed-fact forms.
- Clarify role contracts for supported facts, targeting, complete slot phrases,
  output arrays, hypothetical planning and batch output.
- Inline the success wire schema for R3/R4; validate responses against the original
  strict public schema, including explicit failure responses.
  Require the status discriminator explicitly: Pydantic's default otherwise makes
  it optional in the provider schema, causing tag-less valid wire replies that
  the discriminated result parser correctly rejects. Captured response diagnosis
  identified `union_tag_not_found`; the parser is not relaxed to infer success.
- Large text batches get a 60-second transport timeout, bounded by the original
  absolute run/call budgets and serialized rate limiter. Small calls retain 30s.
- Prevent masked slots from joining surrounding words into false entity claims.
  Connectors still bind slots to the correct fact role; hostile wrappers and
  literal products/locations remain blocked.

## Executed evidence

- Full backend suite: **419 passed**, one existing Starlette/AnyIO deprecation.
- Ruff: **PASS**. Frontend source/API DTOs were unchanged by these fixes.
- Guardian/slot critical branch coverage: **100%** (rules 118/118, slots 20/20;
  numeric observations, normalization and reports also fully covered).
- Later concurrent Git updates introduced committed conflict markers and unsafe
  validation printing in agnes_client.py. These were removed while retaining the
  strict parser. Post-resolution targeted checks: **206 passed**, Ruff PASS.
- Coverage: [live-repair-coverage.json](evidence/live-repair-coverage.json).
- Genuine provider capture and call records:
  [live-campaign-repair.json](evidence/live-campaign-repair.json).
  Timestamped captures preserve failed/partial/interrupted attempts separately.
- Campaign: `e0163b2ee5824f9aaeedcee02796168a`, database
  `data/b8-live-campaign.sqlite3`, assets `data/b8-live-campaign-assets`.
- Hypothetical business facts were checked by an explicitly **simulated test
  operator**. This is not human owner approval or native-reader sign-off.
- One diagnostic Store connection triggered single-worker restart recovery during
  a run. That run was interrupted and is not counted as successful verification.
- Five successful live rehearsals, hotspot checks and production readiness are
  **NOT VERIFIED**. No live cost/latency/sales claim is inferred from mock data.

## Reproduce

Use the pinned Python 3.11 environment and the existing server-only `.env` key.

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check backend scripts/verify_live_campaign.py
.venv\Scripts\python.exe -m scripts.verify_live_campaign --matrix --strategy tools
```

This integration script labels simulated owner actions and records every live
call. It does not perform human/native sign-off or approve an export. `--resume ID`
uses a persisted genuine proposal; `--retry-run ID` preserves ready combinations
and retries only failures. No cached/mock result replaces a live failure.

Run only one process against a campaign database. For diagnostics, use a raw
SQLite read-only connection; constructing Store runs restart recovery.

## Current local preview

The local backend was restarted in LIVE mode against the captured database, and
the frontend was restarted. Actual checks: frontend HTTP 200, proxied health LIVE,
campaign/matrix API reload successful. The displayed campaign is a hypothetical
integration capture with simulated owner actions, not human/native sign-off:
`http://127.0.0.1:3000/?campaign=e0163b2ee5824f9aaeedcee02796168a#campaign-matrix`.

These are process overrides; the private `.env` key is unchanged. Restart using:

```powershell
$env:AGNES_MODE='live'
$env:DATABASE_PATH='data/b8-live-campaign.sqlite3'
$env:ASSET_PATH='data/b8-live-campaign-assets'
$env:STRUCTURED_STRATEGY='tools'
.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Optional UNAPPROVED video draft controls were subsequently implemented at the
user's request; see [current draft limits](VIDEO_DRAFTS.md). Full V1 release
remains gated by core readiness and QA. No video provider call was submitted.
