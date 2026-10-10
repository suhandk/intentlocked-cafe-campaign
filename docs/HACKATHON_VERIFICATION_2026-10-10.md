# Hackathon workflow recovery — 10 October 2026

Latest owner selection: OpenRouter Seedream images supersede the earlier direct
OpenAI choice documented below. A fresh authenticated request returned HTTP 402
PAYMENT_REQUIRED; credits are required. [Current configuration and evidence](SEEDREAM_SWITCH_2026-10-10.md).

The owner authorized direct OpenAI image generation, retained GPT-4o mini text
through OpenRouter, and chose local animated MP4s from campaign posters. These
choices supersede historical provider/model selections. Existing B0–B7 facts,
transactions, Guardians, approval hashes, durable jobs and manual social links remain.

## Observed causes and fixes

1. Intent/forms failures: prior recovery fixes keep evidence-linked typed R1
   proposals and per-key/language/case R2 forms strictly validated. Owner text,
   manual fact entry, clarification and current-revision retries remain editable.
2. Copy failed even after valid facts: R4 repeatedly produced literal "today"
   and "from" date wrappers. Approved missing slots are still appended in code,
   then every Guardian runs. Closed repair feedback now identifies rejected
   expressions without revealing business values; improved prompt grammar avoids
   audience-specific eligibility claims. Three calls per language remain the cap.
3. Final approval failed: R7 sometimes extracted an entire sentence as LOCATION,
   omitted PRODUCT/DAYS sharing an offer/date line, and inferred DINE_IN_RULE from
   an invitation. Its prompt now specifies each independent key/type and audience
   versus eligibility. Wrong discriminators are rejected. No code substitutes a
   canonical value for an extracted value; exact evidence and provenance matching
   still decide PASS/BLOCKED/PENDING. Old failures remain recorded.
4. AI images: Flux Schnell was absent from the selected provider's image catalogue.
   A supported Seedream probe then returned real HTTP 402. The owner chose direct
   OpenAI instead. One bounded client now sends images/visual QA to OpenAI using
   its own server key; ordinary text stays on OpenRouter. Missing keys produce
   an actionable notice and blocks job admission. Later provider failures retain
   explicit partial/fallback provenance; local artwork is never labeled AI success.
5. Video: no verified AI video model was configured and FFmpeg/ffprobe were missing.
   Installed checksum-verified FFmpeg 9.0.2 locally. The separately named local
   animation creates real H.264/AAC 720×1280/30fps MP4s from exact poster pixels,
   with all text visible. Source audit/approval and separate animation review/hash
   approval are required for authorized download. Remote AI footage stays disabled.
6. Website: adding an incomplete menu row or opening-hours row triggered invalid
   autosaves. Those edits now stay visible and unsaved until completed/removed;
   valid fields save sequentially, with existing version/validation guards.
7. Configured MOCK profile: `/api/v1` gateway paths and direct OpenAI portrait
   dimensions were missing in fixtures. Fixed offline route/size handling and
   verified under external-network denial. Mock mode still cannot infer externally.
8. Usage: provider cost/detail fields caused strict token parsing to drop otherwise
   valid counters. Only the three strict nonnegative counters are projected;
   missing/inconsistent counts stay unknown. Provider-reported fees are separate
   from configured list-price estimates and are not verified invoices.
9. The final browser pass exposed a race in Work and recovery: successful progress
   polling cleared a failed saved-output action's message. Connection errors and
   owner-action errors now have separate state, so the missing-cache explanation
   remains visible across healthy polls. The existing workflow test now checks
   that it survives a polling interval. The failed run remains recorded.

## Executed evidence

