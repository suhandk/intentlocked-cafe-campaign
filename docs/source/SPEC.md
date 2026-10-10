# SPEC.md: Intent-Locked Voice Campaign Agent (HR26-AI-02)

**One-line pitch:** Human controls truth. AI controls execution. Code enforces the boundary.

**Demo:** A café owner in Bengaluru speaks a Kanglish idea. The system locks the offer facts, then produces a multilingual, multichannel campaign that is scored, optimized and verified. It can never contradict what the owner approved.

**Time budget:** 30 hours. **Feature freeze at hour 25.** Hours 25 to 30 are for hardening and rehearsal only.

---

## 0. How to use this file with an AI coding tool

1. Paste Section 1 (Master Context) at the start of every session.
2. Paste the Stage prompt (Sections 4, 5, 6) for the stage you are building, plus the code from earlier stages.
3. Ask for working code, tests and run instructions. No placeholders.
4. After each stage, run its "Done when" checks before moving on.

---

## 1. Master Context (paste first, every time)

```
PROJECT: Voice-first marketing campaign agent for small businesses (HR26-AI-02).
Demo: café in Bengaluru, owner speaks Kanglish idea -> multilingual,
multichannel campaign that can never contradict the owner's approved facts.

HARD RULES
1. Facts are typed slots. LLM never writes offer values, dates, prices,
   product, or location; it writes templates with {{SLOT}} tokens and code fills them.
2. Guardian is deterministic first (regex over en+kn digits/weekdays/currency/
   time, claim blacklist, slot presence), LLM semantic check second.
3. Optimizer may only change mutable fields: audience, tone, hook, CTA, theme, layout emphasis.
4. AI images are background art only ("no text"); text is overlaid in code
   (HTML canvas, Noto Sans Kannada).
5. Agnes API (base https://apihub.agnes-ai.com/v1; models agnes-3.0-flash,
   agnes-image-2.5-flash, agnes-video-2.5). Key server-side only. Global queue,
   exponential backoff. Limits: text 10 RPM, image 1K 10 RPM, video 1 RPM.
   Use 1K images only. Batch calls (one per language, not per asset).
   Video async: poll, show status, label fallback clips "saved demo output".
6. Every LLM output is validated by Pydantic; retry with the error on failure.
7. Log every step to a trace table; log tokens and compute cost.

STACK: FastAPI+Pydantic, SQLite, Next.js+Tailwind, Web Speech API (STT/TTS) with typed fallback.

CORE SCHEMAS
Fact{key, canonical, surface:{lang:[forms]}, mutable:false, status:
     proposed|locked|not_specified}
IntentCard{business, goal, facts[], audiences[], languages[], channels[],
           tone, must_say[], must_not_say[], clarifications[]}
Variant{id, audience, language, channel, template, slots_used[], fact_hash,
        status: approved|stale|pending|blocked, scores{}, parent_id, changelog}
GuardianReport{variant_id, passes[], violations[{rule, span, severity}],
               integrity_pct}
ChangeRequest{text, classified: mutable|immutable, affected_variant_ids[]}

DELIVERABLE STYLE: working code, tests, run instructions. No placeholders.
```

---

## 2. Brief requirements this must satisfy

**Minimum objectives (all three must be visibly demonstrated)**

| # | Objective | Where we prove it |
|---|---|---|
| 1 | Coherent campaign adapted to different audiences, languages and channels | Campaign matrix (3 audiences x languages x 3 channels) |
| 2 | Predict performance before launch and autonomously optimize | Prediction panel and optimizer loop (76 to 83 to 89) |
| 3 | Preserve exact business intent while adapting culturally and linguistically | Slot system, Guardian, Expectation Audit, Red-Team |

**Brief sentences to design against**
- "The one thing that cannot go wrong is what customers are told to expect."
- "Changing requirements should be absorbed without losing what was already approved."
- "The owner should know what exists, what changed and what remains pending."
- "The result feels local and authentic rather than generic or translated."
- "Realistic time and cost requirements for a small business."

**Judging assumption (not published):** the three minimum objectives, creativity, demo quality, and realism of cost and time. Build for those.

---

## 3. Differentiators (the out-of-the-box layer)

### 3.1 Facts as slots, not prose
At lock time, Agent 1 produces canonical facts plus approved surface forms per language and script. Example for `20%`: `20%`, `೨೦%`, `ಇಪ್ಪತ್ತು ಶೇಕಡಾ`. The copy model writes templates like `ಈ {{DAYS}} {{PRODUCT}}ಗೆ {{OFFER}}`. Code fills the slots.

