# PROJECT_CONTEXT.md: Intent-Locked Voice Campaign Agent

> **Persistent context for the AI builder.** Load this at the start of EVERY session
> (save it in the repo root as `CLAUDE.md` / `AGENTS.md` / `.cursorrules`).
> Anything here overrides your assumptions. If a task contradicts this file, stop and say so.
> Verified against the Agnes docs on 2026-10-08. Re-verify with `scripts/smoke_agnes.py` (Prompt B0).

---

## 1. Mission

Build the **Intent-Locked Voice Campaign Agent** for hackathon problem **HR26-AI-02 Marketing Campaigns**
(Agnes AI India Hackathon, 8 Oct 2026; 30-hour build; live demo to judges).

A café owner in Bengaluru is behind the counter, hands busy. She speaks an idea in Kannada, English or Kanglish:
*"I run a café in Bengaluru. This weekend I want 20 percent off coffee for college students. Make it Kannada-English and promote it on Instagram and WhatsApp."*

The system must:
1. **Understand** the idea and propose structured business facts; the owner edits and **locks** them.
2. **Generate** a campaign adapted to audiences x languages x channels (copy + posters), in a tone that sounds local, not translated.
3. **Predict** performance before launch and **autonomously optimize** (visible score trajectory and changelog).
4. **Verify** every output against the locked facts (deterministic first). Nothing customers are told to expect may be wrong.
5. **Absorb changes** (new audience, tone, even offer) without losing approved work; show what exists, what changed, what is pending.
6. **Approve and export** (WhatsApp-ready pack). Cost and time must be realistic for a small business.

**Pitch line:** *Human controls truth. AI controls execution. Code enforces the boundary.*

### Brief requirements to design against (HR26-AI-02)
Minimum objectives (all three must be visibly demonstrated):
1. Generate a coherent campaign adapted to different audiences, languages and channels.
2. Predict campaign performance before launch and autonomously optimize it.
3. Preserve the exact business intent while autonomously adapting messaging to different cultural and linguistic contexts.

Key sentences: the one thing that cannot go wrong is what customers are told to expect; changing requirements are absorbed without losing what was approved; the owner knows what exists, what changed and what is pending; results feel local, not translated; the owner stays in control; time and cost are realistic. Extra points for creativity beyond the minimum.

---

## 2. Hard rules (non-negotiable)

| # | Rule |
|---|---|
| H1 | **Facts are typed slots.** The LLM never writes offer values, dates, prices, product, location, conditions. It writes templates with `{{SLOT}}` tokens; **code fills them** from owner-approved surface forms. |
| H2 | **Guardian is deterministic first.** Regex/lexicon/slot rules decide BLOCK. An LLM check is second-line and can only add WARN or raise a semantic mismatch; it can never override a deterministic BLOCK. "An LLM checks the LLM" is never the guarantee for numbers, dates, names. |
| H3 | **Mutable vs immutable.** Optimizer and change engine may edit only mutable fields. Any change to an immutable fact requires explicit owner confirmation with a diff. Never silent. |
| H4 | **AI images are background art only.** Prompts forbid any text. All text (offer, dates, Kannada script) and the logo are rendered by code (HTML canvas, Noto Sans Kannada). |
| H5 | **Agnes models only for AI inference:** `agnes-3.0-flash`, `agnes-image-2.5-flash`, `agnes-video-2.5`. No other LLM/image/video API. The single non-Agnes component is the browser Web Speech API for speech-to-text/text-to-speech (Agnes takes no audio; the brief itself says a separate component is needed). Typed input is always available. |
| H6 | API key is **server-side only**. Never in frontend code, logs, trace payloads, repo or screenshots. |
| H7 | Every Agnes call goes through **one client** (queue, rate limiter, backoff+jitter, timeout, trace, cost). |
| H8 | Every LLM output is validated by Pydantic. Up to **2 repair retries** that send back the validation error. Then fail loudly with a typed error. Never fabricate a result to hide a failure. |
| H9 | **No fake data.** Never hardcode scores or results. Cached outputs must show a visible **"SAVED DEMO OUTPUT"** label (brief rule: label saved outputs). |
| H10 | **Unknown is not invented.** Unspecified conditions stay `not_specified`; copy must not state or imply them. |
| H11 | **Prediction honesty.** Display "Predicted preference (simulated personas + rules), not a CTR forecast", with an uncertainty band. |
| H12 | **Video is optional** and never on the critical path (1 RPM, async). |
| H13 | **Kannada/Kanglish correctness.** All Kannada surface forms are shown to the owner at lock for approval. Guardian lexicons must be reviewed by a native speaker before Gate G2. |
| H14 | **Scope discipline.** No login, no real Instagram/Facebook posting, no analytics, no multi-tenant, no microservices. One FastAPI app, SQLite, one Next.js single-page flow. |

