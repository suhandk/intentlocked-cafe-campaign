# Audit evidence and creative posters — 2026-10-09

The reported `CAFE: extraction has invalid or absent evidence` came from the
blinded R7 customer audit. R7 now receives exact, code-measured field/line spans
without canonical facts, prior scores or provenance. Validation can correct
coordinates only when the original quote occurs exactly once in the same field.
Absent, ambiguous or invented evidence still fails closed; no facts or approvals
are fabricated. The prompt version invalidates incompatible cached responses.

The saved failed job `4632a437be7a47f7a93b55f4eabaf2ea` was explicitly retried
against the configured live Agnes provider. Replacement job
`eb5e68fcbf3e442c8eb420c19f5d1c22` completed on revision 6 at
2026-10-09T16:22:02+05:30: **audit PASS**, one provider call, 20.17 seconds,
$0.00042715 list-price estimate (not a provider invoice). Warning IDs `G14`,
`r7_ambiguity_0`, `r7_promise_0` remain for owner acknowledgment; no approval,
export, publication or delivery was performed.

T1 now requests layered editorial illustrations, decorative shapes and a focal
object. A locked coffee category permits an unbranded coffee mug and steam;
unsupported products, food, gifts, venue features, logos and generated lettering
still fail R9. Canonical brand/offer/date/address literals are excluded from the
art prompt. The local deterministic fallback includes a coffee illustration and
remains identified as local artwork. Art/prompt hashes prevent reuse of the old
background under the new contract.

Canvas b5.2 confines the opaque dark text plate to actual content bounds, leaving
more artwork visible. Layout/renderer hashes change, so existing posters must be
rendered and approved again. Text stays code-rendered. Fast mock mode skips
artificial RPM waits; live provider limits remain enforced. The audit avoids
extra repair calls for uniquely repairable quote offsets. Live latency remains
provider-dependent. Validation exceptions are no longer printed to logs.

Executed checks:

- 449 backend tests PASS in 37.90 seconds; one upstream Starlette deprecation.
- Ruff, frontend TypeScript, ESLint and production build PASS.
- Real headless Chrome canvas rendering PASS, contrast 14.93:1; inspected the
  [local sample preview](evidence/creative-coffee-preview.png). Sample copy is
  verification-only and was not saved as an approved campaign.
- Backend health PASS, configured mode LIVE; frontend production server starts
  at http://127.0.0.1:3000.
- Authenticated R7 retry PASS as recorded above. New live image generation/R9
  image QA, manual Kannada review and microphone/TTS checks: **NOT_TESTED**.

Evidence: [backend results](evidence/creative-audit-tests.xml),
[canvas validation](evidence/creative-canvas.json).