The Guardian then:
- rejects any literal number, weekday, price or time (Latin or Kannada digits) not in the allowlist,
- flags superlatives and absolute claims ("best", "No.1", "guaranteed", "free") unless the owner approved them,
- confirms every required slot is present.

The offer cannot drift because the model never types it.

### 3.2 Expectation Audit (customer-side verification)
Simulated customers read only the final WhatsApp message or poster and answer: What is the offer? Who is eligible? When? Where? Any conditions? Their answers are compared to the locked facts. A Kannada back-translation check also feeds this. This tests what customers will believe, which is the real requirement.

### 3.3 Unknown is not invented
Agent 1 asks about missing conditions ("Student ID required? Dine-in only? Time window?"). Anything unanswered is stored as `not_specified`, and copy must not imply it. "This weekend" resolves to absolute dates (Sat 10 to Sun 11 Oct 2026).

### 3.4 Campaign Ledger with dependency tracking
Every asset stores a hash of the facts it depends on, and a status of Approved, Stale, Pending or Blocked.

- **Mutable** (audience, tone, hook, CTA, visual theme, language mix): apply the change, regenerate only affected assets, show "Offer preserved, Intent Integrity 100%".
- **Immutable** (offer, product, dates, location, conditions): needs explicit owner confirmation. Only assets referencing that fact go stale. Unrelated approved assets are untouched.

### 3.5 Transcreation, not translation
Output Kannada script, Kanglish (Kannada in Roman letters, how many Bengaluru customers text) and English. Use generic local color (filter-coffee culture, exam season, weekend plans, IT-park crowd) but never invented facts. Offer a "sounds like me" tone slider based on the owner's voice sample.

### 3.6 Prediction that holds up
Combine:
- deterministic features: offer in the first line, CTA present, length per channel, poster contrast ratio, offer-text size share;
- a pairwise tournament across 5 simulated personas, with order swapped to cancel position bias.

Display as "Predicted preference 89 +/- 6, not a CTR forecast." The optimizer edits only mutable fields, runs at most 3 rounds, and shows the trajectory with a changelog.

### 3.7 Red-Team button (demo weapon)
Judges type or say "make it 25%", "say we're the best coffee in India", "add free cake". The Guardian blocks it live.

### 3.8 Glass-box trace and cost meter
Show agent steps live and "This campaign cost INR 0.4, took 38 seconds."

### 3.9 WhatsApp-native export
`wa.me` prefilled link, a forward-ready message, and a ZIP pack with the poster in 3 aspect ratios. No Instagram API needed.

### 3.10 Optional pixel-level check
Send the final poster to Agnes (image-URL input) and ask it to transcribe all visible text, then diff against the facts. Verify the image input format in the docs first.

---

## 4. Rules for all stages

- **Hour 0 to 1:** confirm the API key, run one test call per endpoint (text, image, video), and check structured-output support in the wiki docs.
- **Hour 0 to 1:** write schemas and mock JSON fixtures so frontend and backend can work in parallel.
- Single FastAPI app, SQLite, Next.js frontend.
- Work in shifts with sleep.
- **Risk checklist**
  - Rate limits: text 10 RPM, image 1K 10 RPM, video 1 RPM. Batch calls and queue everything.
  - Kanglish speech-to-text: Agnes takes no audio. Use the browser Web Speech API, test Kannada and code-mixed speech early, keep typed input as fallback.
  - Prices and RPM limits are from the brief dated 2 Oct 2026. Re-check the platform before the event.

### Suggested repo layout

```
/backend
  main.py              # FastAPI app
  agnes_client.py      # queue, backoff, cost meter, trace
  schemas.py           # Pydantic models
  db.py                # SQLite
  agents/intent.py     # Agent 1
  agents/strategy.py   # segments + strategy
  agents/copy.py       # slot-based templates
  agents/scoring.py    # features + persona tournament
  agents/optimizer.py  # critic -> optimizer loop
  guardian/rules.py    # deterministic checks
  guardian/semantic.py # back-translation + expectation audit
  orchestrator.py      # state machine + trace streaming
  ledger.py            # variants, hashes, status, versions
  fixtures/            # mock JSON + saved demo campaign
  tests/
/frontend (Next.js + Tailwind)
  app/page.tsx         # single-page flow
  components/          # FactsLock, Matrix, Poster, Trace, Ledger, RedTeam
```

---

## 5. Stage 1: Locked Core (hours 0 to 9)

**Goal:** speak an idea, get locked, verified facts. This is the foundation and the biggest differentiator.

