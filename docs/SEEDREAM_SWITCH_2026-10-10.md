# OpenRouter Seedream selection — 10 October 2026

The owner selected Seedream through OpenRouter after explaining that the key
placed in the direct OpenAI field was actually an OpenRouter key. This selection
supersedes the earlier direct OpenAI image profile. The existing bounded client,
Guardians, fact revisions, approval hashes, durable work and exports are preserved.

## Active configuration

```dotenv
INFERENCE_BASE_URL=https://openrouter.ai/api/v1
TEXT_MODEL=openai/gpt-4o-mini
IMAGE_PROVIDER=gateway
IMAGE_MODEL=bytedance-seed/seedream-5-0-flash
INFERENCE_API_KEY=<private OpenRouter key; never publish>
OPENAI_API_KEY=
ENABLE_VISION=true
LOCAL_VIDEO_ENABLED=true
ENABLE_VIDEO=false
```

Private `.env` was updated without emitting credentials. The existing OpenRouter
key was retained; the misplaced unused OpenAI field was cleared. The safe example
contains blank keys. Text, image generation and GPT-4o mini visual QA all use the
OpenRouter transport. Remote AI video remains disabled; local poster animation
still produces real MP4s. No frontend or approval interface was changed.

## Actual request and outcome

Public capabilities:
`GET https://openrouter.ai/api/v1/images/models/bytedance-seed/seedream-5-0-flash/endpoints`
returned HTTP 200. The exact model, 1K resolution, three application aspect ratios
and n=1 are supported in that returned document. See the [catalogue record](evidence/hackathon-seedream-catalog.json).

At `2026-10-09T23:04:02Z`, one real request was sent to
`POST https://openrouter.ai/api/v1/images` with this raw payload:

```json
{"model":"bytedance-seed/seedream-5-0-flash","prompt":"Photorealistic premium coffee advertising background. One unbranded ceramic coffee mug with visible coffee and subtle steam in lower right. Cinematic warm amber light, anonymous dark espresso studio backdrop, coffee hero fully visible. Negative space upper left. No text, numbers, logos, signage, food, people, furniture, offers, badges, watermarks. Square composition.","n":1,"resolution":"1K","aspect_ratio":"1:1"}
```

HTTP **402** was mapped to the application's normalized error
`{"code":"PAYMENT_REQUIRED","message":"Provider credits or payment required","retryable":false}`.
This is the normalized application error, not a fabricated raw upstream body.
One request was recorded; there was no payment retry. No image bytes were
generated, visual QA was NOT_TESTED, and usage/actual billed cost are unknown.
See the [authenticated failure](evidence/hackathon-seedream-image-live.json).

The documented successful response contains `data[0].b64_json` and an image
media type; actual success on this account remains unverified. The client decodes
bounded bytes and checks the real image format rather than assuming PNG. SDK
conventions are not used to infer the HTTP shape.

## Completed verification

- Selected-profile offline smoke: text, structured tools, truncation rejection,
  1K image download, vision fixture and usage PASS; authenticated status is not
  inferred from fixtures. [Smoke](evidence/hackathon-seedream-smoke-mock.json).
- Initial smoke exposed missing offline capability and image routes. Added a
  local capability fixture and raw image fixture; three aspect-ratio regressions
  run with external networking denied and a fake clock. Preserved the
  [pre-fix failure](evidence/hackathon-seedream-smoke-before-fixture-fix.json).
- **26 targeted backend tests PASS**, including the three new offline regressions,
  raw JPEG handling, unsupported parameters, payment without retries, key
  separation, cancellation, source approval and cached manifest checks.
  [JUnit](evidence/hackathon-seedream-tests.xml).
- Ruff check/format PASS. No frontend code changed in this switch; the earlier
  production build and 26-case browser run remain separately recorded.
- Idle backend restarted. Both ready endpoints and frontend return HTTP 200;
  approved test MP4 and website ZIP re-download with identical SHA256. Cached
  MP4 headers still retain cached/source provenance. [Runtime](evidence/hackathon-seedream-runtime.json).

The full 635-test suite passed before this switch; it is not relabeled as a new
full-suite run. Current authentication requires credits; local artwork does not.

## Unblock live image generation

Add credits to the OpenRouter account associated with `INFERENCE_API_KEY`, then
run from the repository root in PowerShell:

```powershell
.venv\Scripts\python.exe -m scripts.probe_hackathon_image
```

bash: `.venv/bin/python -m scripts.probe_hackathon_image`.
The bounded probe writes a redacted report and exits nonzero for provider/QA
failure. No key change or restart is needed just to add credits to the same key.
Only a successful real image and QA result can clear the live verification block.
Existing failed campaign work needs an explicit current-revision retry; no calls
are automatically repeated to obtain a preferred result.

Official sources checked 10 October 2026:
[Seedream 5.0 Flash](https://openrouter.ai/bytedance-seed/seedream-5-0-flash-20261001),
[Unified Image API](https://openrouter.ai/blog/announcements/image-api/),
[per-endpoint capabilities](https://openrouter.ai/docs/api/api-reference/images/list-image-model-endpoints).
