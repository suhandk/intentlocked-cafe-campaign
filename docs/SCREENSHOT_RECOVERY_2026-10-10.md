# Three screenshot failures: diagnosis and fixes

Date: 10 October 2026, Asia/Kolkata. The owner explicitly confirmed keeping
`openai/gpt-4o-mini` for text and `black-forest-labs/flux-schnell` for images.
Private credential values were neither displayed nor included in evidence.

## 1. Prediction: zero channels and disabled optimization

The actual latest saved selection omitted the strategy's suggested hero audience.
Its two generated variants were blocked. Consequently, there was no eligible
copy to score. The UI also silently selected a ready non-hero audience when one
existed, while the API required the hero. This was a real interface mismatch.
The old unscored count included blocked variants, which obscured the prerequisite.

The UI now exposes an explicit Audience group selector. The API accepts original
baselines from one saved audience and one language, including a non-hero group.
It still rejects mixed audiences/languages, stale revisions, blocked copy and
derived variants. Each run freezes its original baselines and all five saved
personas. No new audience is invented, and scores are not copied across groups.
Only ready variants enter the unscored count. An incomplete baseline has no
fabricated zero-valued trajectory. Missing drafts show an explanation and a
Review campaign copy action instead of an unexplained disabled control.

Files: `PredictionPanel.tsx`, `optimization_service.py`,
`optimization_repository.py`, `CopyReadinessNotice.tsx`.

## 2. Poster: waiting for a valid copy draft

The saved provider responses omitted LOCATION, ELIGIBILITY, ID_RULE and
MIN_PURCHASE_RULE in visible copy. Guardian correctly reported G05. One response
also contained a literal date and an unsupported wrapper, producing G02/G07/G08.
Three model attempts repeated these errors. Poster generation correctly refused
to use blocked text; the UI did not explain the upstream dependency well enough.

Code now appends missing required disclosure references to the body using only
approved fact slots. It never invents a fact value, inserts an unspecified
condition, repairs malformed slot syntax, erases a claim or grants an approval.
Every resulting template still runs through all Guardian rules. Required-field,
script, audience, claim, length and semantic-audit checks remain intact. Failed
repair feedback includes rule/field diagnostics without canonical fact values,
transcripts, surface strings or quoted provider output. R4 gives specific repair
instructions for literal dates, unsupported claims and language script.

A read-only replay of the actual saved responses demonstrated the boundary: the
draft blocked only by missing disclosures passes deterministic checks after slot
completion; the draft with unsupported wording remains blocked. The original
database and approvals were not modified by this replay.

Failed generation now records COPY_VALIDATION_FAILED, and the owner can explicitly
Retry unfinished copy. The retry binds the original audience/language/channel
selection and revision, carries ready cells forward and uses a fresh idempotency
key. Known terminal failures no longer reuse the old native generation key
indefinitely; uncertain network outcomes still retain their key. No automatic
generation loop is added. Poster selection ignores stale/blocked variants and
explains its prerequisites. Existing audits and exact-byte approvals still apply.

The generated-background path also had an undefined storage hash and treated
absent visual QA as ready. The hash is now written and checked, and missing QA
keeps real generated images blocked. Offline QA failures retain the existing
explicitly labelled local-art fallback, with no blind media resubmission.

Files: `generation_context.py`, `generation_service.py`, `prompts/R4.md`,
`CampaignMatrix.tsx`, `PosterPanel.tsx`, `art_service.py`.

## 3. Video: repeated VIDEO_VALIDATOR_MISSING

The running configuration enabled video and selected Grok 2 Vision. The machine
had neither FFmpeg nor FFprobe. Jobs reached tool validation and failed repeatedly.
The provider transport did not implement a verified video capability. A further
incorrect fallback could manufacture a clip ID from a generated image.

Video is disabled at Settings validation and API admission. A direct request is
rejected with HTTP 422 VIDEO_DISABLED before a durable job or inference call is
created. No image is substituted for a video, and a missing catalogue entry no
longer grants access. Installing FFmpeg alone is not proof of video support.
The UI hides unavailable authorizations/duration inputs, shows a disabled
generation control, retains saved draft viewing and presents stopped requests as
history. General workflow controls do not advertise retry for disabled video.