---

## 3. Agnes API contract (from official docs, verified 2026-10-08)

Base URL: `https://apihub.agnes-ai.com/v1`. Header: `Authorization: Bearer $AGNES_API_KEY`. Content-Type JSON.

### 3.1 Text: `agnes-3.0-flash`
- `POST /chat/completions` (also `/responses` and Anthropic-style `/messages` exist; **use chat/completions only**).
- Body: `model`, `messages[{role: system|user|assistant, content: string | [{type:"text",text}, {type:"image_url",image_url:{url}}]}]`, `temperature`, `top_p`, `max_tokens` (max 65,536), `stream`, `tools[{type:"function",function:{name,description,parameters(JSON schema)}}]`, `tool_choice`, `chat_template_kwargs:{enable_thinking:bool}`.
- Response: `choices[0].message.content` or `choices[0].message.tool_calls`; `usage{prompt_tokens, completion_tokens, total_tokens}`. Context window 512K.
- Input: text and **public** image URLs. Output: text only.
- **No documented JSON-mode / `response_format` for text.** Structured output strategy (decided by smoke test, in this order):
  - **S1:** one function tool with the target JSON schema, forced via `tool_choice`; read `tool_calls[0].function.arguments`.
  - **S2:** prompt "return ONLY a JSON object", strip fences, `json.loads`, validate with Pydantic, repair loop (H8).
  - Record the winner in `AGNES_CONTRACT_VERIFIED.md`. Build the client behind `structured_call(schema, ...)` so the strategy is swappable.
- Thinking mode (`enable_thinking: true`) improves planning but costs latency. Use only for strategy (R3) and optimizer (R6). Confirm in the smoke test how reasoning text is returned and strip it.
- Tool results must be sent back to the model before asking for the next action; validate tool arguments before side effects.

### 3.2 Image: `agnes-image-2.5-flash`
- `POST /images/generations`. Body: `model`, `prompt`, `size` (**tier**: `"1K"|"2K"|"3K"|"4K"`), `ratio` (`1:1, 3:4, 4:3, 16:9, 9:16, 2:3, 3:2, 21:9`; default `1:1`), `extra_body:{response_format:"url"|"b64_json", image:[public URLs or data URIs]}`.
- **Never put `response_format` at top level** (causes errors). Image-to-image and multi-image composition take inputs in `extra_body.image` (no tags needed).
- Response: `data[0].url` (public Google Storage URL) or `data[0].b64_json`.
- **Native 1K sizes:** 1:1 = 1024x1024, 9:16 = 736x1312, 16:9 = 1312x736. **1080x1080, 1080x1920, 1200x630 are NOT native.** Generate tier+ratio, then crop/resize in code.
- Timeout 60-360 s. Download the image immediately and persist it locally (do not rely on the URL staying alive).

### 3.3 Video: `agnes-video-2.5` (optional; free tier may be `agnes-video-2.5-flash`, 720P only; make model ID configurable)
- Create: `POST /videos` body `{model, prompt, mode:"text"|"keyframe"|"reference", seconds:"4".."12" (string), size:"720P"|"1080P"|"1K"|"2K", aspect_ratio:"9:16"|"16:9"|"1:1"|"4:3"|"3:4"|"21:9", seed?, n:1}`. Do not send `width/height/fps/num_frames/quality`.
- Response: `{id, task_id, video_id, status: queued|in_progress|completed|failed, progress}`. Save `video_id`.
- Poll: `GET https://apihub.agnes-ai.com/agnesapi?video_id=<id>&model_name=agnes-video-2.5` with Bearer header, every 1.5-2 s until `completed|failed`, hard cap 5 minutes. Result URL is top-level `url`. `429` -> exponential backoff.
- Reference media must be public URLs. Report success only after `status == completed` and `url` is fetched.

