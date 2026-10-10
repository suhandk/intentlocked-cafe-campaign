from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.config import Settings
from backend.main import create_app
from backend.planning import CreatePlan, Planner
from backend.tests.test_delivery import approval_request, setup
from backend.tests.test_generation import locked as locked_fixture


def details(**values):
    return dict(
        title="Weekend coffee",
        brief="Owner brief to review",
        platform="whatsapp",
        planned_for="2026-10-10T10:00",
        **values,
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"planned_for": "2026-02-29T10:00"},
        {"planned_for": "2026-10-10T25:00"},
        {"planned_for": "2026-10-10T10:00Z"},
        {"timezone": "UTC"},
        {"title": "   "},
        {"campaign_revision": 1},
        {"item_ids": ["fake"]},
        {"platform": "email"},
    ],
)
def test_invalid_planning_input(changes):
    with pytest.raises(ValidationError):
        CreatePlan.model_validate({**details(), **changes, "idempotency_key": "plan-test-key"})


def test_persistence_duplicate_save_edit_conflict_cancel_and_no_fake_post(tmp_path):
    settings = Settings(
        _env_file=None, inference_mode="mock", database_path=tmp_path / "db.sqlite3"
    )
    with TestClient(create_app(settings)) as api:
        body = {**details(), "idempotency_key": "first-planning-key"}
        response = api.post("/api/plans", json=body)
        assert response.status_code == 201
        plan = response.json()
        assert api.post("/api/plans", json=body).json() == plan
        assert api.post("/api/plans", json={**body, "title": "different"}).status_code == 409
        snapshot = api.get("/api/plans?month=2026-10").json()
        assert len(snapshot["plans"]) == 1 and snapshot["plans"][0]["readiness"] == "brief_only"
        assert api.get("/api/plans?month=2026-13").status_code == 422
        assert api.get("/api/plans?month=2026-11").json()["plans"] == []
        root = "/api/plans/" + plan["id"]
        updated = api.put(root, json={**details(), "expected_version": 1}).json()
        assert updated["version"] == 2
        assert api.put(root, json={**details(), "expected_version": 1}).status_code == 409
        assert (
            api.post(
                root + "/posted", json={"expected_version": 2, "owner_confirms_manual_post": True}
            ).status_code
            == 422
        )
    with TestClient(create_app(settings)) as api:
        assert api.get("/api/plans?month=2026-10").json()["plans"][0]["version"] == 2
        response = api.post(root + "/cancel", json={"expected_version": 2})
        assert response.json()["status"] == "cancelled"
        assert api.post(root + "/cancel", json={"expected_version": 2}).json() == response.json()
        assert api.post(root + "/start", json={"expected_version": 3}).status_code == 422
        assert api.get("/api/cost").json()["calls"] == 0


