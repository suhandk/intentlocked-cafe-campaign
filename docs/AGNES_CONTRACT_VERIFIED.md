# Agnes contract evidence

## B7 local workflow transport evidence — 2026-10-09

This stage used **MOCK**, not authenticated Agnes. Exact allowlisted text model:
`agnes-3.0-flash`; image model `agnes-image-2.5-flash`; video remains opt-in/off.
No additional capability or entitlement was invented.

| Check | Transport/model/status | Actual outcome |
|---|---|---|
| Durable strategy/generate/reader/change | /api/campaigns/{id}/work → 202; original AgnesClient mock HTTP / text allowlist | strict schemas, real persisted mock results; browser approval/export path exercised |
| 429 queueing | mock Agnes HTTP 429 + Retry-After:31 | fake clock wait, two recorded attempts, completed; replay adds none |
| Image timeout | image allowlist / injected HTTP timeout | one submission, unknown outcome; disclosed deterministic fallback, unsafe resubmit rejected |
| Local event transport | GET /api/stream/{id}, Last-Event-ID; 200 text/event-stream | raw HTTP replay verified in b7-recovery.json; IDs increase; no new calls/costs |
| Authenticated roles/remote image vision/video | server-side Agnes key only | NOT_TESTED / video disabled |

Timestamped actual outcomes: evidence/b7-browser-run.json, b7-recovery.json,
b7-tests.xml and b7-coverage.json. Secret-free local payload example:
`{"kind":"strategy","idempotency_key":"owner-strategy-key","input":{"expected_revision":5}}`.
Response includes server job ID, queued/running/terminal status, deadline, source
mode and saved result. SSE carries `id`, `event: workflow` and typed JSON action
messages; its shape is observed raw HTTP, not an SDK convention. This does not
verify Agnes account transport; authenticated checks remain NOT_TESTED. Run the
existing live smoke command below privately before any live integration claim.

## B6 additions, 2026-10-09

R8 uses the same bounded AgnesClient and strict structured result strategy.
Code validates operation targets/types/scopes/evidence and owns classification.
The actual browser flow used MOCK R8/R2/R7 to publish 20%→15%, audit/approve and
authorize the current manifest. Capture: evidence/b6-browser-run.json, with UTC
timestamp, mode, complete published snapshot and export outcome. This is not live
provider evidence or native-language review. Authenticated R8: **NOT_TESTED**.

For real account transport, privately configure the ignored server key and run
`.venv\Scripts\python.exe -m scripts.smoke_agnes --mode live --vision` (bash:
`.venv/bin/python -m scripts.smoke_agnes --mode live --vision`). Then remove the
demo clock override, use AGNES_MODE=live and perform/review the owner change flow.
Record actual role outcomes before claiming live G6. No external inference was
sent by the executed mock tests; no remote poster vision capability is asserted.

## B5 additions, 2026-10-09

R5/R6/R7 structured role payloads use the existing single AgnesClient, forced
deliver_result/tools or explicitly configured strict JSON strategy. Captured mock
payloads verify five fixed personas, anonymous AB/BA texts, bounded R6 edits and
blinded R7 input without facts/scores. Live authenticated roles: **NOT_TESTED**.

Actual Chrome/API evidence is in evidence/b5-browser-run.json and
evidence/b5-poster-audits.json. It is explicitly MOCK: six optimization transport
attempts, one accepted fixture edit, a no-change stop, and exact saved PNG/text
provenance audits at three sizes. This verifies orchestration/contracts, not real
provider judgment, language quality, conversion lift or billing. R7 remote image
vision/OCR is NOT_TESTED and is not called by this flow.

To verify account transport locally, privately configure the ignored key and run
`.venv\Scripts\python.exe -m scripts.smoke_agnes --mode live --vision` (bash:
`.venv/bin/python -m scripts.smoke_agnes --mode live --vision`). Review that real
report before enabling live runtime. Remove TODAY_OVERRIDE in live mode, start
the backend with AGNES_MODE=live, lock owner-reviewed facts, generate a baseline,
then invoke Optimize hero group. Record actual role outcomes before declaring live
G5 verified. No automatic live-to-mock or remote-vision capability assumption exists.

