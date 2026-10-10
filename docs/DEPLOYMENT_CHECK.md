# Deployment check — 2026-10-09

Verified profile: private Windows laptop, one backend worker, frontend port 3000,
backend port 8000. Public deployment is NOT approved.

| Check | Outcome |
| --- | --- |
| Backend suite | 464 passed after all fixes in 48.61 seconds; one existing AnyIO deprecation warning |
| Backup tests after fix | 4 passed, including immediate Windows cleanup regression |
| Guardian branch coverage | claims, normalize, report, rules, slots: 100% each |
| Ruff lint / format | PASS, 93 Python files formatted |
| Frontend typecheck / lint / build | PASS, Next 16.4.0 |
| Video UI browser test | 1 passed in 6 seconds, no generation submitted |
| Isolated MOCK startup / readiness | HTTP 200; public Host rejected with HTTP 400 |
| Empty / existing migrations | Versions 1–9; repeat initialization unchanged |
| Backup / restore / cleanup | PASS with temporary marked test fixture |
| Repository / frontend secret scan | PASS, 863 repository/build files and 285 frontend files |
| Clean install / lock resolution | NOT RUN: npm and uv absent from this shell |
| Full E2E / live generation / native review / cloud deployment | NOT RUN in this check |

[Startup evidence](evidence/deployment-startup.json); coverage at
`data/deployment-coverage.json`. Backend providers are mocked. The browser test
reads a saved LIVE campaign and tests consent; it does not generate video.
The secret scan covers working tree/build, not Git history.

## Fixes

- Removed a credential from tracked `.env.example` and restored mock/disabled-video
  defaults. **Revoke and replace the exposed key in Agnes before deployment.**
  Removal does not revoke it or remove prior history, logs or copies.
- Resolved conflict markers in requirements, security/release and progress docs,
  preserving both live-repair and Meta-delivery sections.
- Closed SQLite backup/verification connections explicitly. The transaction context
  manager leaves connections open; Windows temporary cleanup previously failed.
- Restarted the stopped backend on 8000 and production frontend on 3000.

## Reproduction

Verified Python **3.11.9**, Node **24.19.0**. All ten direct Python dependencies
match exact project pins. Transitive clean installation remains unverified.
Python must be 3.11 (`<3.12`); frontend requires Node >=22. Use Node 24 to match
this check. Install npm and uv, then run from repository root:

```powershell
uv sync --locked
npm.cmd --prefix frontend ci --no-fund
npm.cmd --prefix frontend run build
# First terminal:
.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 1
# Second terminal:
npm.cmd --prefix frontend run start
```

Use ignored `.env` or private server environment for keys; select `AGNES_MODE=live`
explicitly. Store SQLite and assets on persistent writable storage and back up
both after stopping work. Install Chrome (`channel: chrome`), Node on PATH, and
ffmpeg/ffprobe for optional video. Ignored workspace Windows binaries do not ship
in a checkout. No paid inference or message send occurred during this check.

## Public hosting blockers

Frontend binds to loopback and proxies to fixed `127.0.0.1:8000`; separate hosted
services cannot reach each other that way. API rejects public campaign hosts;
render origin remains local port 8000. Campaign authentication and tenant
authorization are absent. Do not remove host protection to expose this publicly.

A public profile needs access control, deliberate origin/proxy configuration,
persistent storage, rendering/media runtimes and single-worker quota coordination.
Current durable jobs and SQLite/assets are unsuitable for ephemeral serverless
hosting. Full live approval/export, native Kannada review, art/video QA and
release checks remain pending. No production readiness or human sign-off claimed.
