import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.config import Settings
from backend.db import Store
from backend.main import create_app
from backend.social_profiles import SaveSocialProfiles, SocialProfileRepository
from backend.tests.test_delivery import approval_request, setup
from backend.tests.test_generation import locked as locked_fixture


@pytest.mark.parametrize(
    "platform,url",
    [
        ("instagram", "javascript:alert(1)"),
        ("instagram", "http://instagram.com/cafe"),
        ("instagram", "https://instagram.com.evil.test/cafe"),
        ("instagram", "https://instagram.com@evil.test/cafe"),
        ("instagram", "https://owner:password@instagram.com/cafe"),
        ("instagram", "https://instagram.com:443/cafe"),
        ("instagram", "https://instagram.com/cafe#fragment"),
        ("instagram", "https://instagram.com/p/abc"),
        ("instagram", "https://instagram.com/accounts"),
        ("instagram", "https://instagram.com/.."),
        ("instagram", "https://instagram.com/cafe?redirect=https://evil.test"),
        ("instagram", "https://instagram.com/ca\nfe"),
        ("facebook", "https://facebook.com/sharer.php"),
        ("facebook", "https://facebook.com/profile.php?id=1&id=2"),
        ("facebook", "https://facebook.com/profile.php?id=1&next=evil"),
        ("whatsapp", "https://wa.me/+15555550123"),
        ("whatsapp", "https://wa.me/15555550123?text=unapproved"),
        ("whatsapp", "https://evil.test/15555550123"),
    ],
)
def test_unsafe_or_nonprofile_links_rejected(platform, url):
    with pytest.raises(ValidationError):
        SaveSocialProfiles(expected_version=0, **{platform: url})


def test_api_persistence_duplicate_conflict_and_redacted_validation(tmp_path):
    settings = Settings(
        _env_file=None, inference_mode="mock", database_path=tmp_path / "db.sqlite3"
    )
    with TestClient(create_app(settings)) as api:
        assert api.get("/api/social-profiles").json()["version"] == 0
        body = {
            "expected_version": 0,
            "instagram": " https://www.instagram.com/test_cafe/ ",
            "facebook": "https://www.facebook.com/profile.php?id=12345",
            "whatsapp": "https://wa.me/15555550123",
        }
        first = api.put("/api/social-profiles", json=body)
        assert first.status_code == 200 and first.json()["version"] == 1
        assert first.json()["instagram"] == "https://www.instagram.com/test_cafe"
        assert api.put("/api/social-profiles", json=body).json() == first.json()
        conflict = api.put("/api/social-profiles", json={**body, "instagram": None})
        assert conflict.status_code == 409 and conflict.json()["code"] == "REVISION_CONFLICT"
        assert api.get("/api/social-profiles").json() == first.json()
        invalid = api.put(
            "/api/social-profiles", json={**body, "whatsapp": "https://evil.test/15555550123"}
        )
        assert invalid.status_code == 422
        assert "15555550123" not in invalid.text and "evil.test" not in invalid.text
    with TestClient(create_app(settings)) as api:
        assert api.get("/api/social-profiles").json() == first.json()
        cleared = api.put("/api/social-profiles", json={"expected_version": 1})
        assert cleared.status_code == 200 and cleared.json()["version"] == 2
        assert all(cleared.json()[p] is None for p in ["instagram", "facebook", "whatsapp"])


def test_two_connections_cannot_overwrite_other_owner_edits(tmp_path):
    path = tmp_path / "db.sqlite3"
    first, second = Store(path), Store(path)
    try:
        SocialProfileRepository(first).save(
            SaveSocialProfiles(expected_version=0, instagram="https://instagram.com/first")
        )
        from backend.errors import ProviderError

        with pytest.raises(ProviderError):
            SocialProfileRepository(second).save(
                SaveSocialProfiles(expected_version=0, instagram="https://instagram.com/second")
            )
        assert SocialProfileRepository(second).get().instagram == "https://instagram.com/first"
        assert second.connection.in_transaction is False
    finally:
        first.close()
        second.close()


async def test_link_edit_preserves_approved_facts_hashes_and_export(factory):
    client = factory()
    campaign = locked_fixture.__wrapped__()
    changes, approvals, items, _ = await setup(client, campaign)
    await approvals.audit(campaign.id, items[0].id, campaign.revision)
    approval = approvals.approve(campaign.id, approval_request(campaign, items))
    before = changes.ledger.campaigns.get(campaign.id).model_dump()
    pack, files = approvals.export(campaign.id, campaign.revision, [items[0].id])
    SocialProfileRepository(client.store).save(
        SaveSocialProfiles(expected_version=0, instagram="https://instagram.com/cafe")
    )
    after_pack, after_files = approvals.export(campaign.id, campaign.revision, [items[0].id])
    assert after_pack.files == pack.files and after_files == files
    assert after_pack.files[0].approval_id == approval.id
    assert changes.ledger.campaigns.get(campaign.id).model_dump() == before
    await client.close()
