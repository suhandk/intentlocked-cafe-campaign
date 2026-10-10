import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.approval_service import ApprovalService
from backend.change import classify, prepare
from backend.change_service import ChangeService
from backend.delivery_models import (
    ApprovalRequest,
    ChangeParse,
    ChangeRequest,
    ConfirmRequest,
    Operation,
    PublishRequest,
)
from backend.errors import ProviderError
from backend.ledger import fingerprint
from backend.main import create_app
from backend.tests.test_generation import locked as locked_fixture
from backend.tests.test_optimization import completed, prepared
from backend.tests.test_optimization import request as optimization_request


@pytest.fixture
def locked():
    return locked_fixture.__wrapped__()


def change_request(campaign, text="Make it 15%", key="owner-change-key", scope=None):
    return ChangeRequest(
        expected_revision=campaign.revision, text=text, idempotency_key=key, scope_ids=scope or []
    )


async def proposal(service, campaign, text="Make it 15%", scope=None):
    return await service.propose(campaign.id, change_request(campaign, text, scope=scope))


def confirmation(campaign, p, decision="confirm", key="owner-confirm-key"):
    return ConfirmRequest(
        expected_revision=campaign.revision,
        proposal_id=p.id,
        decision=decision,
        idempotency_key=key,
    )


async def published(service, campaign, p):
    service.confirm(campaign.id, confirmation(campaign, p))
    forms = []
    if p.changed_keys:
        p = await service.surfaces(
            campaign.id, SimpleNamespace(expected_revision=campaign.revision, proposal_id=p.id)
        )
        forms = p.forms
    request = PublishRequest(
        expected_revision=campaign.revision,
        proposal_id=p.id,
        reviewed_forms=forms,
        approve_diff_and_forms=True,
        idempotency_key="owner-publish-key",
    )
    result = service.publish(campaign.id, request)
    return result, request


def approval_request(campaign, items, key="owner-approval-key", **values):
    return ApprovalRequest(
        expected_revision=campaign.revision,
        item_ids=[i.id for i in items],
        observed_hashes={i.id: i.snapshot_hash for i in items},
        acknowledged_warning_ids=[],
        owner_approves=True,
        idempotency_key=key,
        **values,
    )


async def setup(client, campaign):
    _, variant = await prepared(client, campaign)
    changes, approvals = ChangeService(client.store, client), ApprovalService(client.store, client)
    items = changes.ledger.sync(campaign)
    return changes, approvals, items, variant


@pytest.mark.parametrize("eligible", [True, False])
async def test_exact_demo_families_premium_preserves_offer_and_checks_eligibility(
    factory, locked, eligible
):
    client = factory()
    if not eligible:
        fact = next(f for f in locked.facts if f.key == "ELIGIBILITY")
        fact.canonical.scope = "students"
    changes, _, _, _ = await setup(client, locked)
    offer = next(f for f in locked.facts if f.key == "OFFER").model_dump()
    if not eligible:
        with pytest.raises(ProviderError) as caught:
            await proposal(changes, locked, "families and premium")
        assert caught.value.body.code == "ELIGIBILITY_CONFLICT"
    else:
        result = await proposal(changes, locked, "families and premium")
        assert result.classification == "mutable"
        assert {o.target for o in result.operations} == {"AUDIENCE", "TONE"}
        assert result.changed_keys == []
        result, _ = await published(changes, locked, result)
        current = changes.ledger.campaigns.get(locked.id)
        assert current.target_audiences == ["families"] and current.brand.tone == "refined"
        assert next(f for f in current.facts if f.key == "OFFER").model_dump() == offer
    await client.close()


