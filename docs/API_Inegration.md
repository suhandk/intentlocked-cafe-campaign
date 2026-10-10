Act as the principal engineer implementing Meta integrations in the existing Intent-Locked Marketing Campaigns project.

Add backend support for:
1. WhatsApp Business Cloud API messaging.
2. Facebook Page publishing.
3. Instagram professional-account publishing.

Do not redesign the completed architecture. Inspect the repository, M0, the complete project guide, AGENTS.md if present, current interfaces, migrations, progress reports, and tests before making changes. Identify conflicts between the existing local-only profile and this new publishing scope. Keep local/mock mode available, and make external publishing an explicit opt-in capability.

The existing WhatsApp wa.me link only opens a draft. Preserve that feature and distinguish it clearly from API sending.

Your task is implementation, documentation, and verification. Do not send a real message or publish a real post during development unless the owner explicitly authorizes that specific live action.

A. Verify platform requirements before implementation

Read current official Meta documentation for WhatsApp Cloud API, Facebook Pages publishing, and Instagram publishing. Use only official documentation for platform requirements.

Verify and document:
- Supported account types and the selected Instagram authentication flow.
- Required permissions, account identifiers, token types, token expiry, and refresh behavior.
- App review or business verification requirements where applicable.
- WhatsApp template versus free-form messaging requirements.
- Supported media formats, limits, and accessibility requirements.
- Publishing status, webhook verification, rate limits, and error behavior.
- Whether the chosen endpoints support idempotency.

Pin a supported Graph API version in configuration. Do not guess endpoint paths, permissions, payload fields, or authentication flows. Do not combine incompatible Instagram login flows.

Create a dated capability report containing documentation links and the exact supported scope. Mark unsupported or unavailable capabilities honestly.

B. Configuration and secrets

Reuse the existing settings system.

Add backend-only configuration for the verified integration requirements. Expected concepts include:
- A master Meta integration enable flag, disabled by default.
- Explicit mock/live mode.
- Pinned Graph API version.
- App ID and app secret where required.
- WhatsApp phone-number ID, business-account ID, and access token.
- Facebook Page ID and Page access token.
- Instagram professional-account ID and the token required by the chosen flow.
- Webhook verification secret.
- Public HTTPS media origin or storage configuration, if required.
- Connection, request, polling, and retry limits.

Choose final variable names after inspecting repository conventions and the verified API flow.

Update .env.example with empty secrets and safe defaults. Never read an existing .env into logs, reports, tool output, or screenshots. Never put credentials in frontend code, NEXT_PUBLIC_* variables, public manifests, URLs, or browser storage.

For a single-owner deployment, backend environment configuration is acceptable. If implementing multiple connected owners, use encrypted credential storage with ownership checks. Do not claim multi-user security unless it is implemented.

Add validation that prevents a partially configured integration from silently operating in live mode.

C. Architecture and contracts

Keep social publishing separate from the Agnes inference client.

Implement provider adapters with narrow interfaces for:
- Connection and capability validation.
- Preparing and submitting a publish/send operation.
- Checking operation status.
- Handling verified webhook events, where supported.
- Mapping provider errors into safe application errors.

Reuse existing API prefixes and response/error conventions.

Define typed request and response models before implementation. Include:
- Campaign and current fact revision.
- Platform and destination.
- Approved content hash and approved artifact hashes.
- Explicit owner confirmation.
- Idempotency key.
- Operation ID, status, timestamps, attempts, and provider identifiers.
- Safe error code and actionable next step.
- Source mode and cached-output provenance.

Persist publishing operations with migrations and repositories. Define clear states, such as:
draft, pending_confirmation, queued, submitting, processing,
succeeded, failed, cancelled, stale, and delivery_unknown.

Distinguish provider acceptance, completed publishing, message delivery, and message reading. Do not label an accepted WhatsApp request as “delivered.”

Record real provider IDs and statuses. Mock IDs must be visibly identified as mock.

D. Approval and revision safeguards

Reuse the existing server-side final approval and export checks.

Before queueing a publish operation, verify:
- The campaign revision is current.
- Content and every selected asset are approved.
- Approved hashes match the actual submitted content and bytes.
- Required audits are complete and not blocked.
- Required warnings have explicit acknowledgments.
- Assets exist and belong to the authorized campaign.
- The destination belongs to the configured/authorized account.
- The owner has confirmed the exact platform, destination, text, and media.

Repeat these checks immediately before submission. A queued operation that becomes stale must not publish.

Fact changes, policy changes, copy edits, changed image bytes, changed font/layout, or affected surface forms must invalidate relevant publishing eligibility through existing dependency rules.

Historical revisions remain viewable but cannot be presented as current or published through a bypass.

For cached output, preserve visible cached/source provenance and require the same current approval checks.

Treat publishing as an irreversible external action. The confirmation must show the actual payload in readable form. Do not automatically publish after generation, optimization, auditing, or export.

If facts change after the provider has already accepted a submission, record that timing truthfully. Do not imply the external action was cancelled or rolled back.

E. Platform behavior

WhatsApp:
- Preserve the existing prefilled wa.me draft and separate poster download.
- Add a distinct API-send operation.
- Validate recipient input and apply current verified platform rules for templates and free-form messages.
- Support only verified message/media types.
- Obtain and record recipient permission where required by the intended workflow.
- Do not treat target-audience facts as a contact list or permission to message people.
- Record send acceptance and webhook delivery outcomes separately.

