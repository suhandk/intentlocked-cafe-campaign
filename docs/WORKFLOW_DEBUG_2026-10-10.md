# Workflow debugging — 10 October 2026

Campaign, prediction, posters and protected video paths were checked with isolated
MOCK inference/storage and actual Chrome canvas rendering. No paid generation,
live video, publishing or message send was performed. Existing campaign databases
were not opened for testing. App servers are left stopped.

## Verified fixes

- Resolved startup/migration merge conflicts, preserved social profiles, planning,
  saved video history and website tables, and regenerated OpenAPI/TypeScript types.
- Validated supported text/image model profiles and disabled unsupported video
  at configuration, API job admission and live inference boundaries. Unknown models
  and historical provider endpoints fail validation. The private environment's
  stale non-secret model selections were updated to current code defaults; private
  credentials were not copied or displayed. Safe example defaults now validate.
- Restored the NanoBanana `size` adapter alongside the current Seedream width/height
  adapter. Mock images now preserve native ratios for both supported adapters.
- Fixed base64 image responses being treated as remote URLs. Inline rasters use
  bounded decode, MIME/format, pixel/dimension and animation checks; SVG, malformed
  data and multiple unexpected image outputs are rejected.
- Removed raw provider-body printing/file logging and raw bodies from API errors.
  An existing raw log was moved into ignored private `data/debug-private-archive`
  storage without reading its contents into outputs. Error redaction has regression
  tests. Credential scans now include the website encryption key too.
- Video UI no longer advises enabling a capability the configuration rejects.
  Access attestation no longer masquerades as verified pricing. Direct calls to
  disabled video return HTTP 422 before creating a job or dispatching inference.
- Updated stale browser expectations for current commercial renderer, centered
  logo safe areas and explicitly selected poster sizes. Fast completed prediction
  jobs are accepted without requiring a transient running state to be visible.
  Cancellation uses a deterministic pending fixture only in the isolated test
  factory; the production app contains no test-control route.
- Added an isolated regression runner with virtual mock quota waits, owned-process
  cleanup and bounded retries for Windows temporary file-handle contention.

## Executed evidence

| Check | Outcome |
| --- | --- |
| Full backend regression | 583 passed after all changes in 39.82 seconds; one existing AnyIO deprecation |
| Branch-coverage run | 582 passed before the final cleanup-only test; critical modules 100% branches |
| New focused regressions | 17 passed, including Windows teardown recovery |
| Critical Guardian/slots branch coverage | claims, normalize, report, rules, slots: 100% each |
| Complete browser workflow | 21 passed in 1.8 minutes; explicit MOCK inference, real canvas/PNG |
| Teardown recheck | 2 foundation tests passed; runner cleanup PASS |
| Frontend typecheck/lint/build | PASS; Next 16.4.0 |
| Ruff lint/format | PASS, 110 Python files |
| Lockfile consistency | `uv lock --check` PASS |
| Repository/frontend credential scans | PASS; configured secrets/defined patterns only, not universal detection/history audit |
| Live gateway catalogue | Could not connect to configured local gateway; zero inference calls |
| Live generation / native Kannada sign-off | NOT VERIFIED / PENDING |

Runtime: Python 3.11.9, Node 24.20.0, npm 11.19.0. Required dependency versions and
locks remain unchanged. Test quota timing is virtual and is not provider latency.
The test clock is deliberately overridden to 2026-10-09 in visibly labeled MOCK
mode; this is not an owner-approved live campaign or human review.

The full browser suite's initial wrapper teardown encountered a Windows file lock
after its 21 tests passed. This was fixed and verified separately; the failure was
not silently relabeled as success. See [full browser result](evidence/workflow-browser-debug-full.json)
and [cleanup recheck](evidence/workflow-browser-debug.json).
See also [gateway check](evidence/workflow-gateway-check.json) and local coverage
`data/workflow-debug-coverage.json`.

Browser cases cover clarification and lock, 27 multilingual audience/channel cells,
stored simulated-score trajectory, retained copy/poster audit, all supported PNG
sizes (1080×1080, 1080×1350, 1080×1920, 1200×630), preview/export hash identity,
long Kannada/offer text, delayed/missing fonts, logos/SVG, stale and failed audits,
atomic changes, owner approval/export, reload, recovery and cancellation/retry.

Actual exported feed, story and long-Kannada PNGs were opened for visual inspection.
Text showed no obvious clipping; this was an assistant visual check of fixture
artwork, not a native Kannada reading or proof of provider-generated photography.
Mock image backgrounds are solid-color fixtures and appear as plain image regions.
Background QA for real generated images remains pending without verified vision.

## Remaining limitations

The selected local gateway is not running/reachable. Live campaign/prediction/image
generation therefore cannot be claimed as working from these offline results.
Configure and start the gateway, verify the selected model identifiers and transport
with the account, then perform explicitly bounded live integration checks.

No verified video model is configured. Video generation remains intentionally
disabled; saved drafts can be viewed but never become approved campaign exports.
Historical offline video parser/composition tests do not prove a live video API.

Live vision is blocked for the configured text profiles. Real generated backgrounds
remain blocked without independent QA; selecting local deterministic art is an
explicit option, not a silent replacement for a live failure. G14/native review,
current provider pricing/account capability, production/public security gates and
five real live rehearsals remain pending. No hackathon/production readiness claim.

## Reproduce

```powershell
.venv\Scripts\python.exe -m pytest -q --cov=backend --cov-branch --cov-report=json:data/workflow-debug-coverage.json
.venv\Scripts\python.exe -m scripts.check_guardian_coverage data/workflow-debug-coverage.json
.venv\Scripts\python.exe -m ruff check backend scripts
npm.cmd --prefix frontend run typecheck
npm.cmd --prefix frontend run lint
npm.cmd --prefix frontend run build
# Requires ports 3000/8000 free; starts/stops only its own MOCK test servers:
.venv\Scripts\python.exe -m scripts.verify_workflow
```