### 3.4 Pricing and limits (free default key; brief dated 2 Oct 2026; re-check on the day)
| | Effective RPM (free/default) | List price | Current price |
|---|---|---|---|
| Text | **10** (reduced from 30 on 2026-09-23) | $0.05/1M in, $0.15/1M out | $0 |
| Image 1K / 2K / 3K-4K | 10 / 5 / 1 | $0.010 / 0.018 / 0.021-0.024 | $0 |
| Video | **1** | $0.025/s at 720P | free for Flash (limited time) |

- Limits are shared per **API key type**; extra keys of the same type do **not** add capacity. If teammates share one key, they eat each other's RPM. **Develop in `AGNES_MODE=mock`; reserve live calls for integration tests and the demo.**
- Cost meter shows list-price estimate and "currently free on the platform".

---

## 4. Rate-limit design and call budget

Configure the limiter at **80% of the limit**: `TEXT_RPM=8`, `IMAGE_RPM=8`, `VIDEO_RPM=1`. Interactive (owner-triggered) calls have **higher priority** than background calls. Batch aggressively: one call per language, never one per asset.

| Phase | Text calls | Image calls |
|---|---|---|
| Intent (R1) | 1 | 0 |
| Surface forms (R2) | 1 | 0 |
| Strategy + segments (R3) | 1 | 0 |
| Copy templates (R4), 1 per language | 3 | 0 |
| Backgrounds: hero audience, 3 ratios (+ vision QA R9, batched) | 1 | 3 (+ retries) |
| Optimize hero group, up to 3 rounds (R5 x2 orders + R6) | up to 9 | 0 |
| Final Customer Reader (R7), batched | 1-2 | 0 |
| **Typical full campaign** | **~17-19** | **~3-6** |
| Change request: parse (R8) + surface forms if fact changed | 1-2 | 0-3 |

At 8 RPM a full run takes about 2-3 minutes of limiter time. Therefore: show progressive results (copy appears before images), run background work while the owner reviews facts, support `DEMO_FAST=1` (max 2 optimizer rounds), and keep a saved demo campaign as a labeled fallback.

---

## 5. Architecture

```
Voice/Text -> [R1 Intent] -> Facts proposed -> OWNER EDITS + LOCKS (gate) -> [R2 Surface forms, owner approves]
 -> Brand kit -> [R3 Strategy+Segments+Personas] -> [R4 Copy templates x language]
 -> CODE: slot fill -> CODE: Guardian -> CODE: poster compositor (AI background art + canvas text)
 -> Score (rule features + R5 persona tournament) -> [R6 Critic+Optimizer] -> Guardian -> keep if better and passing (max 3 rounds)
 -> [R7 Customer Reader: blind back-translation + expectation audit] -> Integrity report
 -> OWNER APPROVES -> Ledger/versions -> Export (wa.me, copy, ZIP)
 Change request (voice/text) -> [R8 Change Parser] -> CODE classifies mutable/immutable -> cascade via Ledger
```

### AI vs deterministic code
| AI (Agnes) | Deterministic code |
|---|---|
| R1 intent, R2 surface forms, R3 strategy, R4 copy templates, R5 persona judge, R6 critic-optimizer, R7 customer reader, R8 change parser, R9 background QA, image/video generation | Slot fill, Guardian rules G01-G13/G15, scoring features, score aggregation, mutability classification, dependency hashing, Ledger status, poster layout/contrast, aspect-ratio crop/resize, ZIP/export, rate limiting, cost accounting |

Orchestrator: a ~150-line explicit state machine (no agent framework) with a step budget, wall-time budget, stop rules, and a **trace event for every step** streamed to the UI via SSE.

---

## 6. Domain model (Pydantic v2; SQLite)

