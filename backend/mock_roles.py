"""Offline role fixtures with conservative parameter substitution. Never live AI output."""

import re


def evidence(text, match):
    return {"start": match.start(), "end": match.end(), "quote": match.group()}


def intent_fixture(data):
    text, facts = data["transcript"], []

    def add(key, canonical, match):
        facts.append({"key": key, "canonical": canonical, "evidence": evidence(text, match)})

    name = re.search(r"(?:caf[eé] name:|caf[eé] (?:named|called))\s*([^.;\n]+)", text, re.I)
    if name:
        # Evidence may include the label; the canonical value is exactly its name portion.
        add("CAFE", {"kind": "text", "value": name[1].strip()}, name)
    location = re.search(r"Bengaluru|ಬೆಂಗಳೂರು", text, re.I)
    if location:
        add("LOCATION", {"kind": "text", "value": location.group()}, location)
    product = re.search(r"\bcoffee\b|ಕಾಫಿ", text, re.I)
    if product:
        add("PRODUCT", {"kind": "text", "value": product.group()}, product)
    offer = re.search(r"(\d+(?:\.\d+)?|fifteen|fifty)\s*(?:%|percent)", text, re.I)
    if offer:
        value = {"fifteen": 15, "fifty": 50}.get(offer[1].lower())
        value = float(offer[1]) if value is None else value
        if 0 < value <= 100:
            add("OFFER", {"kind": "percent_off", "value": value, "unit": "percent"}, offer)
    eligibility = re.search(r"open to all|everyone|ಎಲ್ಲರಿಗೂ|ellarigu", text, re.I)
    restricted = re.search(
        r"students only|only students|ವಿದ್ಯಾರ್ಥಿಗಳಿಗೆ ಮಾತ್ರ|students maatra", text, re.I
    )
    if eligibility and not restricted:
        add("ELIGIBILITY", {"kind": "eligibility", "scope": "all", "description": ""}, eligibility)
    elif restricted and not eligibility:
        add(
            "ELIGIBILITY",
            {"kind": "eligibility", "scope": "students", "description": ""},
            restricted,
        )
    required = re.search(r"\bID required\b", text, re.I)
    not_required = re.search(r"\bno ID needed\b", text, re.I)
    if required and not not_required:
        add("ID_RULE", {"kind": "id_rule", "required": True}, required)
    elif not_required and not required:
        add("ID_RULE", {"kind": "id_rule", "required": False}, not_required)
    dates = re.search(
        r"this weekend|coming weekend|ಈ ವಾರಾಂತ್ಯ|ee weekend|today|tomorrow|"
        r"\d{4}-\d{2}-\d{2}(?:\s+(?:to|through)\s+\d{4}-\d{2}-\d{2})?",
        text,
        re.I,
    )
    return {
        "result": {
            "status": "success",
            "facts": facts,
            "date_proposal": {"phrase": dates.group(), "evidence": evidence(text, dates)}
            if dates
            else None,
            "target_audiences": ["students"] if re.search(r"students?|ವಿದ್ಯಾರ್ಥಿ", text, re.I) else [],
            "clarification_questions": ["Supply the café name explicitly."] if not name else [],
            "warnings": [],
        }
    }


def surface_fixture(data):
    forms = []
    weekdays = {
        "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
        "kn": ["ಸೋಮವಾರ", "ಮಂಗಳವಾರ", "ಬುಧವಾರ", "ಗುರುವಾರ", "ಶುಕ್ರವಾರ", "ಶನಿವಾರ", "ಭಾನುವಾರ"],
        "kn-Latn": [
            "Somavara",
            "Mangalavara",
            "Budhavara",
            "Guruvara",
            "Shukravara",
            "Shanivara",
            "Bhanuvara",
        ],
    }
    for fact in data["facts"]:
        value = fact["canonical"]
        if value is None:
            continue
        surfaces = {}
        for lang in data["languages"]:
            kind = value["kind"]
            if kind == "text":
                word = value["value"]
                localized = {"coffee": "ಕಾಫಿ", "bengaluru": "ಬೆಂಗಳೂರು", "namma cafe": "ನಮ್ಮ ಕೆಫೆ"}
                word = localized.get(word.lower(), word) if lang == "kn" else word
            elif kind == "percent_off":
                word = f"{value['value']:g}%" + (" ರಿಯಾಯಿತಿ" if lang == "kn" else " off")
            elif kind == "amount_off":
                word = f"INR {value['amount']:g} off"
            elif kind == "buy_get":
                word = f"Buy {value['buy']}, get {value['get']}"
            elif kind == "dates":
                word = value["start"] + " – " + value["end"]
            elif kind == "days":
                word = " / ".join(
                    weekdays[lang][["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"].index(d)]
                    for d in value["weekdays"]
                )
            elif kind == "eligibility":
                word = (
                    {"all": "ಎಲ್ಲರಿಗೂ", "students": "ವಿದ್ಯಾರ್ಥಿಗಳಿಗೆ ಮಾತ್ರ"}
                    if lang == "kn"
                    else {"all": "Open to all", "students": "Students only"}
                ).get(value["scope"], value["description"])
            elif kind == "id_rule":
                word = "ID required" if value["required"] else "No ID required"
            elif kind == "time_window":
                word = value["start"] + " – " + value["end"]
            elif kind == "dine_in_rule":
                word = {
                    "dine_in_only": "Dine-in only",
                    "takeaway_only": "Takeaway only",
                    "both": "Dine-in and takeaway",
                }[value["scope"]]
            elif kind == "minimum_purchase":
                word = f"Minimum purchase INR {value['amount']:g}"
            elif kind == "combine_rule":
                word = (
                    "Can combine with other offers"
                    if value["allowed"]
                    else "Cannot combine with other offers"
                )
            cases = {"nom": [word]}
            if kind == "text" and lang != "en":
                special = {
                    "ಕಾಫಿ": ["ಕಾಫಿಗೆ", "ಕಾಫಿಯ", "ಕಾಫಿಯಲ್ಲಿ"],
                    "ಬೆಂಗಳೂರು": ["ಬೆಂಗಳೂರಿಗೆ", "ಬೆಂಗಳೂರಿನ", "ಬೆಂಗಳೂರಿನಲ್ಲಿ"],
                    "ನಮ್ಮ ಕೆಫೆ": ["ನಮ್ಮ ಕೆಫೆಗೆ", "ನಮ್ಮ ಕೆಫೆಯ", "ನಮ್ಮ ಕೆಫೆಯಲ್ಲಿ"],
                }
                values = special.get(
                    word,
                    [
                        word + suffix
                        for suffix in (
                            ["ಗೆ", "ಯ", "ಯಲ್ಲಿ"] if lang == "kn" else ["-ge", "-da", "-alli"]
                        )
                    ],
                )
                cases.update(dict(zip(["dat", "gen", "loc"], [[v] for v in values], strict=True)))
            surfaces[lang] = cases
        forms.append({"key": fact["key"], "surface": surfaces})
    return {
        "result": {
            "status": "success",
            "forms": forms,
            "uncertainties": [
                "MOCK forms are local test data. Review all wording; unsupported translations "
                "retain the source language."
            ],
        }
    }
