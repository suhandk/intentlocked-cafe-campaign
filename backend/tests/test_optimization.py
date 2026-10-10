import asyncio
import json

import httpx
import pytest

from backend.errors import ProviderError
from backend.generation_service import GenerationService
from backend.mock import handler
from backend.optimization_models import (
    CritiqueResult,
    JudgeResult,
    OptimizeRequest,
    Promise,
    ReaderResult,
)
from backend.optimization_service import OptimizationService, apply_edits
from backend.scoring import acceptance, features, map_votes, score
from backend.semantic_audit import compare
from backend.tests.test_generation import finish, inputs, seed, selection  # noqa: F401
from backend.tests.test_generation import locked as locked_fixture


@pytest.fixture
def locked():
    return locked_fixture.__wrapped__()


async def prepared(client, campaign):
    seed(client, campaign)
    generation = GenerationService(client.store, client)
    plan = await generation.strategy(campaign.id, campaign.revision)
    run = await finish(
        generation,
        generation.start(
            campaign.id,
            selection(
                campaign,
                plan,
                audience_ids=[plan.hero_audience_id],
                languages=["en"],
                channels=["whatsapp"],
            ),
        ),
    )
    return plan, run.cells[0].variant


async def completed(service, run):
    task = service.tasks.get(run.id)
    if task:
        await task
    return service.repo.get(run.id)


def request(campaign, variant, key="optimization-test-key"):
    return OptimizeRequest(
        expected_revision=campaign.revision, variant_ids=[variant.id], idempotency_key=key
    )


def altered(request, change):
    response = handler(request).json()
    function = response["choices"][0]["message"]["tool_calls"][0]["function"]
    data = json.loads(function["arguments"])
    change(data)
    function["arguments"] = json.dumps(data)
    return httpx.Response(200, json=response)


def role(request):
    return inputs(request)[0]["messages"][0]["content"]


async def test_frozen_run_executes_accept_stop_persists_and_cache(factory, locked):
    captured = []

    def transport(req):
        captured.append(inputs(req))
        return handler(req)

    client = factory(transport, demo_fast=True)
    plan, variant = await prepared(client, locked)
    service = OptimizationService(client.store, client)
    initial = service.start(locked.id, request(locked, variant))
    assert service.start(locked.id, request(locked, variant)).id == initial.id
    run = await completed(service, initial)
    assert run.status == "completed", run.stop_reason
    group = run.groups[0]
    assert group.baseline_score.tournament == 50
    assert group.rounds[0].accepted, group.rounds[0].reasons
    assert group.rounds[0].score.complete_judgments == 10
    assert group.rounds[0].score.overall > group.baseline_score.overall
    assert group.rounds[1].reasons == ["NO_CHANGE"]
    assert group.stop_reason == "NO_GAIN"
    assert group.final_audit.status == "PASS"
    assert run.max_rounds == 2 and run.calls_used == 6 and run.mock_calls == 6
    assert run.known_cost_usd == 0 and run.elapsed_ms >= 0
    assert run.personas == plan.personas and group.baseline == variant
    retained = service.art.variant(locked, group.current_id)
    assert retained.parent_id == variant.id and not retained.baseline
    assert retained.template == group.current_template and retained.report.status == "PASS"
    with pytest.raises(ProviderError, match="never rebase"):
        service.start(locked.id, request(locked, retained, "no-rebase-test-key"))
    for payload, data in captured:
        system = payload["messages"][0]["content"]
        if "ROLE: R7" in system:
            assert set(data) == {
                "language",
                "channel",
                "fields",
                "visual_description",
                "evidence_spans",
            }
            assert "canonical" not in json.dumps(data)
            for span in data["evidence_spans"]:
                assert data["fields"][span["field"]][span["start"] : span["end"]] == span["quote"]
        if "ROLE: R5" in system:
            assert "baseline" not in data and "scores" not in data
            assert data["personas"] == [p.model_dump() for p in run.personas]
    # Exact inputs/context/model/prompt reuse; different run ID is not a cache input.
    second = await completed(
        service, service.start(locked.id, request(locked, variant, "another-test-key"))
    )
    assert second.calls_used == 0
    assert second.groups[0].rounds[0].calls[0].provenance == "cache"
    assert service.repo.snapshot(locked.id).unscored_variant_ids == []
    service.repo.db.execute("UPDATE campaigns SET revision=2 WHERE id=?", (locked.id,))
    service.repo.db.rollback()
    await service.close()
    await client.close()


