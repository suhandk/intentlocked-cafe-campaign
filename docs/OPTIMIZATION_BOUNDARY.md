# B5 prediction and optimization boundary

Version b5.1, 2026-10-09 (Asia/Kolkata). Runtime inference remains Agnes-only.
The implemented comparison is explicitly MOCK in executed browser evidence.
R5/R6/R7 authenticated behavior and native Kannada remain NOT_TESTED.

## Frozen run and finite execution

POST `/api/campaigns/{id}/optimize` takes an expected revision, one to three
original baseline variant IDs and an idempotency key. Selection is restricted to
one language, the saved hero audience, and generated social channels. Five saved
hypothetical personas, baseline templates/reports, campaign context, model and
prompt hashes are frozen. A retained candidate cannot become a new baseline.
Same-key/same-payload requests return the same run; changed payloads return 409.

One active optimization run is allowed. All roles share the existing Agnes client
with other work. A run has 48 transport attempts, a persisted 480-second deadline,
and `groups × (1 + 4 × max_rounds)` role steps. Maximum rounds are three, or two
with server `DEMO_FAST=1`. Cached steps also consume steps and respect the deadline.
Client transport retries and schema repairs consume the same call budget; no
score-seeking retry exists. Startup marks queued/running runs interrupted and
never repeats their calls. Stale asynchronous results cannot select a candidate.

Each group executes baseline features and blinded audit, R6 critique, code edit
authorization, Guardian, blinded candidate audit, AB/BA judge batches, computed
comparison, atomic selection and stop. Accepted rounds replan using the retained
template, abstract vote outcomes and remaining rounds. The first non-improving,
invalid, blocked, unscored or no-change round stops that group. Budget, deadline,
unavailable critique and revision failures have explicit terminal reasons.

Only `template.headline`, `template.body`, `template.cta`, and `template.alt_text`
are editable here; at most four distinct operations. Approved slot/case inventory
must be preserved. Repeating an existing approved slot for emphasis is allowed;
required visible disclosures still pass Guardian. Fact values/forms, eligibility,
budgets, scores and arbitrary paths cannot be edited. Other mutable preferences
and layout edits belong to their later authorized paths. A deterministic BLOCK
receives no judge calls and cannot be averaged away.

## Features, votes and selection

Text features are documented product heuristics, each 0–100:

| Feature | Measurement and threshold |
|---|---|
| Offer first line | Complete approved OFFER provenance span in first headline line (body first line when headline absent), within 80 code points: 100; otherwise 0 |
| CTA presence | Nonempty CTA: 100; otherwise 0 |
| Channel fit | Total rendered field length within Guardian product channel budget: 100; otherwise 20 |
| Required fact completeness | G05 passed: 100; otherwise 0; a BLOCK independently prevents acceptance |
| Script fit | G11 passed: 100; otherwise 60 and its review warning remains visible |
| Poster contrast | Actual canvas contrast ≥4.5: 100; 3–<4.5: 60; <3: 20 |
| Poster offer area | Measured approved-offer glyph bounding area / full canvas: 6–18%: 100; 3–25% outside target: 60; otherwise 20 |

Poster features are excluded for text comparisons. The shared canvas-b5.1 renderer
measures offer strings with the same drawing font. If a complete form is split
across lines or unavailable, area is **applicable but unavailable**, not a zero or
an excluded measurement. Incomplete applicable features cannot produce an overall
score. Existing B4 artifacts without the new measurement remain unavailable for it.
Poster audits expose measured features, but no persona tournament/CTR is fabricated
for a poster that has only received a text-provenance audit.

R5 receives five fixed hypothetical personas, final texts and anonymous X/Y labels.
AB maps X=original, Y=candidate; BA reverses them. Code maps to stable IDs. Missing,
duplicate, unknown-persona or invalid judgments are recorded; a complete batch is
never inferred. Tournament = `100 × (wins + 0.5 × ties) / 10`, with all ten valid
judgments required. Baseline tournament=50 is a declared self-reference convention.
Overall = `0.5 × applicable-feature mean + 0.5 × tournament`.

Acceptance requires complete matching feature masks, zero BLOCK, completed audit,
at least six weighted wins/10, feature-mean decrease **strictly less than three**
points versus retained current, and overall **strictly greater** than retained
current. Each comparison still uses the same original baseline. A rejected score
is recorded on the chart, while the retained trajectory stays at the last accepted
score. No gain is a valid final outcome.

The sensitivity band uses exact deterministic resampling of five paired-persona
units (5^5 samples), retaining AB/BA together, with 10th/90th percentile tournament
points. Order disagreement is reported separately. This is simulated judge
sensitivity, not a confidence interval or evidence of market certainty. All-identical
votes can produce a narrow band without implying real customer evidence.

## R7 and persisted evidence

R7 receives only final rendered fields, language/channel and an empty optional
visual-description field. It receives no canonical facts, provenance labels,
earlier scores or desired result. Its output covers twelve tagged expectations,
exact field/code-point evidence, ambiguity, other promises and back-translation.
Code checks evidence against displayed text, matches it to authoritative slot
provenance and compares typed expectations with the approved revision. Date/day,
scope, specified/unspecified and translated approved-form distinctions are retained.
Mismatches block. Missing/invalid extraction or unavailable R7 leaves G14 pending.
Other promises/ambiguities yield explicit review warnings; matching facts do not
clear those warnings or any deterministic block. Reports and audit records carry
the warning IDs. B6 must bind owner acknowledgments to the current audit/hashes.

Poster audits first verify actual saved PNG bytes/hash and exact render-input text
against provenance, then read that text. They do **not** claim remote image OCR,
pixel vision or native-language verification. Remote vision remains NOT_TESTED.
Audits are immutable, include content/dependency/artifact hashes, reader output,
render provenance, model/prompt/input/output hashes, capture time and call records.

Role caches bind complete anonymous content, persona/context, schema, exact prompt,
model, mode, structured strategy, temperature and version. Cache records include
full role inputs/outputs in local owner storage and their provenance; cached work
is labeled cache with the source mode. Failed outputs are not cached. API calls
record retries, repairs, usage and queue/request timing. Run costs sum returned
live list-price estimates; mock and unknown charges remain distinct. Actual billing
is unknown. Default traces contain brief decisions, never prompts or reasoning.

## Downstream interface and limits

Migration 005 persists optimization runs, immutable inference cache and immutable
semantic audits. OptimizedVariant keeps VariantContract fields, pending status,
parent baseline, exact dependencies, report and mode. B4 render accepts only a
completed run's retained, audited candidate ID; rejected/historical candidates
cannot resolve as its current output. The UI can render/download a retained square
draft. Source baselines remain immutable. No selection creates owner approval.

GET `/api/campaigns/{id}/optimization` returns saved runs and explicitly unscored
current matrix IDs. GET `/api/optimization/jobs/{id}` provides persisted progress.
POST `/api/assets/{id}/audit` and GET `/api/audits/{id}` expose persisted poster
text audits. Revision conflicts use 409, invalid selection/edit 422, absent run
404, and provider failures the existing typed error contract.

Optimization does not promise real engagement lift. Native Kannada/voice checks,
authenticated roles, public release, SSE/cancel UI and final owner approval/export
remain their declared gates. MOCK R7 recognizes a bounded demonstration fixture;
unsupported business/condition wording fails conservatively rather than becoming
a fabricated verified extraction.
