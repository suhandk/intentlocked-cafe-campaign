"""Deterministic protection boundary. Unknown semantics require B5's blind reader."""

import re
import unicodedata as ud

from backend.guardian import lexicon_en as en
from backend.guardian import lexicon_kn as kn
from backend.guardian.claims import CURRENCIES, UNITS, matches, numbers, surface_numeric_valid, word
from backend.guardian.normalize import normalize
from backend.guardian.policy import CHANNELS, CONDITIONS, CORE_REQUIRED, RULES, VERSION
from backend.guardian.report import CheckRequest, Finding, GuardianReport, RuleResult, summarize
from backend.guardian.slots import SlotError, fields, parse, render
from backend.intent_rules import digest, domain_error
from backend.schemas import Campaign


def check(campaign: Campaign, request: CheckRequest) -> GuardianReport:
    # Validate even direct Python calls using DTOs built with model_construct/copy.
    request = CheckRequest.model_validate(request.model_dump())
    campaign = Campaign.model_validate(campaign.model_dump())
    if request.campaign_id != campaign.id or request.expected_revision != campaign.revision:
        raise domain_error("REVISION_CONFLICT", "Reload the campaign before checking")
    if campaign.status != "locked":
        raise domain_error("FACTS_INCOMPLETE", "Lock facts before Guardian checks")
    if request.language not in campaign.languages or request.channel not in campaign.channels:
        raise domain_error("GUARDIAN_SELECTION", "Select a locked campaign language and channel")
    checks = {r: RuleResult(rule=r) for r in RULES}
    checks["G11"].severity = "WARN"
    checks["G14"] = RuleResult(
        rule="G14",
        applicable=request.mode == "asset",
        completed=False,
        passed=None,
        findings=[
            Finding(
                field="*",
                source="policy",
                message="Blinded Configured provider R7 reader pending B5",
            )
        ],
    )

    def fail(rule, message, field="*", text="", span=None, source="template"):
        checks[rule].passed = False
        checks[rule].findings.append(
            Finding(
                field=field,
                source=source,
                start=span[0] if span else None,
                end=span[1] if span else None,
                quote=text[span[0] : span[1]] if span else "",
                message=message,
            )
        )

    templates = fields(request.template)
    tokens = {}
    for field, text in templates.items():
        try:
            tokens[field] = parse(text)
        except SlotError as exc:
            fail("G13", str(exc), field, text, (exc.start, exc.end))
    rendered = None
    if checks["G13"].passed:
        try:
            rendered = render(campaign, request.template, request.language)
        except SlotError as exc:
            fail("G06", str(exc), exc.field, templates[exc.field], (exc.start, exc.end))
    facts = {f.key: f for f in campaign.facts}

    for field, text in templates.items():
        # Mask tokens at identical offsets, then normalize. No shifting diagnostics.
        chars = list(text)
        for token in tokens.get(field, []):
            chars[token.start : token.end] = " " * (token.end - token.start)
            # Keep a lexical barrier: collapsing blank slots would join surrounding
            # words, turning 'at {{CAFE}} in {{LOCATION}}' into the false claim 'at in'.
            chars[token.start] = "·"
            prefix = normalize(text[: token.start])
            connector = re.search(r"\b(at|in|visit|serving|buy)\s*$", prefix.text)
            if connector and token.key not in (
                {"CAFE", "LOCATION"} if connector[1] in {"at", "in", "visit"} else {"PRODUCT"}
            ):
                fail(
                    "G08",
                    "Connector assigns the slot to an incompatible fact role",
                    field,
                    text,
                    (prefix.original_span(*connector.span())[0], token.end),
                )
            before = normalize(text[: token.start]).text[-1:]
            after = normalize(text[token.end :]).text[:1]
            if (before and word(before)) or (after and word(after)):
                fail(
                    "G06",
                    "Unapproved affix attached to slot; use an approved case form",
                    field,
                    text,
                    (token.start, token.end),
                )
        shadow = normalize("".join(chars))
        value = shadow.text

        def flag(rule, span, message, shadow=shadow, field=field, text=text):
            original = shadow.original_span(*span)
            fail(rule, message, field, text, original)
            if rule in {"G01", "G02", "G03", "G04", "G08", "G09"}:
                fail("G07", "Factual claim outside an authoritative slot", field, text, original)

        for n in numbers(value):
            flag("G01", (n.start, n.end), "Numeric claim lacks amount/unit/fact-role provenance")
        for span in matches(value, UNITS):
            flag("G01", span, "Discount unit outside OFFER provenance")
        # 'may' as modal and 'sat' as a verb are not date claims without date context.
        dates = [d for d in en.DATES + kn.DATES if d not in {"may", "sat", "march"}]
        for span in matches(value, dates):
            flag("G02", span, "Date/weekday must use DATES or DAYS")
        for m in re.finditer(r"\b(?:may|march|sat)\b(?=\s*(?:\d|[,/–-]))", value):
            flag("G02", m.span(), "Date literal outside provenance")
        for span in matches(value, CURRENCIES):
            flag("G03", span, "Currency claim must bind amount and fact role")
        for span in matches(value, en.TIMES + kn.TIMES):
            flag("G04", span, "Time claim outside TIME_WINDOW")
        for m in re.finditer(r"\d{1,2}(?::\d{2}|\s*(?:am|pm)\b)", value):
            flag("G04", m.span(), "Unapproved time")
        for span in matches(value, en.CLAIMS + kn.CLAIMS):
            flag("G08", span, "Unsupported promise, superlative, restriction or instruction")
        for span in matches(value, en.CONDITIONS + kn.CONDITIONS):
            flag("G09", span, "Condition needs its own approved slot")
        for span in matches(value, en.PRODUCTS_LOCATIONS + kn.PRODUCTS_LOCATIONS):
            flag("G08", span, "Product/location literals require their own slots")
        for fact in campaign.facts:
            if fact.canonical is not None:
                for forms in fact.surface.values():
                    for options in forms.model_dump().values():
                        for span in matches(value, options or []):
                            fail(
                                "G07",
                                "Use a slot even for an approved factual literal",
                                field,
                                text,
                                shadow.original_span(*span),
                            )
        # Generic entity constructions catch names outside the small demo lexicon.
        for m in re.finditer(r"\b(?:at|in|visit|serving|buy)\s+([\w\u0c80-\u0cff]+)", value):
            if m[1] not in {"a", "the", "with", "us", "and", "for", "to"}:
                flag("G08", m.span(), "Unproven location/product construction")
        if any(tokens.values()):
            for span in matches(value, en.WRAPPERS + kn.WRAPPERS):
                flag("G08", span, "Wrapper can negate, qualify or reassign a locked fact")
            for match in re.finditer(r"~~|\b(?:was|formerly|no longer)\b", value):
                flag("G08", match.span(), "Wrapper can cancel the displayed fact")
        for match in re.finditer(r"[{}]", value):
            flag("G13", match.span(), "Normalized unresolved template delimiter")
        for m in re.finditer(r"\[[^\]]+\]|<[^>]+>|\b(?:xx|xxx|tbd)\b|\$\{[^}]*\}", value):
            flag("G13", m.span(), "Unresolved placeholder or markup")
        # Camel-case and concatenated hashtags must not hide claims.
        if field.startswith("hashtags."):
            compact = re.sub(r"[^\w%₹]", "", value)
            for phrase in ["free", "best", "guaranteed", "noid", "unlimited", "cake"]:
                if compact.startswith(phrase) or compact.endswith(phrase):
                    flag("G08", (0, len(value)), "Unsupported hashtag claim")

    if rendered:
        for span in rendered.spans:
            fact = facts[span.key]
            text = rendered.fields[span.field]
            if not surface_numeric_valid(fact, span.approved_form):
                fail(
                    "G01",
                    "Approved surface conflicts with canonical amount, unit or fact role",
                    span.field,
                    text,
                    (span.start, span.end),
                    "rendered",
                )
            # Surface approval does not grant arbitrary unrelated claims.
            allowed = CONDITIONS if fact.key in CONDITIONS else set()
            if not allowed:
                claims = en.CLAIMS + kn.CLAIMS
                if fact.canonical.kind == "buy_get":
                    claims = [c for c in claims if c != "free"]
                if list(matches(normalize(span.approved_form).text, claims)):
                    fail(
                        "G08",
                        "Unrelated claim embedded in fact surface",
                        span.field,
                        text,
                        (span.start, span.end),
                        "rendered",
                    )
        if request.displayed is not None:
            for field, displayed in fields(request.displayed).items():
                if displayed != rendered.fields.get(field):
                    fail(
                        "G06",
                        "Displayed surface differs from server rendering",
                        field,
                        displayed,
                        (0, len(displayed)) if displayed else None,
                        "displayed",
                    )
            if fields(request.displayed).keys() != rendered.fields.keys():
                fail("G06", "Displayed fields differ from server rendering")

        for field, text in rendered.fields.items():
            shadow = normalize(text)
            for span in matches(shadow.text, campaign.brand.must_not_say):
                fail(
                    "G10",
                    "Brand forbidden phrase",
                    field,
                    text,
                    shadow.original_span(*span),
                    "rendered",
                )
            if "{{" in text or "}}" in text:
                fail(
                    "G13",
                    "Placeholder remained after fill",
                    field,
                    text,
                    (0, len(text)),
                    "rendered",
                )
        letters = [c for text in rendered.fields.values() for c in text if c.isalpha()]
        kannada = sum("KANNADA" in ud.name(c, "") for c in letters)
        latin = sum("LATIN" in ud.name(c, "") for c in letters)
        if letters and (
            (request.language == "kn" and kannada / len(letters) < 0.5)
            or (request.language != "kn" and latin != len(letters))
        ):
            fail("G11", "Script differs from selected language", source="policy")

    if request.mode == "asset":
        required = CORE_REQUIRED | {k for k in CONDITIONS if facts.get(k) and facts[k].canonical}
        visible = (
            {s.key for s in rendered.spans if s.field in {"headline", "body", "cta"}}
            if rendered
            else set()
        )
        missing = sorted(required - visible)
        policy = CHANNELS[request.channel]
        empty = [f for f in policy["fields"] if not templates[f].strip()]
        if missing or empty:
            fail(
                "G05", f"Missing visible slots {missing}; required fields {empty}", source="policy"
            )
        if rendered:
            visible_text = " ".join(rendered.fields[f] for f in ["headline", "body", "cta"])
            for phrase in campaign.brand.must_say:
                if not list(matches(normalize(visible_text).text, [phrase])):
                    fail("G10", "Required brand wording absent", source="policy")
    else:
        checks["G05"].applicable = False

    measured = rendered.fields if rendered else templates
    limit = CHANNELS[request.channel]["limit"]
    if sum(len(s) for s in measured.values()) > limit:
        checks["G12"].severity = "BLOCK" if request.channel == "poster" else "WARN"
        fail("G12", f"Content exceeds policy length budget {limit}", source="policy")
    elif request.channel == "poster" and request.mode == "asset":
        checks["G12"].completed, checks["G12"].passed = False, None
        checks["G12"].findings.append(
            Finding(
                field="*",
                source="policy",
                message="Pixel overflow measurement pending B4 renderer",
            )
        )

    eligibility = facts.get("ELIGIBILITY")
    audiences = [*campaign.target_audiences, request.audience]
    if eligibility and eligibility.canonical and eligibility.canonical.scope != "all":
        scope = eligibility.canonical.scope
        allowed = {"students", "college students", "ವಿದ್ಯಾರ್ಥಿಗಳು", "vidyarthigalu"}
        if scope == "custom" or any(
            normalize(a).text.strip() not in allowed for a in audiences if a
        ):
            fail("G15", "Audience eligibility is incompatible or unresolved", source="policy")
    elif (not eligibility or not eligibility.canonical) and any(audiences):
        fail("G15", "Audience eligibility has not been resolved", source="policy")

    status, missing_checks, warnings, integrity = summarize(list(checks.values()))
    return GuardianReport(
        campaign_id=campaign.id,
        campaign_revision=campaign.revision,
        mode=request.mode,
        content_hash=digest(
            {
                "template": request.template.model_dump(),
                "displayed": request.displayed.model_dump() if request.displayed else None,
                "rendered": rendered.model_dump() if rendered else None,
            }
        ),
        dependency_hash=digest(
            {
                "facts": [f.model_dump() for f in campaign.facts],
                "brand": campaign.brand.model_dump(),
                "revision": campaign.revision,
                "policy": VERSION,
                "language": request.language,
                "channel": request.channel,
                "audience": audiences,
            }
        ),
        rendered=rendered,
        checks=list(checks.values()),
        status=status,
        missing_checks=missing_checks,
        warning_ids=warnings,
        integrity=integrity,
    )
