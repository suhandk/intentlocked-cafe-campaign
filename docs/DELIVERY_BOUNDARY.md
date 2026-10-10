# B6 changes, approval and export boundary

Version b6.1, 2026-10-09 (Asia/Kolkata). The local owner-only profile still has no
login, posting service or public deployment authorization. Executed R8/R2/R7
flows are MOCK. Authenticated R8 and native Kannada/voice remain NOT_TESTED.

## Changes and atomic truth

R8 outputs bounded typed operations, exact owner-text evidence, scopes and questions.
Code classifies FACT:CAFE/LOCATION/OFFER/PRODUCT/DATES/ELIGIBILITY/ID_RULE/
TIME_WINDOW/DINE_IN_RULE/MIN_PURCHASE_RULE/COMBINE_RULE as immutable. DAYS is code
derived from DATES and cannot be changed independently. AUDIENCE/TONE/THEME/HOOK/
CTA/LANGUAGE_MIX/CHANNELS/LAYOUT_EMPHASIS are mutable. Unknown, duplicate or
ambiguous targets are rejected; no model-supplied classification is accepted.
Evidence, scope IDs and operation values are validated. Eligibility is independent
of marketing targeting; incompatible student-only/family targeting is rejected.
Tone/hook/CTA/layout edits can be item-scoped; theme/audience/language/channel
preferences are campaign-wide and reject an item-only scope rather than widening it.

POST change creates a persisted proposal and visible before/after diff. Confirm
records consent, not a campaign edit. New canonical values require R2 proposals
and owner approval of the displayed forms. R8 surface proposals are also reviewed;
only specified languages are merged. Publication uses BEGIN IMMEDIATE, checks
expected revision, validates forms/core facts/dates/policy again, appends fact/brand
versions and campaign snapshots, updates current revision, links outputs and records
invalidation in one commit. No await occurs in that transaction. Mixed changes
publish together; cancellation publishes neither part. Confirmation/publication
keys bind full payload hashes, so double-clicks cannot create two revisions.
Cancellation while form generation runs prevents a late result from reviving it.

Pending proposals are explicitly proposals: current facts remain the last published
revision until owner publication. After publication, older revisions/approvals are
historical. Opening history never sets it current. Current API exports always require
the exact current expected revision. Generation/optimization/render results retain
their original revision and cannot commit across a change.

## Minimal invalidation and lineage

Migration 006 adds immutable delivery items, current revision links, change
proposals, owner action keys, version history, ledger events, audit bindings and
asset approvals. Delivery imports only server-owned baseline, retained optimization
and validated poster records. Preview fields/status/hashes never come from clients.

Dependency fingerprints include selected language forms, used facts, every policy
condition (including unspecified states), eligibility even when not printed,
audience policy, required/forbidden brand wording, and poster palette/theme,
renderer, font and layout. Global campaign revision/brand revision alone does not
invalidate unrelated content. A canonical numeric offer change refills compatible
templates into new pending IDs; old scores/audits remain historical, and posters
require rerender. Abstract compatible background art can be reused without image
inference. An offer discriminator change (percentage to BOGO) requires structural
regeneration. Tone/hook/CTA updates alter only scoped copy, run Guardian and require
new audit/approval. Layout offer emphasis moves the approved OFFER slot into the
headline for measured rendering. Theme/language/channel/audience changes have
explicit render/regeneration consequences. Closed theme/tone values prevent
invented factual promises from becoming preferences.

An unchanged item retains its immutable bytes, dependency hash and original owner
approval; a new revision link marks compatibility. A surface-only English edit
invalidates English outputs but preserves unchanged Kannada forms and compatible
approved Kannada bytes. A fresh deterministic check and code comparison of the
saved blinded reader still run at export. Manifests show current fact versions,
source fact versions and each file's original approved revision; carry-forward is
never presented as a new owner approval. Old artifacts with changed dependencies
are regeneration_required and cannot be approved/exported as current.

## Approval and authorized outputs

Each delivery item must have persisted R7 evidence. R7 sees final rendered text,
language/channel and optional empty visual description, never facts or scores.
Poster copy retains its selected social channel's rules; physical posters do not
require a separate selected channel. Text comes from canonical render inputs, with actual PNG/hash,
background/QA/logo, canvas bounds, font, layout and renderer checks. Completing G12
uses validated persisted pixel evidence and cannot clear a deterministic block.
Unavailable audit remains PENDING; semantic mismatch remains BLOCKED. No remote
vision/OCR capability is inferred. Approval recomputes Guardian and compares the
reader extraction with current approved facts. All required checks must be complete,
zero BLOCK, each warning ID acknowledged and observed preview hashes exact.
Kannada/Kanglish require an explicit owner native-review attestation; mock tests do
not constitute human native review.

Server approval records exact item hashes, revision, timestamp and warning/native
acknowledgments in a transaction. Every export repeats dependency, source payload,
audit/readiness, approval, font/layout and byte checks. A stale/pending/blocked/
tampered/dangling item cannot export through direct HTTP requests. No client PASS
report, approval status, file path, image bytes or arbitrary export filename is
accepted. ZIP includes only authorized bytes and manifest, with generated filenames.

Clipboard copy and wa.me links require an owner click. The WhatsApp URL opens a
prefilled draft: **nothing is sent; no poster is attached automatically**. Posters
have a separate authorized download URL. Draft image preview/download APIs remain
clearly pending and do not create final approval. MODE is preserved in manifest.

## API examples

All endpoints use /api and the existing error envelope. Validation/review failures
are 422; stale/idempotency conflicts 409; absent delivery records 404. Secrets never
appear in request examples or manifest.

```json
{"expected_revision":5,"text":"Make it 15%","scope_ids":[],"idempotency_key":"owner-change-example"}
```

POST /api/campaigns/{id}/change → proposed immutable Proposal (R8 b6.1).
POST /change/confirm takes proposal_id, decision confirm|cancel, expected_revision,
idempotency_key. POST /change/{proposal_id}/surface takes expected_revision.
POST /change/publish takes proposal_id, expected_revision, reviewed_forms,
approve_diff_and_forms=true and idempotency_key; returns published revision only
after the atomic commit. Preference-only publications take reviewed_forms=[].

GET /delivery → current items/statuses/proposals/versions/events. GET /ledger and
GET /versions expose history. POST /delivery/{item_id}/audit takes expected_revision.
POST /approve takes item_ids, observed_hashes, owner_approves=true, warning IDs,
native_review_confirmed and idempotency_key. GET /export?expected_revision=N&item_ids=ID
returns authorized manifest, copy_text and whatsapp_drafts. GET /export.zip and
GET /export/files/{item_id} repeat authorization. POST /red-team takes mode
instruct_ai|edit_copy, text, language, revision and key; returns a proposal or an
immediate Guardian report respectively. “Make it 25%” has different correct outcomes.

Actual timestamped browser requests/results, published snapshot and authorized
manifest are in evidence/b6-browser-run.json. Backend outcomes/coverage and remaining
manual checks are recorded in PROGRESS.md. Public release and B7 jobs/UI integration
remain separate gates.