async def test_numeric_change_reuses_template_but_requires_new_audit_approval(factory, locked):
    client = factory()
    changes, approvals, items, variant = await setup(client, locked)
    await approvals.audit(locked.id, items[0].id, locked.revision)
    old_approval = approvals.approve(locked.id, approval_request(locked, items))
    p = await proposal(changes, locked)
    assert p.classification == "immutable" and p.diffs[0].consequence == "refill"
    p, req = await published(changes, locked, p)
    current = changes.ledger.campaigns.get(locked.id)
    assert current.revision == locked.revision + 1
    current_items = changes.ledger.active(current)
    assert len(current_items) == 1 and current_items[0].variant.template == variant.template
    assert "15%" in current_items[0].fields["body"]
    assert current_items[0].audit_id is None and current_items[0].approval_id is None
    with pytest.raises(ProviderError):
        approvals.export(locked.id, locked.revision, [items[0].id])
    with pytest.raises(ProviderError):
        approvals.export(locked.id, current.revision, [current_items[0].id])
    assert changes.publish(locked.id, req) == p  # double-click publication safe
    await approvals.audit(locked.id, current_items[0].id, current.revision)
    new_approval = approvals.approve(
        locked.id, approval_request(current, current_items, "new-approval-key")
    )
    assert new_approval.id != old_approval.id
    pack, files = approvals.export(locked.id, current.revision, [current_items[0].id])
    assert (
        "15%" in pack.copy_text[current_items[0].id]
        and "wa.me/?text=" in pack.whatsapp_drafts[current_items[0].id]
    )
    assert pack.files[0].sha256 == current_items[0].sha256 and files
    assert approvals.zip(locked.id, current.revision, [current_items[0].id]).startswith(b"PK")
    versions = changes.ledger.versions(locked.id)
    assert [v.current for v in versions] == [True, False]
    assert changes.ledger.campaigns.get(locked.id).revision == current.revision
    await client.close()


async def test_mutable_tone_preserves_unrelated_approved_item(factory, locked):
    client = factory()
    changes, approvals, items, variant = await setup(client, locked)
    # A second independent immutable output has its own approved hash.
    second = changes.ledger.derive(
        locked, items[0], variant.template.model_copy(update={"cta": "Come along!"})
    )
    client.store.connection.commit()
    for item in [items[0], second]:
        await approvals.audit(locked.id, item.id, locked.revision)
    original = approvals.approve(locked.id, approval_request(locked, [items[0], second]))
    p = await proposal(changes, locked, "tone calm", [items[0].id])
    assert p.classification == "mutable"
    await published(changes, locked, p)
    current = changes.ledger.campaigns.get(locked.id)
    active = changes.ledger.active(current)
    untouched = next(i for i in active if i.id == second.id)
    assert untouched.approval_id == original.id
    assert (
        approvals.export(locked.id, current.revision, [second.id])[0].files[0].approved_revision
        == locked.revision
    )
    changed = next(i for i in active if i.id != second.id)
    assert changed.approval_id is None and changed.fields["headline"] == "Take a moment"
    await client.close()


async def test_structural_offer_requires_regeneration(factory, locked):
    client = factory()
    changes, approvals, items, _ = await setup(client, locked)
    p = await proposal(changes, locked, "Make it BOGO")
    assert p.diffs[0].consequence == "regenerate"
    await published(changes, locked, p)
    current = changes.ledger.campaigns.get(locked.id)
    assert changes.ledger.active(current)[0].status == "regeneration_required"
    with pytest.raises(ProviderError):
        approvals.export(locked.id, current.revision, [items[0].id])
    await client.close()


async def test_mixed_cancel_no_partial_mutation_and_confirmation_idempotent(factory, locked):
    client = factory()
    changes, _, _, _ = await setup(client, locked)
    p = await proposal(changes, locked, "Make it 15% and tone calm")
    assert p.classification == "mixed"
    req = confirmation(locked, p, "cancel")
    result = changes.confirm(locked.id, req)
    assert changes.confirm(locked.id, req) == result
    assert result.status == "cancelled" and changes.ledger.campaigns.get(locked.id) == locked
    await client.close()


async def test_concurrent_owner_edits_rejected(factory, locked):
    client = factory()
    changes, _, _, _ = await setup(client, locked)
    one = await proposal(changes, locked)
    two = await changes.propose(
        locked.id, change_request(locked, "Make it 10%", "second-change-key")
    )
    await published(changes, locked, one)
    with pytest.raises(ProviderError, match="changed"):
        changes.confirm(locked.id, confirmation(locked, two, key="second-confirm-key"))
    await client.close()