### Build
- API client with queue, backoff, cost meter and trace logging.
- Voice or text input, then Agent 1 returns an IntentCard with clarification questions and relative dates resolved.
- Facts editor with Lock. After approval, TTS reads facts back ("Twenty percent off coffee, Saturday and Sunday, for students. Correct?").
- Surface-form generator per language, owner approves at lock.
- Brand kit (hardcoded demo café plus logo and color upload).
- **Guardian v1:** deterministic extractor and checker with slot rules and claim blacklist.
- Pydantic schemas, SQLite, mock-fixture pipeline.

### Done when
- Speaking the sample sentence produces a locked card with resolved dates and a missing-info question.
- 15 adversarial strings pass or fail correctly in unit tests (see Section 9).

### AI builder prompt
```
[Paste master context.] Implement Stage 1: (a) Agnes client with queue/backoff/
cost+trace; (b) POST /intent/extract using agnes-3.0-flash returning IntentCard
with clarification questions, resolving relative dates against today's date
(2026-10-08 in demo); (c) fact lock endpoints with per-language surface forms;
(d) deterministic guardian.check(text, facts) covering en+Kannada digits, weekday
names (en/kn/Kanglish), %/₹/time patterns, claim blacklist, required-slot
presence; (e) Next.js voice/text input page and Facts Lock screen with TTS
read-back. Write pytest tests with at least 15 adversarial cases.
```

---

## 6. Stage 2: Campaign Engine and Intelligence Loop (hours 9 to 20)

**Goal:** facts become audience x language x channel content, which is scored, optimized and verified.

### Build
- **Strategy and segments:** one call returns 3 audiences with motivation, hook, tone and channel preference.
- **Copy:** templates with slots, one batched call per language. Output English, Kannada and Kanglish. Each audience gets a different angle, not a translation.
- **Poster pipeline:** 1K AI background, code-overlaid text, offer prominence rule, deterministic export to 1080x1080, 1080x1920, 1200x630.
- **Channel previews:** Instagram, WhatsApp, Facebook mockups.
- **Prediction:** rule features plus pairwise persona tournament.
- **Critic and optimizer loop:** structured edit ops on mutable fields, max 3 rounds, Guardian after every round, keep a variant only if it improves and passes.
- **Guardian v2:** back-translation check and Expectation Audit.
- **Orchestrator:** a state machine with LLM nodes. A ~150-line custom loop is faster than a framework. Stream the live trace to the UI.

### Done when
- One spoken input produces at least 3 audiences x 2 languages x 3 channels.
- A variant improves (for example 76 to 89) with a visible changelog.
- Guardian blocks a deliberately corrupted variant, and Expectation Audit reports 100% match on the good one.

### AI builder prompt
```
[Paste master context + Stage 1 code.] Implement Stage 2: strategy+segments
(single call), slot-based copy generation (one batched call per language incl.
Kanglish in Roman script), poster compositor (agnes-image-2.5-flash 1K, "no
text" prompt, HTML-canvas overlay with Noto Sans Kannada, 3 aspect exports),
deterministic scoring features (offer-in-first-line, CTA, channel length,
contrast ratio, offer text area share), pairwise persona tournament (5 personas,
both orders), critic->optimizer loop (max 3 rounds, mutable fields only,
guardian after each round, accept only if score up and guardian passes),
guardian v2 (back-translation + expectation audit via simulated customers),
and an orchestrator state machine that streams trace events to the frontend.
```

---

## 7. Stage 3: Change, Prove, Win (hours 20 to 30)

**Goal:** demonstrate what the brief rewards, then harden. **Feature freeze at hour 25.**

### Build (hours 20 to 25)
- **Change Request Engine:** voice change, classify mutable vs immutable, diff view, cascade through the Ledger. Dashboard shows "Changed / Preserved / Intent Integrity 100%".
- **Ledger and version history:** approved, stale, pending, blocked; v1/v2/v3 with changelog.
- **Red-Team mode** and Final Approval screen.
- **Export pack:** `wa.me` link, copyable messages, ZIP of posters.
- **Video (optional):** queued, status polling, labeled fallback clip.
- **Polish:** loading states, cost meter, error toasts.

### Harden and rehearse (hours 25 to 30)
- Cache a complete demo campaign as a labeled fallback ("saved output").
- Run the full demo 5+ times. Test on venue Wi-Fi and a phone hotspot.
- Record a backup demo video, prepare screenshots and a 5-slide pitch.
- Test rate-limit behavior by running two generations back to back.

### Done when
- The demo works end to end, including the failure fallback.
- Red-Team inputs are blocked reliably.