```python
Lang   = Literal["en","kn","kn-Latn"]        # kn = Kannada script; kn-Latn = Kanglish (Kannada+English in Roman letters)
Case   = Literal["nom","dat","gen","loc"]     # Kannada suffix agreement: -ge (dat), -da (gen), -alli/-nalli (loc)
Channel= Literal["instagram","whatsapp","facebook","poster"]
Status = Literal["approved","stale","pending","blocked"]

class Fact(BaseModel):
    key: SlotKey                  # CAFE, LOCATION, OFFER, PRODUCT, DAYS, DATES, ELIGIBILITY, ID_RULE, TIME_WINDOW, DINE_IN_RULE, MIN_PURCHASE_RULE, COMBINE_RULE
    status: Literal["proposed","locked","not_specified"]
    canonical: dict | None        # e.g. OFFER {"offer_type":"percent_off","value":20}; DAYS {"start":"2026-10-10","end":"2026-10-11","weekdays":["SAT","SUN"]}
    surface: dict[Lang, dict[Case, list[str]]]   # approved forms; first = primary
    source_span: str | None       # transcript excerpt
    version: int
    mutable: Literal[False] = False

class IntentCard(BaseModel):
    business: dict; goal: str; facts: list[Fact]
    audiences_mentioned: list[str]; languages: list[Lang]; channels: list[Channel]
    tone: str | None; must_say: list[str]; must_not_say: list[str]
    clarifications: list[Clarification]; transcript_warnings: list[TranscriptWarning]

class Variant(BaseModel):
    id: str; campaign_id: str; audience_id: str; language: Lang; channel: Channel
    template: dict[str,str]       # fields with {{SLOT|case}} tokens (headline, body, cta, ...)
    slots_used: list[str]; fact_hash: str     # sha256 over canonical JSON of ONLY the facts it uses
    status: Status; scores: dict; parent_id: str | None; changelog: list[ChangeEntry]
    content_hash: str             # hash of filled text; approved_hash set at approval

class GuardianReport(BaseModel):
    variant_id: str; passes: list[str]; violations: list[Violation]   # {rule, span, severity: BLOCK|WARN|INFO, detail}
    integrity_pct: float          # checks passed / checks run x 100; approval requires BLOCK == 0

class ChangeRequest(BaseModel):
    text: str; ops: list[ChangeOp]            # target in MUTABLE_TARGETS or "FACT:<KEY>"
    classified: Literal["mutable","immutable","mixed","rejected"]; affected_variant_ids: list[str]
```

**Tables:** `campaigns, fact_versions, brand_kits, audiences, variants, assets, scores, ledger_events, campaign_versions, approvals, trace_events, api_calls`. Facts are versioned (`fact_versions`); old versions never deleted.

**Required facts per campaign:** CAFE, LOCATION, OFFER, PRODUCT, DAYS (+DATES). **Condition facts** (ELIGIBILITY, ID_RULE, TIME_WINDOW, DINE_IN_RULE, MIN_PURCHASE_RULE, COMBINE_RULE) are `not_specified` unless owner states or answers them.

**Target audience is not eligibility.** "For college students" may be marketing focus or a real restriction. Agent 1 must ask. If ELIGIBILITY restricts the offer, targeting a non-eligible audience (e.g. "families") is an **eligibility conflict (G15)**: surface it and require the owner to widen eligibility (immutable change, confirmed) or keep the audience.

---

## 7. Slot system

- Token grammar: `{{KEY}}` or `{{KEY|case}}`; regex `\{\{([A-Z_]+)(?:\|(nom|dat|gen|loc))?\}\}`.
- Each locked fact has **approved surface forms per language and case**, e.g. OFFER: en `20% off`; kn `20% ರಿಯಾಯಿತಿ` / `೨೦% ರಿಯಾಯಿತಿ`; kn-Latn `20% off`. PRODUCT dat: kn `ಕಾಫಿಗೆ`; kn-Latn `Coffee-ge`.
- Kannada is agglutinative, so grammatical case suffixes attach to the noun; the case is part of the slot token and the approved form.
- R4 never sees real values, only `shape_hint`s with `<N>` placeholders. Templates containing fact-like literals fail G07 and are regenerated.
- **Immutable fact changes are cheap by design:** a new OFFER value regenerates only surface forms (1 call), then all templates are re-filled in code (0 calls), re-verified, and posters re-rendered. If the `offer_type` changes (e.g. percent -> BOGO) that is **structural**: regenerate affected copy templates.

---

## 8. Guardian (deterministic core)

Normalization (on a shadow copy; keep offset map for spans): Unicode NFKC; strip zero-width chars (U+200B-D, U+2060, U+FEFF) **in the shadow copy only** (ZWJ/ZWNJ matter in displayed Kannada); fold confusables (Cyrillic/Greek lookalikes -> Latin; letter `O`/`l` adjacent to digits -> `0`/`1`); map Kannada (U+0CE6-0CEF), Devanagari (U+0966-096F), Arabic-Indic (U+0660-0669) digits to ASCII; lowercase; collapse whitespace.

