import json

import pytest
from pydantic import ValidationError

from backend.generation_service import GenerationService
from backend.mock import handler
from backend.optimization_models import Expectation
from backend.tests.test_generation import (
    finish,
    inputs,
    mutate_response,
    seed,
    selection,
)
from backend.tests.test_generation import (
    locked as locked_fixture,
)


@pytest.fixture
def locked():
    return locked_fixture.__wrapped__()


async def test_bounded_copy_repair_names_rejected_words_without_business_facts(factory, locked):
    batches = []

    def transport(request):
        _, data = inputs(request)
        if "combinations" not in data:
            return handler(request)
        batches.append(data)
        if len(batches) == 1:

            def corrupt(result):
                for entry in result["entries"]:
                    entry["template"]["cta"] = "Visit us today!"
                    entry["template"]["body"] += " from {{DATES}}"

            return mutate_response(request, corrupt)
        feedback = data["repair_feedback"]
        assert feedback and all(
            {"today", "from"} <= set(v["remove_expressions"])
            for f in feedback
            for v in f["violations"]
            if v["rule"] in {"G02", "G07", "G08"}
        )
        return handler(request)

    client = factory(transport)
    seed(client, locked)
    service = GenerationService(client.store, client)
    plan = await service.strategy(locked.id, locked.revision)
    run = await finish(
        service,
        service.start(locked.id, selection(locked, plan, languages=["en"], channels=["instagram"])),
    )
    assert run.status == "completed" and run.calls_used == 2
    assert all(c.attempts[0].reasons and c.state == "ready" for c in run.cells)
    assert "Namma Cafe" not in json.dumps(batches) and "Bengaluru" not in json.dumps(batches)
    await client.close()


def test_reader_wrong_canonical_discriminator_rejected():
    with pytest.raises(ValidationError):
        Expectation.model_validate(
            {
                "key": "LOCATION",
                "state": "stated",
                "canonical": {"kind": "eligibility", "scope": "all"},
                "evidence": [{"field": "body", "start": 0, "end": 9, "quote": "Bengaluru"}],
            }
        )
