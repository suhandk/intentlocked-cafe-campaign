"""Guardian-compatible suggestions for typed factual forms, never a live fallback.

R2 must still return and validate its complete result. These are input constraints;
no provider response is replaced. Native review of Kannada lexicons remains pending.
"""

from copy import deepcopy

from backend.inference_client import success_wire_schema
from backend.schemas import CaseForms, SurfaceResult


def surface_wire_schema(campaign):
    """Bind R2's transport to exact fact keys, languages and approved typed grammar.

    All outcomes stay available. The original strict result and domain validation
    still decide whether any proposals can be saved.
    """
    constraints = surface_constraints(campaign.facts, campaign.languages)
    variants = []
    for fact in campaign.facts:
        if fact.canonical is None:
            continue
        languages = {}
        for language in campaign.languages:
            cases = deepcopy(CaseForms.model_json_schema())
            if fact.key in constraints:
                cases["properties"]["nom"]["const"] = constraints[fact.key][language]["nom"]
            elif language == "en":
                cases["properties"]["nom"]["items"]["const"] = fact.canonical.value
            else:
                cases["required"] = ["nom", "dat", "gen", "loc"]
                for case in ("dat", "gen", "loc"):
                    cases["properties"][case] = cases["properties"][case]["anyOf"][0]
            languages[language] = cases
        variants.append(
            {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "const": fact.key},
                    "surface": {
                        "type": "object",
                        "properties": languages,
                        "required": campaign.languages,
                        "additionalProperties": False,
                    },
                },
                "required": ["key", "surface"],
                "additionalProperties": False,
            }
        )
    wire = success_wire_schema(SurfaceResult, "SurfaceSuccess")
    success = wire["properties"]["result"]
    success["properties"]["forms"].update(
        items={"oneOf": variants}, minItems=len(variants), maxItems=len(variants)
    )
    wire["properties"]["result"] = {
        "oneOf": [
            success,
            success_wire_schema(SurfaceResult, "NeedsInput")["properties"]["result"],
            success_wire_schema(SurfaceResult, "RoleFailure")["properties"]["result"],
        ]
    }
    return wire


def surface_constraints(facts, languages):
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
    day_index = {d: i for i, d in enumerate(["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"])}
    constraints = {}
    for fact in facts:
        value = fact.canonical
        if value is None or value.kind == "text":
            continue
        forms = {}
        for language in languages:
            if value.kind == "percent_off":
                role = {"en": "off", "kn": "ರಿಯಾಯಿತಿ", "kn-Latn": "riyayiti"}[language]
                text = f"{value.value:g}% {role}"
            elif value.kind == "amount_off":
                text = f"INR {value.amount:g} off"
            elif value.kind == "buy_get":
                text = f"Buy {value.buy}, get {value.get}"
            elif value.kind == "dates":
                text = value.start + " to " + value.end
            elif value.kind == "days":
                text = " / ".join(weekdays[language][day_index[d]] for d in value.weekdays)
            elif value.kind == "eligibility":
                if value.scope == "custom":
                    text = value.description
                else:
                    text = {
                        "en": {"all": "Open to all", "students": "Students only"},
                        "kn": {"all": "ಎಲ್ಲರಿಗೂ", "students": "ವಿದ್ಯಾರ್ಥಿಗಳಿಗೆ ಮಾತ್ರ"},
                        "kn-Latn": {"all": "ellarigu", "students": "students maatra"},
                    }[language][value.scope]
            elif value.kind == "id_rule":
                text = "ID required" if value.required else "No ID required"
            elif value.kind == "time_window":
                text = value.start + " to " + value.end
            elif value.kind == "minimum_purchase":
                text = f"Minimum purchase INR {value.amount:g}"
            elif value.kind == "dine_in_rule":
                text = {
                    "dine_in_only": "Dine-in only",
                    "takeaway_only": "Takeaway only",
                    "both": "Dine-in and takeaway",
                }[value.scope]
            else:
                text = (
                    "Can combine with other offers"
                    if value.allowed
                    else "Cannot combine with other offers"
                )
            forms[language] = {"nom": [text]}
        constraints[fact.key] = forms
    return constraints