@pytest.mark.parametrize(
    "attack,expected",
    [
        ("missing_core", "BLOCKED"),
        ("ambiguous_core", "BLOCKED"),
        ("ambiguous_unknown", "PASS"),
        ("invented_condition", "BLOCKED"),
        ("duplicate_key", "PENDING"),
        ("invalid_not_stated", "PENDING"),
        ("invalid_promise_evidence", "PENDING"),
    ],
)
async def test_semantic_states_never_invent_a_pass(factory, locked, attack, expected):
    client = factory()
    _, variant = await prepared(client, locked)
    service = OptimizationService(client.store, client)
    audit = await service.audit_report(
        locked, variant.report, "en", "whatsapp", client.budget(calls=3, seconds=90), []
    )
    reader = audit.reader.model_copy(deep=True)
    cafe = next(e for e in reader.expectations if e.key == "CAFE")
    unknown = next(e for e in reader.expectations if e.key == "ID_RULE")
    if attack == "missing_core":
        cafe.state, cafe.canonical, cafe.evidence = "not_stated", None, []
    elif attack == "ambiguous_core":
        cafe.state = "ambiguous"
    elif attack == "ambiguous_unknown":
        unknown.state, unknown.evidence = "ambiguous", cafe.evidence
    elif attack == "invented_condition":
        from backend.schemas import IDRule

        unknown.state, unknown.canonical, unknown.evidence = (
            "stated",
            IDRule(required=False),
            cafe.evidence,
        )
    elif attack == "duplicate_key":
        unknown.key = "CAFE"
    elif attack == "invalid_not_stated":
        unknown.evidence = cafe.evidence
    else:
        reader.other_promises = [
            Promise(
                description="promise",
                evidence={"field": "cta", "start": 0, "end": 4, "quote": "fake"},
            )
        ]
    result = compare(locked, variant.report, reader, "en", audit.call)
    assert result.status == expected
    if attack == "ambiguous_unknown":
        assert result.warning_ids and result.guardian.warning_ids == result.warning_ids
        assert result.guardian.integrity < 100
    if expected == "PENDING":
        assert "G14" in result.guardian.missing_checks
    await client.close()


@pytest.mark.parametrize(
    "contrast,area,contrast_score,area_score",
    [
        (4.5, 0.06, 100, 100),
        (3, 0.04, 60, 60),
        (2.9, 0.01, 20, 20),
        (5, None, 100, None),
    ],
)
async def test_measured_poster_feature_thresholds_and_unavailable(
    factory, locked, contrast, area, contrast_score, area_score
):
    from types import SimpleNamespace

    client = factory()
    _, variant = await prepared(client, locked)
    poster = SimpleNamespace(validation=SimpleNamespace(contrast=contrast, offer_area_ratio=area))
    measured = features(variant.report, "poster", poster)
    values = {f.name: f for f in measured}
    assert values["text_contrast"].value == contrast_score
    assert values["offer_area"].applicable and values["offer_area"].value == area_score
    if area is None:
        assert score(measured, baseline=True).overall is None
    await client.close()


