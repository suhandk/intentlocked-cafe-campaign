# Website model and functional check — 10 October 2026

The website layout model is now **qwen/qwen3-coder-flash** through the direct
OpenRouter API (`https://openrouter.ai/api/v1`). Campaign, prediction, poster and
video model settings are unchanged.

The earlier website renderer had no AI model. The new model selects a strict visual
plan (layout, spacing, headings, cards and photo arrangement). Code renders all
HTML/CSS and locked fact values. Raw model HTML, JavaScript, URLs, prices, offers
or other copy are never accepted. The owner's colour/style and missing-section
rules remain intact. Facts, freeform owner prose, menu prices, contact data, media
URLs, Netlify tokens and platform keys are excluded from the model input.

OpenRouter documents [Qwen3 Coder Flash](https://openrouter.ai/qwen/qwen3-coder-flash)
as a coding model with JSON output support, without JSON-schema enforcement.
The client requests JSON-object mode and provider parameter support; strict local
Pydantic validation and fixed CSS mappings enforce the boundary. At most two
provider requests/repairs are permitted within 90 seconds. Invalid responses,
missing credentials, cancellation and stale revisions preserve prior work and
never silently substitute fixture output for a failed live request.

## Server configuration

```dotenv
WEBSITE_MODEL=qwen/qwen3-coder-flash
WEBSITE_AI_MODE=mock
OPENROUTER_API_KEY=
```

Set `OPENROUTER_API_KEY` privately in the root ignored `.env` or server environment,
then select `WEBSITE_AI_MODE=live` and restart the backend to enable real inference.
No key is requested in the website wizard. Never put this key in `NEXT_PUBLIC_*`.
The key is distinct from owner Netlify publish tokens and from the campaign gateway
credential; neither is reused for OpenRouter. Mock mode is explicit and displayed
in the wizard/bundle metadata. Old deterministic bundles retain BASIC provenance.
Source mode, model, plan, prompt/input hashes and bounded call metadata are stored
with new bundles. Fact or draft changes during generation reject the late result.

## Executed outcomes

- OpenRouter public catalogue: HTTP 200, model listed, `response_format` supported.
  This does not prove account access. No OpenRouter server key is configured, so
  authenticated generation remains NOT_RUN. No paid inference was submitted.
- Backend full suite: **597 passed**, one existing AnyIO deprecation warning.
  Fourteen new design cases cover concealment, request shape, invalid/extra/script
  output, bounded repairs, missing live credentials, stale facts/drafts, cancellation,
  duplicate submissions, source provenance and unchanged campaign data.
- Website HTTPS browser suite: **2 passed (12.8 seconds)** using explicitly mocked
  model/hosting responses, actual HTTP routes and actual rendered pages.
- Browser flow checks resume, required fields, read-only offer, model/mode display,
  labeled Guardian results, preview, ZIP, invalid hosting token, encrypted remember/
  deletion and exact hash approval. Optional menu/hours/contact/social/logo/photos
  and English/Kannada sections render. Mobile width 390px has no horizontal overflow.
- Frontend typecheck/lint/build, Ruff lint/format and credential scans: PASS.
  Nine CSV/client validation tests also pass. Model failures remain visible.
- Actual [mobile page](evidence/website-openrouter-page-mobile.png) and
  [desktop page](evidence/website-openrouter-page-desktop.png) screenshots were opened
  for visual inspection. Images/owner data are explicit fixtures, not real café proof.

Publishing remains optional/disabled by default and requires HTTPS plus owner token,
read-only connection test and exact bundle approval. Netlify live publishing and
native Kannada reading remain unverified. Missing G14 is still pending, never passed.
Application servers were left stopped after the isolated checks.

## Reproduce

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_website.py backend/tests/test_website_design.py -q
npm.cmd --prefix frontend run typecheck
npm.cmd --prefix frontend run lint
npm.cmd --prefix frontend run build
.venv\Scripts\python.exe -m scripts.verify_website_ui
```

The last command temporarily starts its own private MOCK test servers and stops them.
See [catalogue evidence](evidence/website-openrouter-catalogue.json).
