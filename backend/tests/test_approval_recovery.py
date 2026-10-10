import json

from fastapi.testclient import TestClient

from backend.config import Settings
from backend.ledger import item_hash
from backend.main import create_app
from backend.optimization_models import Evidence
from backend.semantic_audit import evidence_valid, reader_spans
from backend.tests.test_generation import locked
from backend.tests.test_optimization import prepared


def test_approval_snapshot_explains_stale_audit_without_changing_owner_hash(tmp_path):
    settings = Settings(
        _env_file=None,
        demo_fast=True,
        database_path=tmp_path / "db.sqlite3",
        asset_path=tmp_path / "assets",
    )
    app = create_app(settings)
    with TestClient(app) as api:
        campaign = locked.__wrapped__()
        api.portal.call(prepared, app.state.client, campaign)
        root = f"/api/campaigns/{campaign.id}"
        initial = api.get(root + "/delivery").json()["items"][0]
        assert not initial["approval_blockers"] and initial["audit_status"] is None
        response = api.post(
            root + f"/delivery/{initial['id']}/audit", json={"expected_revision": campaign.revision}
        )
        assert response.status_code == 200 and response.json()["status"] == "PASS"
        after = api.get(root + "/delivery").json()["items"][0]
        assert after["snapshot_hash"] == initial["snapshot_hash"]
        assert after["audit_status"] == "PASS" and not after["approval_blockers"]
        raw = app.state.changes.ledger.raw_item(initial["id"])
        raw.audit_findings = ["Display-only review information"]
        raw.approval_blockers = ["Display-only blocker"]
        assert item_hash(raw) == initial["snapshot_hash"]
        audit = response.json()
        audit["artifact_hash"] = "wrong-artifact"
        audit["id"] = "nonbinding-audit-test"
        with app.state.store.connection:
            app.state.store.connection.execute(
                "INSERT INTO semantic_audits VALUES(?,?,?,?)",
                (audit["id"], campaign.id, audit["content_hash"], json.dumps(audit)),
            )
            app.state.store.connection.execute(
                "UPDATE delivery_audits SET audit_id=? WHERE item_id=?",
                (audit["id"], initial["id"]),
            )
        stale = api.get(root + "/delivery").json()["items"][0]
        assert stale["approval_blockers"] == ["Audit does not bind the current content/artifact"]
        approval = api.post(
            root + "/approve",
            json={
                "expected_revision": campaign.revision,
                "item_ids": [initial["id"]],
                "observed_hashes": {initial["id"]: initial["snapshot_hash"]},
                "acknowledged_warning_ids": [],
                "native_review_confirmed": False,
                "owner_approves": True,
                "idempotency_key": "blocked-audit-confirm",
            },
        )
        assert approval.status_code == 422


def test_long_customer_copy_gets_exact_bounded_evidence_not_truncated_text():
    fields = {"body": "Long copy with café evidence. " * 70 + "ಕಾಫಿ"}
    spans = reader_spans(fields)
    assert len(spans) > 1
    covered = set()
    for span in spans:
        assert len(span["quote"]) <= 400
        assert evidence_valid(Evidence(**span), fields)
        covered.update(range(span["start"], span["end"]))
    assert covered == set(range(len(fields["body"])))
