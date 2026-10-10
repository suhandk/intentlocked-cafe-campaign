# Implementation prompt — manual social publishing

Extend the existing single-owner campaign workspace. Preserve Agnes, facts,
Guardian, audits, hashes, approval/export authorization and durable work. Replace
the owner-facing Meta API delivery panel with manual publishing; no access tokens,
OAuth, API sends, publishing jobs, scraping or browser automation.

Persist optional Instagram profile, Facebook Page and WhatsApp chat URLs in a
separate single-owner settings table. URL edits do not alter campaign facts or
invalidate approved creative. GET/PUT /api/social-profiles must validate HTTPS,
exact platform domains and supported paths, reject credentials/ports/unsafe
schemes and keep optimistic settings versions. Concurrent edits must conflict;
identical duplicate saves must be safe. Never fetch the saved URLs server-side.

Provide accessible settings with save/reload, clear errors and unset states.
After final server-authorized export, show a manual publishing card for the exact
selected approved revision: exact PNG download, approved description with copy
and manual-copy fallback, and links to saved profiles in a new tab with
noopener/noreferrer. Profiles must not be opened automatically after approval.
Missing links explain how to configure them. Changes in selected hashes, revision
or approval readiness hide stale export controls.

Opening a profile does not upload or prefill a social post. Explain downloading,
creating a post, attaching the image, pasting the description and publishing
manually. wa.me opens a chat, not a Status composer. Keep the separate existing
prefilled WhatsApp draft and supply a clearly labeled WhatsApp Web entry point
for manual activity; never imply automatic sending or poster attachment.
Mock and cached output remain visibly labeled. Do not show posting success.

Keep previously implemented optional API adapters dormant for compatibility;
remove every API-delivery control/request from the normal owner interface.
Do not enable legacy provider delivery configuration or change existing .env.

Add tests for URL attacks, persistence/restart, concurrent and duplicate saves,
unchanged fact/approval hashes, exact authorized copy/downloads, missing links,
clipboard failure, reload, changed selection and no Meta API requests. Record
executed evidence and untested real-account actions. No real publishing test.
