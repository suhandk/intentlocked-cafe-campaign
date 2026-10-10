"""Explicit offline simulators, not customer research or native-language validation."""

import re

from backend.schemas import KEYS


def judge_fixture(data):
    x = bool(re.search(r"\d+(?:\.\d+)?%", data["X"].get("headline", "")))
    y = bool(re.search(r"\d+(?:\.\d+)?%", data["Y"].get("headline", "")))
    choice = "tie" if x == y else "X" if x else "Y"
    return {
        "judgments": [
            {
                "persona_id": p["id"],
                "choice": choice,
                "reason": "MOCK heuristic prefers a visible offer in the headline; otherwise tie.",
            }
            for p in data["personas"]
        ]
    }


def critique_fixture(data):
    template = data["template"]
    if "{{OFFER}}" in template["headline"]:
        return {
            "critique": "MOCK: no additional defensible edit in this fixture.",
            "edits": [],
            "no_change": True,
        }
    return {
        "critique": "MOCK: lead with the approved offer slot while keeping disclosures.",
        "edits": [
            {"target": "template.headline", "value": "{{OFFER}} · " + template["headline"]},
        ],
        "no_change": False,
    }


def reader_fixture(data):
    found = {}

    def add(key, value, field, match):
        found[key] = {
            "key": key,
            "state": "stated",
            "canonical": value,
            "evidence": [
                {"field": field, "start": match.start(), "end": match.end(), "quote": match.group()}
            ],
        }

    names = {
        "CAFE": r"Namma Cafe|Namma Café|ನಮ್ಮ ಕಫೆ|ನಮ್ಮ ಕೆಫೆ",
        "LOCATION": r"Bengaluru|ಬೆಂಗಳೂರು",
        "PRODUCT": r"coffee|ಕಾಫಿ|kaafi|kaapi",
    }
    for field, text in data["fields"].items():
        for key, pattern in names.items():
            match = re.search(pattern, text, re.I)
            if match and key not in found:
                add(key, {"kind": "text", "value": match.group()}, field, match)
        match = re.search(r"(\d+(?:\.\d+)?)%[^·\n]*", text)
        if match and "OFFER" not in found:
            add(
                "OFFER",
                {"kind": "percent_off", "value": float(match[1]), "unit": "percent"},
                field,
                match,
            )
        match = re.search(
            r"(\d{4}-\d{2}-\d{2})\s*(?:to|–|-|ರಿಂದ|inda)\s*(\d{4}-\d{2}-\d{2})[^·\n]*", text
        )
        if match and "DATES" not in found:
            add(
                "DATES",
                {
                    "kind": "dates",
                    "start": match[1],
                    "end": match[2],
                    "original_phrase": "customer text",
                    "timezone": "Asia/Kolkata",
                },
                field,
                match,
            )
        match = re.search(
            r"Saturday[^·\n]*Sunday|ಶನಿವಾರ[^·\n]*ಭಾನುವಾರ|Shanivara[^·\n]*Bhanuvara", text, re.I
        )
        if match and "DAYS" not in found:
            add("DAYS", {"kind": "days", "weekdays": ["SAT", "SUN"]}, field, match)
        match = re.search(
            r"Open to all|ಎಲ್ಲರಿಗೂ|ellarigu|Students only|ವಿದ್ಯಾರ್ಥಿಗಳಿಗೆ ಮಾತ್ರ|students maatra", text, re.I
        )
        if match and "ELIGIBILITY" not in found:
            scope = "all" if re.search(r"all|ಎಲ್ಲರಿಗೂ|ellarigu", match.group(), re.I) else "students"
            add(
                "ELIGIBILITY",
                {"kind": "eligibility", "scope": scope, "description": ""},
                field,
                match,
            )
    return {
        "expectations": [
            found.get(key, {"key": key, "state": "not_stated", "canonical": None, "evidence": []})
            for key in KEYS
        ],
        "other_promises": [],
        "ambiguities": [],
        "back_translation": "MOCK bounded fixture extraction; unsupported text is not inferred.",
    }
