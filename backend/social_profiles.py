"""Single-owner profile links; no remote requests or campaign fact mutations."""

import re
from urllib.parse import parse_qs, urlsplit, urlunsplit

from fastapi import APIRouter, Request
from pydantic import Field, field_validator

from backend.contracts import StrictModel
from backend.intent_rules import domain_error


def profile_url(value, platform):
    if value is None or not value.strip():
        return None
    value = value.strip()
    if any(ord(c) < 33 or ord(c) == 127 for c in value) or "\\" in value:
        raise ValueError("Invalid profile link")
    parsed = urlsplit(value)
    hosts = {
        "instagram": {"instagram.com", "www.instagram.com"},
        "facebook": {"facebook.com", "www.facebook.com", "m.facebook.com"},
        "whatsapp": {"wa.me"},
    }
    if (
        parsed.scheme != "https"
        or parsed.hostname not in hosts[platform]
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port is not None
        or parsed.fragment
    ):
        raise ValueError("Use the platform's HTTPS profile URL")
    path = parsed.path.rstrip("/")
    if platform == "instagram":
        if parsed.query or not re.fullmatch(r"/[A-Za-z0-9_.]{1,30}", path):
            raise ValueError("Use an Instagram profile URL")
        if path.lower() in {"/accounts", "/explore", "/direct", "/p", "/reel", "/..", "/."}:
            raise ValueError("Use a profile, not an Instagram operation")
    elif platform == "facebook":
        if path == "/profile.php":
            query = parse_qs(parsed.query, strict_parsing=True)
            if set(query) != {"id"} or len(query["id"]) != 1 or not query["id"][0].isdigit():
                raise ValueError("Use a Facebook Page URL")
        elif parsed.query or not re.fullmatch(r"/[A-Za-z0-9_.-]+", path):
            raise ValueError("Use a Facebook Page URL")
        if path.lower() in {"/login", "/logout", "/dialog", "/sharer.php", "/share", "/..", "/."}:
            raise ValueError("Use a Page, not a Facebook operation")
    elif parsed.query or not re.fullmatch(r"/[1-9][0-9]{6,14}", path):
        raise ValueError("Use wa.me with an international number, without a plus sign")
    return urlunsplit(("https", parsed.hostname, path, parsed.query, ""))


class SocialLinks(StrictModel):
    instagram: str | None = Field(default=None, max_length=500)
    facebook: str | None = Field(default=None, max_length=500)
    whatsapp: str | None = Field(default=None, max_length=500)

    @field_validator("instagram", "facebook", "whatsapp")
    @classmethod
    def safe_url(cls, value, info):
        return profile_url(value, info.field_name)


class SocialProfiles(SocialLinks):
    version: int = Field(default=0, ge=0)


class SaveSocialProfiles(SocialLinks):
    expected_version: int = Field(ge=0)


class SocialProfileRepository:
    def __init__(self, store):
        self.db = store.connection

    def get(self):
        row = self.db.execute("SELECT payload FROM social_profiles WHERE id=1").fetchone()
        return SocialProfiles.model_validate_json(row[0]) if row else SocialProfiles()

    def save(self, body):
        links = body.model_dump(exclude={"expected_version"})
        self.db.execute("BEGIN IMMEDIATE")
        try:
            current = self.get()
            if links == current.model_dump(exclude={"version"}):
                self.db.commit()
                return current
            if current.version != body.expected_version:
                raise domain_error(
                    "REVISION_CONFLICT", "Social links changed. Reload before saving."
                )
            result = SocialProfiles(**links, version=current.version + 1)
            self.db.execute(
                "INSERT INTO social_profiles VALUES(1,?,?) "
                "ON CONFLICT(id) DO UPDATE SET version=excluded.version,payload=excluded.payload",
                (result.version, result.model_dump_json()),
            )
            self.db.commit()
            return result
        except Exception:
            self.db.rollback()
            raise


router = APIRouter(prefix="/api", tags=["manual social publishing"])


@router.get("/social-profiles", response_model=SocialProfiles)
async def get_profiles(request: Request):
    return SocialProfileRepository(request.app.state.store).get()


@router.put("/social-profiles", response_model=SocialProfiles)
async def save_profiles(body: SaveSocialProfiles, request: Request):
    return SocialProfileRepository(request.app.state.store).save(body)
