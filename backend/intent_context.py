"""R1 transport contract: proposals only; code continues to resolve dates."""

from copy import deepcopy

from backend.schemas import FACT_KINDS, IntentResult


def intent_wire_schema() -> dict:
    document = IntentResult.model_json_schema()
    definitions = document["$defs"]

    def inline(value):
        if isinstance(value, list):
            return [inline(item) for item in value]
        if not isinstance(value, dict):
            return value
        if "$ref" in value:
            return inline(definitions[value["$ref"].split("/")[-1]])
        result = {
            key: inline(item)
            for key, item in value.items()
            if key not in {"$defs", "discriminator"}
        }
        tags = [key for key in ("status", "kind") if key in result.get("properties", {})]
        if tags:
            result["required"] = list(dict.fromkeys([*result.get("required", []), *tags]))
        return result

    canonical = {
        definition["properties"]["kind"]["const"]: inline(definition)
        for definition in definitions.values()
        if "kind" in definition.get("properties", {})
    }
    fact = inline(definitions["ProposedFact"])
    variants = []
    for key, kinds in FACT_KINDS.items():
        if key in {"DATES", "DAYS"}:
            continue
        variant = deepcopy(fact)
        variant["properties"]["key"] = {"type": "string", "const": key}
        variant["properties"]["canonical"] = (
            canonical[kinds[0]] if len(kinds) == 1 else {"oneOf": [canonical[k] for k in kinds]}
        )
        variants.append(variant)
    success = inline(definitions["IntentSuccess"])
    success["properties"]["facts"]["items"] = {"oneOf": variants}
    return {
        "type": "object",
        "properties": {
            "result": {
                "oneOf": [
                    success,
                    inline(definitions["NeedsInput"]),
                    inline(definitions["RoleFailure"]),
                ]
            }
        },
        "required": ["result"],
        "additionalProperties": False,
    }
