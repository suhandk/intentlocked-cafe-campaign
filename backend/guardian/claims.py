"""Typed lexical observations; numbers never enter a global value allowlist."""

import re
import unicodedata
from dataclasses import dataclass

from backend.guardian import lexicon_en as en
from backend.guardian import lexicon_kn as kn
from backend.guardian.normalize import normalize

NUMBER_WORDS = {**en.NUMBERS, **kn.NUMBERS}
NUMBER_PATTERN = re.compile(
    r"\d+(?:[.,]\d+)?(?:\s*[/⁄]\s*\d+)?|"
    + "|".join(re.escape(w) for w in sorted(NUMBER_WORDS, key=len, reverse=True))
)
UNITS = ["%", "percent", "per cent", "percentage", "ಶೇಕಡಾ", "ಶೇಕಡ", "shekada", "pratishata"]
CURRENCIES = ["₹", "$", "€", "£", "rs", "inr", "usd", "rupees", "ರೂ", "ರೂಪಾಯಿ"]


def word(char: str) -> bool:
    return char.isalnum() or unicodedata.category(char).startswith("M") or char == "_"


def matches(text: str, phrases):
    """Unicode-safe boundaries including Kannada combining marks."""
    expression = "|".join(
        re.escape(normalize(p).text) for p in sorted(phrases, key=len, reverse=True)
    )
    if not expression:
        return
    for match in re.finditer(expression, text):
        a, b = match.span()
        if (a == 0 or not word(text[a - 1]) or not word(text[a])) and (
            b == len(text) or not word(text[b]) or not word(text[b - 1])
        ):
            yield a, b


@dataclass(frozen=True)
class Number:
    start: int
    end: int
    value: float


def numbers(text: str) -> list[Number]:
    result = []
    for match in NUMBER_PATTERN.finditer(text):
        a, b = match.span()
        token = match.group()
        if token in NUMBER_WORDS:
            if (a and word(text[a - 1])) or (b < len(text) and word(text[b])):
                continue
            value = NUMBER_WORDS[token]
        elif "/" in token or "⁄" in token:
            numerator, denominator = re.split("[/⁄]", token)
            value = float(numerator) / float(denominator) if float(denominator) else float("inf")
        else:
            value = float(token.replace(",", "."))
        result.append(Number(a, b, value))
    return result


def surface_numeric_valid(fact, form: str) -> bool:
    """Validate value AND unit AND role within this exact authoritative surface.

    Non-ISO date surfaces are conservatively rejected until a reviewed date grammar
    exists. Names may contain digits, but cannot thereby authorize an offer claim.
    """
    text = normalize(form).text
    observed = numbers(text)
    values = [n.value for n in observed]
    value = fact.canonical
    percent = list(matches(text, UNITS))
    money = list(matches(text, CURRENCIES))
    if value.kind == "percent_off":
        discount = list(matches(text, ["off", "discount", "ರಿಯಾಯಿತಿ", "riyayithi", "riyayiti"]))
        remainder = list(text)
        for a, b in [(n.start, n.end) for n in observed] + percent + discount:
            remainder[a:b] = " " * (b - a)
        return (
            values == [value.value]
            and len(percent) == 1
            and not money
            and bool(discount)
            and not "".join(remainder).strip()
        )
    if value.kind in {"amount_off", "minimum_purchase"}:
        role = ["off", "ರಿಯಾಯಿತಿ"] if value.kind == "amount_off" else ["minimum purchase"]
        role_spans = list(matches(text, role))
        remainder = list(text)
        for a, b in [(n.start, n.end) for n in observed] + money + role_spans:
            remainder[a:b] = " " * (b - a)
        return (
            values == [value.amount]
            and len(money) == 1
            and not percent
            and bool(list(matches(text, ["₹", "rs", "inr", "ರೂ", "ರೂಪಾಯಿ", "rupees"])))
            and len(role_spans) == 1
            and not "".join(remainder).strip()
        )
    if value.kind == "buy_get":
        return (
            values == [value.buy, value.get]
            and not percent
            and not money
            and bool(re.fullmatch(r"buy \d+,? get \d+(?: free)?", text))
        )
    if value.kind == "dates":
        return text in {
            value.start + " – " + value.end,
            value.start + " to " + value.end,
            value.start if value.start == value.end else "",
        }
    if value.kind == "time_window":
        return text in {value.start + " – " + value.end, value.start + " to " + value.end}
    if value.kind == "text":
        return not percent and not money
    if value.kind == "days":
        weekdays = {
            "MON": ["monday", "ಸೋಮವಾರ", "somavara"],
            "TUE": ["tuesday", "ಮಂಗಳವಾರ", "mangalavara"],
            "WED": ["wednesday", "ಬುಧವಾರ", "budhavara"],
            "THU": ["thursday", "ಗುರುವಾರ", "guruvara"],
            "FRI": ["friday", "ಶುಕ್ರವಾರ", "shukravara"],
            "SAT": ["saturday", "ಶನಿವಾರ", "shanivara"],
            "SUN": ["sunday", "ಭಾನುವಾರ", "bhanuvara"],
        }
        parts = re.split(r"\s*(?:/|–|,|\band\b)\s*", text)
        return len(parts) == len(value.weekdays) and all(
            p in weekdays[d] for p, d in zip(parts, value.weekdays, strict=True)
        )
    if value.kind == "eligibility":
        allowed = {
            "all": ["open to all", "everyone", "ಎಲ್ಲರಿಗೂ", "ellarigu"],
            "students": ["students only", "only students", "ವಿದ್ಯಾರ್ಥಿಗಳಿಗೆ ಮಾತ್ರ", "students maatra"],
            "custom": [normalize(value.description).text],
        }
        return text in allowed[value.scope]
    if value.kind == "id_rule":
        return text in (
            ["id required", "ಐಡಿ ಬೇಕು", "id beku"]
            if value.required
            else ["no id required", "no id needed", "ಐಡಿ ಬೇಡ", "id beda"]
        )
    if value.kind == "dine_in_rule":
        return (
            text
            == {
                "dine_in_only": "dine-in only",
                "takeaway_only": "takeaway only",
                "both": "dine-in and takeaway",
            }[value.scope]
        )
    # All other members of the validated canonical union returned above.
    return text == (
        "can combine with other offers" if value.allowed else "cannot combine with other offers"
    )
