import json
import re
import unicodedata
from pathlib import Path

from backend.guardian.claims import surface_numeric_valid
from backend.intent_context import intent_wire_schema
from backend.intent_rules import (
    days_for,
    digest,
    domain_error,
    evidence_valid,
    require_ready,
    resolve_dates,
    today,
    transcript_warnings,
)
from backend.repository import CampaignRepository, approval_stamp, revise_fact
from backend.schemas import (
    Campaign,
    DraftRequest,
    FactSurface,
    IntentRequest,
    IntentResult,
    LockRequest,
    SurfaceRequest,
    SurfaceResult,
    Warning,
)
from backend.surface_policy import surface_constraints, surface_wire_schema

PROMPTS = Path(__file__).parent / "prompts"


def prompt(role: str) -> str:
    return (
        (PROMPTS / "R0.md").read_text(encoding="utf-8")
        + "\n"
        + (PROMPTS / f"{role}.md").read_text(encoding="utf-8")
    )


def validate_forms(campaign: Campaign, proposals: list[FactSurface]):
    expected = {f.key for f in campaign.facts if f.canonical is not None}
    if len({p.key for p in proposals}) != len(proposals) or {p.key for p in proposals} != expected:
        raise domain_error("FORMS_INVALID", "Forms must cover exactly the specified facts")
    facts = {f.key: f for f in campaign.facts}
    for proposal in proposals:
        if set(proposal.surface) != set(campaign.languages):
            raise domain_error("FORMS_INVALID", "Every selected language needs reviewed forms")
        canonical = facts[proposal.key].canonical
        for lang, forms in proposal.surface.items():
            if lang != "en" and proposal.key in {"CAFE", "LOCATION", "PRODUCT"}:
                if not all([forms.dat, forms.gen, forms.loc]):
                    raise domain_error(
                        "FORMS_INVALID", "Kannada/Kanglish nouns need nom/dat/gen/loc forms"
                    )
            for values in forms.model_dump().values():
                for form in values or []:
                    if any(s in form for s in ["{{", "}}", "\n", "\r"]) or any(
                        unicodedata.category(c) == "Cc" for c in form
                    ):
                        raise domain_error(
                            "FORMS_INVALID", "Forms cannot contain placeholders or controls"
                        )
                    if canonical.kind != "text":
                        if not surface_numeric_valid(facts[proposal.key], form):
                            raise domain_error(
                                "FORMS_INVALID",
                                "The displayed factual form must match its value, unit and role",
                            )
    # Semantic equivalence still requires owner review; full Guardian is B2.


def repair_evidence(span, transcript: str):
    if span and span.quote:
        if not evidence_valid(span, transcript):
            locs = [m.start() for m in re.finditer(re.escape(span.quote), transcript, re.I)]
            if len(locs) == 1:
                span.start, span.end = locs[0], locs[0] + len(span.quote)
                span.quote = transcript[span.start : span.end]
            elif not locs:
                clean = span.quote.strip()
                locs = [m.start() for m in re.finditer(re.escape(clean), transcript, re.I)]
                if len(locs) == 1:
                    span.start, span.end = locs[0], locs[0] + len(clean)
                    span.quote = transcript[span.start : span.end]


def validate_intent(value: IntentResult, transcript: str):
    result = value.result
    if result.status != "success":
        return
    keys = [f.key for f in result.facts]
    if len(keys) != len(set(keys)) or set(keys) & {"DATES", "DAYS"}:
        raise domain_error("INVALID_PROPOSAL", "Duplicate or code-derived fact proposal")
    for fact in result.facts:
        if fact.canonical is None:
            raise domain_error("INVALID_PROPOSAL", "Omit unspecified facts from proposals")
        repair_evidence(fact.evidence, transcript)
        if not evidence_valid(fact.evidence, transcript):
            raise domain_error(
                "INVALID_EVIDENCE", "A proposed fact has no matching transcript evidence"
            )
        if (
            fact.canonical is not None
            and fact.canonical.kind == "text"
            and fact.canonical.value.casefold() not in fact.evidence.quote.casefold()
        ):
            raise domain_error("INVALID_EVIDENCE", "Named facts must preserve the owner's spelling")
    proposal = result.date_proposal
    if proposal:
        repair_evidence(proposal.evidence, transcript)
        if (
            not evidence_valid(proposal.evidence, transcript)
            or proposal.phrase.casefold() not in proposal.evidence.quote.casefold()
        ):
            raise domain_error("INVALID_EVIDENCE", "Date phrase must match exact source evidence")


