# Modern reference-directed café posters — 10 October 2026

The supplied screenshot shows historical DETERMINISTIC artwork. Its image was
contained in a small central window, with dark strips behind the copy. Changing
the AI prompt alone could not change those locally illustrated posters or the
code-owned typography.

The supplied Café Moments reference is used as visual art direction: cream paper,
forest-green offer panel, mustard highlights and a large right-side coffee hero.
Its pixels are not submitted to the provider or reused as campaign artwork.
Its café identity, 25% discount, food dishes and advertising claims are not copied.
Only the campaign's approved forms supply the rendered name, offer and conditions.

## Implementation

- `backend/prompts/T1.txt` requests realistic editorial coffee photography, with
  warm side lighting, ceramic texture, steam and the complete mug/handle visible.
  It rejects vector/cartoon imagery and generated promotional lettering. Coffee
  is permitted only for the supported locked coffee category; other categories
  retain decorative textures without invented menu items.
- `backend/art_context.py` defines the right-side hero composition, paper/text
  region and new prompt/layout versions. Full prompt and renderer hashes remain
  dependencies, preventing reuse of obsolete designs as current output.
- `frontend/public/renderer/canvas.js` adds curved cream paper, restrained texture,
  a unified green offer panel, large gold offer typography and a green CTA.
  The source image is contained, not stretched or duplicated; only its outer top
  edge is faded to blend into the right-side backdrop. Logos align with the copy.
  Long native-language copy can use the wider layout at existing minimum sizes.
- `backend/art_service.py` updates the explicitly labeled local coffee illustration
  to match the new palette. It remains an illustration, not an AI photograph.
- `backend/ledger.py` revalidates the current compact poster presentation for the
  new renderer. Guardian, R7, warning acknowledgments, approved hashes and owner
  approval/export gates remain required. Prior PNGs remain historical.
- `frontend/components/PosterPanel.tsx` explains the current style and historical
  outputs. OpenAPI/types preserve old prompt labels while supporting the new one.

## Verification

74 focused offline backend tests PASS, including reference-claim isolation,
non-coffee subject exclusion, cache invalidation, tampered bytes, approval/export
and local animation. One upstream AnyIO deprecation warning remains.

Production build/TypeScript, ESLint and focused Ruff checks PASS. All eight actual
Chrome browser cases PASS: size/preview/hash/reuse, long Kannada grapheme wrapping,
font waits/failures, same-origin protection, reviewed PNG logo placement, 4:5 feed,
bounded optimization/audits, and real FFmpeg MP4 plus website ZIP/reload/approval.
See [browser results](evidence/modern-cafe-browser-final.json) and
[backend results](evidence/modern-cafe-tests.xml). Browser inference is explicitly
MOCK; rendering and encoding use real local tools. Deliberately aborted font
requests emitted a Windows connection-reset diagnostic while expected failure
assertions passed; this is not evidence of successful provider inference.

Source secret scan PASS (1,165 files); frontend build secret scan PASS (434 files).
Known configured credentials were checked without printing values. These scans
are limited to known values and configured patterns, not a security certification.
Git whitespace check PASS. Both normal app services were restored: backend
readiness and frontend HTTP 200, with the new renderer served successfully.
See [runtime check](evidence/modern-cafe-runtime.json).

Initial browser testing exposed long-Kannada overflow because the enlarged offer
font also applied to the verbose fallback. Restored the fallback's earlier font
sizes without truncation or smaller policy minima. A subsequent test expected the
old centered logo; the new design deliberately places it at the copy's left edge.
The assertion now verifies exact left alignment and headline alignment; safe-area,
missing-logo and SVG rejection assertions remain. Failed runs are preserved in
`evidence/modern-cafe-browser-before-wrap-fix.json` and
`evidence/modern-cafe-browser-before-logo-update.json`.

The sample [square PNG](evidence/modern-cafe-local-square.png) uses MOCK campaign
copy and DETERMINISTIC local artwork. It is UNAPPROVED; it demonstrates layout,
not authenticated photography or a real owner's sign-off.

Authenticated Seedream photography with this prompt and its R9 visual QA are
**NOT_TESTED**. The last real image request, on 2026-10-09 at 23:04:02 UTC, returned
HTTP 402 PAYMENT_REQUIRED. No successful photo or vision outcome is inferred from
mock/local artwork. Evidence: [provider failure](evidence/hackathon-seedream-image-live.json).
Manual native Kannada review remains **NOT_TESTED**.

## Use

Refresh the workspace after the current build starts. Select AI-generated café
artwork for a photo, or local artwork for an instant disclosed illustration. Render
the selected poster sizes again: old PNG files do not change in place. Review the
new pixels, run their audit and approve before export. The image provider needs
credits for authenticated photographic generation; text generation and local
artwork/animation do not prove that image capability succeeded.