Files: `config.py`, `video_service.py`, `VideoPanel.tsx`, `WorkflowStatus.tsx`.

## Provider and runtime limitations

The old health response used hard-coded model defaults, so it could misreport
the configured models. It now reports actual settings, provider and image/video
availability. This project's idle backend/frontend were restarted; both
`/api/ready` endpoints return the selected GPT-4o mini/Flux pair, with video and
the unsupported image adapter disabled. Existing facts/history/approvals remain.

The public OpenRouter catalogues were checked on this date: GPT-4o mini is listed,
but Flux Schnell is absent from both the general and dedicated image catalogues.
The gateway `/images/generations` adapter is not OpenRouter's dedicated Image API.
The application therefore preserves Flux selection and rejects unverified image
transport before a potentially charged request. Choose local illustration
explicitly for posters, or provision a separately verified compatible Flux
gateway. No other image model is silently selected. Real image generation and
visual QA remain unverified; successful copy does not prove those capabilities.

Official sources:

- [General model catalogue](https://openrouter.ai/api/v1/models)
- [Image model catalogue](https://openrouter.ai/api/v1/images/models)
- [Dedicated Image API contract](https://openrouter.ai/docs/guides/overview/multimodal/image-generation)
- [Grok 2 Vision capabilities](https://openrouter.ai/x-ai/grok-2-vision-1212)

## Executed regression evidence

| Check | Actual outcome |
|---|---|
| Full offline backend suite | 589 passed; one existing AnyIO deprecation |
| New screenshot-specific backend tests | Six passed |
| Browser recovery and approval/export regressions | Four passed; explicitly MOCK API fixtures |
| Production frontend build, TypeScript and lint | PASS |
| Ruff lint/format and diff whitespace | PASS |
| Repository and frontend credential scans | PASS within documented scanner limits |
| Actual saved-response replay | One disclosure-only draft clears; unsafe draft stays blocked; zero provider calls |
| Running backend and frontend readiness | HTTP 200; actual configured model identities; unavailable capabilities explicit |
| Bounded real copy retry | LIVE GPT-4o mini: one of two drafts ready in three calls / 17.6 seconds; remaining G02/G07/G08 blocked |
| Actual local poster creation | One 1080 × 1350 PNG, 140135 bytes; validation PASS; zero provider calls; owner approval pending |
| Running app browser check | Selected non-hero optimization enabled, stored PNG visible, local render enabled, video disabled; zero UI writes |
| Live image/video and native Kannada/voice review | NOT VERIFIED / NOT PERFORMED |

Evidence: `evidence/screenshot-recovery-backend-tests.xml`,
`evidence/screenshot-recovery-targeted-tests.xml`,
`evidence/screenshot-recovery-browser-tests.xml`,
`evidence/screenshot-recovery-saved-replay.json`, and
`evidence/screenshot-recovery-live-copy.json`,
`evidence/screenshot-recovery-local-poster.json`, and
`evidence/screenshot-recovery-running-ui.json`. Tests cover missing approved slots,
unknown ID conditions, malformed tokens, retained claim rejection, concealed
repair values, non-hero selection, mixed-audience rejection, duplicate unsupported
video admission, unavailable-image dispatch, exact approval/export recovery and
the browser's deliberate retry/render navigation. None grants owner approval.

The local poster is an actual stored draft derived from the valid LIVE copy,
using explicitly selected deterministic artwork. It is not a provider-generated
Flux image. Its downloaded bytes match the saved SHA256, and the server returns
`X-Artifact-Approval: pending`. Neither the live check nor its browser inspection
performed a final audit, owner approval, social publication or message send.
The remaining unsafe draft was retained as blocked; no further calls were made
to force a preferred outcome. Live optimization itself was not run.

Reproduce from PowerShell at the repository root:

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check backend scripts
npm.cmd --prefix frontend run lint
npm.cmd --prefix frontend run build
Set-Location frontend
node node_modules/playwright/cli.js test --config=playwright.recovery.config.ts
```

The browser runner uses its own port 3002 and simulated responses; it does not
send social messages or approve real campaign output. Earlier failing runs were
corrected and rerun; the linked reports describe the final executed outcomes.