| ID | Rule | Severity |
|---|---|---|
| G01 | Every numeric token (digits, English/Kannada/Kanglish number words, "half", fractions, percent words ಶೇಕಡಾ/shekada) must map to an allowlisted value from locked facts | BLOCK |
| G02 | Weekdays (en/kn/Kanglish/abbreviations), months, dates, "today/tomorrow/tonight" must be allowlisted | BLOCK |
| G03 | Currency (₹, Rs, INR, ರೂ, "rupees") with amounts must be allowlisted | BLOCK |
| G04 | Time of day / "till", "after", "all day", "24x7", "midnight" must be allowlisted | BLOCK |
| G05 | Required slots for the channel are present (after fill) | BLOCK |
| G06 | Each filled slot equals an approved surface form for that language and case | BLOCK |
| G07 | Pre-fill templates contain no fact-like literals | BLOCK (regenerate) |
| G08 | Claim blacklist (en/kn/Kanglish): best, No.1, #1, top, finest, guaranteed, free, unlimited, only, lowest price, cheapest, 100%, award-winning, healthy, authentic, "in the city/India", comparatives, etc., unless in `approved_claims` (derived from locked facts) | BLOCK |
| G09 | Phrases implying a `not_specified` condition ("no ID needed", "all day", "dine-in only", "with every cup") | BLOCK |
| G10 | Brand kit `must_not_say` / forbidden claims | BLOCK |
| G11 | Script fit (kn mostly Kannada script; kn-Latn Latin only; en Latin) | WARN |
| G12 | Channel length limits (poster overflow = BLOCK) | WARN/BLOCK |
| G13 | No unresolved `{{...}}` or placeholder-like text (`[offer]`, `XX%`) | BLOCK |
| G14 | Semantic: R7 Customer Reader answers vs locked facts. Offer/product/days/eligibility/location mismatch = BLOCK; non-empty `other_promises` = WARN | BLOCK/WARN |
| G15 | Eligibility vs target audience conflict | BLOCK for approval |

**Intent Integrity %** = checks passed / checks run across all variants (per variant, per fact: present, correct, no conflicting value) x 100. **Approval requires 0 BLOCK.**

**Lexicons** (`guardian/lexicon_*.py`): number words 0-100 (+ hundred) for en, kn (ಒಂದು, ಎರಡು, ಮೂರು, ನಾಲ್ಕು, ಐದು, ಆರು, ಏಳು, ಎಂಟು, ಒಂಬತ್ತು, ಹತ್ತು, ಇಪ್ಪತ್ತು, ಮೂವತ್ತು, ನಲವತ್ತು, ಐವತ್ತು, ಅರವತ್ತು, ಎಪ್ಪತ್ತು, ಎಂಬತ್ತು, ತೊಂಬತ್ತು, ನೂರು and compounds such as ಇಪ್ಪತ್ತೈದು = 25) and kn-Latn transliterations; weekdays (ಸೋಮವಾರ, ಮಂಗಳವಾರ, ಬುಧವಾರ, ಗುರುವಾರ, ಶುಕ್ರವಾರ, ಶನಿವಾರ, ಭಾನುವಾರ; somavara, mangalavara, budhavara, guruvara, shukravara, shanivara, bhanuvara). **A native Kannada speaker must review these before Gate G2.**

---

## 9. Scoring and optimizer

**Rule features (0-100 each):** `offer_first_line` (offer slot in first line/80 chars), `cta_present`, `channel_length_fit`, `required_facts_complete`, `script_fit`, `poster_contrast` (WCAG ratio >= 4.5 -> 100; 3-4.5 -> 60; <3 -> 20), `offer_area_share` (offer text area 6-18% of poster).

**Persona tournament:** 5 personas (from R3) judge candidate vs baseline A, in **both orders** (AB and BA) = 10 judgments (2 text calls). `tournament = 100 x (wins + 0.5 x ties) / 10` (baseline = 50).

**Overall** = `0.5 x mean(features) + 0.5 x tournament`. Uncertainty `±` = `1.96 x sqrt(p(1-p)/10) x 50` rounded, shown as "Predicted preference 74 ± 9". Never hardcode.

**Optimizer loop (hero group = primary audience x primary language, all channels):**
1. Score baseline. 2. R6 returns critique + <=4 edit ops on **mutable fields only** (hook, cta, tone, headline emphasis, layout emphasis, theme, ordering). 3. Code applies ops, re-fills slots. 4. Guardian. 5. Score vs baseline. 6. **Accept only if** Guardian has 0 BLOCK AND tournament >= 6/10 AND mean(features) drops by < 3 points. 7. Stop after 3 rounds, or 1 round without gain, or step/time budget. Record every round (accepted or rejected) in the changelog. Non-hero groups get one optimization round lazily (or inherit accepted edit patterns).