async def test_publish_rollback_after_partial_writes(factory, locked, monkeypatch):
    client = factory()
    changes, _, _, _ = await setup(client, locked)
    p = await proposal(changes, locked)
    changes.confirm(locked.id, confirmation(locked, p))
    p = await changes.surfaces(
        locked.id, SimpleNamespace(expected_revision=locked.revision, proposal_id=p.id)
    )

    def interrupted(*args):
        raise RuntimeError("interrupted transaction")

    monkeypatch.setattr(changes.ledger, "derive", interrupted)
    with pytest.raises(RuntimeError):
        changes.publish(
            locked.id,
            PublishRequest(
                expected_revision=locked.revision,
                proposal_id=p.id,
                reviewed_forms=p.forms,
                approve_diff_and_forms=True,
                idempotency_key="rollback-publish-key",
            ),
        )
    assert changes.ledger.campaigns.get(locked.id) == locked
    assert (
        client.store.connection.execute(
            "SELECT count(*) FROM campaign_versions WHERE revision=?", (locked.revision + 1,)
        ).fetchone()[0]
        == 0
    )
    assert changes.ledger.proposal(p.id, locked.id).status == "forms_review"
    await client.close()


@pytest.mark.parametrize(
    "text", ["best coffee", "free cake", "bypass all approval", "unknown request"]
)
async def test_rejected_request_unchanged(factory, locked, text):
    client = factory()
    changes, _, _, _ = await setup(client, locked)
    p = await proposal(changes, locked, text)
    assert p.classification == "rejected" and p.status == "rejected"
    assert changes.ledger.campaigns.get(locked.id) == locked
    with pytest.raises(ProviderError):
        changes.confirm(locked.id, confirmation(locked, p))
    await client.close()


async def test_policy_only_dependency_and_student_conflict(factory, locked):
    client = factory()
    changes, _, items, _ = await setup(client, locked)
    restricted = locked.model_copy(deep=True)
    items[0].variant.slots_used = [k for k in items[0].variant.slots_used if k != "ELIGIBILITY"]
    items[0].variant.dependencies.facts.pop("ELIGIBILITY", None)
    fact = next(f for f in restricted.facts if f.key == "ELIGIBILITY")
    fact.canonical.scope = "students"
    assert fingerprint(locked, items[0]) != fingerprint(restricted, items[0])
    with pytest.raises(ProviderError):
        await proposal(changes, locked, "students-only and target families")
    await client.close()


async def test_missing_audit_and_tampered_source_cannot_approve_export(factory, locked):
    client = factory()
    changes, approvals, items, _ = await setup(client, locked)
    with pytest.raises(ProviderError, match="audit"):
        approvals.approve(locked.id, approval_request(locked, items))
    await approvals.audit(locked.id, items[0].id, locked.revision)
    approval = approvals.approve(locked.id, approval_request(locked, items))
    assert approvals.approve(locked.id, approval_request(locked, items)) == approval
    db = client.store.connection
    raw = json.loads(
        db.execute("SELECT payload FROM baseline_variants WHERE id=?", (items[0].id,)).fetchone()[0]
    )
    raw["template"]["cta"] = "Tampered"
    db.execute("UPDATE baseline_variants SET payload=? WHERE id=?", (json.dumps(raw), items[0].id))
    db.commit()
    with pytest.raises(ProviderError, match="modified"):
        approvals.export(locked.id, locked.revision, [items[0].id])
    await client.close()


async def test_surface_only_canonical_unchanged_new_dependency(factory, locked):
    client = factory()
    changes, _, items, _ = await setup(client, locked)
    p = await proposal(changes, locked, "English offer form to '20 percent off'")
    assert (
        next(f for f in p.candidate.facts if f.key == "OFFER").canonical
        == next(f for f in locked.facts if f.key == "OFFER").canonical
    )
    await published(changes, locked, p)
    current = changes.ledger.campaigns.get(locked.id)
    item = changes.ledger.active(current)[0]
    assert (
        "20 percent off" in item.fields["body"] and item.dependency_hash != items[0].dependency_hash
    )
    assert item.audit_id is None
    await client.close()


