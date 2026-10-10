import pytest

from backend.db import Store
from scripts.backup_restore import backup, restore, verify


def test_backup_restore_releases_database_handles():
    from pathlib import Path
    from tempfile import TemporaryDirectory

    # Windows rejects immediate cleanup when sqlite connections remain open.
    with TemporaryDirectory(prefix="backup-handle-test-") as folder:
        root = Path(folder)
        store = Store(root / "source.sqlite3")
        store.close()
        assets = root / "assets"
        assets.mkdir()
        backup(root / "source.sqlite3", assets, root / "backup")
        restore(root / "backup", root / "restored")


def test_consistent_backup_restore_and_tamper_rejection(tmp_path):
    source = tmp_path / "source.sqlite3"
    store = Store(source)
    store.close()
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "immutable.png").write_bytes(b"test immutable byte fixture")
    manifest = backup(source, assets, tmp_path / "backup")
    assert {p.name for p in (tmp_path / "backup").iterdir()} == {
        "campaigns.sqlite3",
        "assets",
        "manifest.json",
    }
    assert restore(tmp_path / "backup", tmp_path / "restored") == manifest
    with pytest.raises(AssertionError):
        restore(tmp_path / "backup", tmp_path / "restored")
    (tmp_path / "restored/assets/immutable.png").write_bytes(b"tampered")
    with pytest.raises(AssertionError):
        verify(tmp_path / "restored")


def test_backup_rejects_extra_credential_file(tmp_path):
    source = tmp_path / "source.sqlite3"
    store = Store(source)
    store.close()
    assets = tmp_path / "assets"
    assets.mkdir()
    backup(source, assets, tmp_path / "backup")
    (tmp_path / "backup/.env").write_text("private config fixture")
    with pytest.raises(AssertionError):
        verify(tmp_path / "backup")


async def test_r1_supplies_exact_spans_without_relaxing_evidence_validation(factory):
    import json

    import httpx

    from backend.campaign_service import CampaignService
    from backend.errors import ProviderError
    from backend.mock import handler
    from backend.schemas import CampaignCreate, IntentRequest

    captured = []
    invalid = False

    def transport(request):
        payload = json.loads(request.content)
        data = json.loads(json.loads(payload["messages"][1]["content"])["input"])
        captured.append(data)
        result = handler(request).json()
        if invalid:
            function = result["choices"][0]["message"]["tool_calls"][0]["function"]
            parsed = json.loads(function["arguments"])
            parsed["result"]["facts"][0]["evidence"]["end"] += 1
            # Exact unique quotes permit coordinate recovery; absent source text does not.
            parsed["result"]["facts"][0]["evidence"]["quote"] = "Absent source evidence"
            function["arguments"] = json.dumps(parsed)
        return httpx.Response(200, json=result)

    client = factory(transport)
    service = CampaignService(client.store, client, client.settings)
    campaign = service.repo.create(CampaignCreate(), "mock", "2026-10-09", False)
    brief = "Café name: Namma Cafe. Bengaluru alli coffee mele 20% off ee weekend. Offer ellarigu."
    current = await service.intent(
        campaign.id, IntentRequest(expected_revision=1, transcript=brief)
    )
    assert captured[0]["evidence_spans"]
    assert all(brief[s["start"] : s["end"]] == s["quote"] for s in captured[0]["evidence_spans"])
    invalid = True
    with pytest.raises(ProviderError) as caught:
        await service.intent(
            campaign.id, IntentRequest(expected_revision=current.revision, transcript=brief)
        )
    assert caught.value.body.code == "INVALID_EVIDENCE"
    assert service.repo.get(campaign.id).revision == current.revision
    assert len(captured) == 4  # Initial success plus the existing two-repair limit.
    await client.close()
