# B4 art and artifact boundary · b4.1

## Current modern reference amendment — 2026-10-10

Active T1 `t1-modern-cafe-b1.0` and renderer `canvas-modern-cafe-b1.0` use a
right-side coffee hero with code-owned cream paper, green offer panel and mustard
typography. The supplied reference is style guidance only; its pixels, 25% offer,
identity and extra food are not copied. Local artwork remains an explicitly
deterministic illustration. Existing QA and approval/export gates still apply.
[Current implementation and checks](MODERN_CAFE_POSTERS_2026-10-10.md).
Earlier design and provider records below are historical.

## Current owner-directed design amendment — 2026-10-09

The original abstract-only composition below is historical. Active T1/R9 and
canvas-pinterest-b1.0 use warm editorial coffee imagery, ivory paper and separate
image/text regions. A locked coffee category permits an anonymous mug; unsupported
products, gifts, lettering and venues still block. `poster_copy.py` groups every
specified fact through approved slots, keeps the hook/CTA, preserves the original
social caption and omits poster hashtags. Required owner brand wording retains
its source body. Ledger revalidation checks the same derived poster presentation.
Previous renderer/layout artifacts are marked stale in poster snapshots and need
fresh rendering/audit/approval. See [current evidence](PINTEREST_POSTER_DESIGN.md).

G4 is verified offline with actual Chrome-rendered PNGs and explicit mock Agnes
background/QA responses. Live generation and vision remain NOT_TESTED. Native
Kannada/Kanglish review remains PENDING. B4 produces validated draft artifacts;
mandatory G14 and owner approval/export remain B5/B6 gates.

## T1 and R9

T1 projects only validated brand colors, fixed calm minimalism, abstract curves,
quiet space and a native ratio. No literal campaign values, raw brand/theme text,
products, product subtypes, venue details, people, free extras or food are sent.
This conservative profile represents no business feature visually. A future
product-art profile needs explicit visual-subject approval and its own policy.

Each ratio (1:1, 9:16, 16:9) uses Agnes size=1K. Native pixels are safely downloaded
immediately, MIME-sniffed, decoded and re-encoded to PNG before use. R9 receives the
exact persisted pixels as a data:image/png URI, plus the nonfactual brief. It must
report loaded/fully inspected pixels, lettering/numbers, logos/watermarks, objects,
venue details, promotional implications and usable/reject/uncertain. Code accepts
only usable with complete inspection and every disallowed flag false. A malformed,
unavailable or uncertain QA result cannot authorize generated art.

At most two completed generated candidates per ratio; all transport retries and
R9 schema repairs share six calls/240 seconds. A definite visual rejection may
request a second candidate. Ambiguous image submission, invalid/expired download
or failed QA stops resubmission and produces the disclosed deterministic fallback.
This is application-drawn abstract art, never an unlabeled live-to-mock switch.
Rejected generated backgrounds are recorded as blocked and cannot be served.
Fallback records reasons, source, mode, models, prompt/QA versions, capture time,
run ID, bytes/hash and call attempts. Owner-selected deterministic art makes zero
inference calls. Production R9 data-URI support still needs authenticated evidence;
unsupported vision falls back visibly instead of inventing QA success.

Art reuse keys include campaign, palette/composition/ratio, source/mode and actual
T1/R9 prompt hashes. They exclude offer/location/date/name values because none
affect abstract art. Numeric offer edits rerender current text with the same art.
Changed colors or art policy invalidate reuse. No image call occurs per matrix cell.

## Shared canvas and bytes

`frontend/public/renderer/canvas.js` is the only poster compositor. The backend
launches headless Chrome through the installed Playwright/Node runtime, on a
restricted local worker page. Network requests are limited to its exact same-origin
script, bundled fonts and stored asset IDs. Remote/client-selected URLs, SVG and
executable inputs are never render parameters. Production needs Node and Chrome;
missing runtime/font fails closed, without a substitute rasterizer.

Noto Sans and Noto Sans Kannada variable TTFs are bundled, unmodified, at a pinned
Google Fonts repository commit. Hashes, source URLs and full SIL OFL 1.1 notices
are in `frontend/public/fonts/manifest.json` and adjacent OFL files. Both faces must
load before measurement; 8-second font deadline, no successful fallback when load
fails. Browser shaping and Intl.Segmenter wrap whole graphemes without normalizing,
truncating or altering displayed strings. Wrapping preserves every original code
point; explicit newline separators are recorded in canonical input.

Measured ink bounds and line widths decide layout. Font reduction has a minimum
(26px square, 30px story, 24px landscape). Text never uses ellipsis or canvas clipping
to conceal overflow. Bounds must fit square 64px margins, story 200px top/240px
bottom with 72px sides, or landscape 48px margins. Optional owner-reviewed PNG logos
have aspect-preserving placement and reserved measured space. Missing chosen logo
blocks; no logo is valid when explicitly omitted. No brand logo is fabricated.

An opaque #172B23 text plate, white copy and a background scrim ensure measured
contrast exceeds 7:1 independently of art pixels. These are versioned product
safe-area/readability policies, not claims about platform specifications.

Canvas inputs, exact displayed fields, font/renderer/layout/background/logo hashes,
fact and variant dependencies, text-line measurements and Guardian evidence are
stored with each PosterArtifact. Font/renderer files are checked again after the
pending render. Current revision is checked at commit. PNG bytes are decoded,
dimension-checked and canonically re-encoded, then stored under their SHA-256.
Reading verifies that hash; tampering or missing bytes fails closed. Preview and
draft download use `/api/assets/{id}` directly, without image transforms. The future
approved export must reference this same immutable ID/hash, never rerender a new
image. `approved_bytes` currently rejects all requests pending B5/B6 evidence.

## Storage and limits

- Raster limits: 12MB and 16 million pixels; animation and metadata/trailing content
  rejected or removed. Logos: owner-reviewed PNG only, 2MB limit. SVG is rejected,
  including scripts and external references; no conversion path exists.
- The existing downloader rejects redirects/non-200 status, unexpected MIME,
  credentialed/private/unapproved hosts and oversized streams. Google Storage DNS
  is pinned to a public IP; provider URL changes need reviewed host policy.
- Controlled asset routes send image/png, nosniff, ETag, no-store and pending
  approval headers. Draft access is local-owner access, not authorized export.
- One worker and serialized art operations. No distributed render queue or public
  cancellation API in B4. Successful posters persist progressively between sizes;
  failure returns an actionable error and does not remove earlier artifacts.
- Font shaping/glyph appearance, culturally natural copy, logo claims, QA coverage
  and arbitrary visual semantics still need native/B5 review. Automated bounds and
  mock QA cannot provide human sign-off. No external OCR/provider was added.

Actual file observations are in B4_VISUAL_REVIEW.md. The native checklist remains
unsigned in KANNADA_NATIVE_REVIEW.md. No approved export was produced for B4.
