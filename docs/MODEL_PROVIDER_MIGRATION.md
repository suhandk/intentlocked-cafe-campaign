# Current model configuration

## Selected OpenRouter Seedream profile — 10 October 2026

Current owner choice supersedes the direct OpenAI profile below: GPT-4o mini
text, Seedream 5.0 Flash images and GPT-4o mini visual QA use OpenRouter with
`INFERENCE_API_KEY`. `IMAGE_PROVIDER=gateway`, exact image slug
`bytedance-seed/seedream-5-0-flash`, optional `OPENAI_API_KEY` blank.
Public capabilities HTTP 200; authenticated image HTTP 402 PAYMENT_REQUIRED.
No image/vision success is asserted. [Switch report](SEEDREAM_SWITCH_2026-10-10.md).

## Earlier direct OpenAI image configuration — 10 October 2026

The owner changed the image-provider choice after the real OpenRouter image
request returned HTTP 402. Current text is `openai/gpt-4o-mini` through OpenRouter;
images are `gpt-image-2.5-flare-2026-09-08` through direct OpenAI. Set
`IMAGE_PROVIDER=openai`, `OPENAI_API_KEY` privately, and `ENABLE_VISION=true`.
Ordinary text uses `INFERENCE_API_KEY`. Visual QA uses direct OpenAI GPT-4o mini
with the image key. Keys are never sent to each other's endpoint or the frontend.
The final supplied key returned HTTP 401 on an actual image request. OpenAI image
bytes/vision remain NOT_TESTED; authentication FAILED. Local artwork and real
FFmpeg poster animation are explicit alternatives.
Remote AI video remains disabled. [Current report](HACKATHON_VERIFICATION_2026-10-10.md).

Raw transport: POST `https://api.openai.com/v1/images/generations` with model,
prompt, n=1, quality=medium, output_format=png and size 1024x1024 (square),
864x1536 (portrait), or 1536x864 (landscape). The adapter reads data[0].b64_json,
validates bounded bytes and actual image encoding, and retains usage/cost only
when returned. There is no response_format parameter for this GPT image model.
Mock HTTP shape tests pass; that does not establish real account entitlement.
OpenAI image/vision API availability and charges remain real-probe dependent.

