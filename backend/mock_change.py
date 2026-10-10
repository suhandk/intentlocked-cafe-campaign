"""Explicit, bounded R8 fixture parser. Unknown requests are rejected, never guessed."""

import re


def change_fixture(data):
    text = data["text"]
    operations = []
    facts = {f["key"]: f["canonical"] for f in data["facts"]}

    def add(target, match, **values):
        operations.append(
            {
                "target": target,
                "evidence": {"start": match.start(), "end": match.end(), "quote": match.group()},
                "scope_ids": data.get("scope_ids", []),
                **values,
            }
        )

    if re.search(r"best coffee|free cake", text, re.I):
        return {
            "operations": [],
            "questions": ["Unsupported promise cannot be introduced as a preference."],
        }
    surface = re.search(r"(?:English|en) offer form to ['\"]([^'\"]+)['\"]", text, re.I)
    if surface:
        add("FACT:OFFER", surface, canonical=facts["OFFER"], surface={"en": {"nom": [surface[1]]}})
    else:
        match = re.search(r"(\d+(?:\.\d+)?)\s*(?:%|percent)", text, re.I)
        if match:
            add(
                "FACT:OFFER",
                match,
                canonical={"kind": "percent_off", "value": float(match[1]), "unit": "percent"},
            )
    match = re.search(r"BOGO|buy one get one", text, re.I)
    if match:
        add("FACT:OFFER", match, canonical={"kind": "buy_get", "buy": 1, "get": 1})
    match = re.search(r"students?[- ]only", text, re.I)
    if match:
        add(
            "FACT:ELIGIBILITY",
            match,
            canonical={"kind": "eligibility", "scope": "students", "description": ""},
        )
    # Exact demo wording maps to existing closed preferences; never a new factual claim.
    demo = re.search(r"\bfamilies and premium\b", text, re.I)
    if demo:
        add("AUDIENCE", demo, value=["families"])
        add("TONE", demo, value="refined")
    match = re.search(r"(?:tone(?: to)?\s+)(warm|playful|calm|direct|refined)", text, re.I)
    if match:
        add("TONE", match, value=match[1].lower())
    match = re.search(
        r"(?:target|audience(?: to)?)\s+(students|families|professionals|everyone)", text, re.I
    )
    if match:
        add("AUDIENCE", match, value=[match[1].lower()])
    for target, label in [("HOOK", "hook"), ("CTA", "cta")]:
        match = re.search(label + r"(?: to)?\s+['\"]([^'\"]+)['\"]", text, re.I)
        if match:
            add(target, match, value=match[1])
    return {
        "operations": operations,
        "questions": [] if operations else ["Specify a supported exact change."],
    }