@pytest.mark.parametrize(
    "choices,expected,disagreement",
    [
        (["Y"] * 5 + ["X"] * 5, 100, 0),
        (["tie"] * 10, 50, 0),
        (["X"] * 10, 50, 5),
        (["X"] * 5 + ["Y"] * 5, 0, 0),
        (["Y", "X", "tie", "Y", "X", "X", "Y", "tie", "Y", "X"], 50, 2),
    ],
)
async def test_swapped_mapping_ties_identical_and_disagreement(
    factory, locked, choices, expected, disagreement
):
    client = factory()
    plan, variant = await prepared(client, locked)
    votes = []
    for offset, order in [(0, "AB"), (5, "BA")]:
        result = JudgeResult(
            judgments=[
                {"persona_id": p.id, "choice": choices[offset + i], "reason": "test"}
                for i, p in enumerate(plan.personas)
            ]
        )
        votes += map_votes(result, plan.personas, order, "baseline", "candidate")
    computed = score(features(variant.report, variant.channel), votes)
    assert computed.tournament == expected
    assert computed.order_disagreement == disagreement
    assert computed.sensitivity_band is not None
    if expected in (0, 100):
        assert computed.sensitivity_band == [expected, expected]
    await client.close()


@pytest.mark.parametrize("attack", ["missing", "duplicate", "unknown"])
async def test_missing_invalid_judgments_are_unscored(factory, locked, attack):
    client = factory()
    plan, variant = await prepared(client, locked)
    judgments = [{"persona_id": p.id, "choice": "Y", "reason": "test"} for p in plan.personas]
    if attack == "missing":
        judgments.pop()
    if attack == "duplicate":
        judgments[-1]["persona_id"] = judgments[0]["persona_id"]
    if attack == "unknown":
        judgments[-1]["persona_id"] = "invented"
    result = JudgeResult(judgments=judgments)
    votes = map_votes(result, plan.personas, "AB", "base", "candidate")
    votes += map_votes(None, plan.personas, "BA", "base", "candidate", "TIMEOUT")
    computed = score(features(variant.report, variant.channel), votes)
    assert computed.overall is None and computed.tournament is None
    assert computed.complete_judgments < 10
    assert all(v.winner_id is None for v in votes if v.outcome == "missing")
    await client.close()


@pytest.mark.parametrize(
    "attack", ["immutable", "guardian", "tie", "invalid_judge", "r7_mismatch", "r7_unavailable"]
)
async def test_bad_candidates_or_incomplete_evidence_stop_and_retain(factory, locked, attack):
    seen = []

    def transport(req):
        system = role(req)
        seen.append(system)
        if "ROLE: R6" in system and attack == "immutable":
            return altered(
                req, lambda d: d["edits"].__setitem__(0, {"target": "facts.OFFER", "value": "50"})
            )
        if "ROLE: R6" in system and attack == "guardian":
            return altered(
                req, lambda d: d["edits"][0].__setitem__("value", "{{OFFER}} · free cake")
            )
        if "ROLE: R5" in system and attack == "tie":
            return altered(req, lambda d: [j.__setitem__("choice", "tie") for j in d["judgments"]])
        if "ROLE: R5" in system and attack == "invalid_judge":
            return altered(req, lambda d: [j.__setitem__("choice", "win") for j in d["judgments"]])
        if "ROLE: R7" in system and attack == "r7_unavailable":
            raise httpx.ReadTimeout("mock")
        if "ROLE: R7" in system and attack == "r7_mismatch":
            return altered(
                req,
                lambda d: next(e for e in d["expectations"] if e["key"] == "OFFER")[
                    "canonical"
                ].__setitem__("value", 25),
            )
        return handler(req)

    client = factory(transport)
    _, variant = await prepared(client, locked)
    service = OptimizationService(client.store, client)
    run = await completed(service, service.start(locked.id, request(locked, variant)))
    group = run.groups[0]
    assert group.current_id == variant.id
    assert not any(r.accepted for r in group.rounds)
    assert len(group.rounds) <= 1
    if attack in {"guardian", "immutable"}:
        assert not any("ROLE: R5" in r for r in seen)
    if attack == "r7_unavailable":
        assert group.final_audit.status == "PENDING"
        assert run.calls_used == 3  # exact bounded transport retries, no retry-until-pass
    if attack == "r7_mismatch":
        assert group.final_audit.status == "BLOCKED"
    await client.close()