| Check | Actual outcome and scope | Evidence |
|---|---|---|
| Full backend suite | 635 PASS, zero failures; external networking denied, fake-clock quota tests | [JUnit](evidence/hackathon-backend-tests.xml) |
| Browser workflow | Final 26 cases PASS (158.36s), isolated MOCK inference; real Chrome canvas PNGs and real FFmpeg MP4 | [Final run](evidence/hackathon-browser-final.json), [earlier polling failure](evidence/hackathon-browser-before-poll-fix.json) |
| Media browser | Rapid double click creates one job; source gate blocks unauthorized MP4; simulated owner approval, exact SHA download, playback/seek, reload, website ZIP, incomplete-row recovery PASS | [Result](evidence/hackathon-media-browser.json), [animation view](evidence/hackathon-local-animation.png), [website view](evidence/hackathon-website-download.png) |
| Current-profile smoke | Text/tools, truncation rejection, 1K PNG bytes, image vision fixture and usage MOCK_PASSED; authenticated status NOT_TESTED | [Mock report](evidence/hackathon-models-smoke-mock.json) |
| LIVE English campaign | Fresh synthetic café; real R1/R2/R3/R4, 3/3 channel drafts, bounded optimization and four real R7 audits; simulated test-owner approval/export, real local PNG/MP4, static website ZIP PASS | [Live run](evidence/hackathon-live-workflow.json) |
| LIVE text connectivity | GPT-4o mini, HTTP 200, one actual request PASS | [Probe](evidence/hackathon-text-live.json) |
| Final LIVE text/tools/usage smoke | Two genuine requests PASS; detailed provider usage counters and reported fees retained; image/vision NOT_TESTED | [Current smoke](evidence/hackathon-models-smoke-live.json) |
| Earlier LIVE image | Seedream catalogue parameters read; charged submission returned HTTP 402, FAILED; no payment retry | [Catalogue](evidence/hackathon-image-catalog.json), [failed request](evidence/hackathon-image-live.json) |
| Direct OpenAI image + QA | FAILED: key supplied at final handoff; one real request returned HTTP 401 AUTH_FAILED at 23:00:51Z. Image bytes and vision NOT_TESTED; no retry | [Authenticated probe](evidence/hackathon-openai-image-live.json) |
| Frontend build/types/lint, Ruff | PASS | Commands below; build inspected for configured secret bytes |
| Source/build secret scan | PASS for configured keys and defined patterns; private `.env` excluded | [Scan](evidence/b8-secret-scan.json) |
| Runtime log secret scan | No configured key bytes in the four owned runtime logs | [Log scan](evidence/hackathon-runtime-log-secret-scan.json) |
| Ordinary app after restart | Backend/frontend ready HTTP 200; persisted approved test MP4 and website ZIP re-download with exact hashes; original owner campaign unchanged | [Runtime](evidence/hackathon-runtime.json) |

The final fresh LIVE rehearsal started at `2026-10-09T22:34:11Z` and took 111.5s.
It used `openai/gpt-4o-mini` for text, explicitly local artwork and a local MP4.
Thirteen actual provider calls reported a combined $0.0081372 cost; actual invoice
NOT_VERIFIED, configured list prices unknown. One candidate was accepted, a later
Guardian-blocked candidate rejected, and the run stopped at NO_GAIN. The report
retains each job, call, cost, audit and selection outcome. No improvement is promised.

The synthetic café is `7fc325b1bccd4e4e8b31c4b3d1dd10d8` (Hackathon Test Cafe).
Only this new test data received simulated owner approvals. The original owner
campaign was not altered or approved. Prior failed live outcomes are retained in
[pre-fix evidence](evidence/hackathon-live-workflow-before-eligibility-prompt.json).

Human Kannada/Kanglish, real microphone/TTS, full LIVE multilingual campaign,
OpenAI image bytes/vision, real hosting publication and owner social posting are
NOT_TESTED. OpenAI authentication was tested and FAILED (401); replace the direct
API key locally, restart the backend, then repeat the bounded image probe.
English test-operator actions are not real business-owner sign-off.
The owner explained the supplied image key is an OpenRouter key, which cannot
authenticate directly with OpenAI. GPT-4o mini text already uses OpenRouter.
The initial handoff query used the general model catalogue; that query does not
establish GPT image availability in the separate image catalogue. No unsupported
capability should be inferred from it. The owner subsequently selected Seedream
through OpenRouter; both earlier and fresh image requests returned HTTP 402.
Website ZIP generation works without hosting credentials; its semantic/native
checks remain explicitly pending. A website bundle does not approve a campaign.

