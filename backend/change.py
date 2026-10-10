"""Code-owned operation classification, diff construction and canonical proposals."""

import json

from backend.delivery_models import Diff
from backend.generation_context import SEGMENTS, TONES, eligible_segments
from backend.intent_rules import days_for, digest, domain_error, evidence_valid, require_ready
from backend.repository import revise_fact
from backend.schemas import CORE, KEYS, FactInput

MUTABLE = {
    "AUDIENCE",
    "TONE",
    "THEME",
    "HOOK",
    "CTA",
    "LANGUAGE_MIX",
    "CHANNELS",
    "LAYOUT_EMPHASIS",
}


def classify(operations):
    targets = [op.target for op in operations]
    if not targets or len(set(targets)) != len(targets):
        return "rejected"
    immutable = [t.startswith("FACT:") and t[5:] in KEYS and t != "FACT:DAYS" for t in targets]
    if any(not locked and t not in MUTABLE for t, locked in zip(targets, immutable, strict=True)):
        return "rejected"
    return "immutable" if all(immutable) else "mixed" if any(immutable) else "mutable"


def describe(value):
    return json.dumps(
        value.model_dump() if hasattr(value, "model_dump") else value,
        ensure_ascii=False,
        sort_keys=True,
    )


def prepare(campaign, request, parsed, items, fingerprint):
    classification = classify(parsed.operations)
    candidate = campaign.model_copy(deep=True)
    changed, diffs = [], []
    if parsed.questions or classification == "rejected":
        return "rejected", candidate, changed, diffs
    known = {i.id for i in items}
    for op in parsed.operations:
        if not evidence_valid(op.evidence, request.text):
            raise domain_error("CHANGE_INVALID", "Operation evidence does not match owner text")
        scopes = op.scope_ids or request.scope_ids
        if not set(scopes) <= known or not set(request.scope_ids) <= known:
            raise domain_error("CHANGE_INVALID", "Unknown or historical scope ID")
        if op.scope_ids and request.scope_ids and not set(op.scope_ids) <= set(request.scope_ids):
            raise domain_error("CHANGE_INVALID", "Parser widened the requested scope")
        if op.target.startswith("FACT:"):
            if op.value is not None or (op.canonical is None and op.target[5:] in CORE):
                raise domain_error("CHANGE_INVALID", "Fact change needs a typed canonical value")
            key = op.target[5:]
            FactInput(key=key, canonical=op.canonical)
            fact = next(f for f in candidate.facts if f.key == key)
            if fact.canonical == op.canonical and (
                op.surface is None or op.surface == fact.surface
            ):
                raise domain_error("CHANGE_INVALID", "Proposal makes no change")
            structural = (
                fact.canonical is not None
                and op.canonical is not None
                and (fact.canonical.kind != op.canonical.kind)
            )
            diffs.append(
                Diff(
                    target=op.target,
                    before=describe(
                        {
                            "canonical": fact.canonical.model_dump() if fact.canonical else None,
                            "surface": {k: v.model_dump() for k, v in fact.surface.items()},
                        }
                    ),
                    after=describe(
                        {
                            "canonical": op.canonical.model_dump() if op.canonical else None,
                            "proposed_surface": {
                                k: v.model_dump() for k, v in (op.surface or {}).items()
                            },
                        }
                    ),
                    affected_ids=[],
                    consequence="regenerate" if structural else "refill",
                )
            )
            surface = (
                {**(fact.surface if fact.canonical == op.canonical else {}), **op.surface}
                if op.surface is not None
                else (fact.surface if fact.canonical == op.canonical else {})
            )
            candidate.facts = [
                revise_fact(
                    f,
                    canonical=op.canonical,
                    surface=surface,
                    canonical_hash=digest(op.canonical.model_dump() if op.canonical else None),
                    status="proposed" if op.canonical else "not_specified",
                    source="owner",
                    source_span=op.evidence,
                    approved_at=None,
                    approval_id=None,
                )
                if f.key == key
                else f
                for f in candidate.facts
            ]
            changed.append(key)
            if key == "DATES":
                candidate.facts = [
                    revise_fact(
                        f,
                        canonical=days_for(op.canonical),
                        surface={},
                        canonical_hash=digest(days_for(op.canonical).model_dump()),
                        status="proposed",
                        source="derived",
                        approved_at=None,
                        approval_id=None,
                    )
                    if f.key == "DAYS"
                    else f
                    for f in candidate.facts
                ]
                changed.append("DAYS")
        else:
            if scopes and op.target in {"THEME", "AUDIENCE", "LANGUAGE_MIX", "CHANNELS"}:
                raise domain_error(
                    "CHANGE_INVALID",
                    "This preference applies to the whole campaign; choose all current items",
                )
            if op.canonical is not None or op.surface is not None:
                raise domain_error("CHANGE_INVALID", "Preferences cannot carry facts or forms")
            value = op.value
            if op.target == "TONE" and value not in TONES:
                raise domain_error("CHANGE_INVALID", "Unsupported tone")
            if op.target == "THEME" and value not in {"minimal", "warm", "celebration"}:
                raise domain_error("CHANGE_INVALID", "Unsupported visual theme")
            if op.target in {"HOOK", "CTA"} and (
                not isinstance(value, str) or not value.strip() or len(value) > 300
            ):
                raise domain_error("CHANGE_INVALID", "Creative edit needs bounded text")
            if op.target == "LAYOUT_EMPHASIS" and value not in {"offer", "balanced"}:
                raise domain_error("CHANGE_INVALID", "Unsupported layout emphasis")
            choices = {
                "AUDIENCE": SEGMENTS,
                "LANGUAGE_MIX": {"en", "kn", "kn-Latn"},
                "CHANNELS": {"instagram", "whatsapp", "facebook", "poster"},
            }
            if op.target in choices and (
                not isinstance(value, list)
                or not value
                or len(set(value)) != len(value)
                or not set(value) <= choices[op.target]
            ):
                raise domain_error("CHANGE_INVALID", "Invalid preference selection")
            if op.target == "AUDIENCE":
                candidate.target_audiences = value
            if op.target == "LANGUAGE_MIX":
                candidate.languages = value
            if op.target == "CHANNELS":
                candidate.channels = value
            if not scopes and op.target in {"TONE", "THEME"}:
                setattr(candidate.brand, op.target.lower(), value)
            affected = [
                i.id for i in items if not scopes or i.id in scopes or i.variant.id in scopes
            ]
            consequence = (
                "copy_review"
                if op.target in {"TONE", "HOOK", "CTA"}
                else ("rerender" if op.target in {"THEME", "LAYOUT_EMPHASIS"} else "regenerate")
            )
            diffs.append(
                Diff(
                    target=op.target,
                    before=describe(
                        {
                            "preference": {
                                "TONE": campaign.brand.tone,
                                "THEME": campaign.brand.theme,
                                "AUDIENCE": campaign.target_audiences,
                                "LANGUAGE_MIX": campaign.languages,
                                "CHANNELS": campaign.channels,
                                "LAYOUT_EMPHASIS": "balanced",
                            }.get(op.target),
                            "copy": {
                                i.id: (
                                    i.variant.template.cta
                                    if op.target == "CTA"
                                    else i.variant.template.headline
                                )
                                for i in items
                                if i.id in affected
                            },
                        }
                    ),
                    after=describe(value),
                    affected_ids=affected,
                    consequence=consequence,
                )
            )
    require_ready(candidate)
    policy_candidate = candidate.model_copy(deep=True)
    for fact in policy_candidate.facts:
        if fact.canonical is not None:
            fact.status = "locked"
    eligible_segments(policy_candidate)  # targeting cannot widen factual eligibility
    for diff in diffs:
        if diff.target.startswith("FACT:"):
            key = diff.target[5:]
            # Policy-only facts count even when the slot is not printed.
            diff.affected_ids = [
                i.id
                for i in items
                if key in i.variant.dependencies.facts
                or key
                in {
                    "ELIGIBILITY",
                    "ID_RULE",
                    "TIME_WINDOW",
                    "DINE_IN_RULE",
                    "MIN_PURCHASE_RULE",
                    "COMBINE_RULE",
                }
                or fingerprint(campaign, i) != fingerprint(candidate, i)
            ]
    return classification, candidate, list(dict.fromkeys(changed)), diffs


def edited_template(item, proposal):
    template = item.variant.template.model_copy(deep=True)
    for op, diff in zip(proposal.operations, proposal.diffs, strict=True):
        if item.id not in diff.affected_ids:
            continue
        if op.target == "HOOK":
            template.headline = op.value
        elif op.target == "CTA":
            template.cta = op.value
        elif op.target == "TONE":
            # Fixed nonfactual expression. Guardian still checks the entire candidate.
            hooks = {
                "warm": "Make room for a shared pause",
                "playful": "Shall we meet?",
                "calm": "Take a moment",
                "direct": "Come along",
                "refined": "A shared pause",
            }
            template.headline = hooks[op.value]
        elif op.target == "LAYOUT_EMPHASIS" and op.value == "offer":
            if "{{OFFER}}" not in template.headline:
                template.headline = "{{OFFER}} · " + template.headline
    return template