def test_direct_api_forged_approval_and_red_team_modes(tmp_path):
    from backend.config import Settings
    from backend.tests.test_generation import locked as fixture
    from backend.tests.test_generation import seed

    settings = Settings(_env_file=None, database_path=tmp_path / "api.sqlite")
    with TestClient(create_app(settings)) as browser:
        campaign = fixture.__wrapped__()
        seed(browser.app.state.client, campaign)
        root = f"/api/campaigns/{campaign.id}"
        forged = {
            "expected_revision": campaign.revision,
            "item_ids": ["forged"],
            "observed_hashes": {"forged": "forged"},
            "owner_approves": True,
            "idempotency_key": "forged-approval-key",
            "status": "approved",
        }
        assert browser.post(root + "/approve", json=forged).status_code == 422
        forged.pop("status")
        assert browser.post(root + "/approve", json=forged).status_code == 422
        assert (
            browser.get(
                root + "/export", params={"expected_revision": campaign.revision}
            ).status_code
            == 422
        )
        payload = {
            "expected_revision": campaign.revision,
            "text": "Make it 25%",
            "idempotency_key": "red-team-instruction-key",
            "mode": "instruct_ai",
        }
        result = browser.post(root + "/red-team", json=payload)
        assert (
            result.status_code == 200 and result.json()["proposal"]["classification"] == "immutable"
        )
        assert result.json()["proposal"]["status"] == "proposed"
        payload.update(mode="edit_copy", idempotency_key="red-team-edit-key")
        result = browser.post(root + "/red-team", json=payload)
        assert result.status_code == 200 and result.json()["report"]["status"] == "BLOCKED"


@pytest.mark.parametrize(
    "target,values",
    [
        ("FACT:OFFER", {"value": "15"}),
        ("FACT:CAFE", {}),
        ("TONE", {"canonical": {"kind": "percent_off", "value": 15.0}}),
        ("TONE", {"value": "best coffee"}),
        ("THEME", {"value": "fake award"}),
        ("HOOK", {"value": []}),
        ("CTA", {"value": " "}),
        ("LAYOUT_EMPHASIS", {"value": "hidden facts"}),
        ("AUDIENCE", {"value": ["children"]}),
        ("CHANNELS", {"value": ["whatsapp", "whatsapp"]}),
        ("LANGUAGE_MIX", {"value": []}),
        ("FACT:OFFER", {"canonical": {"kind": "percent_off", "value": 20.0}}),
    ],
)
async def test_classifier_rejects_invalid_operation_values(factory, locked, target, values):
    client = factory()
    changes, _, items, _ = await setup(client, locked)
    req = change_request(locked, "owner evidence")
    op = Operation(
        target=target, evidence={"start": 0, "end": 14, "quote": "owner evidence"}, **values
    )
    with pytest.raises((ProviderError, ValueError)):
        prepare(locked, req, ChangeParse(operations=[op]), items, fingerprint)
    assert changes.ledger.campaigns.get(locked.id) == locked
    await client.close()


@pytest.mark.parametrize(
    "target,value",
    [
        ("AUDIENCE", ["families"]),
        ("CHANNELS", ["whatsapp"]),
        ("LANGUAGE_MIX", ["en"]),
        ("THEME", "minimal"),
        ("LAYOUT_EMPHASIS", "offer"),
        ("HOOK", "A shared pause"),
        ("CTA", "Come along!"),
    ],
)
async def test_permitted_preference_has_diff_consequence(factory, locked, target, value):
    from backend.change import edited_template

    client = factory()
    _, _, items, _ = await setup(client, locked)
    req = change_request(locked, "owner evidence")
    op = Operation(
        target=target, value=value, evidence={"start": 0, "end": 14, "quote": "owner evidence"}
    )
    classification, candidate, keys, diffs = prepare(
        locked, req, ChangeParse(operations=[op]), items, fingerprint
    )
    assert classification == "mutable" and not keys and diffs[0].affected_ids
    assert diffs[0].before and diffs[0].after and candidate.revision == locked.revision
    p = SimpleNamespace(operations=[op], diffs=diffs)
    changed = edited_template(items[0], p)
    if target == "HOOK":
        assert changed.headline == value
    if target == "CTA":
        assert changed.cta == value
    await client.close()


