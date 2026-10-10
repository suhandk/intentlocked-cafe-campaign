# Approval recovery — 2026-10-09

The screenshot contains failed audit job `4632a437be7a47f7a93b55f4eabaf2ea`, the
previously repaired R7 evidence failure. Its live replacement
`eb5e68fcbf3e442c8eb420c19f5d1c22` remains completed. A fresh read-only check with
current approval code confirms its saved text passes readiness, with warnings
`G14`, `r7_ambiguity_0`, `r7_promise_0`. No additional provider call or real owner
approval was made. Other items have blocked, absent or pending audits; text
approval cannot authorize those posters or other variants.

Corrections:

- Durable work errors retain failed-job identity. Delivery refresh clears an old
  item-audit error only after that same current item passes with no server blocker.
- Delivery snapshots expose `audit_findings` and `approval_blockers`. The backend
  uses approval's verification/readiness checks to explain changed layouts,
  hashes, missing sources or nonbinding audits before a button is clicked.
  These diagnostics are excluded from immutable owner snapshot hashes.
- Owner confirmation, warning acknowledgments and native review bind to selected
  current hashes/audit IDs. Changed content/audits reset effective checked state.
  Approval/export selection uses actual current items, excluding stale selected IDs.
- Items show actionable pending/blocked findings. Changed posters link back to
  regeneration. Final navigation points to approval/export controls instead of a
  permanently disabled Continue button.
- Exact R7 evidence uses overlapping chunks of at most 400 characters, below the
  500-character quote limit, without truncating customer copy or inventing evidence.

Executed: **456 backend tests PASS**, Ruff PASS; frontend TypeScript/ESLint/build
PASS. Isolated browser test PASS on port 3002 with offline API fixtures: failed
audit → recovered PASS → warning review → changed audit resets confirmation →
deliberate simulated approval → authorized export → reload. Exactly one approval
request. No real campaign approved or platform send. Server regression tests keep
audits immutable, link a deliberately nonbinding test audit, expose its blocker
and reject approval. UI diagnostics preserve owner hashes.

Fresh real saved-text readiness PASS with zero provider calls. New live inference,
real owner approval/export execution, native-language and voice checks were not
performed. One upstream Starlette deprecation warning remains.

Evidence: [backend results](evidence/approval-tests.xml),
[browser outcome](evidence/approval-browser-result.json),
[mobile view](evidence/approval-recovery-mobile.png). Browser fixture data and
approval actions are explicitly MOCK.

Restart backend/frontend from this worktree. Select the intended current item in
Approve, audit if absent/incomplete, review displayed warnings and exact content,
complete required native review, then approve and authorize export. Rerender old
layout posters separately; text approval does not approve or attach a poster.
Exports and WhatsApp drafts still do not send or publish anything.

Operational verification: both running services were confirmed to serve this
worktree, and all campaigns had zero queued/running jobs. They were restarted
with the existing local configuration and database. Backend startup/health PASS;
frontend startup/HTTP 200 PASS. No pending inference or delivery was interrupted.

The first frontend restart exposed missing installed Next modules (HTTP 500).
Dependency repair encountered a locked SWC file and overlapping installation;
after those processes completed, required Next modules were restored and the
running page returned HTTP 200. Final running configuration is MOCK; local
settings report no live key available. The existing saved live text and audit
retain LIVE provenance and PASS readiness, but no new live check was fabricated.
