# Optional Agnes video drafts

Open **Campaign previews → Agnes video generation** after locking facts. This
panel works independently of whether all matrix cells succeeded. The backend must
be in LIVE mode. No mock clip replaces a failed live request.

Choose 24 seconds (3×6 generated seconds + 6-second end card) or 30 seconds
(4×6 + 6). The panel displays the exact number of generated seconds and requires
explicit per-job confirmation of model access, clip count and possible charges.
Authenticated model inventory checks the exact configured Agnes identifier before
submission. Catalogue listing does not establish billing/entitlement; owner access
attestation and actual provider authorization remain distinct.

Select a current validated **story poster** to reuse its exact canvas-rendered
pixels as the six-second end card. Without one, only 18/24 seconds of text-free
footage is composed, visibly labeled footage-only. The service does not fabricate
an end card or translate/rewrite locked text. Conceptual coffee imagery replaces
unapproved iced-product/venue details in the earlier suggested storyboard.

Durable Work kind `video` and migration 009 store clip IDs, states, downloaded
hashes and final hash. Clip concurrency is two, video job admission uses a separate
pool, creation is rate limited to one/minute, polling is bounded, and cancellation
stops all remaining clips. A separate instance of the same Agnes-only client
keeps long video rate waits out of the core inference queue. Generic retry is
disabled for video: inspect saved IDs before authorizing another paid job.

Downloads use the existing controlled-host/DNS/MIME/size boundary. Raw dimensions
and duration are checked before composition. ffmpeg produces 720×1280 H.264,
yuv420p, 30 fps, silent AAC. ffprobe verifies the finished file. Download rechecks
fact revision/hash and artifact bytes. Preview/download refer to the same saved
file. Failed/cancelled/stale jobs cannot expose a completed approved artifact.

## Release limitations

This is a **draft generation feature**, not a fully approved V1 release pipeline.
Raw footage OCR/visual-claim QA, native-reader observations, animated multilingual
shot overlays, licensed music/beat timing/cross-dissolves and video approval/export
are not implemented or verified here. Draft files are always **UNAPPROVED**.
The ordinary campaign approval/export boundary cannot approve these video files.
Saved artifacts are labeled SAVED DEMO OUTPUT with source/capture metadata. No
social posting occurs. No cost, delivery time or human/native sign-off is asserted.

## Executed checks

- Backend suite: **463 passed**, one existing Starlette/AnyIO deprecation warning.
- Ruff, frontend typecheck, lint and production build: PASS.
- Video tests cover missing/false confirmation, altered counts/models/prompts,
  IDs/hashes, failed/one failed clip, bounded timeout, expired/undownloadable output,
  cancellation, stale download, encoding rejection and core-pool isolation.
- Migration/backup targeted checks pass on empty/existing test databases.
- Actual live-mode browser control check: PASS, desktop/mobile screenshots in
  `docs/evidence/video-option-{desktop,mobile}.png`. It verifies duration selection,
  consent reset, disabled/enabled button and **zero provider submissions**.
- Authentication/catalogue read is genuine. All provider/media unit tests are
  explicit offline mocks. No actual generated-video evidence or approval is claimed.
- Locally installed ffmpeg/ffprobe 9.0.2 from Gyan's essentials release archive,
  verified against its published SHA-256; binaries remain ignored under data/.

Read-only browser check (with a running LIVE backend and locked campaign):

```powershell
$env:VIDEO_UI_CAMPAIGN_ID='e0163b2ee5824f9aaeedcee02796168a'
node frontend/node_modules/@playwright/test/cli.js test frontend/e2e/video-option.spec.ts
```

Run from frontend instead for the configured Playwright base directory. Model
create/poll IDs are bound to the configured `VIDEO_MODEL` (default
`agnes-video-2.5-flash`). The website confirmation is required before any billable
submission; global video smoke flags remain independent and disabled by default.
