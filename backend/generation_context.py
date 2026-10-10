"""Closed projections prevent fact leakage through brand/strategy/repair text."""

import re

from backend.generation_models import StrategyPlan
from backend.guardian.normalize import normalize
from backend.guardian.policy import CHANNELS, CONDITIONS, CORE_REQUIRED, VERSION
from backend.intent_rules import digest, domain_error

SEGMENTS = {"students", "families", "professionals", "everyone"}
TONES = {"warm", "playful", "calm", "direct", "refined"}
REPAIR_EXPRESSIONS = (
    "today",
    "tomorrow",
    "weekend",
    "from",
    "starting",
    "up to",
    "only",
    "if",
    "without",
)


def repair_expressions(template):
    text = "\n".join(
        normalize(getattr(template, f)).text for f in ("headline", "body", "cta", "alt_text")
    )
    return [word for word in REPAIR_EXPRESSIONS if re.search(r"\b" + word + r"\b", text)]


def dependency_hash(campaign):
    return digest({"campaign": campaign.model_dump(), "policy": VERSION, "prompts": "b3.1"})


def eligible_segments(campaign) -> set[str]:
    eligibility = next(f for f in campaign.facts if f.key == "ELIGIBILITY")
    if eligibility.canonical is None or eligibility.status != "locked":
        raise domain_error("ELIGIBILITY_UNRESOLVED", "Resolve and lock eligibility before strategy")
    scope = eligibility.canonical.scope
    if scope == "custom":
        raise domain_error(
            "ELIGIBILITY_UNRESOLVED", "Custom eligibility needs a reviewed segment policy"
        )
    allowed = {"students"} if scope == "students" else SEGMENTS
    # B2 and B3 both enforce owner targeting, never widen student-only eligibility.
    aliases = {"college students": "students", "ವಿದ್ಯಾರ್ಥಿಗಳು": "students", "vidyarthigalu": "students"}
    for target in campaign.target_audiences:
        value = normalize(target).text.strip()
        if scope == "students" and aliases.get(value, value) not in allowed:
            raise domain_error("ELIGIBILITY_CONFLICT", "Owner targeting conflicts with eligibility")
    return allowed


def slot_inventory(campaign, language):
    # Keys, cases and discriminators only. Never surface strings or canonical values.
    slots = []
    for fact in campaign.facts:
        if fact.status == "locked" and fact.canonical is not None:
            forms = fact.surface.get(language)
            if forms is None:
                raise domain_error("FORMS_INVALID", "Missing approved language forms")
            slots.append(
                {
                    "key": fact.key,
                    "shape": fact.canonical.kind,
                    "cases": [case for case, values in forms.model_dump().items() if values],
                }
            )
    return slots


def strategy_input(campaign):
    social = [c for c in campaign.channels if c != "poster"]
    if not social:
        raise domain_error("GENERATION_SELECTION", "Select a social channel; posters arrive in B4")
    return {
        "eligible_segments": sorted(eligible_segments(campaign)),
        "preferred_segments": [s for s in campaign.target_audiences if s in SEGMENTS],
        "languages": campaign.languages,
        "channels": social,
        "tone": campaign.brand.tone if campaign.brand.tone in TONES else "warm",
        "available_slots": [f.key for f in campaign.facts if f.status == "locked"],
    }


def validate_plan(campaign, plan: StrategyPlan):
    allowed = eligible_segments(campaign)
    if plan.campaign_revision != campaign.revision or plan.dependency_hash != dependency_hash(
        campaign
    ):
        raise domain_error("REVISION_CONFLICT", "Strategy no longer matches the locked campaign")
    if any(a.segment not in allowed for a in plan.audiences):
        raise domain_error("ELIGIBILITY_CONFLICT", "Strategy contains an ineligible segment")


def copy_input(campaign, plan, language, cells, repair_codes=None):
    ids = {c.audience_id for c in cells}
    required = CORE_REQUIRED | {
        f.key for f in campaign.facts if f.canonical and f.key in CONDITIONS
    }
    return {
        "language": language,
        "audiences": [
            {
                "id": a.id,
                "segment": a.segment,
                "motivation": a.motivation,
                "angle": a.angle,
                "tone": a.tone,
            }
            for a in plan.audiences
            if a.id in ids
        ],
        "combinations": [{"audience_id": c.audience_id, "channel": c.channel} for c in cells],
        "slots": slot_inventory(campaign, language),
        "grammar": "{{KEY}} or {{KEY|case}}; cases: nom/dat/gen/loc; no external suffixes",
        "required_visible_slots": sorted(required),
        "message_hierarchy": plan.message_hierarchy,
        "policies": {c.channel: CHANNELS[c.channel] for c in cells},
        "brand_voice": campaign.brand.tone if campaign.brand.tone in TONES else "warm",
        "repair_codes": repair_codes or [],
        "repair_feedback": [
            {
                "audience_id": cell.audience_id,
                "channel": cell.channel,
                "violations": [
                    {
                        "rule": rule.rule,
                        "fields": sorted({f.field for f in rule.findings}),
                        # Closed vocabulary, never rendered findings or business values.
                        "remove_expressions": repair_expressions(cell.variant.template)
                        if rule.rule in {"G02", "G07", "G08"}
                        else [],
                    }
                    for rule in cell.variant.report.checks
                    if rule.passed is False
                ],
            }
            for cell in cells
            if cell.variant and cell.state == "blocked"
        ],
        "code_owned_disclosures": (
            "Code appends missing required visible slots; do not negate them."
        ),
        # No transcript, dates, raw brand text, examples, prior templates, findings or personas.
    }


def complete_disclosures(campaign, template):
    """Append authoritative slot references only; all wording still faces Guardian.

    Never repair malformed syntax, add unspecified conditions, or approve output.
    The model's hook, claims and language remain subject to all existing checks.
    """
    from backend.guardian.slots import SlotError, parse

    try:
        visible = {
            token.key
            for text in (template.headline, template.body, template.cta)
            for token in parse(text)
        }
    except SlotError:
        return template, []
    required = CORE_REQUIRED | {
        fact.key for fact in campaign.facts if fact.canonical is not None and fact.key in CONDITIONS
    }
    missing = sorted(required - visible)
    if not missing or not template.body.strip():
        return template, []
    disclosure = " · ".join("{{" + key + "}}" for key in missing)
    return template.model_copy(update={"body": template.body.rstrip() + "\n" + disclosure}), missing