async def test_scope_evidence_and_unknown_target_boundaries(factory, locked):
    client = factory()
    _, _, items, _ = await setup(client, locked)
    req = change_request(locked, "owner evidence")
    base = {
        "target": "TONE",
        "value": "calm",
        "evidence": {"start": 0, "end": 14, "quote": "owner evidence"},
    }
    for changes in [
        {"scope_ids": ["forged"]},
        {"evidence": {"start": 0, "end": 1, "quote": "forged"}},
    ]:
        with pytest.raises(ProviderError):
            prepare(
                locked,
                req,
                ChangeParse(operations=[Operation(**{**base, **changes})]),
                items,
                fingerprint,
            )
    narrowed = req.model_copy(update={"scope_ids": [items[0].id]})
    op = Operation(**{**base, "scope_ids": ["forged"]})
    with pytest.raises(ProviderError):
        prepare(locked, narrowed, ChangeParse(operations=[op]), items, fingerprint)
    assert classify([Operation(**{**base, "target": "APPROVE"})]) == "rejected"
    assert classify([Operation(**base), Operation(**base)]) == "rejected"
    with pytest.raises(ProviderError, match="whole campaign"):
        prepare(
            locked,
            narrowed,
            ChangeParse(operations=[Operation(**{**base, "target": "THEME", "value": "warm"})]),
            items,
            fingerprint,
        )
    await client.close()


async def test_date_edit_derives_days_and_cannot_publish_inconsistent_forms(factory, locked):
    client = factory()
    _, _, items, _ = await setup(client, locked)
    req = change_request(locked, "owner evidence")
    op = Operation(
        target="FACT:DATES",
        canonical={
            "kind": "dates",
            "start": "2026-10-12",
            "end": "2026-10-12",
            "original_phrase": "owner evidence",
        },
        evidence={"start": 0, "end": 14, "quote": "owner evidence"},
    )
    _, candidate, keys, diffs = prepare(
        locked, req, ChangeParse(operations=[op]), items, fingerprint
    )
    assert keys == ["DATES", "DAYS"] and next(
        f for f in candidate.facts if f.key == "DAYS"
    ).canonical.weekdays == ["MON"]
    assert diffs[0].affected_ids
    await client.close()


@pytest.mark.parametrize(
    "attack", ["bytes", "font", "layout", "dangling", "missing_audit", "metadata"]
)
async def test_poster_approval_export_revalidates_artifact(
    factory, locked, tmp_path, monkeypatch, attack
):
    import backend.approval_service as boundary
    from backend.art_models import BackgroundRequest, RenderRequest
    from backend.art_service import ArtService
    from backend.tests.test_art import fake_canvas

    client = factory(asset_path=tmp_path / "assets")
    changes, approvals, _, variant = await setup(client, locked)
    art = ArtService(client.store, client, client.settings)
    art.renderer = fake_canvas
    bg = await art.background(
        locked.id,
        BackgroundRequest(expected_revision=locked.revision, size="square", source="deterministic"),
    )
    poster = await art.render(
        locked.id,
        RenderRequest(
            expected_revision=locked.revision,
            size="square",
            variant_id=variant.id,
            background_id=bg.id,
        ),
    )
    items = changes.ledger.sync(locked)
    item = next(i for i in items if i.id == poster.id)
    await approvals.audit(locked.id, item.id, locked.revision)
    approvals.approve(locked.id, approval_request(locked, [item]))
    assert approvals.export(locked.id, locked.revision, [item.id])[0].files[0].artifact_url
    db = client.store.connection
    if attack == "bytes":
        (art.storage.root / f"{poster.sha256}.png").write_bytes(b"tampered")
    elif attack == "font":
        monkeypatch.setattr(boundary, "font_manifest", lambda: "changed font")
    elif attack == "layout":
        monkeypatch.setitem(boundary.LAYOUT, "scrim", "#000000")
    elif attack == "dangling":
        db.execute("DELETE FROM poster_artifacts WHERE id=?", (poster.id,))
        db.commit()
    elif attack == "missing_audit":
        db.execute("DELETE FROM delivery_audits WHERE item_id=?", (poster.id,))
        db.commit()
    else:
        value = poster.model_dump()
        value["render_input"]["fields"]["body"] = "tampered"
        db.execute(
            "UPDATE poster_artifacts SET payload=? WHERE id=?", (json.dumps(value), poster.id)
        )
        db.commit()
    with pytest.raises(ProviderError):
        approvals.export(locked.id, locked.revision, [item.id])
    await client.close()


