# Manual publishing — 9 October 2026

The café owner saves optional links in the Approve + Export panel. After the
server authorizes the exact approved output, the page provides its poster
preview/download, approved description/text download, copy action, and profile
links. The owner uploads and publishes manually in their own signed-in account.
No credentials, OAuth, sending or publishing jobs are needed. Links open only
on explicit clicks, in a new tab with opener/referrer protection.

Supported settings:

- Instagram: `https://www.instagram.com/your_cafe/`.
- Facebook: `https://www.facebook.com/YourCafe` or the direct
  `https://www.facebook.com/profile.php?id=PAGE_ID` form with a numeric ID.
- WhatsApp: `https://wa.me/` plus the full international number, with no plus,
  spaces or message query. This opens a chat, not a profile or Status composer.
  The separate WhatsApp Web link lets owners open WhatsApp for manual activity;
  publishing a Status still requires the owner's normal app workflow. See the
  [official WhatsApp click-to-chat documentation](https://faq.whatsapp.com/5913398998672934),
  reviewed 9 October 2026. Existing prefilled approved-message drafts remain
  separate and never attach poster files or send automatically.

Leave unused platforms blank. Save links before opening them. Incomplete or
unsafe URLs display an actionable error; links are never fetched server-side.
Account ownership, login state and posting privileges are managed by the social
platform, not asserted by this app. Profile opening does not prefill an
Instagram/Facebook composer or claim a post succeeded.

Persistence uses migration 009 and a separate single-owner `social_profiles`
table. `GET /api/social-profiles` returns optional links and settings `version`;
`PUT /api/social-profiles` accepts those links plus `expected_version`. Conflicting
edits return the existing REVISION_CONFLICT/409 convention. Identical duplicate
saves are idempotent. Links persist across backend restart and campaigns; their
edits do not change campaign facts, creative dependencies or approval hashes.
This follows the existing local-only, single-owner authorization boundary.

Normal owner UI no longer mounts the Meta API panel or makes any `/meta` request.
The prior optional backend adapters remain dormant for compatibility with saved
history and backend tests. Their default disabled setting is unchanged. No
environment file or provider configuration was edited.

Manual buttons appear only with an authorized current selection, including
explicit retrieval after reload. Changing selected IDs/hashes or revision hides
the stale pack and its publishing links. Server export routes independently
reject pending, blocked, stale or tampered content; setting links grants no
approval. Modes/disclaimers remain visible on mock or saved output. If clipboard
access is denied, select the read-only description and copy normally or download
the text file. Missing profile links and backend failures have retry instructions.

Verification: 479 backend tests PASS, including 21 social-link tests for hostile
URLs, redaction, restart persistence, duplicates, concurrent edits and unchanged
approved export. Frontend lint/TypeScript/production build PASS. Two isolated
Chrome browser tests PASS: approval/export recovery and manual publishing with
link persistence, missing links, clipboard denial, backend failure, selection
changes and mobile layout. The browser recorded zero Meta API calls, zero real
approvals and no publishing. Fixture account links are test data, not café defaults.

Evidence: `evidence/manual-social-all-tests.xml`, `manual-social-tests.xml`,
`evidence/manual-social-browser.json`, `evidence/manual-social-mobile.png`.
The implementation prompt is `MANUAL_SOCIAL_PUBLISHING_PROMPT.md`.

Real account login, external-link destinations, actual manual publishing and
native-language review remain NOT_TESTED. No real social profiles were invented
or preconfigured. One pre-existing Starlette deprecation warning remains.

Checks (PowerShell or bash, from repository root):

```text
python -m pytest backend/tests/test_social_profiles.py -q
npm --prefix frontend run lint
npm --prefix frontend run build
```

Browser test from `frontend`: `npx playwright test --config=playwright.manual.config.ts`.
It uses an isolated production frontend on port 3002 and offline API fixtures.

Operational check: backend restarted with migration 009 and production frontend
restarted with the new bundle. Both returned HTTP 200; real profile settings
remain empty for the owner to configure. No existing configuration was replaced.

Follow-up redirect verification: actual Chrome clicks opened four new tabs for
Instagram, Facebook, wa.me and WhatsApp Web. Each tab reached its expected URL
with external requests intercepted by offline fixtures; no real account was
contacted and no Referer header was sent. Both browser tests PASS on rerun.
Frontend/backend/profile endpoint HTTP 200. The desktop tool transport was closed;
the running page must be opened with the local browser link. Screenshot:
`evidence/manual-social-desktop.png`. Real-account destination availability and
publishing remain NOT_TESTED. Existing café settings were not changed.
