# B7 workflow and recovery contract

Current 10 October 2026 extension: local poster animations use existing durable
jobs and source/byte approval checks. Cached views label animation cards, approved
MP4 response headers and manifests CACHED while retaining original source mode;
the `saved_view` flag never bypasses current authorization. Current inference
mode is `INFERENCE_MODE`. The selected image profile is OpenRouter Seedream with
the server-only `INFERENCE_API_KEY`; a fresh image probe returned 402, so credits
are required. Optional direct OpenAI images require a different private key.
Historical provider/fallback observations below describe their captured version.
See [current verification](HACKATHON_VERIFICATION_2026-10-10.md).

Optional `meta_delivery` extends this job system without changing inference jobs.
Only owner-confirmed previews are admitted. It has 12 total Meta attempts within
the existing 480-second deadline; generic work-start/retry cannot authorize it.
On restart, queued social operations are cancelled and submission/processing is
delivery_unknown; replay never resends. Accepted WhatsApp is distinct from signed
delivered/read callbacks. See [META_INTEGRATION.md](META_INTEGRATION.md).

The eight navigation links point to the existing Speak/Type, Facts Lock,
Brand + Strategy, Campaign Matrix, Prediction + Optimization, Guardian + Red-Team,
Ledger + Changes and Approve + Export services. Unavailable steps explain what
must be completed first. Warm neutral cards, visible status words/icons, labeled
forms, native keyboard controls and a skip link support desktop and mobile use.
Technical actions/decisions stay in optional drawers; traces contain no model
reasoning, raw transcripts, credentials or signed provider URLs.

## Durable admission

Migration 007 adds `work_jobs` and the append-only replay journal
`workflow_events`. These wrap the existing campaign, generation, canvas,
optimization and approval services; they do not replace their repositories or
revision/approval boundaries. Run with **one backend worker** and persistent local
database/assets directories. The limiter does not coordinate other computers.

`POST /api/campaigns/{id}/work` returns 202 and a `WorkJob` immediately.
`kind` selects the strict existing DTO for `input`; unexpected fields are rejected:

| Kind | Input DTO / saved target |
|---|---|
| intent / forms | IntentRequest / SurfaceRequest |
| strategy | RevisionRequest |
| generate / optimize | GenerateRequest / OptimizeRequest |
| background / render | BackgroundRequest / RenderRequest |
| poster_batch | PosterBatchInput: selected sizes, saved copy/logo, source |
| poster_audit / item_audit | RevisionRequest + target_id |
| change / change_forms | ChangeRequest / RevisionRequest + proposal target_id |
| red_team | RedTeamRequest; instruction proposes, copy mode checks immediately |

Parent jobs have a 480-second persisted deadline and at most 48 provider attempts,
including retries/repairs/QA. Native optimization retains its stricter existing
round, step and call budgets. Generation steps are language batches; poster steps
are background + render for each of at most three sizes. Two parent jobs execute;
at most 16 more queue. The single Agnes transport also caps waiting requests at
16, with its existing interactive priority/starvation protection and rate limiter.
Queue wait estimates use queue position plus the current limiter delay; they are
planning estimates, not completion promises. Text/image 8 RPM and Retry-After can
make waits longer.

The key is unique per campaign and binds the entire kind/input/target/revision.
Duplicate requests return the same saved job. Dispatch is written before awaiting
HTTP. Its completion updates the same call ID, so a process crash leaves an
unknown-cost attempt instead of deleting evidence of a possibly charged request.
Usage/list prices remain estimates; mock calls are excluded from USD charges.

`GET /api/campaigns/{id}/work` lists recent work with queue position, elapsed time,
steps, calls, known list-price estimate and unknown costs. `GET /api/work/{id}`
also supports older IDs. Owner input is persisted privately for explicit retries;
it is not included in trace events. No input or output can authorize itself.

## Stop, retry and replay

`POST /api/work/{id}/cancel` is idempotent. Completed outputs stay stored.
Cancelled native runs reject late writes, even if a transport returns after
cancellation. Cancellation after media dispatch can still incur unknown charges.

`POST /api/work/{id}/retry` takes an expected revision and new idempotency key.
Only stopped/partial work can retry. Changed facts require a newly reviewed
operation. Generation retry binds the exact old selection and carries ready cells
forward unchanged; it calls only unfinished batches. The old run remains history.
Uncertain media submissions reject retry with `RETRY_UNSAFE`; inspect provider
history or select deterministic art. No automatic resubmission occurs.

Restart marks unfinished jobs/native runs **interrupted**, retains completed cells,
strategy and files, and starts no replacement calls. Browser close/reload does not
cancel a worker or start another one. Initial reads and polling recover persisted
state. Polling propagates state changes to matrix/assets/approval panels even when
an event was missed during mounting or reconnect.

`GET /api/stream/{campaign_id}` emits increasing global SQLite IDs, `event:
workflow`, JSON data, retry interval and five-second comment heartbeats. Replay
honors `Last-Event-ID` and the explicit `after` query. Event data has campaign,
revision, job/native run, timestamp, action and concise result/stop message.
Streaming/replay only reads the journal; it never dispatches work or changes costs.

## Modes and saved output

Every source still identifies MOCK/LIVE. **Switch explicitly to saved output**
requires an actual completed/partial generation or render capture; missing capture
returns `SAVED_OUTPUT_MISSING` (404). The view is read-only and labels cards,
outputs and jobs CACHED, with source mode, provider, capture time, fact revision
and stored prompt hashes. It never silently substitutes cached output after a
provider failure. Server `AGNES_MODE=cached` prohibits inference.

`saved_view=true` on authorized export/ZIP labels the manifest and every file
cached while retaining `source_mode`, hashes, approval IDs, fact versions,
available capture metadata and cached comparison evidence. The same current
revision/audit/approval/byte checks apply. Legacy pre-B7 captures can have null
timestamp/empty prompt metadata; these are unknown, never reconstructed proof.
Saved ZIP selects actually approved items and the server rechecks them at download.
WhatsApp opens an owner-triggered draft and sends/attaches nothing automatically.

Agnes image timeout keeps the existing explicitly labeled deterministic fallback.
Its job is partial with a visible notice; it is never presented as successful
Agnes artwork. Remote vision entitlement remains NOT_TESTED.

## Verification

Run the mock backend/frontend as in README, then the pytest and browser commands.
`python -m scripts.verify_recovery` starts a separate local mock server on port
8001, terminates it abruptly after one completed batch, reopens the same storage,
checks identical asset bytes, and verifies raw HTTP Last-Event-ID replay with no
new calls/cost. It does not contact an inference provider. Evidence is timestamped
in `docs/evidence/b7-recovery.json`.

Real microphone permission, speech recognition, OS Kannada voice quality and
native Kannada review are separate manual checks and remain NOT_TESTED. Browser
tests simulate denial/unavailable voices and verify the editable typed fallback.
Live provider roles/account checks remain NOT_TESTED; public release is B8.