Facebook:
- Publish only to the configured authorized Page.
- Support a deliberately limited initial scope, such as text and a single image, if current official APIs support it.
- Preserve the exact approved text and asset association.
- Record the resulting provider post ID and verified status.

Instagram:
- Use the authentication flow selected in section A.
- Support a limited verified initial format, such as a single-image feed post.
- Handle media-container creation, bounded status polling, and publishing as separate persisted steps.
- Validate media requirements before submission.
- Do not invent support for Stories, Reels, carousels, or personal accounts.
- Record container and published-media IDs separately.

F. Durable jobs, retries, and duplicate prevention

Integrate with the existing durable job infrastructure and SSE replay.

Use bounded concurrency, finite attempts, finite polling, and finite deadlines. Respect Retry-After within the remaining budget.

Do not blindly retry publishing POST requests after a timeout or connection loss. The provider may already have accepted the request.

Use provider-supported idempotency where verified. Otherwise:
- Use local transactional idempotency to prevent repeated owner requests.
- Persist the submission attempt before performing the network request.
- Reconcile with the provider where possible.
- Mark ambiguous outcomes delivery_unknown when reconciliation is unavailable.
- Require an explicit safe recovery action.
- Never promise exactly-once external publishing without supporting evidence.

A double click, SSE reconnect, page reload, or backend restart must not create another send/post.

Cancellation before submission must prevent the operation. Cancellation after submission must accurately state the provider action may already have occurred.

Do not repeat calls until a desired result appears.

G. Media and network security

Reuse persistent approved assets.

Where Meta requires a publicly accessible HTTPS media URL, implement a documented controlled delivery mechanism. A localhost URL is not sufficient.

Serve only authorized approved assets through opaque, limited-lifetime URLs or a supported authenticated upload flow. Account for provider fetch delays and retries.

Do not expose the entire asset directory, internal paths, secrets, or unrelated files.

Validate MIME type, actual file content, dimensions, and size.

Restrict outbound destinations to the verified provider and approved storage hosts. Do not implement an arbitrary URL-fetch endpoint.

Verify webhook signatures using the current documented algorithm. Reject invalid signatures, deduplicate repeated events, and match events to the correct persisted operation. Never log tokens or full sensitive recipient data.

H. UI integration

Use the existing approval/export panel and established styling.

Add:
- Connection status and configuration guidance.
- Separate actions for WhatsApp draft, WhatsApp API send,
  Facebook publish, and Instagram publish.
- A readable confirmation preview.
- Platform-specific pending, processing, successful, failed,
  stale, cancelled, and unknown status text.
- Actionable errors and explicit safe retry/reconciliation.
- Published post links where the provider returns or supports them.
- Clear mock/live and cached-output labels.

Keep technical traces in the optional drawer. Do not display secrets.

If the current ownership/authentication model cannot safely support live publishing, implement and test mock mode, explain the missing security prerequisite, and keep live actions disabled.

I. Tests

Use isolated mock transports and a controllable fake clock. Mock mode must be unable to contact external publishing endpoints.

Test at least:
- Missing, invalid, expired, and insufficient-permission credentials.
- Unsupported account type and disconnected destination.
- 429 with Retry-After, bounded 5xx retries, and timeouts.
- Ambiguous submission outcome without automatic duplicate sending.
- Duplicate idempotency key and conflicting payload.
- Two rapid clicks, restart, reload, and SSE reconnect.
- Cancellation before and after submission.
- Pending, blocked, stale, and historical revisions.
- Forged approval and tampered text/image/font/layout.
- Missing audit, warning acknowledgment, and dangling asset.
- Facts changing while queued or while submission is in flight.
- Unsupported media and inaccessible public media.
- Instagram container failure and polling deadline.
- WhatsApp template/free-form validation.
- Webhook verification, invalid signature, duplicate event,
  out-of-order event, and unknown operation.
- Secret redaction and absence of credentials in frontend build.
- Cached-output provenance in publishing records.

Preserve existing tests and run appropriate backend, frontend, migration, lint, type, build, and browser checks.

J. Documentation and completion gate

Document:
- Exact verified endpoints and redacted request/response examples.
- Required configuration and where each backend setting belongs.
- Windows PowerShell and bash setup/run/test commands.
- Meta dashboard prerequisites and verified permissions.
- Token maintenance and webhook/public-media setup.
- How to confirm an operation and interpret every status.
- Limitations and unsupported formats.
- A source-to-feature requirement matrix.

For every verification result, record timestamp, mode, platform,
endpoint, status, and actual outcome.

If credentials or suitable accounts are unavailable:
- Complete and run mock verification.
- Mark authenticated checks NOT_TESTED.
- Provide exact local commands for connection checks.
- Keep live sending/publishing disabled until prerequisites pass.
- Do not fabricate successful integration evidence.

Connection checks must be read-only where possible. A live message/post test requires explicit authorization for the exact recipient/Page/account and content.

The gate passes only when:
- Existing application checks still pass.
- Mock integration tests pass.
- Approval, revision, and artifact policy is enforced server-side.
- Durable operations recover without duplicate external actions.
- Secrets stay backend-only.
- Reports distinguish verified, mock-tested, and untested behavior.
- Live capability is enabled only for independently verified platforms.

Finish with a concise report of changed files, verified behavior,
test results, configuration steps, remaining limitations, and
authenticated checks still NOT_TESTED.