async def test_retry_accounting_and_guardian_cannot_be_averaged_away(factory, locked):
    failure = True

    def transport(req):
        nonlocal failure
        if "ROLE: R5" in role(req) and failure:
            failure = False
            return httpx.Response(429, headers={"Retry-After": "2"})
        return handler(req)

    client = factory(transport)
    _, variant = await prepared(client, locked)
    service = OptimizationService(client.store, client)
    run = await completed(service, service.start(locked.id, request(locked, variant)))
    assert run.calls_used == 7
    group = run.groups[0]
    candidate = group.rounds[0].score
    report = group.rounds[0].guardian.model_copy(update={"status": "BLOCKED"})
    reasons = acceptance(group.baseline_score, candidate, report, group.final_audit)
    assert "GUARDIAN_BLOCK" in reasons
    assert "NO_STRICT_OVERALL_GAIN" not in reasons
    await client.close()


async def test_stale_async_result_discarded_and_budget_exhausted(factory, locked):
    waiting, release = asyncio.Event(), asyncio.Event()

    async def transport(req):
        if "ROLE: R6" in role(req):
            waiting.set()
            await release.wait()
        return handler(req)

    client = factory(transport)
    _, variant = await prepared(client, locked)
    service = OptimizationService(client.store, client)
    run = service.start(locked.id, request(locked, variant))
    await waiting.wait()
    campaign = service.repo.generation.campaigns.get(locked.id)
    campaign.revision += 1
    with service.repo.db:
        service.repo.db.execute(
            "UPDATE campaigns SET revision=?,payload=? WHERE id=?",
            (campaign.revision, campaign.model_dump_json(), campaign.id),
        )
    release.set()
    final = await completed(service, run)
    assert final.status == "stale"
    assert final.groups[0].current_id == variant.id
    assert not any(r.accepted for r in final.groups[0].rounds)
    await client.close()


async def test_r7_evidence_and_warning_handling(factory, locked):
    client = factory()
    _, variant = await prepared(client, locked)
    service = OptimizationService(client.store, client)
    budget = client.budget(calls=3, seconds=90)
    audit = await service.audit_report(locked, variant.report, "en", "whatsapp", budget, [])
    reader = audit.reader.model_copy(deep=True)
    reader.other_promises = [
        Promise.model_validate(
            {
                "description": "possible promise",
                "evidence": {"field": "cta", "start": 0, "end": 4, "quote": "Come"},
            }
        )
    ]
    reader = ReaderResult.model_validate_json(reader.model_dump_json())
    warned = compare(locked, variant.report, reader, "en", audit.call)
    assert "r7_promise_0" in warned.warning_ids and not warned.approval_ready
    reader.expectations[0].evidence[0].quote = "forged"
    pending = compare(locked, variant.report, reader, "en", audit.call)
    assert pending.status == "PENDING" and "G14" in pending.guardian.missing_checks
    await client.close()


def test_edit_limits_and_authorization():
    from backend.schemas import TemplateContent

    template = TemplateContent(
        headline="Hook", body="{{OFFER}}", cta="Come", hashtags=[], alt_text=""
    )
    with pytest.raises(ProviderError):
        apply_edits(
            template,
            CritiqueResult(
                critique="try", no_change=False, edits=[{"target": "facts.OFFER", "value": "25"}]
            ),
        )
    with pytest.raises(ProviderError):
        apply_edits(
            template,
            CritiqueResult(
                critique="try",
                no_change=False,
                edits=[{"target": "template.body", "value": "no slots"}],
            ),
        )


@pytest.mark.parametrize(
    "headline,value",
    [
        ("h" * 73 + "{{OFFER}}", 100),
        ("h" * 74 + "{{OFFER}}", 0),
        ("Hook\n{{OFFER}}", 0),
    ],
)
async def test_offer_first_line_and_exact_eighty_character_boundary(
    factory, locked, headline, value
):
    client = factory()
    _, variant = await prepared(client, locked)
    service = OptimizationService(client.store, client)
    template = variant.template.model_copy(update={"headline": headline})
    report = service.report(locked, variant, template)
    measured = features(report, variant.channel)
    assert next(f for f in measured if f.name == "offer_first_line").value == value
    await client.close()


