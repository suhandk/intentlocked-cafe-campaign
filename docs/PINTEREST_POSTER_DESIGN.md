# Pinterest-inspired café posters — 2026-10-09

The previous poster copied a long social caption and hashtags onto a single dark
green plate, hiding the generated artwork. The new compositor uses a cream canvas,
espresso typography, terracotta rules, a shadowed image window and separate offer,
fact and CTA regions. Square/story use a centered editorial stack; landscape uses
copy beside artwork. Full source pixels are contained in the window rather than
cropped away. Code does not paint a blanket dark rectangle over the image.

T1 and the safe art projection now request Pinterest-inspired coffee still-life,
tactile collage or airy flat-lay profiles by ratio. Coffee mugs are permitted only
for the locked coffee category. R9 accepts that explicit generic motif and still
blocks extra items, venue claims, text, logos and unsupported promises. Image
prompt/QA version labels and hashes reflect the actual new policy; older stored
version labels remain readable. The local fallback is a deterministic textured
coffee illustration with paper layers and shadows, never represented as AI art.

`poster_copy.py` derives compact presentation from owner-approved slots. It retains
every specified core fact and condition, the source hook and CTA, but excludes
social hashtags and unnecessary caption prose. It cannot invent an unknown ID
rule, infer eligibility, rewrite approved dates or edit canonical values. Mandatory
brand wording preserves the source body. The original social variant stays intact.
Guardian, Ledger revalidation, R7 and approval/export hash checks operate on the
actual new poster fields. No approval or delivery is automatic. Existing old
designs appear as historical, rather than as current redesigned output.

Verification executed:

- **454 backend tests PASS**, including source preservation, exact slot evidence,
  unknown-fact exclusion, art direction, approval/export and invalidation checks.
  One upstream Starlette deprecation warning remains.
- **9 actual offline Chrome renders PASS**: square/story/landscape across en, kn,
  kn-Latn. Their results also pass server `validate_canvas`: exact text, measured
  bounds, bundled fonts, minimum font sizes and contrast >=7. Every browser request
  in `frontend/scripts/verify-editorial.mjs` is fulfilled from local fixtures;
  external assets, overflowing text and obsolete renderer versions are rejected.
- English square/landscape and Kannada story PNGs were visually inspected.
- Ruff, Git whitespace checks, frontend TypeScript/ESLint and production build
  PASS. OpenAPI and generated frontend types include the versioned art metadata.

Evidence: [backend results](evidence/pinterest-tests.xml),
[canvas results](evidence/pinterest-canvas.json),
[square sample](evidence/pinterest-square-en.png),
[landscape sample](evidence/pinterest-landscape-en.png),
[Kannada story](evidence/pinterest-story-kn.png).
Sample campaign data and artwork are OFFLINE fixtures, not live generated or
approved campaign outputs. Authenticated generation/QA with the new image prompt,
manual native Kannada review and voice checks remain **NOT_TESTED**.

To apply to running processes, restart backend/frontend from this worktree, then
render the selected poster sizes again. A new poster needs its own R7 audit,
warning acknowledgment and owner approval. Saved old PNGs do not change in place.
