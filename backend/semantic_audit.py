"""R7 sees text only; code binds its extraction to approved facts and render evidence."""

import re
from uuid import uuid4

from backend.guardian.normalize import normalize
from backend.guardian.policy import CORE_REQUIRED
from backend.guardian.report import Finding, summarize
from backend.intent_rules import domain_error
from backend.optimization_models import Audit
from backend.schemas import KEYS


def reader_spans(fields):
    """Blinded exact spans bounded below Evidence.quote's 500-character limit."""
    spans = []
    for field, value in fields.items():
        for line in re.finditer(r"[^\n]+", value):
            start = line.start()
            while start < line.end():
                end = min(start + 400, line.end())
                spans.append(
                    {"field": field, "start": start, "end": end, "quote": value[start:end]}
                )
                if end == line.end():
                    break
                start = end - 80  # overlap keeps facts near a chunk boundary quotable
    return spans


def ground_reader(reader, fields):
    """Repair coordinate mistakes only for a unique exact quote in the same field."""
    if len(reader.expectations) != len(KEYS) or {e.key for e in reader.expectations} != set(KEYS):
        raise domain_error("READER_EVIDENCE", "Cover each of the twelve keys exactly once")
    evidence = []
    for expectation in reader.expectations:
        if expectation.state == "not_stated":
            if expectation.evidence or expectation.canonical is not None:
                raise domain_error("READER_EVIDENCE", "not_stated must have no value or evidence")
        elif not expectation.evidence:
            raise domain_error(
                "READER_EVIDENCE", "Stated/ambiguous expectations need exact quoted evidence"
            )
        evidence.extend(expectation.evidence)
    evidence.extend(p.evidence for p in reader.other_promises)
    for span in evidence:
        if evidence_valid(span, fields):
            continue
        value = fields.get(span.field, "")
        locations = (
            [m.start() for m in re.finditer(f"(?={re.escape(span.quote)})", value)]
            if span.quote
            else []
        )
        if len(locations) != 1:
            raise domain_error(
                "READER_EVIDENCE",
                "Use supplied exact field spans; absent/ambiguous quotes cannot be repaired",
            )
        span.start, span.end = locations[0], locations[0] + len(span.quote)


def equivalent(extracted, fact, language):
    if extracted is None or fact.canonical is None or extracted.kind != fact.canonical.kind:
        return False
    left, right = extracted.model_dump(), fact.canonical.model_dump()
    if extracted.kind == "text":
        forms = fact.surface.get(language)
        approved = (
            [
                fact.canonical.value,
                *[v for values in forms.model_dump().values() for v in values or []],
            ]
            if forms
            else [fact.canonical.value]
        )
        return normalize(extracted.value).text in {normalize(v).text for v in approved}
    if extracted.kind == "dates":
        return (extracted.start, extracted.end, extracted.timezone) == (
            fact.canonical.start,
            fact.canonical.end,
            fact.canonical.timezone,
        )
    if extracted.kind == "days":
        return set(extracted.weekdays) == set(fact.canonical.weekdays)
    if extracted.kind == "eligibility" and extracted.scope != "custom":
        return extracted.scope == fact.canonical.scope
    return left == right


def evidence_valid(evidence, fields):
    value = fields.get(evidence.field, "")
    return (
        0 <= evidence.start < evidence.end <= len(value)
        and value[evidence.start : evidence.end] == evidence.quote
    )


def compare(campaign, report, reader, language, call, artifact_hash=None):
    report = report.model_copy(deep=True)
    findings, warnings = [], []
    fields = report.rendered.fields if report.rendered else {}
    spans = report.rendered.spans if report.rendered else []
    status = "PASS"
    if reader is None or not report.rendered:
        status, findings = "PENDING", ["R7 unavailable or rendered text unavailable"]
    elif len({e.key for e in reader.expectations}) != 12 or {
        e.key for e in reader.expectations
    } != set(KEYS):
        status, findings = "PENDING", ["R7 did not cover the twelve fact keys exactly once"]
    else:
        for expectation in reader.expectations:
            fact = next(f for f in campaign.facts if f.key == expectation.key)
            if expectation.state == "not_stated":
                if expectation.canonical is not None or expectation.evidence:
                    status = "PENDING" if status != "BLOCKED" else status
                    findings.append(f"{fact.key}: malformed not_stated extraction")
                elif fact.canonical is not None:
                    if fact.key in CORE_REQUIRED:
                        status = "BLOCKED"
                        findings.append(f"{fact.key}: specified fact was not communicated")
                    else:
                        warnings.append(f"omitted_{fact.key}")
                continue
            if not expectation.evidence or not all(
                evidence_valid(e, fields) for e in expectation.evidence
            ):
                status = "PENDING" if status != "BLOCKED" else status
                findings.append(f"{fact.key}: extraction has invalid or absent evidence")
                continue
            if expectation.state == "ambiguous":
                if fact.key in CORE_REQUIRED or fact.canonical is not None:
                    status = "BLOCKED"
                    findings.append(f"{fact.key}: customer expectation is ambiguous")
                else:
                    warnings.append(f"ambiguous_{fact.key}")
                continue
            support = any(
                s.key == fact.key and e.field == s.field and e.start <= s.start and e.end >= s.end
                for e in expectation.evidence
                for s in spans
            )
            if not support or not equivalent(expectation.canonical, fact, language):
                status = "BLOCKED"
                findings.append(f"{fact.key}: expectation differs from approved fact/provenance")
        for i, promise in enumerate(reader.other_promises):
            if not evidence_valid(promise.evidence, fields):
                status = "PENDING" if status != "BLOCKED" else status
                findings.append("Other promise lacks valid evidence")
            else:
                warnings.append(f"r7_promise_{i}")
                findings.append("Review other customer promise: " + promise.description)
        warnings += [f"r7_ambiguity_{i}" for i, _ in enumerate(reader.ambiguities)]
    g14 = next(c for c in report.checks if c.rule == "G14")
    g14.completed, g14.passed = (
        status != "PENDING",
        True if status == "PASS" else False if status == "BLOCKED" else None,
    )
    if status == "PASS" and warnings:
        g14.severity, g14.passed = "WARN", False
    g14.findings = [Finding(field="*", source="policy", message=f) for f in findings]
    report.status, report.missing_checks, report.warning_ids, report.integrity = summarize(
        report.checks
    )
    report.warning_ids = sorted(set([*report.warning_ids, *warnings]))
    # A matching semantic extraction never clears another deterministic block.
    if report.status == "BLOCKED":
        status = "BLOCKED"
    elif report.missing_checks:
        status = "PENDING"
    return Audit(
        id=uuid4().hex,
        campaign_id=campaign.id,
        campaign_revision=campaign.revision,
        content_hash=report.content_hash,
        dependency_hash=report.dependency_hash,
        artifact_hash=artifact_hash,
        status=status,
        findings=findings,
        warning_ids=report.warning_ids,
        reader=reader,
        guardian=report,
        provenance=[s.model_dump() for s in spans],
        call=call,
    )