---

## 10. Ledger, versions, change engine

- Every variant stores `fact_hash` over only the facts it uses. Statuses: `approved | stale | pending | blocked`.
- **Mutable targets:** AUDIENCE, TONE, THEME, HOOK, CTA, LANGUAGE_MIX, CHANNELS, LAYOUT_EMPHASIS. Apply and regenerate only affected variants.
- **Immutable targets:** `FACT:<KEY>` for every fact. Require confirmation modal (before/after, affected variant count). On confirm: new fact version -> surface forms -> only variants whose `slots_used` include the key go `stale` -> re-fill -> Guardian -> `pending` for re-approval. Unrelated approved variants remain `approved`.
- Classification is **deterministic**: R8 only parses; the code decides mutability from the target name. Never trust an LLM label for mutability.
- **Version history:** `v1, v2, v3` with human-readable changelog ("v3 changed tone and headline; offer unchanged"). Change dashboard shows 🔄 Changed / 🔒 Preserved per field and Intent Integrity %.
- **Red-Team box (two modes, so judges are never confused):**
  - *Instruct the AI* (free text, e.g. "make it 25%", "say we're the best coffee in Bengaluru", "add free cake"): goes through R8 + classification. Fact edits -> "Immutable change: needs your confirmation". Unapproved claims -> **BLOCKED** with the rule shown.
  - *Edit the copy directly* (judge types caption text): runs Guardian live. "25% off" -> **OFFER CONFLICT 20 -> 25, BLOCKED**.

---

## 11. Creative pipeline

- Backgrounds: Agnes image, `size: IMAGE_TIER` (default `1K`), native ratio per output: `1:1` (Instagram post), `9:16` (story), `16:9` (Facebook, crop to 1200x630). Prompt template T1 (no text). **R9 vision QA** (the returned image URL is public) rejects backgrounds containing text/numbers/logos; regenerate up to 2 times.
- Compositor (browser canvas): background + dark/light scrim chosen by sampled luminance behind text + headline/sub/CTA/footer text + logo PNG from the brand kit. Footer (`{{LOCATION}} · {{DAYS}}`) is always filled by code. Wait for `document.fonts.load()` of Noto Sans Kannada (bundled locally, not CDN) before drawing; break lines at grapheme-cluster boundaries (`Intl.Segmenter`), never mid-cluster.
- Exports: 1080x1080, 1080x1920 (keep key text out of top/bottom 250px), 1200x630. ZIP built in the browser (JSZip). WhatsApp: `https://wa.me/?text=<urlencoded filled message>` plus copy button.
- Optional video: T2 prompt, `mode:"text"`, `9:16`, `720P`, `seconds:"6"`, no text in the clip; offer text overlaid on the clip (ffmpeg overlay of the rendered PNG, or CSS overlay in-app). Queue, poll, label fallback "SAVED DEMO OUTPUT".

## 12. Voice

- Web Speech API with language toggle `kn-IN` / `en-IN`; show interim and final transcript; **transcript is editable before Agent 1 runs** (speech recognition mishears numbers: fifteen/fifty).
- Facts Lock screen reads facts back via TTS (en-IN; Kannada voice only if the OS has one) AND shows them visually. Always provide typed input fallback. Test Kannada and code-mixed speech in the first 2 hours.

## 13. Frontend (single page, no router)

Panels: (1) Speak/Type; (2) Facts Lock (edit, clarification chips, lock, TTS read-back, Kannada surface-form approval); (3) Brand kit + strategy summary; (4) Campaign matrix (audience x language selectors, channel tabs, live previews: Instagram, WhatsApp, Facebook, posters); (5) Prediction and Optimization (trajectory, per-feature scores, changelog); (6) Guardian and Intent Integrity (+ Red-Team); (7) Ledger/Versions and Change box (voice/text); (8) Approve and Export. Persistent: **Trace drawer** (live SSE), **Cost/time meter**, **Mode banner** (LIVE / MOCK / SAVED DEMO OUTPUT). Loading skeletons everywhere; errors as toasts with retry.

## 14. Backend API (one FastAPI app)