### AI builder prompt
```
[Paste master context + Stage 1-2 code.] Implement Stage 3: ChangeRequest
classification (mutable vs immutable) with fact-hash dependency cascade that
marks only affected variants stale; Ledger UI (approved/stale/pending/blocked),
version history with changelog, "Intent Integrity" panel; Red-Team input box
that routes free-text through guardian and shows violations; export pack (wa.me
link, ZIP of poster sizes); optional video job queue with status polling and a
labeled saved-fallback clip; fallback mode that serves cached results labeled
"saved demo output"; loading/error states; cost meter in UI.
```

---

## 8. Hour-by-hour checkpoints

| Hours | Checkpoint |
|---|---|
| 0 to 1 | API keys verified, one call per endpoint, schemas and fixtures written |
| 1 to 5 | Agnes client, intent extraction, facts editor |
| 5 to 9 | Lock flow, TTS read-back, Guardian v1 with tests |
| 9 to 14 | Strategy, segments, slot-based copy in 3 language variants |
| 14 to 17 | Poster pipeline, channel previews, exports |
| 17 to 20 | Scoring, persona tournament, optimizer loop, Guardian v2 |
| 20 to 25 | Change engine, Ledger, Red-Team, export pack, optional video |
| **25** | **FEATURE FREEZE** |
| 25 to 30 | Fallback cache, rehearsals, backup video, pitch deck |

If behind schedule, cut in this order: video, pixel-level check, tone slider, ZIP export. Never cut: facts lock, slots, Guardian, optimizer loop, Red-Team.

---

## 9. Test cases the Guardian must pass

Locked facts: `20%` off, `coffee`, `Saturday-Sunday (10-11 Oct 2026)`, `Bengaluru`, `students`.

| Input | Expected |
|---|---|
| "20% off coffee this Saturday and Sunday" | PASS |
| "25% off coffee" | FAIL (offer conflict) |
| "೨೫% ರಿಯಾಯಿತಿ" | FAIL (Kannada digits, wrong value) |
| "ಇಪ್ಪತ್ತೈದು ಶೇಕಡಾ" (25 in words) | FAIL |
| "Monday-Tuesday special" | FAIL (date conflict) |
| "ಸೋಮವಾರ" (Monday in Kannada) | FAIL |
| "Somavara offer" (Kanglish weekday) | FAIL |
| "Best coffee in Bengaluru" | FAIL (unsupported superlative) |
| "No.1 cafe in town" | FAIL |
| "Free cake with every cup" | FAIL (unapproved claim) |
| "Guaranteed lowest price" | FAIL |
| "Flat Rs 50 off" | FAIL (unapproved price) |
| "Offer valid till 9 PM" | FAIL (unapproved time) |
| Copy missing the offer slot | FAIL (slot absent) |
| Copy that implies "no ID needed" when conditions are `not_specified` | FAIL |

Also test: slot-filled output passes; unrelated numbers such as "100% fresh" are flagged for review; a change to an immutable fact marks only dependent variants stale.

---

## 10. The 3-minute demo script

1. **0:00** The owner, hands busy, speaks in Kanglish. The facts card appears, TTS reads it back, the agent asks "Student ID required?" The owner answers and locks.
2. **0:45** The campaign matrix appears (audiences x languages x channels) with a poster in Kannada and in Kanglish.
3. **1:15** Prediction panel: Variant A 76 to B 89, with what changed. The trace shows the agent working.
4. **1:40** Voice change: "Make it for families and premium." Tone and visuals change; the Ledger shows Offer preserved, Integrity 100%. Then "Actually make it 15%": only offer-bearing assets go stale and re-verify.
5. **2:20** Red-Team: a judge types "say we're the best coffee in Bengaluru" or "25% off". Blocked live.
6. **2:45** Export to WhatsApp, show the cost meter. Close with: *"Human controls truth. AI controls execution. Code enforces the boundary."*

### Backup plan
- Pre-recorded demo video on the laptop and phone.
- Saved campaign loaded in "saved demo output" mode, clearly labeled.
- Typed input if speech recognition fails.
- Saved clip if video generation is slow (label it).

---

## 11. Do not build

Login (hardcode the demo café), real Instagram or Facebook posting, analytics dashboards, multi-tenant accounts, microservices, and anything where video is required for the core flow.

---

## 12. Pitch slide outline (5 slides)

1. **Problem:** the café owner and "what customers are told to expect cannot go wrong".
2. **Idea:** facts locked as typed slots; agents get autonomy only after approval.
3. **Architecture:** understand, lock, plan, generate, score, optimize, verify, approve (one diagram).
4. **Proof:** Red-Team results, Intent Integrity 100%, score trajectory, cost per campaign.
5. **Impact:** small business, Kannada and Kanglish, INR under 1 per campaign, WhatsApp-native.