## B4 additions, 2026-10-09

Offline mocks now test T1 image generation at 1K with 1:1, 9:16 and 16:9 ratios;
immediate validated raster download; R9 forced structured QA with an attached
persisted PNG data URI; complete flag gating, schema repair and deterministic
fallback. Actual non-AI canvas rendering was executed in Chrome and PNGs inspected.
This is not authenticated Agnes evidence. Native dimensions of fixture art are
1024×1024, 576×1024 and 1024×576; real provider dimensions are validated against
ratio/tolerance and minimum resolution, not assumed to equal export dimensions.

Account checks for those ratios, 1K output, structured vision and data-URI support
remain **NOT_TESTED**. The attempted official docs refresh was inaccessible via
the web tool; existing documented transport/profile is retained without claiming
new provider verification. If attached-pixel vision is unsupported/unavailable,
R9 stays unapproved and the application uses a labeled deterministic background.
No inference provider besides Agnes was introduced. See ART_BOUNDARY.md.

B0 review: 2026-10-08, Asia/Kolkata. Authenticated requests: **none**. Environment key absent; no root/backend `.env` file was found (contents were not printed). All account checks remain **NOT_TESTED**. Offline implementation evidence is separate below. The filename does not imply live verification.

## Executed offline evidence

`python -m scripts.smoke_agnes --mode mock --vision` passed text, forced-tool parsing, local truncation rejection, usage handling, a 1024x1024 PNG download/decode/hash, and the mocked public-image request shape. This uses local fixtures and proves no real model compliance, visual understanding, entitlement or remote media accessibility.

Authoritative timestamp, model IDs, attempt/repair counts, measured durations, usage, artifact filename and SHA-256 are in [smoke-mock.json](evidence/smoke-mock.json). Artifact bytes persist under ignored `data/assets`. The mock PNG hash is `2962bb20817bf5b765507bae1a8d91feb2d838e87eb3ff0de409d191d107fce0` (5,339 bytes). Video was not requested. Unit tests separately exercise explicit strict-JSON fallback, authentication errors, 429/Retry-After, bounded 5xx/timeouts, malformed output and safe schema repairs. Mock statuses use MOCK_PASSED or LOCAL_PASSED, never account VERIFIED.

Exact live command after privately configuring a server key: `.venv\Scripts\python.exe -m scripts.smoke_agnes --mode live --vision` (bash: `.venv/bin/python -m scripts.smoke_agnes --mode live --vision`). Report: `docs/evidence/smoke-live.json`. Remove `--vision` to omit the optional probe. No live report exists yet. Video additionally requires `--video`, explicit enabled/verified-entitlement settings and ffprobe; it remains untested and disabled by default.

## Redacted raw transport examples (mock-tested, not provider captures)

Header on live requests: `Authorization: Bearer <server-secret>`. Mock requests send no authorization header. Text endpoint: `POST https://apihub.agnes-ai.com/v1/chat/completions`; body includes model, messages, temperature=0, bounded max_tokens. Forced structured calls use the following fields; no text response_format is assumed:

```json
{
  "model": "agnes-3.0-flash",
  "messages": [{"role": "user", "content": "{\"input\":\"Return a greeting in message.\"}"}],
  "temperature": 0,
  "max_tokens": 1024,
  "tools": [{"type":"function","function":{"name":"deliver_result","description":"Return the validated result","parameters":{"type":"object","properties":{"message":{"type":"string","minLength":1,"maxLength":100}},"required":["message"],"additionalProperties":false}}}],
  "tool_choice": {"type":"function","function":{"name":"deliver_result"}}
}
```

The client also supplies a schema-bearing system message. The fixture response is `choices[0].message.tool_calls[0].function.arguments` containing `{"message":"MOCK structured result"}`, `finish_reason=tool_calls`, one expected function, and usage 20 input / 8 output / 28 total tokens. Extra/missing calls, wrong tool names, conflicting content, truncation, duplicate JSON keys and schema violations are rejected. These are fixture tokens, not a measured Agnes bill.

Image endpoint: `POST https://apihub.agnes-ai.com/v1/images/generations`:

