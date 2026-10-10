# F1 approval/export and photographic posters — 9 October 2026

The final-output controls required a second export action after approval, lost
selection after reload, and did not expose individual text downloads. Failed
customer-audit evidence and outdated poster dependencies are real blockers,
not successful approvals. Existing R7 evidence grounding and server readiness
checks remain authoritative.

DeliveryPanel now retrieves the authorized selected export after successful owner
approval. An explicit “Show approved final output” operation retrieves already
approved compatible items after reload, without reapproving them. Output display
is bound to campaign, revision, view mode, selected IDs and snapshot hashes. Text,
poster and ZIP downloads still call server authorization. Warning/native review
and exact owner confirmation remain required; blocked/pending items cannot export.
Individual file export now accepts the existing saved-view convention.

The attached reference supplied visual direction, not new business facts. Active
T1/R9, the safe visual projection and canvas now use photographic coffee, warm
amber lighting, espresso/cream colours and a gold offer highlight. Anonymous studio
wood texture/bokeh is decorative; unapproved food, venue amenities, names and
claims remain forbidden. Only locked coffee permits a coffee motif. Code owns
all exact factual typography. A 1080×1350 `feed` format uses the already supported
1:1 provider ratio. Batches remain bounded to three selected formats. Renderer,
prompt and layout hashes invalidate old posters and their approval eligibility.
Old layouts remain historical. Local fallback is labeled illustration, not AI
photography. Models and raw Agnes transport conventions are unchanged.

Changed implementation: art_context, art_models, art_service, work_models,
ledger, delivery_routes, T1/R9; DeliveryPanel, PosterPanel, canvas.js and generated
API schema/types. Existing social draft/send boundaries remain unchanged.

Executed evidence:

- 458 backend tests PASS; Ruff PASS. One upstream Starlette deprecation warning.
- Frontend lint and production build/TypeScript PASS.
- Offline browser approval/export regression PASS, including automatic output,
  text download control and explicit output retrieval after reload. Exactly one
  simulated approval request; no real owner approval.
- 12 actual offline Chrome renders PASS across four sizes and three languages;
  server validates exact text, safe areas, minimum fonts and contrast.
- One LIVE poster batch completed: two provider calls, 27.42 seconds; measured
  list-price estimate $0.01 plus one call with unknown cost. Background QA and
  1080×1350 render succeeded. One LIVE customer audit completed PASS: one call,
  17.19 seconds, list-price estimate $0.0004327. Current readiness has no blockers.
  Poster remains pending owner approval and warning review. No real export,
  platform send or publish was executed.

Evidence files: `evidence/final-output-tests.xml`,
`evidence/approval-browser-result.json`, `evidence/commercial-canvas-results.json`,
`evidence/commercial-live-job.json`, `evidence/commercial-audit-job.json`,
`evidence/commercial-live-readiness.json`, `evidence/commercial-live-poster.png`.

The live key became available during verification; no environment values were
printed. Earlier no-key observations are superseded by these actual live checks.
Native Kannada reading, microphone/TTS and real owner approval/export remain
NOT_TESTED. Image pixels are not claimed to reproduce the reference exactly;
unsupported sandwiches, cake and venue furnishings were intentionally excluded.

Open Approve + Export, select the new feed poster or passing text, review audit
findings and warnings, and confirm exact content. Approve selected items now shows
authorized final output automatically. After reload, use Show approved final
output. Old posters must be regenerated and audited before a new approval.

The workspace production frontend was restarted with the rebuilt bundle; HTTP
200 confirmed. Backend serves the current renderer. No active provider work was
interrupted. Existing conflict markers in progress/security documentation were
preserved as pre-existing repository state.
