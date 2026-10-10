# Content calendar: analysis, placement and verification

Implemented 9 October 2026 as an extension of the existing single-owner workspace.
No new dependency, provider, login system or social publishing API was added.

## Analysis of the supplied files and screenshot

| Source | Useful idea | Issue resolved in this implementation |
|---|---|---|
| `page (1).tsx` and calendar screenshot | Monthly calendar, upcoming cards, café styling | Original month/events/statuses were static; navigation did nothing and October dates were misaligned. Dates now align to weekdays and cards come from persisted owner plans. |
| `ClientLayout.tsx` | Clear navigation and warm neutral shell | Its unrelated `/app` routes/authentication would conflict with the completed eight-stage workspace. Existing shell is preserved with a separate planning entry. |
| `page.tsx` | Campaign overview | Sample reach, conversion figures, campaigns and publishing logs were invented. Only actual saved-plan counts are shown. |
| `client.tsx` | Reuse preferences from a past campaign | The prototype inserted a campaign ID into a transcript without loading that campaign's rules. The backend now reads an actual saved campaign, copies tone/theme/colours/languages, and creates a fresh draft. Facts, restrictions, dates, targeting, assets and approvals are not copied. No effectiveness prediction is claimed. |

The attachments are design references, not permission to adopt their fake data,
extra services or application architecture.

## Placement and owner flow

**Plan ahead** in the workspace header opens `/calendar`, even before a campaign
exists. This precedes Speak/Type without changing the eight existing stages.

1. Select a day/month, enter a title, posting time (IST), platform and editable brief.
2. Save a plan; reload, edit or cancel it later. No generation or approval occurs.
3. Choose **Start campaign from brief**. One new persisted draft opens in Speak/Type.
   Review canonical facts and forms, then use the existing lock/generate/audit flow.
4. After authorized final output is available, use **Plan a manual … post with
   approved output** in Approve + Export. The calendar receives the exact item IDs,
   campaign and revision. Choose the original plan, navigating to its month when
   necessary, or explicitly create another plan.
5. Save the selection. Current approval, hashes, audit and artifacts are checked
   server-side before the plan is labeled **Approved output ready**.
6. When due, open the linked campaign's existing manual export/publishing flow,
   download the approved poster, copy the description and open your saved profile.
   After actually posting, **I posted this manually** records the owner's report.

Posting time and offer validity are separate. Moving a calendar date never edits
locked offer dates. Planning beyond an offer's expiry requires review. Use absolute
offer dates in future briefs; relative phrases resolve through the normal campaign
clock when facts are proposed. The calendar clock uses actual IST, independent of
the visible demo fact-extraction override.

The calendar does not schedule automatic publishing, contact social platforms,
send notifications or infer that a post succeeded. `owner_posted` means owner
reported, not platform verified. Upcoming/due cards cover the selected month.
The monthly response is bounded to 200 plans and lists the latest 100 campaigns;
the interface explicitly discloses the monthly cap. No reach/CTR analytics appear.

## Persistence and contracts

Migration `010_plans.sql` adds `campaign_plans`; migration 009 and existing
campaign/approval/work storage remain compatible. Generated OpenAPI and frontend
types include the new strict models. API operations:

| Route | Input / result |
|---|---|
| `GET /api/plans?month=YYYY-MM` | Actual IST clock, month-scoped PlanViews and saved campaign choices |
| `POST /api/plans` | CreatePlan with idempotency key; 201 persisted Plan |
| `PUT /api/plans/{id}` | Complete editable plan + expected_version; updated Plan |
| `POST /api/plans/{id}/start` | expected_version; one fresh Campaign, atomically linked to plan |
| `POST /api/plans/{id}/cancel` | expected_version; cancelled Plan |
| `POST /api/plans/{id}/posted` | expected_version + explicit owner_confirms_manual_post; independently verified current approved selection required |

Dates are validated local ISO minutes in `Asia/Kolkata`, with the supported range
2020–2100. Closed plans are immutable. Create keys bind the complete request;
different data under an existing key returns 409. Competing edits return 409.
Duplicate start returns the already linked campaign, and duplicate terminal
actions return the saved outcome. No async work is admitted for planning.

Derived readiness is `brief_only`, `review_required`, `ready` or `stale`, distinct
from planned/cancelled/owner_posted lifecycle status. Saved readiness is never
trusted as approval. Item selection is constrained to campaign/platform; generic
poster items can be attached to a social plan. Stale revisions and unapproved or
tampered content cannot be marked posted through direct API requests.

Two internal transaction-ownership parameters let existing campaign creation and
export verification participate in the planner's transaction without committing
early. All previous callers retain their default transaction behaviour and exact
Guardian/audit/approval/bytes checks. Starting a plan either writes the campaign,
facts, brand and link together or rolls all of them back.

The existing loopback-only single-owner authorization profile applies. Plans can
contain private owner notes and must stay in the same persistent private database.
No provider key, existing environment file or inference configuration was changed.

## Actual verification, 9 October 2026

| Check | Outcome and evidence |
|---|---|
| Full backend regression | PASS: 490 tests; `evidence/planning-all-tests.xml` |
| Planner tests, including strengthened locked-source test | PASS: 11 cases; `evidence/planning-tests.xml`: validation, restart persistence, duplicate save/start/cancel, edit conflict, rollback, fresh unknown facts, expiry, current approvals and stale revision |
| Browser regressions, isolated production frontend + explicitly mock API fixtures | PASS: four Chrome tests: approval recovery, manual social links, calendar/draft handoff, approved-output attachment to the original future plan |
| Calendar correctness | PASS: October 1, 2026 is Thursday; previous/next month; save/reload/edit; new draft handoff without inference/publishing |
| Mobile/desktop | PASS: 390px and 1440px screenshots visually inspected; no horizontal overflow in calendar or draft workspace |
| Lint, strict TypeScript and production build | PASS; `/calendar` included in production routes |
| Backend Ruff and diff whitespace check | PASS |
| Frontend secret scan | PASS: 392 production build files scanned; no credential contents emitted |
| Real inference, social account login/posting, real owner sign-off | NOT_TESTED for this extension; planning needs none of these capabilities |

Browser evidence: `evidence/planning-browser.json`, `planning-browser-tests.xml`,
`planning-desktop.png` and `planning-mobile.png`. Browser fixtures are not live
success. Python tests use actual backend services and isolated persistent SQLite
storage. One existing Starlette/AnyIO deprecation warning remains.

No normal frontend/backend server is left running after verification. The isolated
browser server stops when its tests finish. Final port check is recorded in
`evidence/planning-server-state.json`.

Recheck in PowerShell from the repository root:

```powershell
.venv/Scripts/python.exe -m pytest backend/tests/test_planning.py -q
npm.cmd --prefix frontend run lint
npm.cmd --prefix frontend run build
Set-Location frontend
node node_modules/playwright/cli.js test --config=playwright.planning.config.ts
Set-Location ..
```

Bash:

```bash
.venv/bin/python -m pytest backend/tests/test_planning.py -q
npm --prefix frontend run lint
npm --prefix frontend run build
cd frontend
node node_modules/playwright/cli.js test --config=playwright.planning.config.ts
cd ..
```