async def test_late_optimizer_cannot_commit_after_fact_publication(factory, locked):
    from backend.optimization_service import OptimizationService

    client = factory()
    changes, _, _, variant = await setup(client, locked)
    optimize = OptimizationService(client.store, client)
    entered, release = asyncio.Event(), asyncio.Event()
    original = client.structured

    async def delayed(*args, **kwargs):
        if "ROLE: R5" in kwargs.get("system_prompt", ""):
            entered.set()
            await release.wait()
        return await original(*args, **kwargs)

    client.structured = delayed
    run = optimize.start(locked.id, optimization_request(locked, variant))
    await entered.wait()
    p = await proposal(changes, locked)
    await published(changes, locked, p)
    release.set()
    final = await completed(optimize, run)
    assert final.status == "stale" and final.stop_reason == "REVISION_CONFLICT"
    assert changes.ledger.campaigns.get(locked.id).revision == locked.revision + 1
    assert final.groups[0].current_id == variant.id
    await client.close()


async def test_import_retained_optimization_provenance_and_missing_records(factory, locked):
    from backend.optimization_service import OptimizationService

    client = factory()
    changes, approvals, _, variant = await setup(client, locked)
    optimization = OptimizationService(client.store, client)
    run = await completed(
        optimization, optimization.start(locked.id, optimization_request(locked, variant))
    )
    items = changes.ledger.sync(locked)
    retained = next(i for i in items if i.id == run.groups[0].current_id)
    assert retained.source_table == "optimization"
    await approvals.audit(locked.id, retained.id, locked.revision)
    approvals.approve(locked.id, approval_request(locked, [retained]))
    assert approvals.export(locked.id, locked.revision, [retained.id])[0].mode == "mock"
    with pytest.raises(ProviderError):
        changes.ledger.raw_item("dangling")
    with pytest.raises(ProviderError):
        changes.ledger.proposal("dangling", locked.id)
    p = await proposal(changes, locked)
    assert await changes.propose(locked.id, p.request) == p
    with pytest.raises(ProviderError):
        await changes.propose(locked.id, p.request.model_copy(update={"text": "Make it 10%"}))
    changes.confirm(locked.id, confirmation(locked, p))
    with pytest.raises(ProviderError):
        changes.confirm(locked.id, confirmation(locked, p, "cancel"))
    await client.close()


async def test_surface_edit_preserves_other_language_approval(factory, locked):
    client = factory()
    changes, approvals, items, variant = await setup(client, locked)
    seed = items[0].model_copy(deep=True)
    seed.variant.language = "kn"
    second = changes.ledger.derive(locked, seed, variant.template)
    client.store.connection.commit()
    reviewed = await approvals.audit(locked.id, second.id, locked.revision)
    req = approval_request(locked, [second], native_review_confirmed=True).model_copy(
        update={"acknowledged_warning_ids": reviewed.warning_ids}
    )
    old = approvals.approve(locked.id, req)
    p = await proposal(changes, locked, "English offer form to '20 percent off'")
    await published(changes, locked, p)
    current = changes.ledger.campaigns.get(locked.id)
    preserved = next(i for i in changes.ledger.active(current) if i.id == second.id)
    assert preserved.approval_id == old.id
    pack, _ = approvals.export(locked.id, current.revision, [second.id])
    assert pack.files[0].approved_revision == locked.revision
    assert pack.current_fact_versions["OFFER"] > pack.files[0].source_fact_versions["OFFER"]
    await client.close()


async def test_poster_for_selected_social_channel_does_not_require_poster_selection(
    factory, locked, tmp_path
):
    from backend.art_models import BackgroundRequest, RenderRequest
    from backend.art_service import ArtService
    from backend.tests.test_art import fake_canvas

    locked.channels = ["whatsapp"]
    client = factory(asset_path=tmp_path / "art")
    changes, approvals, _, variant = await setup(client, locked)
    art = ArtService(client.store, client, client.settings)
    art.renderer = fake_canvas
    background = await art.background(
        locked.id,
        BackgroundRequest(expected_revision=locked.revision, size="square", source="deterministic"),
    )
    poster = await art.render(
        locked.id,
        RenderRequest(
            expected_revision=locked.revision,
            variant_id=variant.id,
            size="square",
            background_id=background.id,
        ),
    )
    item = next(i for i in changes.ledger.sync(locked) if i.id == poster.id)
    audit = await approvals.audit(locked.id, item.id, locked.revision)
    assert audit.status == "PASS"
    approvals.approve(locked.id, approval_request(locked, [item]))
    assert (
        art.approved_bytes(poster.id)
        == approvals.export(locked.id, locked.revision, [item.id])[1][f"en-whatsapp-{item.id}.png"]
    )
    await client.close()