def test_start_is_atomic_idempotent_and_never_copies_locked_facts(tmp_path):
    settings = Settings(
        _env_file=None, inference_mode="mock", database_path=tmp_path / "db.sqlite3"
    )
    app = create_app(settings)
    with TestClient(app, raise_server_exceptions=False) as api:
        source = app.state.changes.ledger.campaigns.create(
            __import__("backend.schemas", fromlist=["CampaignCreate"]).CampaignCreate(),
            "mock",
            "2026-10-09",
            False,
        )
        source.brand.tone = "calm"
        source.facts = locked_fixture.__wrapped__().facts
        source.status = "locked"
        source.languages = ["en", "kn"]
        source.brand.must_say = ["Never reuse this old campaign statement"]
        with app.state.store.connection:
            app.state.store.connection.execute(
                "UPDATE campaigns SET payload=? WHERE id=?", (source.model_dump_json(), source.id)
            )
        body = {**details(source_campaign_id=source.id), "idempotency_key": "atomic-plan-key"}
        plan = api.post("/api/plans", json=body).json()
        db = app.state.store.connection
        with db:
            db.execute(
                "CREATE TRIGGER interrupt_start BEFORE UPDATE ON campaign_plans "
                "BEGIN SELECT RAISE(ABORT,'interrupted'); END"
            )
        count = db.execute("SELECT count(*) FROM campaigns").fetchone()[0]
        response = api.post(f"/api/plans/{plan['id']}/start", json={"expected_version": 1})
        assert response.status_code == 500
        assert db.execute("SELECT count(*) FROM campaigns").fetchone()[0] == count
        assert Planner(app).get(plan["id"]).campaign_id is None
        with db:
            db.execute("DROP TRIGGER interrupt_start")
        response = api.post(f"/api/plans/{plan['id']}/start", json={"expected_version": 1})
        assert response.status_code == 200
        campaign = response.json()
        assert campaign["status"] == "draft" and campaign["brand"]["tone"] == "calm"
        assert campaign["languages"] == ["en", "kn"] and campaign["brand"]["must_say"] == []
        assert campaign["transcript"] == body["brief"]
        assert all(f["canonical"] is None and f["approval_id"] is None for f in campaign["facts"])
        again = api.post(f"/api/plans/{plan['id']}/start", json={"expected_version": 1})
        assert again.json()["id"] == campaign["id"]
        assert db.execute("SELECT count(*) FROM campaigns").fetchone()[0] == count + 1
        assert api.get("/api/cost").json()["calls"] == 0


async def test_ready_plan_rechecks_approval_revision_dates_and_owner_report(factory):
    client = factory()
    campaign = locked_fixture.__wrapped__()
    changes, approvals, items, _ = await setup(client, campaign)
    from types import SimpleNamespace

    app = SimpleNamespace(
        state=SimpleNamespace(store=client.store, changes=changes, approvals=approvals)
    )
    planner = Planner(app, clock=lambda: datetime.fromisoformat("2026-10-10T10:01:00+05:30"))
    plan = planner.create(
        CreatePlan(
            **details(
                campaign_id=campaign.id, campaign_revision=campaign.revision, item_ids=[items[0].id]
            ),
            idempotency_key="approved-plan-key",
        )
    )
    assert planner.view(plan).readiness == "review_required" and planner.view(plan).due
    await approvals.audit(campaign.id, items[0].id, campaign.revision)
    approvals.approve(campaign.id, approval_request(campaign, items))
    assert planner.view(plan).readiness == "ready"
    from backend.errors import ProviderError
    from backend.planning import FinishPlan, UpdatePlan

    with pytest.raises(ProviderError):
        planner.finish(plan.id, FinishPlan(expected_version=1, owner_confirms_manual_post=False))
    late = planner.update(
        plan.id,
        UpdatePlan(
            **{
                **details(
                    campaign_id=campaign.id,
                    campaign_revision=campaign.revision,
                    item_ids=[items[0].id],
                ),
                "planned_for": "2026-10-12T10:00",
            },
            expected_version=1,
        ),
    )
    assert planner.view(late).readiness == "review_required"
    assert (
        next(
            f for f in changes.ledger.campaigns.get(campaign.id).facts if f.key == "OFFER"
        ).canonical.value
        == 20
    )
    restored = planner.update(
        plan.id,
        UpdatePlan(
            **details(
                campaign_id=campaign.id, campaign_revision=campaign.revision, item_ids=[items[0].id]
            ),
            expected_version=2,
        ),
    )
    finished = planner.finish(
        plan.id, FinishPlan(expected_version=3, owner_confirms_manual_post=True)
    )
    assert finished.status == "owner_posted"
    assert (
        planner.finish(plan.id, FinishPlan(expected_version=3, owner_confirms_manual_post=True))
        == finished
    )
    campaign.revision += 1
    with client.store.connection:
        client.store.connection.execute(
            "UPDATE campaigns SET payload=? WHERE id=?", (campaign.model_dump_json(), campaign.id)
        )
    assert planner.view(restored).readiness == "stale"
    await client.close()