`POST /api/campaigns` · `POST /api/campaigns/{id}/intent` · `POST .../facts/surface` · `POST .../facts/lock` · `POST .../generate` · `POST .../optimize` · `POST /api/guardian/check` · `POST .../change` · `POST .../change/confirm` · `GET .../ledger` · `GET .../versions` · `POST .../approve` · `GET .../export` · `POST .../video` · `GET .../video/{id}` · `GET /api/stream/{id}` (SSE) · `GET /api/cost` · `GET /api/health`.

## 15. Repo layout, env, modes

```
/backend  main.py agnes_client.py schemas.py db.py orchestrator.py ledger.py
  agents/{intent,surface,strategy,copy,scoring,optimizer,reader,change}.py
  guardian/{normalize,rules,slots,lexicon_en,lexicon_kn,claims,report}.py
  prompts/*.md   fixtures/   mock_agnes/   tests/
/frontend  (Next.js + Tailwind)  app/page.tsx  components/  public/fonts/NotoSansKannada*
/scripts  smoke_agnes.py  prompt_lab.py  seed_demo.py
/docs  INTERFACES.md  DECISIONS.md  PROGRESS.md  AGNES_CONTRACT_VERIFIED.md
```
Env: `AGNES_API_KEY, AGNES_BASE_URL, TEXT_MODEL, IMAGE_MODEL, VIDEO_MODEL, TEXT_RPM=8, IMAGE_RPM=8, VIDEO_RPM=1, IMAGE_TIER=1K, AGNES_MODE=live|mock|cached, DEMO_FAST=0|1, TODAY_OVERRIDE=2026-10-08`.
`mock` = local fake Agnes server returning recorded fixtures (parallel dev, offline tests). `cached` = saved demo campaign, always labeled.

## 16. Engineering standards

Python 3.11, type hints, Pydantic v2, `ruff`, `pytest`. Frontend TypeScript strict. Structured JSON logs with trace IDs (no secrets, no raw API keys). Inputs capped (transcript <= 2,000 chars; uploads PNG/SVG <= 2 MB, MIME-validated). Treat transcript, change requests and pasted text as **untrusted data** (prompt injection): wrap in `<user_data>` delimiters in prompts; LLM output can never mutate locked facts because fact fields are never accepted from LLM output after lock. Render LLM text via React (escaped) only. CORS restricted to the frontend origin. Each module ships with tests; critical modules (Guardian, slots, ledger, change classification) require **>= 90% branch coverage and a 40+ case adversarial suite**.

## 17. Demo contract (3 minutes; everything below must work on stage)

1. Owner speaks Kanglish -> facts card -> TTS read-back -> clarification ("Is the offer only for students or open to all? ID needed?") -> lock.
2. Matrix: 3 audiences x languages x channels; Kannada and Kanglish posters.
3. Prediction panel: baseline vs optimized with real computed numbers, changelog, trace.
4. Voice change "Make it for families and premium" -> mutable changes, 🔒 Offer preserved, Integrity 100% (eligibility must be open-to-all, else G15 fires; the demo owner answered "open to everyone" at lock). Then "Actually make it 15%" -> confirmation modal -> only offer-bearing variants go stale -> re-fill and re-verify.
5. Red-Team (both modes) blocks live.
6. Export to WhatsApp; cost meter; closing line.

**Fallbacks:** typed input; `AGNES_MODE=cached` saved campaign labeled; saved video clip labeled; backup screen recording.

## 18. Definition of done and cut order

Done = demo contract passes 5 consecutive runs in `live` mode on hotspot Wi-Fi, plus `cached` mode, plus all gate checks in BUILD_PROMPTS.md. **Cut order if behind:** video -> ffmpeg overlay -> voice-sample tone slider -> ZIP export -> non-hero optimization -> vision QA (R9). **Never cut:** facts lock, slots, Guardian, optimizer loop, change engine/Ledger, Red-Team, trace, labeled fallback.

## 19. How you (the AI builder) must work

1. **Plan first** (files to touch, interfaces, risks) and wait for "go" unless told "no-plan mode".
2. Implement in small vertical slices; write tests first for critical modules.
3. Run the tests and show real command output; never claim success without it.
4. No placeholders, TODO stubs, or invented API parameters. If the contract is unclear, say so and propose the smoke test.
5. If something is ambiguous, pick the simplest option consistent with this file, record it in `docs/DECISIONS.md`, and continue.
6. End every task with: files changed, commands to run, test results, known gaps, updated `docs/INTERFACES.md` and `docs/PROGRESS.md`.
7. Do not add features outside the current prompt. Do not refactor unrelated code.
