"""Deterministic date/evidence/approval prerequisites, not a semantic Guardian."""

import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone

from backend.errors import ProviderError
from backend.schemas import CORE, Campaign, Clarification, DatesValue, DaysValue, Warning

INDIA = timezone(timedelta(hours=5, minutes=30), "Asia/Kolkata")


def today(override: str | None = None) -> date:
    return date.fromisoformat(override) if override else datetime.now(INDIA).date()


def digest(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def days_for(value: DatesValue) -> DaysValue:
    start, end = date.fromisoformat(value.start), date.fromisoformat(value.end)
    names = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
    days = list(
        dict.fromkeys(
            names[(start + timedelta(days=i)).weekday()] for i in range((end - start).days + 1)
        )
    )
    return DaysValue(weekdays=days)


def resolve_dates(phrase: str, reference: date) -> DatesValue | None:
    value = phrase.casefold().strip()
    if value in {"this weekend", "coming weekend", "ಈ ವಾರಾಂತ್ಯ", "ee weekend"}:
        saturday = reference + timedelta(days=(5 - reference.weekday()) % 7)
        start, end = saturday, saturday + timedelta(days=1)
    elif value in {"today", "ಇಂದು", "ivattu"}:
        start = end = reference
    elif value in {"tomorrow", "ನಾಳೆ", "naale"}:
        start = end = reference + timedelta(days=1)
    else:
        match = re.fullmatch(
            r"(\d{4}-\d{2}-\d{2})(?:\s+(?:to|through)\s+(\d{4}-\d{2}-\d{2}))?", value
        )
        if not match:
            return None
        try:
            start, end = date.fromisoformat(match[1]), date.fromisoformat(match[2] or match[1])
        except ValueError:
            return None
    if end < start or (end - start).days > 366:
        return None
    return DatesValue(start=start.isoformat(), end=end.isoformat(), original_phrase=phrase)


def evidence_valid(span, transcript: str) -> bool:
    return (
        0 <= span.start < span.end <= len(transcript)
        and transcript[span.start : span.end] == span.quote
    )


def prerequisites(campaign: Campaign) -> list[Clarification]:
    facts = {f.key: f.canonical for f in campaign.facts}
    questions = [
        Clarification(
            key=key, question=f"Please supply {key.lower()} before locking.", required=True
        )
        for key in sorted(CORE - {"DAYS"})
        if facts[key] is None
    ]
    if facts["ELIGIBILITY"] is None and any(
        "student" in s.lower() for s in campaign.target_audiences
    ):
        questions.append(
            Clarification(
                key="ELIGIBILITY",
                question="Are students the marketing focus, or is the offer students-only? "
                "Choose open to all or an exact restriction.",
                required=True,
            )
        )
    for key, question in [
        ("ID_RULE", "Is an ID required? Leave unknown unless decided."),
        ("TIME_WINDOW", "Any daily time window?"),
        ("DINE_IN_RULE", "Any dine-in or takeaway restriction?"),
        ("MIN_PURCHASE_RULE", "Any minimum purchase?"),
        ("COMBINE_RULE", "Can this combine with other offers?"),
    ]:
        if facts[key] is None:
            questions.append(Clarification(key=key, question=question, required=False))
    return questions


def transcript_warnings(transcript: str) -> list[Warning]:
    if re.search(r"\b(fifteen|fifty)\b", transcript, re.I):
        return [
            Warning(
                id="number_readback",
                message="Speech can confuse fifteen and fifty. Check the offer amount visually "
                "and acknowledge it before continuing.",
            )
        ]
    return []


def require_ready(campaign: Campaign):
    missing = [q.key for q in prerequisites(campaign) if q.required]
    if missing:
        raise domain_error(
            "FACTS_INCOMPLETE",
            "Complete required facts and eligibility clarification",
            missing=missing,
        )
    pending = [w.id for w in campaign.warnings if w.id not in campaign.acknowledged_warning_ids]
    if pending:
        raise domain_error(
            "REVIEW_REQUIRED", "Acknowledge the visible review warnings", missing=pending
        )


def domain_error(code: str, message: str, **details) -> ProviderError:
    error = ProviderError(code, message)
    error.body.details = details
    return error
