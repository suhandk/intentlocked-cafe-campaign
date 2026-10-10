# B4 visual evidence · 2026-10-09

Engineering visual inspection: **performed on actual PNGs**. Native-reader status:
**PENDING — no human/native reviewer has supplied observations or signed off.**
Reviewer name/date/source revision for native review: pending.

Opened exported draft bytes with the image viewer, not just canvas/unit-test output:

| Evidence | Engineering observation |
|---|---|
| evidence/b4-poster-square.png, 1080×1080 | Visible Kannada headline, body, dates, 20% offer, product and CTA. No visible missing-glyph boxes or clipped ink; clear white/dark contrast. |
| evidence/b4-poster-story.png, 1080×1920 | Headline wraps, body remains visible; top/bottom story safe areas retained. No visible clipping. |
| evidence/b4-poster-landscape.png, 1200×630 | All visible copy fits; dates and offer remain readable in the full-size file. |
| evidence/b4-long-kannada.png | Explicit renderer stress example, not a business-approved campaign: long café text, Kannada word-form percentage and multi-line dates preserve connected glyph shapes and line spacing. |
| evidence/b4-logo-square.png | Explicit owner-reviewed test circle logo is contained in the top-left safe region; headline/body shift below it without overlap. |
| evidence/b4-posters-desktop.png and b4-posters-mobile.png | UI selects copy/source/sizes/logo, shows actual saved images and draft download links. All three sizes visible; no horizontal overflow at 390px. |

The art is deliberately abstract/quiet, with a large opaque text plate and generous
unused space. Mock images are solid-color fixtures, explicitly labeled MOCK in the
UI/metadata. This does not establish live Agnes art quality or R9 model compliance.
No font files came from an operating-system fallback when loading failed: those
cases were blocked by browser tests. Naturalness, orthography, phrase choices and
all glyph details need the native review below.

Browser assertions: actual persisted PNG hashes and header dimensions; same-origin
preview pixel access without canvas taint; reload retains artifact IDs; second
audience reuses art with no further inference calls; long Kannada/café strings and
20%, Kannada ೨೫%, ಇಪ್ಪತ್ತೈದು ಶೇಕಡಾ, INR/₹ and buy/get forms; severe overflow blocked;
slow font waits, missing/timeout fonts block; cross-origin URL and missing/SVG logos
reject. Actual artifact manifests are in evidence/b4-artifacts.json. Pure typography
stress cases do not bypass Guardian on production rendering routes.

Native-reader observations (separate, pending):

- [ ] Inspect all three full-size posters, long Kannada case and actual live outputs.
- [ ] Record orthography, conjunct shaping, vowel placement, line-break acceptability,
      natural phrasing and reading size for the Kannada forms.
- [ ] Review Kanglish expression, mixed-script forms, numeral variants and conditions.
- [ ] Review the exact café/logo/offer representations against the owner-approved brief.
- [ ] Record correction examples, reviewed revision/hash, name/date and explicit decision.

Release decision: **PENDING native review and mandatory G14/B6 approval**. Engineering
inspection or an automated test must not check the native-review boxes.
