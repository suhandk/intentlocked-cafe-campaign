"""Diagnostic reports are evidence, never an approval capability supplied by clients."""

from typing import Literal

from pydantic import Field, model_validator

from backend.contracts import StrictModel
from backend.guardian.policy import RULES, VERSION
from backend.guardian.slots import Rendered
from backend.schemas import Channel, Lang, TemplateContent


class CheckRequest(StrictModel):
    campaign_id: str = Field(min_length=1, max_length=100)
    expected_revision: int = Field(ge=1)
    mode: Literal["fragment", "asset"]
    language: Lang
    channel: Channel
    template: TemplateContent
    audience: str = Field(default="", max_length=200)
    # A supplied displayed copy is checked against an independently rendered copy.
    displayed: TemplateContent | None = None

    @model_validator(mode="after")
    def bounded(self):
        for content in [self.template, self.displayed]:
            if content is not None and (
                len(content.hashtags) > 30
                or sum(
                    len(v)
                    for v in [
                        content.headline,
                        content.body,
                        content.cta,
                        content.alt_text,
                        *content.hashtags,
                    ]
                )
                > 12000
            ):
                raise ValueError("Guardian input exceeds content budget")
        return self


class Finding(StrictModel):
    field: str
    source: Literal["template", "displayed", "rendered", "policy"]
    start: int | None = None
    end: int | None = None
    quote: str = ""
    message: str


class RuleResult(StrictModel):
    rule: str
    applicable: bool = True
    completed: bool = True
    passed: bool | None = True
    severity: Literal["BLOCK", "WARN", "INFO"] = "BLOCK"
    findings: list[Finding] = Field(default_factory=list)


class GuardianReport(StrictModel):
    schema_version: Literal["guardian-report-2.1"] = "guardian-report-2.1"
    policy_version: str = VERSION
    campaign_id: str
    campaign_revision: int
    mode: Literal["fragment", "asset"]
    content_hash: str
    dependency_hash: str
    rendered: Rendered | None
    checks: list[RuleResult]
    status: Literal["PASS", "BLOCKED", "INCOMPLETE"]
    missing_checks: list[str]
    warning_ids: list[str]
    integrity: float | None
    approval_ready: Literal[False] = False
    native_review: Literal["PENDING"] = "PENDING"


def summarize(checks: list[RuleResult]) -> tuple[str, list[str], list[str], float | None]:
    indexed = {c.rule: c for c in checks}
    missing = [
        r
        for r in RULES
        if r not in indexed
        or (indexed[r].applicable and (not indexed[r].completed or indexed[r].passed is None))
    ]
    blocked = any(c.passed is False and c.severity == "BLOCK" for c in checks)
    warnings = [c.rule for c in checks if c.passed is False and c.severity == "WARN"]
    run = [c for c in checks if c.applicable and c.completed and c.passed is not None]
    integrity = (
        None if missing or not run else round(100 * sum(c.passed for c in run) / len(run), 2)
    )
    return (
        "BLOCKED" if blocked else "INCOMPLETE" if missing else "PASS",
        missing,
        warnings,
        integrity,
    )


def require_approval_ready(report: GuardianReport) -> None:
    """B6 must recompute readiness transactionally; B2 reports cannot authorize assets.

    B5 supplies persisted R7 evidence bound to content/dependency hashes, reader/prompt
    versions and successful completion. No client audit/status/pass flag is accepted.
    """
    raise ValueError("Approval unavailable: persisted G14 reader and B6 approval are pending")