@pytest.mark.parametrize("fast,limit", [(True, 2), (False, 3)])
async def test_exact_round_cap_and_fixed_baseline_chart(factory, locked, fast, limit):
    judges = 0
    critiques = 0

    def transport(req):
        nonlocal judges, critiques
        system = role(req)
        if "ROLE: R6" in system:
            critiques += 1
            if critiques > 1:
                return altered(
                    req,
                    lambda d: d.update(
                        critique="MOCK: refine CTA",
                        no_change=False,
                        edits=[{"target": "template.cta", "value": f"Come along{'!' * critiques}"}],
                    ),
                )
        if "ROLE: R5" in system:
            judges += 1
            if judges <= 2:
                return altered(req, lambda d: d["judgments"][0].__setitem__("choice", "tie"))
        return handler(req)

    client = factory(transport, demo_fast=fast)
    _, variant = await prepared(client, locked)
    service = OptimizationService(client.store, client)
    run = await completed(service, service.start(locked.id, request(locked, variant)))
    group = run.groups[0]
    assert len(group.rounds) == limit
    assert group.rounds[0].accepted and group.rounds[1].accepted
    assert group.baseline_score.tournament == 50
    assert group.baseline_score.overall == 65
    assert group.current_score.overall == 100
    assert group.stop_reason == ("ROUND_LIMIT" if fast else "NO_GAIN")
    # Every judge sees the original, even after a candidate was accepted.
    assert group.baseline.template == variant.template
    assert group.rounds[-1].score.overall == 100
    await client.close()


async def test_fake_deadline_and_interrupted_recovery(factory, locked):
    client = factory()
    _, variant = await prepared(client, locked)
    service = OptimizationService(client.store, client)
    initial = service.start(locked.id, request(locked, variant))
    task = service.tasks[initial.id]
    # Cancel queued execution before it begins; no uncertain work is repeated.
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    service.repo.recover()
    assert service.repo.get(initial.id).status == "interrupted"
    assert service.repo.get(initial.id).stop_reason == "PROCESS_RESTARTED"
    late = service.start(locked.id, request(locked, variant, "deadline-test-key"))
    original = client.structured

    async def exhaust(*args, **kwargs):
        value = await original(*args, **kwargs)
        client.clock.value += 500
        return value

    client.structured = exhaust
    final = await completed(service, late)
    assert final.status == "failed" and final.stop_reason == "BUDGET_EXHAUSTED"
    assert final.groups[0].current_id == variant.id
    assert final.calls_used == 1
    await client.close()


async def test_poster_audit_exact_text_hash_provenance_and_features(factory, locked, tmp_path):
    from backend.art_models import BackgroundRequest, RenderRequest
    from backend.art_service import ArtService
    from backend.tests.test_art import fake_canvas

    client = factory(asset_path=tmp_path / "art")
    _, variant = await prepared(client, locked)
    art = ArtService(client.store, client, client.settings)
    art.renderer = fake_canvas  # only the renderer boundary; browser E2E uses real pixels
    background = await art.background(
        locked.id, BackgroundRequest(expected_revision=1, size="square", source="deterministic")
    )
    poster = await art.render(
        locked.id,
        RenderRequest(
            expected_revision=1, variant_id=variant.id, background_id=background.id, size="square"
        ),
    )
    service = OptimizationService(client.store, client)
    audit = await service.audit_poster(poster.id, 1)
    assert audit.status == "PASS" and audit.artifact_hash == poster.sha256
    assert audit.provenance and audit.remote_vision == "NOT_TESTED"
    assert service.repo.audit(audit.id) == audit
    contrast = next(f for f in audit.measured_features if f.name == "text_contrast")
    assert contrast.applicable and contrast.value == 100
    (art.storage.root / f"{poster.sha256}.png").write_bytes(b"tampered")
    with pytest.raises(ProviderError, match="hash"):
        await service.audit_poster(poster.id, 1)
    await client.close()