class CampaignService:
    def __init__(self, store, client, settings):
        self.repo = CampaignRepository(store)
        self.client, self.settings = client, settings

    def draft(self, campaign_id: str, request: DraftRequest) -> Campaign:
        if len({f.key for f in request.facts}) != len(request.facts):
            raise domain_error("DUPLICATE_FACT", "Fact keys must be unique")
        if len(set(request.languages)) != len(request.languages) or len(
            set(request.channels)
        ) != len(request.channels):
            raise domain_error("DUPLICATE_SELECTION", "Select each language/channel once")

        def edit(campaign):
            inputs = {f.key: f.canonical for f in request.facts}
            if "DAYS" in inputs:
                dates = inputs.get("DATES")
                if inputs["DAYS"] != (days_for(dates) if dates else None):
                    raise domain_error(
                        "DATE_DAY_CONFLICT", "Weekdays must be derived from the absolute dates"
                    )
            if "DATES" in inputs:
                inputs["DAYS"] = days_for(inputs["DATES"]) if inputs["DATES"] else None
            languages_changed = request.languages != campaign.languages
            transcript_changed = (
                request.transcript is not None and request.transcript != campaign.transcript
            )
            for index, fact in enumerate(campaign.facts):
                canonical = inputs.get(fact.key, fact.canonical)
                changed = canonical != fact.canonical
                if changed or languages_changed or transcript_changed:
                    campaign.facts[index] = revise_fact(
                        fact,
                        canonical=canonical,
                        surface={},
                        source="derived"
                        if fact.key == "DAYS"
                        else "owner"
                        if changed or transcript_changed
                        else fact.source,
                        source_span=None if changed or transcript_changed else fact.source_span,
                        status="proposed" if canonical else "not_specified",
                        canonical_hash=digest(canonical.model_dump() if canonical else None),
                    )
            campaign.languages, campaign.channels = request.languages, request.channels
            campaign.target_audiences, campaign.brand = request.target_audiences, request.brand
            campaign.acknowledged_warning_ids = request.acknowledged_warning_ids
            campaign.agent_questions = []
            if request.transcript is not None:
                campaign.transcript = request.transcript
                campaign.warnings = transcript_warnings(request.transcript)
                campaign.acknowledged_warning_ids = []
            campaign.status = "draft"

        return self.repo.commit(campaign_id, request.expected_revision, edit)

    async def intent(self, campaign_id: str, request: IntentRequest) -> Campaign:
        campaign = self.repo.get(campaign_id)
        self.repo.check(campaign, request.expected_revision)
        reference = today(self.settings.today_override)
        result = (
            await self.client.structured(
                json.dumps(
                    {
                        "transcript": request.transcript,
                        "reference_date": reference.isoformat(),
                        "timezone": "Asia/Kolkata",
                        "languages": campaign.languages,
                        "channels": campaign.channels,
                        # Exact source spans remove model counting errors; validation is unchanged.
                        "evidence_spans": [
                            {"start": m.start(), "end": m.end(), "quote": m.group()}
                            for m in re.finditer(r"[^\n.!?]+(?:[.!?]|$)", request.transcript)
                        ],
                    },
                    ensure_ascii=False,
                ),
                IntentResult,
                self.client.budget(calls=6, seconds=180),
                system_prompt=prompt("R1"),
                max_tokens=4096,
                validate=lambda value: validate_intent(value, request.transcript),
                wire_schema=intent_wire_schema(),
            )
        ).result
        if result.status == "error":
            error = domain_error(
                "INTENT_UNAVAILABLE",
                "The model could not interpret this brief. Edit and retry, or enter facts "
                "manually. Existing facts have not changed.",
            )
            error.body.details = {"reason": result.reason}
            raise error
        inputs, evidence = {}, {}
        questions = (
            result.questions if result.status == "needs_input" else result.clarification_questions
        )
        if result.status == "success":
            for fact in result.facts:
                repair_evidence(fact.evidence, request.transcript)
                if fact.key in inputs or fact.key in {"DAYS", "DATES"} or fact.canonical is None:
                    raise domain_error(
                        "INVALID_PROPOSAL", "R1 returned duplicate, empty or code-derived facts"
                    )
                if not evidence_valid(fact.evidence, request.transcript):
                    raise domain_error(
                        "INVALID_EVIDENCE", "A proposed fact has no matching transcript evidence"
                    )
                if (
                    fact.canonical.kind == "text"
                    and fact.canonical.value.casefold() not in fact.evidence.quote.casefold()
                ):
                    raise domain_error(
                        "INVALID_EVIDENCE", "Named facts must preserve the owner's spelling"
                    )
                if fact.key == "ID_RULE":
                    pattern = (
                        r"(?<!no )\bID (?:is )?required\b|ID ಬೇಕು|ಐಡಿ ಬೇಕು"
                        if fact.canonical.required
                        else r"\bno ID (?:is )?(?:needed|required)\b|\bwithout ID\b|ಐಡಿ ಬೇಡ"
                    )
                    if not re.search(pattern, fact.evidence.quote, re.I):
                        questions.append("Please specify any ID requirement in the facts editor.")
                        continue
                if fact.key == "ELIGIBILITY":
                    quote = fact.evidence.quote.casefold()
                    patterns = {
                        "all": r"\b(open to all|everyone|everybody)\b|ಎಲ್ಲರಿಗೂ|ellarigu",
                        "students": (
                            r"students?\s+only|only\s+students?|ವಿದ್ಯಾರ್ಥಿಗಳಿಗೆ ಮಾತ್ರ|students maatra"
                        ),
                    }
                    if fact.canonical.scope in patterns and not re.search(
                        patterns[fact.canonical.scope], quote
                    ):
                        questions.append(
                            "Please confirm targeting versus eligibility in the facts editor."
                        )
                        continue
                inputs[fact.key], evidence[fact.key] = fact.canonical, fact.evidence
            if result.date_proposal:
                proposal = result.date_proposal
                repair_evidence(proposal.evidence, request.transcript)
                if (
                    not evidence_valid(proposal.evidence, request.transcript)
                    or proposal.phrase.casefold() not in proposal.evidence.quote.casefold()
                ):
                    raise domain_error(
                        "INVALID_EVIDENCE", "Date phrase has no matching transcript evidence"
                    )
                dates = resolve_dates(proposal.phrase, reference)
                if dates:
                    inputs["DATES"], inputs["DAYS"] = dates, days_for(dates)
                    evidence["DATES"] = evidence["DAYS"] = proposal.evidence
                else:
                    questions.append("The date phrase is ambiguous. Enter exact start/end dates.")

        def edit(current):
            current.transcript = request.transcript
            current.reference_date, current.demo_clock = (
                reference.isoformat(),
                bool(self.settings.today_override),
            )
            current.facts = [
                revise_fact(
                    fact,
                    canonical=inputs.get(fact.key),
                    surface={},
                    source_span=evidence.get(fact.key),
                    source="derived"
                    if fact.key == "DAYS" and fact.key in inputs
                    else "R1"
                    if fact.key in inputs
                    else "unspecified",
                    status="proposed" if fact.key in inputs else "not_specified",
                    canonical_hash=digest(
                        inputs[fact.key].model_dump() if fact.key in inputs else None
                    ),
                )
                for fact in current.facts
            ]
            current.target_audiences = result.target_audiences if result.status == "success" else []
            current.warnings = transcript_warnings(request.transcript)
            if result.status == "success":
                current.warnings += [
                    Warning(id="r1_" + digest(text)[:12], message=text) for text in result.warnings
                ]
            current.agent_questions = questions
            current.acknowledged_warning_ids = []
            current.status = "draft"

        return self.repo.commit(campaign_id, request.expected_revision, edit)

    async def surfaces(self, campaign_id: str, request: SurfaceRequest) -> Campaign:
        def confirm(campaign):
            require_ready(campaign)
            campaign.status = "canonical_confirmed"

        confirmed = self.repo.commit(campaign_id, request.expected_revision, confirm)
        result = (
            await self.client.structured(
                json.dumps(
                    {
                        "facts": [
                            {
                                "key": f.key,
                                "canonical": f.canonical.model_dump() if f.canonical else None,
                            }
                            for f in confirmed.facts
                        ],
                        "languages": confirmed.languages,
                        "surface_constraints": surface_constraints(
                            confirmed.facts, confirmed.languages
                        ),
                    },
                    ensure_ascii=False,
                ),
                SurfaceResult,
                self.client.budget(calls=6, seconds=180),
                system_prompt=prompt("R2"),
                max_tokens=8192,
                validate=lambda value: validate_forms(confirmed, value.result.forms)
                if value.result.status == "success"
                else None,
                wire_schema=surface_wire_schema(confirmed),
            )
        ).result
        if result.status != "success":
            error = domain_error(
                "SURFACES_UNAVAILABLE",
                "The wording could not be prepared. Your canonical facts are saved; "
                "review them and retry. Nothing is locked.",
            )
            error.body.details = {
                "reason": result.reason if result.status == "error" else "needs_input",
                "current_revision": self.repo.get(campaign_id).revision,
            }
            raise error
        validate_forms(confirmed, result.forms)
        mapping = {f.key: f.surface for f in result.forms}

        def edit(campaign):
            campaign.facts = [
                revise_fact(f, surface=mapping[f.key]) if f.key in mapping else f
                for f in campaign.facts
            ]
            campaign.warnings = [
                w
                for w in campaign.warnings
                if not w.id.startswith("r2_") and w.id != "native_review"
            ]
            campaign.warnings += [
                Warning(id="r2_" + digest(t)[:12], message=t) for t in result.uncertainties
            ]
            if any(lang != "en" for lang in campaign.languages):
                campaign.warnings.append(
                    Warning(
                        id="native_review",
                        message="Kannada/Kanglish has not been reviewed by a native speaker. "
                        "Review each proposed spelling and case form. Human language review "
                        "remains a separate release gate.",
                    )
                )
            campaign.status = "forms_review"

        return self.repo.commit(campaign_id, confirmed.revision, edit)

    def lock(self, campaign_id: str, request: LockRequest) -> Campaign:
        def edit(campaign):
            if campaign.status != "forms_review":
                raise domain_error(
                    "FORMS_NOT_READY", "Confirm canonical facts and generate forms before locking"
                )
            campaign.acknowledged_warning_ids = request.acknowledged_warning_ids
            require_ready(campaign)
            versions = {f.key: f.version for f in campaign.facts}
            if request.reviewed_fact_versions != versions:
                raise domain_error(
                    "REVISION_CONFLICT",
                    "Reviewed fact versions no longer match the draft",
                    current_revision=campaign.revision,
                )
            validate_forms(campaign, request.forms)
            mapping = {f.key: f.surface for f in request.forms}
            approval_id, stamp = approval_stamp()
            campaign.facts = [
                revise_fact(
                    f,
                    status="locked",
                    surface=mapping[f.key],
                    approved_at=stamp,
                    approval_id=approval_id,
                )
                if f.canonical
                else f
                for f in campaign.facts
            ]
            campaign.fact_hash = digest(
                [
                    {
                        "key": f.key,
                        "canonical": f.canonical.model_dump() if f.canonical else None,
                        "surface": f.surface and {k: v.model_dump() for k, v in f.surface.items()},
                        "version": f.version,
                    }
                    for f in campaign.facts
                ]
            )
            campaign.approved_at, campaign.status = stamp, "locked"

        return self.repo.commit(
            campaign_id,
            request.expected_revision,
            edit,
            lock_key=request.idempotency_key,
            request_hash=digest(request.model_dump()),
        )
