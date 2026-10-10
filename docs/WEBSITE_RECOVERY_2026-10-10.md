# Website wizard recovery — 10 October 2026

The screenshot showed unfinished optional opening hours and a generic close/save
error. This was reproduced against the previous production build in an isolated
browser: returning to Basics failed because every step change first saved the
entire draft, and validation rejected the unfinished hours row. Save-and-close
failed the same validation and provided no discard option. [Pre-fix failure](evidence/website-recovery-before-fix.json).

Changes stay within the existing website wizard and strict draft API:

- Navigation can display any step while edits remain incomplete in memory.
  It never saves invalid fields or enables generation from them.
- The visible validation message offers a button leading to the affected field:
  hours/phone/social links in Visit info, menu rows in Menu. Same-day hours must
  still close after opening. Optional unfinished rows can be explicitly removed.
- Close explains incomplete inputs and offers Keep editing or Discard unsaved
  edits and close. Saved data is retained. No edits are silently discarded.
- Failed network saves retain inputs and expose Retry save. Version conflicts
  remain conflicts; the UI never overwrites a newer server revision automatically.
- Requests time out after 15 seconds. Unreadable responses and network failures
  produce actionable messages instead of leaving the wizard indefinitely busy.
- Queued obsolete typing snapshots are skipped. A completed older autosave cannot
  mark newer incomplete edits as saved. Newest valid fields use the existing
  sequential queue and expected-version guard.

No model change or inference request was required. Website generation remains
the deterministic existing renderer with locked campaign facts, Guardian checks,
an unpublished preview and ZIP export. Hosting publication still requires HTTPS,
a valid connection and approval of the current exact bundle hash.

Changed files: `frontend/components/WebsiteWizard.tsx`,
`frontend/lib/website-api.ts`, `frontend/e2e/website-recovery.spec.ts`,
`frontend/tests/website-api.test.mjs`, `scripts/verify_workflow.py` (includes the
new regression file in the default future workflow suite).

## Executed checks

- 12 JavaScript tests PASS: CSV/validation, affected-step routing, bounded abort
  signal, unavailable/unreadable server handling, and preservation of 409 errors.
  An older assertion expected the plural word "prices"; updated its wording to
  match the existing singular message, keeping the invalid-price assertion.
- 45 existing backend website tests PASS. Backend contracts were not changed.
- Four browser tests PASS after the final build: incomplete hours → other steps
  → explicit review block → fix → actual website preview/ZIP → reload; incomplete
  menu explicit discard; injected HTTP 503 then retry with edits preserved;
  controlled delayed autosave and rapid typing; existing real local MP4 approval
  and website ZIP integration. [Browser evidence](evidence/website-recovery-browser.json).
- Production build/TypeScript and ESLint PASS.
- One separate HTTPS browser check PASS in 8.7 seconds for draft reload, readonly
  offer, ZIP without a token, invalid-token recovery, exact-hash approval,
  simulated publishing and credential cleanup. Hosting was an isolated fake
  provider; no live Netlify deployment occurred.
  [HTTPS evidence](evidence/website-recovery-https.json).
- Ordinary backend/frontend restarted with the final production build; readiness,
  homepage and website config HTTP 200. Existing persisted synthetic website ZIP
  still matches its saved hash. Runtime logs and source/build secret scans PASS.
  [Runtime](evidence/website-recovery-runtime.json).

Browser inference is explicitly MOCK with a fake clock; rendering and ZIP bytes
are real. Owner review is simulated on separate synthetic campaigns. No real
hosting publication or native-language review is implied by these tests.

Repeat relevant checks from the repository root:

```powershell
node --experimental-strip-types --test frontend/tests/website-api.test.mjs
.venv\Scripts\python.exe -m pytest -q backend/tests/test_website.py
npm.cmd --prefix frontend run lint
npm.cmd --prefix frontend run build
# Stop ordinary services before this isolated browser command:
.venv\Scripts\python.exe -m scripts.verify_workflow e2e/website-recovery.spec.ts e2e/hackathon-media.spec.ts
```

bash uses `.venv/bin/python` and `npm` instead.

For an already open old browser tab, finish or remove its incomplete hours row
and use Save and close before refreshing, so its unsaved edits are preserved.
The updated wizard appears after refresh. Incomplete new edits are held in
memory; they are not promised to survive a page reload until saved successfully.