The last browser run logged a nonfatal Windows Proactor connection-reset callback
while testing intentionally rejected browser resources. All 26 cases and server
cleanup passed. The backend suite has one upstream AnyIO deprecation warning.
Neither warning is treated as a failed test or hidden as successful provider output.

## Raw provider contracts (secrets omitted)

Ordinary text: POST `https://openrouter.ai/api/v1/chat/completions`, model
`openai/gpt-4o-mini`, messages, temperature=0, configured tools/JSON strategy.
HTTP 200 text/structured replies were parsed and validated in the LIVE rehearsal.
Response usage may include extra detail/cost fields; unknown counts are not zero.

Direct image: POST `https://api.openai.com/v1/images/generations`:

```json
{"model":"gpt-image-2.5-flare-2026-09-08","prompt":"Unbranded coffee hero, warm amber studio light, no lettering or extra products","n":1,"size":"1024x1024","quality":"medium","output_format":"png"}
```

Expected documented response: `{"data":[{"b64_json":"<image bytes>"}]}`.
The adapter validates actual bounded image bytes; portrait size is 864×1536 and
landscape 1536×864. Real response NOT_TESTED. R9 visual QA uses direct OpenAI
`/v1/chat/completions`, wire model `gpt-4o-mini`, exact image data and schema;
it must actually pass before provider art can authorize export. No SDK extra_body
example is used as proof of the raw request. Unavailable QA remains blocked.

Documentation verified 10 October 2026:
[OpenAI Images raw API](https://developers.openai.com/api/reference/resources/images/methods/generate),
[image generation guide](https://developers.openai.com/api/docs/guides/tools-image-generation),
[OpenRouter Images raw tutorial](https://openrouter.ai/blog/tutorials/image-generation/),
[official FFmpeg downloads](https://ffmpeg.org/download.html),
[published Windows build checksum](https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-9.0.2-essentials_build.zip.sha256).

## Local commands

PowerShell, repository root (do not overwrite an existing `.env`):

```powershell
# Selected profile: put the OpenRouter key privately into INFERENCE_API_KEY.
# IMAGE_PROVIDER=gateway; IMAGE_MODEL=bytedance-seed/seedream-5-0-flash.
# Restart only an idle backend after editing configuration.
.venv\Scripts\python.exe -m scripts.probe_hackathon_image
.venv\Scripts\python.exe -m scripts.install_video_tools
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check backend scripts
npm.cmd --prefix frontend run lint
npm.cmd --prefix frontend run build
# Ordinary app servers must be stopped before the isolated browser suite:
.venv\Scripts\python.exe -m scripts.verify_workflow
```

Start ordinary services in separate terminals:

```powershell
.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 1
npm.cmd --prefix frontend run start
```

bash substitutes `.venv/bin/python` and `npm`. Install FFmpeg/ffprobe through the
OS package manager; the checksum-verified ZIP installer is Windows only.

After the genuine image/QA probe passes, optional synthetic rehearsal:
`python -m scripts.verify_hackathon_live --optimize --image` using the venv.
This may incur provider charges and performs only simulated review of its own
synthetic campaign. It does not publish sites or send/post social content.

Owner flow: input → editable facts/clarifications → reviewed forms → Lock →
strategy → copy → poster → audit/approval → authorized export. For local video,
create animation from a validated poster, approve the source, then review and
approve the animation. Use Create website for editable basics and a static ZIP.
Saved social URLs open the owner's accounts; poster upload/posting stays manual.
