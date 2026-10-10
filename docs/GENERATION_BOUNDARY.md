# B3 generation boundary · b3.1

G3 is an offline functional gate. Strategy, personas and mock previews are explicitly
hypothetical. A `ready` cell means a saved draft passed implemented deterministic
checks; its variant is `pending`, Guardian is `INCOMPLETE`, and approval_ready is
false because G14 has no semantic-reader result. No approval or export is added.

## Inputs and facts

R3 receives eligible segment enums, selected social channels/languages, available
slot keys and a closed tone. It returns three distinct motivations/angles and five
distinct persona profiles covering them. Code binds stable IDs to the saved plan
and rechecks eligibility. Student-only campaigns use three student strategies;
unknown or custom eligibility blocks until a reviewed compatibility policy exists.

R4 receives one language, requested audience/channel pairs, closed segment/angle/
motivation/tone values, approved slot keys/kinds/cases, slot message hierarchy,
channel requirements and code-only repair reasons. Raw transcript, brand text,
canonical facts, surface forms, date/offer/location examples, previous templates
and Guardian findings are withheld. Brand voice is passed only if it exactly
matches a tone enum; otherwise warm. Must-say/must-not-say rules still execute in
Guardian, which can block a draft rather than leak their values back to R4.

Fact shapes describe types, not values. Eligibility segment is intentionally
shared to target compatible audiences, but the literal eligibility phrase must
still use a slot. Renderer selects approved forms and stores fact-to-span provenance.
Every template field, including CTA/hashtags/alt text, goes through Guardian.
`slots_used` is derived with the token parser. Malformed templates have no trusted
slot inventory and remain blocked.

## Batches, repair and persistence

Every selected combination gets a persisted cell before inference. One initial R4
request covers a selected language across up to three audiences and three social
channels. The entire cartesian selection must be accounted for. Missing, duplicate
or unknown combinations are blocked explicitly. Malformed schema entries reject
that submitted batch; individually valid entries in a structurally valid batch are
saved and excluded from repair. Only unresolved cells are resubmitted.

R3: three total calls / 120s. R4: three total calls / 150s **per language**, shared
across transport retries, structured schema repairs and semantic template repairs.
The single AgnesClient queue enforces configured request spacing and Retry-After.
Normal full matrix: one R3 + three R4 calls. Exhaustion records reasons, retains
successful cells and continues other languages. No mock fallback exists in live
mode. Cached mode rejects new inference; saved artifacts retain their origin mode.

SQLite migration 003 stores plans, run snapshots and immutable baseline variants.
Each progressive commit checks the current locked revision and dependency hash.
Late results after edits are discarded; saved earlier work remains as stale history.
Idempotency binds a run to the exact request. Restart marks unfinished runs
interrupted, retaining saved cells, and never silently replays billable calls.
The current UI displays the latest run; older runs remain accessible by job ID.

## Limits and pending gates

- One server worker and one active copy run; no distributed quota, durable worker
  lease, SSE or public cancellation endpoint yet. Those are B7 scope.
- Selected-script checks are conservative heuristics. Native Kannada/Kanglish
  review is PENDING in KANNADA_NATIVE_REVIEW.md; screenshots certify layout only.
- Distinct normalized hooks and nonidentical channel templates are enforced.
  Semantic differentiation, persuasion and factual paraphrase coverage need B5;
  Guardian's bounded lexicons cannot certify arbitrary natural language.
- Closed creative enums intentionally restrict personalization. Unsupported custom
  eligibility and unsatisfiable raw brand requirements block rather than guess.
- Provider/schema failures are recorded as codes; rejected provider prose is not
  exposed or recycled as repair instructions. No authenticated Agnes execution was
  performed for this stage. Explicit mock fixtures are development evidence only.
- Posters, fonts, pixel QA and assets are B4; G14 reader B5; approval/export B6.
