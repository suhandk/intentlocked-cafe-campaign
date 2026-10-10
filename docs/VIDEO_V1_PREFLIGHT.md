# Optional video V1 — pending core gate

Historical preflight received 2026-10-09: full V1 release requires the core gate.
Subsequent user instructions enabled optional UNAPPROVED draft controls; see
[current implementation and limits](VIDEO_DRAFTS.md). No actual paid video
submission or human approval has been performed. Full V1 release remains pending.

## Current blockers

- Latest completed live matrix is partial: 9/27 ready; 18 blocked. R1/R2/R3 pass;
  complete live semantic audit, poster/export workflow and required human/native
  review remain unverified.
- The supplied iced/cold coffee, tall glasses, shutter, wooden counter, table,
  signage and venue imagery are not established by locked PRODUCT/LOCATION facts.
  They must not become visual product/venue promises. Generated footage must be
  revised to neutral imagery or these details separately owner-approved first.
- The current locked-facts schema has no CTA fact. Use an exact approved campaign
  CTA bound to its content/dependency hashes, or obtain the required CTA approval;
  never invent a CTA from model output.
- Account video entitlement/model identifier is unverified. Standard/Flash access
  and billing are not inferred from a model catalogue or previous text/image calls.
- Generated clip text/claim QA and final ffprobe/font/artifact checks have not run.

## Required owner confirmation, after prerequisites pass

Show exact entitled model identifier and **four generated clips × six seconds =
24 generated seconds**, followed by a six-second deterministic end card (30-second
final). The 24-second alternative drops shot 2: **three clips = 18 generated
seconds**, plus the same six-second end card. Require an explicit selection and
confirmation before submitting any clip. Do not describe either model as free.

## Implementation contract retained for the next eligible stage

Use the same Agnes-only client and durable jobs. Keep video optional and isolated
from core campaign readiness. Persist provider IDs and downloaded bytes; bounded
polling/backoff, max concurrency two, cancellation and one safe retry per clip.
Unknown media submission outcomes must not be resubmitted blindly. Generated
footage has no text; exact approved overlays and end-card text are burned into
the export. Encode H.264/yuv420p, 720×1280, 30 fps with an AAC track. Verify raw
frames and final specifications, bind approval to facts/overlay/clip/final hashes
and model ID, and reject stale/missing QA. Export never publishes. Deterministic
poster footage, if separately allowed, is visibly labeled fallback; no fabricated
footage or human/native sign-off.

Required failure/cancellation/timeout/stale/expiry/download/spec/overlay/font/core-
isolation tests are **NOT EXECUTED** because the prerequisite has not passed.