Documentation checked 10 October 2026:
[OpenAI raw Images API](https://developers.openai.com/api/reference/resources/images/methods/generate),
[image generation guide](https://developers.openai.com/api/docs/guides/tools-image-generation).
The optional gateway adapter uses OpenRouter's dedicated `/api/v1/images` route,
after checking model endpoint parameters, as documented in
[OpenRouter's raw HTTP tutorial](https://openrouter.ai/blog/tutorials/image-generation/).
The failed 402 result remains in `evidence/hackathon-image-live.json`.

## Earlier owner-confirmed pair — historical

The owner confirmed retaining `openai/gpt-4o-mini` and
`black-forest-labs/flux-schnell` during screenshot recovery. Video is disabled.
The former model profiles below remain compatible options, not automatic fallbacks.
Current OpenRouter model/image catalogues contain no Flux Schnell entry; unsupported
image transport fails before inference. Local artwork is an explicit alternative.
Health now reports the actual configured pair. See
[screenshot recovery](SCREENSHOT_RECOVERY_2026-10-10.md) for current evidence and
limitations. Historical provider checks below do not verify this pair.


10 October 2026 update: current code defaults are `upstage/solar-mini4` and
`bytedance-seed/seedream-5-0-flash`. The earlier GPT-OSS/NanoBanana gateway profile
below remains explicitly selectable; no automatic fallback occurs. The current
Seedream adapter uses width/height; NanoBanana retains its size/response-format
adapter. Both have controlled offline ratio/download tests. Live gateway remains
unreachable, and neither profile has verified live vision/video capability in
this application. See [current debugging evidence](WORKFLOW_DEBUG_2026-10-10.md).

Verification date: 9 October 2026. The owner's model replacement request overrides
the original guide's Agnes model allowlist. Historical Agnes evidence describes
previous runs and does not verify these replacement models.

| Operation | Exact permitted model | Current evidence |
|---|---|---|
| Text, facts, strategies, scoring, edits, text audits | `ollama/gpt-oss:120b` | Offline tests; authenticated checks NOT_TESTED |
| Image generation | `nb/nanobanana-flash` | Offline raw-request/download tests; authenticated checks NOT_TESTED |
| Vision | Unsupported by the selected text model | Capability documentation; no live call attempted |
| Video | Disabled | Rejected before provider transport; existing history retained |

The single server-side client is `backend/inference_client.py`. Existing approval,
Guardian, revisions, jobs, cancellation, retry budgets and API error conventions
are retained. No old model fallback exists. Historical records retain their
original model identifiers. Art cache keys include the gateway and model context.
Unknown provider prices remain unknown; former Agnes rates are not reused.

## Gateway and credentials

These names are documented kRouter provider aliases. The compatible default is
`http://127.0.0.1:20128/v1`; this gateway must be installed/configured separately.
The read-only local connectivity check found no gateway running in this session.
Remote gateways require HTTPS and a gateway client key. Another gateway must
support these exact identifiers and documented transport before live use.

The ignored root `.env` has server-only credential slots; `.env.example` keeps
them blank. Two populated upstream keys appeared in the example during final
verification and were moved into private `.env` without displaying their values.
The gateway key remains to be configured. Safe example configuration:

```dotenv
INFERENCE_MODE=mock
INFERENCE_BASE_URL=http://127.0.0.1:20128/v1
INFERENCE_API_KEY=
NANOBANANA_API_KEY=
OLLAMA_API_KEY=
TEXT_MODEL=ollama/gpt-oss:120b
IMAGE_MODEL=nb/nanobanana-flash
STRUCTURED_STRATEGY=json
MEDIA_ALLOWED_HOSTS=[]
ENABLE_VIDEO=false
VIDEO_MODEL=disabled
```

`INFERENCE_API_KEY` is the gateway's client token. The NanoBanana and Ollama fields
are private credential slots for provisioning the upstream providers: configure
those providers in the gateway dashboard using their respective keys. The app
does not substitute an upstream key as the gateway bearer token, nor configure
the separate gateway automatically. Local Ollama may not need a cloud key.
Never put any key in `NEXT_PUBLIC_*`, browser storage or frontend configuration.
Meta delivery remains disabled; saved social profile links remain manual.

## Verified documentation and HTTP contract

Official sources inspected on the date above:

- [kRouter NanoBanana provider](https://krouter.kodelyth.com/providers/nanobanana)
- [kRouter Ollama provider](https://krouter.kodelyth.com/providers/ollama)
- [kRouter API](https://krouter.kodelyth.com/docs/api)
- [Official raw image route](https://github.com/sifxprime/krouter/blob/main/src/app/api/v1/images/generations/route.js)
- [Official NanoBanana image adapter](https://github.com/sifxprime/krouter/blob/main/open-sse/handlers/imageProviders/nanobanana.js)
- [Ollama GPT-OSS 120B capabilities](https://ollama.com/library/gpt-oss:120b)
- [Ollama vision model requirements](https://docs.ollama.com/capabilities/vision)

Chat uses `POST /v1/chat/completions`, the exact text model and `messages`.
Strict JSON instructions plus Pydantic validation are the default. Forced tools
remain an explicitly selectable strategy only after its real probe succeeds.
Image generation uses `POST /v1/images/generations` with this raw JSON:

```json
{"model":"nb/nanobanana-flash","prompt":"Approved café art direction","size":"1024x1024","n":1,"response_format":"url"}
```

The documented adapter maps `size` to the NanoBanana aspect ratio and normalizes
the response to `data: [{url, revised_prompt}]`. This was checked against source
and controlled HTTP fixtures, not authenticated raw traffic. No SDK `extra_body`
assumption is used. Configure verified exact public CDN hosts for downloads;
private addresses, redirects, invalid MIME, oversized bytes and tampering fail.

## Image approval boundary

GPT-OSS is text-only, so it cannot perform the existing visual R9 checks. A live
generated image is persisted with its real hash and blocked/pending QA status.
The restricted unapproved preview is labelled blocked; it grants no export
authorization. No fabricated visual inspection is stored. Use the existing local
artwork path to proceed through normal approval until compatible visual QA is
explicitly designed and verified. Offline mock QA is only a fixture simulation.

## Local verification after adding credentials

Configure the gateway's upstream providers, its client token and exact image CDN
host allowlist first. Keep the app in MOCK until reviewing real smoke evidence.

PowerShell from the repository root:

```powershell
.venv\Scripts\python.exe -m scripts.smoke_models --mode live --output docs/evidence/models-smoke-live.json
```

bash:

```bash
.venv/bin/python -m scripts.smoke_models --mode live --output docs/evidence/models-smoke-live.json
```

The command sends real requests and can incur charges. It records text,
structured-output, schema rejection, usage and image/download outcomes separately.
Vision/video remain UNSUPPORTED. Failures do not switch to mock or old models.
Do not resubmit uncertain image jobs automatically. Successful generation alone
does not establish visual QA or approval/export eligibility.

Offline smoke evidence: `docs/evidence/models-smoke-mock.json`. Authenticated
checks for both replacement models are explicitly NOT_TESTED because a configured gateway
is unavailable. Presence of upstream keys alone does not verify access. Automated regression and browser
results are in the model-migration JUnit reports alongside that evidence.
