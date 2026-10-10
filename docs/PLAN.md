# Staged delivery plan

Current slice: B7 integration on the existing B1–B6 foundation. Eight panels,
durable job admission/cancel/retry, replay/reload, saved provenance and accessibility
are implemented. Next bounded slice is B8 freeze/handoff. Authenticated integration
and manual native Kannada/voice checks remain NOT_TESTED. Actual npm commands in
README supersede the provisional pnpm commands below.

| Slice | Bounded work and planned files | Evidence required before passing |
|---|---|---|
| B0 / G0 | Backend/frontend manifests and lockfiles; `backend/main.py`, `backend/agnes_client.py`, config/errors; `scripts/smoke_agnes.py`; fixtures; basic page; safe env and README | Backend starts; frontend builds; mock client tests pass for auth, rate limits, retries, timeouts, malformed/truncated output, cancellation, redaction and model allowlist. Record authenticated checks separately. |
| B1 / G1 | `schemas.py`, `db.py`, migrations, repositories, intent/surface prompts; Speak/Type and Facts Lock | Typed intent -> clarification -> reviewed forms -> atomic lock survives reload. Missing facts and stale revisions blocked; voice checks recorded separately. |
| B2 / G2 | `guardian/{slots,normalize,rules,report,lexicon_en,lexicon_kn}.py`, policy; Guardian panel | >=40 meaningful adversarial cases plus positive controls; >=90% branch coverage on implemented critical modules; original offsets correct; native review explicitly pending until performed. |
| B3 / G3 | Strategy/copy agents and prompts; variant storage; Campaign Matrix | Eligible differentiated strategies; selected matrix complete and reloadable; one batch/language; slot-only templates; partial failures visible; no stale job overwrite. |
| B4 / G4 | Safe media service, shared canvas renderer, licensed local fonts, asset-render route | Persisted PNGs at all three sizes; actual visual review of Kannada, safe areas, contrast and overflow; QA or disclosed deterministic background; artifact provenance. |
| B5 / G5 | Scoring/optimizer/reader agents; persisted orchestrator; prediction panel | Frozen-baseline AB/BA judgments, measured features, paired sensitivity, acceptance/rejection/no-gain stops and budgets; blinded audit blocks failures. |
| B6 / G6 | Change parser/classifier, ledger, approvals/export; Changes, Red-Team and Export panels | Minimal invalidation; mixed proposal atomicity; 409 races; >=90% branch coverage for ledger/change; direct API cannot export stale/tampered/unapproved content; manifest matches bytes. |
| B7 / G7 | All eight panels, trace/cost, voice recovery, durable jobs/SSE/cancel | Browser critical path, keyboard/mobile checks, reconnect/restart, cancellation, duplicate-click idempotency, labeled modes and actionable errors. |
| B8 / G8 | Freeze, integration, runbook, genuine saved output and rehearsal | Clean lockfile install; pytest/coverage/ruff; TS typecheck/lint/build; E2E; backup/restore; live evidence; five live rehearsals only if actually performed. |
| A1 | Adversarial audit and targeted fixes | Reproductions and evidence for repaired risks; remaining issues explicit. |
| P1 | Selected deployment release gate | Access boundary, persistence, restore, recovery, retention and operational evidence. Public release blocked until required controls pass. |
| V1 | Optional video only after core passes | Verified entitlement, consistent model polling, playable downloaded and hashed file, validated overlays, no effect on core failures. |

Each stage begins with a short plan and ends with exact executed commands/outcomes, changed files, skipped/manual checks, risk notes and updated progress/interfaces. Preserve passing work and unrelated changes. Do not advance solely because code exists.

## Planned verification commands

These are command targets to establish in B0, not currently runnable scripts or results:

- Python 3.11 environment: `python -m pytest`, `python -m ruff check backend scripts`.
- Critical logic: `python -m pytest --cov=backend.guardian --cov=backend.ledger --cov=backend.change --cov-branch --cov-report=term-missing` with a genuine >=90% critical-module gate established as modules arrive.
- Frontend: `pnpm --dir frontend typecheck`, `pnpm --dir frontend lint`, `pnpm --dir frontend build`, and `pnpm --dir frontend test:e2e` once scripts exist.
- Provider: `python scripts/smoke_agnes.py --mode mock`, then explicit live mode once implemented and a server-side key is available. Video stays opt-in.

Pin and lock a compatible dependency set in B0 before declaring these commands supported. The bundled document-inspection Python is not evidence of a working Python 3.11 application environment.
