"""Strict token parser and deterministic, server-owned surface renderer."""

from dataclasses import dataclass
from typing import Literal

from backend.contracts import StrictModel
from backend.schemas import KEYS, Campaign, Lang, SlotKey, TemplateContent

Case = Literal["nom", "dat", "gen", "loc"]


class SlotError(ValueError):
    def __init__(self, message: str, start: int, end: int, field: str = "*"):
        super().__init__(message)
        self.start, self.end = start, end
        self.field = field


@dataclass(frozen=True)
class Token:
    start: int
    end: int
    key: str
    case: str


class Provenance(StrictModel):
    field: str
    start: int
    end: int
    template_start: int
    template_end: int
    key: SlotKey
    version: int
    language: Lang
    case: Case
    approved_form: str
    approval_id: str


class Rendered(StrictModel):
    fields: dict[str, str]
    spans: list[Provenance]
    slots_used: list[SlotKey]


def parse(text: str) -> list[Token]:
    tokens = []
    i = 0
    while i < len(text):
        if text[i] not in "{}":
            i += 1
            continue
        start = i
        if text[i : i + 2] != "{{":
            raise SlotError("Malformed template delimiter", i, i + 1)
        end = text.find("}}", i + 2)
        if end == -1:
            raise SlotError("Unclosed slot", i, len(text))
        parts = text[i + 2 : end].split("|")
        if len(parts) > 2 or parts[0] not in KEYS:
            raise SlotError("Unknown or malformed slot key", start, end + 2)
        case = parts[1] if len(parts) == 2 else "nom"
        if case not in {"nom", "dat", "gen", "loc"}:
            raise SlotError("Unknown grammatical case", start, end + 2)
        tokens.append(Token(start, end + 2, parts[0], case))
        i = end + 2
    return tokens


def fields(content: TemplateContent) -> dict[str, str]:
    return {
        "headline": content.headline,
        "body": content.body,
        "cta": content.cta,
        **{f"hashtags.{i}": tag for i, tag in enumerate(content.hashtags)},
        "alt_text": content.alt_text,
    }


def lookup(campaign: Campaign, key: str, language: str, case: str) -> tuple[str, object]:
    fact = next((f for f in campaign.facts if f.key == key), None)
    if (
        fact is None
        or fact.status != "locked"
        or fact.canonical is None
        or not fact.approval_id
        or not fact.approved_at
    ):
        raise ValueError("Slot must reference an owner-locked, specified fact")
    forms = fact.surface.get(language)
    values = getattr(forms, case, None)
    if not values:
        raise ValueError("Missing approved language/case form")
    return values[0], fact


def render(campaign: Campaign, content: TemplateContent, language: Lang) -> Rendered:
    output, spans = {}, []
    for field, text in fields(content).items():
        cursor, result = 0, ""
        for token in parse(text):
            result += text[cursor : token.start]
            try:
                form, fact = lookup(campaign, token.key, language, token.case)
            except ValueError as exc:
                raise SlotError(str(exc), token.start, token.end, field) from exc
            spans.append(
                Provenance(
                    field=field,
                    start=len(result),
                    end=len(result) + len(form),
                    template_start=token.start,
                    template_end=token.end,
                    key=token.key,
                    version=fact.version,
                    language=language,
                    case=token.case,
                    approved_form=form,
                    approval_id=fact.approval_id,
                )
            )
            result += form
            cursor = token.end
        output[field] = result + text[cursor:]
    return Rendered(fields=output, spans=spans, slots_used=sorted({s.key for s in spans}))
