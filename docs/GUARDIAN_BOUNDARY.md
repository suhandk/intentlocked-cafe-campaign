# Guardian B2 boundary and limitations

The backend loads a locked campaign by ID and checks its revision. Requests accept
templates, selected language/channel, diagnostic mode, an additional audience, and
optionally a displayed copy to compare. They never accept canonical facts, approved
forms, span maps, slot inventories, policy overrides, semantic results, or approval flags.
The direct Python entry point also revalidates its DTOs and revision/selection gates.
An internal caller must supply the authoritative CampaignRepository snapshot.

The parser scans delimiters and accepts only `{{KEY}}` or `{{KEY|nom/dat/gen/loc}}`.
Lookup requires locked facts and approval provenance. Rendering picks the first
approved form deterministically and derives slots_used and field-local spans. All
spans are half-open Unicode code-point offsets, not UTF-8 bytes or JavaScript UTF-16
indices. A browser should use `Array.from(text).slice(start, end)` for highlighting.
The UI displays exact quoted findings without slicing UTF-16 incorrectly.

Shadow text uses compatibility normalization on base/mark clusters, case folding,
decimal digit conversion, whitespace collapse, removal of format controls, and a
small explicit confusable table. Every shadow character retains the original
cluster range. Displayed text is never normalized or reconstructed from the shadow.
This mapping is intended for the selected English/Kannada/Kanglish scripts; it does
not promise full grapheme segmentation for arbitrary writing systems.

Numbers bind to their own canonical role and unit. A date containing 25 never
authorizes a 25% discount. Offer surfaces require the correct numeric value,
percentage/currency, and discount role. ISO date/time grammars and exact known
condition grammars are deliberately conservative. Owner-approved spelling alone
cannot waive a deterministic contradiction. Approved `students only` is allowed
inside ELIGIBILITY; the same literal outside a slot is blocked. Matching uses letter
and combining-mark boundaries, avoiding `coffee`/`free`, `carefree`/`free`, and
`rooftop`/`top` substring matches in ordinary prose.

Policy `guardian-policy-2.1` is a versioned product policy, not a claim about current
platform API maxima. Instagram requires body/CTA/alt text (2,200 code points),
Facebook body/CTA/alt text (3,000), WhatsApp body/CTA (1,500), poster headline/body/
CTA/alt text (600). Length sums all supplied fields including hashtags and alt text.
Every complete asset must visibly disclose CAFE, LOCATION, OFFER, PRODUCT, DATES,
DAYS and every specified condition in headline/body/CTA. Hashtags and alt text are
checked but cannot discharge visible disclosure. Fragments skip completeness.
All modes check every supplied customer-facing field. Future filename/decorative
copy fields must be added to this contract before those outputs are implemented.

G01–G10/G13/G15 block conflicts. G11 script mismatch warns. G12 length warns for
social copy and blocks posters. Actual poster pixel overflow is incomplete until
the B4 renderer supplies server-owned measurements; a character count cannot prove
layout safety. Reports contain all G01–G15 results, applicability, completion,
nullable pass state, severity, original spans, missing checks and warning IDs.
BLOCKED takes precedence over INCOMPLETE. Integrity is null while mandatory checks
are missing; fragment integrity describes deterministic checks only.

## G14 handoff to B5

G14 is mandatory for every complete asset; B2 reports it as applicable=true,
completed=false, passed=null. Fragment diagnostics mark it inapplicable and cannot
authorize approval. Every B2 report has approval_ready=false, and the approval
guard refuses all reports. Approval/export endpoints remain unimplemented (404),
not permissive stubs. A report is a diagnostic document, not an authorization token.

B5 must run Agnes R7 with final rendered fields and language/channel, blinded to
locked facts. Persist reader answers, completion/error state, provider/mode, run ID,
reader/schema/prompt version, exact content/dependency hashes, and campaign revision.
Compare offer/product/dates/days/location/eligibility/conditions to locked facts in
code after reading. Mismatch blocks; other promises warn and require explicit
review. Missing, malformed, failed, cancelled, stale, or unbound evidence remains
incomplete or blocked. Reader success can never erase deterministic failures.
The B6 transaction must recompute all gates against current persisted content,
artifact bytes, versions and acknowledgments; never trust submitted reports.

## Known limits

- Deterministic vocabularies detect the tested claims, named literals, numeric
  roles, known entities and common entity constructions. They cannot prove the
  meaning of arbitrary prose, novel product/location names, metaphors, sarcasm,
  multilingual paraphrases or every adversarial transliteration. This is why G14
  is mandatory and **no B2 result permits release or export**.
- Kannada/Kanglish lexical coverage is a draft, including incomplete number-word
  compounds and transliterations. Do not present it as universal language support.
  Native validation remains pending; see KANNADA_NATIVE_REVIEW.md.
- Conservative wrapper detection can reject innocent uses of words such as
  `from`, `before`, `only`, and `not` around slots. Date surfaces currently use ISO
  dates; additional natural date/time/condition grammars require reviewed tests.
- Unknown unrestricted eligibility cannot be inferred from audience targeting.
  Custom eligibility requires semantic/manual resolution and currently blocks G15.
- API diagnostics are synchronous and not persisted approvals. B3/B5/B6 own durable
  variants, audit evidence and approval transactions. No authenticated Agnes calls,
  native speaker review, or poster visual review were performed for B2.