```json
{"model":"agnes-image-2.5-flash","prompt":"Abstract background; no writing or logos.","size":"1K","ratio":"1:1","extra_body":{"response_format":"url"}}
```

Fixture response: `{"data":[{"url":"https://mock.invalid/background.png"}]}`. The downloader uses a separate credential-free client; mock.invalid is only accepted with the offline transport. Real downloads require reviewed Google Storage hosts and public-IP pinning. Optional image references and raw request variations were not tested. No SDK request-merging convention is relied upon.

Status vocabulary: VERIFIED = this account's recorded test succeeded; DOCUMENTED_NOT_TESTED = official documentation reviewed, no authenticated evidence; FAILED = an actual attempted capability failed; NOT_TESTED = no test/evidence. Track documentation and account outcomes independently.

| Capability | Documentation status | Account smoke status | Next evidence |
|---|---|---|---|
| Text chat, agnes-3.0-flash | DOCUMENTED_NOT_TESTED | NOT_TESTED | B0 basic response, usage, finish status |
| Function tools / forced structured result | DOCUMENTED_NOT_TESTED | NOT_TESTED | Exactly one expected tool; validated arguments/name/count/finish; determine forced behavior |
| Strict JSON prompt fallback | NOT_TESTED | NOT_TESTED | Use only if tool strategy unsuitable; bounded Pydantic repairs, reject malformed/truncated results |
| Thinking extension | DOCUMENTED_NOT_TESTED | NOT_TESTED | Disabled until response handling verified; R3/R6 only |
| Public image URL text/vision input | DOCUMENTED_NOT_TESTED | NOT_TESTED | Optional B0 public-image probe; no localhost claims |
| 1K image URL generation | DOCUMENTED_NOT_TESTED | NOT_TESTED | Raw httpx POST, immediate safe download, MIME/decode/dimensions/hash |
| Image references | DOCUMENTED_NOT_TESTED, inconsistent presentations noted by guide | NOT_TESTED | Optional separate raw payload probe; unnecessary for required background MVP |
| Video create/poll/download and Flash entitlement | NOT_TESTED in this review; supplied PDF/guide describe it | NOT_TESTED | V1 opt-in; disabled by default |
| Actual key quota, shared limits, billing | NOT_TESTED for account | NOT_TESTED | Platform/account evidence; no free-entitlement claim |

## Official documentation reviewed

- [Text model](https://wiki.agnes-ai.com/en/docs/agnes-30-flash): chat endpoint, Bearer authentication, tools/tool_choice, usage and finish_reason, public image inputs, thinking extension. This documents features, not reliable schema compliance on this account.
- [Image model](https://wiki.agnes-ai.com/en/docs/agnes-image-25-flash): size tiers and ratio; URL output under `extra_body.response_format`; optional reference descriptions. It explicitly warns against top-level response_format. SDK merging is not a raw transport test.
- [Access plans](https://wiki.agnes-ai.com/en/docs/tokenplan): effective default text and 1K-image limits displayed as 10 RPM. Plan client defaults at 8 RPM; teammates may share the pool.
- [Pricing](https://wiki.agnes-ai.com/en/docs/pricing): reviewed alongside the supplied brief; list-price estimates must remain separate from account charges and entitlements.

## B0 probe plan

Base `https://apihub.agnes-ai.com/v1`, append `/chat/completions` or `/images/generations` once. Secret only in server Bearer header. Probe tools first, strict JSON fallback second; no assumed text JSON mode. Basic image uses `model=agnes-image-2.5-flash`, `size=1K`, ratio and `extra_body.response_format=url`. Never send credentials to media hosts.

Record timestamp, capability/model, redacted request shape, HTTP and finish status, selected structured strategy, attempt/repair count, duration, usage (or unknown), download validation/hash, actual outcome and artifact reference. Do not record keys, authorization headers, raw personal data or signed URL query strings. Mock evidence has its own label and cannot update account status to VERIFIED.

No authenticated smoke command has run. `scripts/smoke_agnes.py` exists and was exercised in mock mode only. No automatic media resubmission after ambiguous timeout; optional video remains off. Official text/image pages were revisited during B0; the optional Flash-video page was opened, but no account entitlement was inferred.
