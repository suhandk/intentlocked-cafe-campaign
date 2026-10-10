"""Website inputs are owner data; locked offer values have no editable input field."""

import re
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator

from backend.contracts import StrictModel
from backend.schemas import Lang


class Hours(StrictModel):
    day: Literal["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
    open: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    close: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")

    @model_validator(mode="after")
    def ordered(self):
        if self.close <= self.open:
            raise ValueError("Close must follow open on the same day")
        return self


class MenuItem(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    price: float = Field(ge=0, le=1_000_000, allow_inf_nan=False)


class WebsiteFields(StrictModel):
    name: str = Field(default="", max_length=120)
    area: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=1000)
    languages: list[Lang] = Field(default_factory=lambda: ["en"], min_length=1, max_length=3)
    address: str = Field(default="", max_length=500)
    hours: list[Hours] = Field(default_factory=list, max_length=7)
    phone: str = Field(default="", max_length=20)
    whatsapp: str = Field(default="", max_length=20)
    menu: list[MenuItem] = Field(default_factory=list, max_length=100)
    social_links: list[str] = Field(default_factory=list, max_length=5)
    logo_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    photo_ids: list[str] = Field(default_factory=list, max_length=5)
    style: Literal["simple", "warm", "modern"] = "simple"
    colour: str = Field(default="#43362d", pattern=r"^#[a-fA-F0-9]{6}$")

    @field_validator("name", "area", "description", "address")
    @classmethod
    def clean_text(cls, value):
        if any(ord(ch) < 32 and ch not in "\n\t" for ch in value):
            raise ValueError("Control characters are not permitted")
        return value.strip()

    @field_validator("phone", "whatsapp")
    @classmethod
    def phone_format(cls, value):
        if value and not re.fullmatch(r"\+?[1-9][0-9]{6,14}", value):
            raise ValueError("Use 7–15 digits with optional leading +")
        return value

    @field_validator("social_links")
    @classmethod
    def urls(cls, values):
        for value in values:
            parsed = urlsplit(value)
            if (
                len(value) > 500
                or parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.port not in {None, 443}
            ):
                raise ValueError("Social links must be HTTPS URLs without credentials")
        return values

    @model_validator(mode="after")
    def unique(self):
        for values in [self.languages, [h.day for h in self.hours], self.photo_ids]:
            if len(values) != len(set(values)):
                raise ValueError("Repeated languages, days or images are not permitted")
        return self


class DraftSave(StrictModel):
    expected_version: int = Field(ge=1)
    step: int = Field(ge=0, le=6)
    fields: WebsiteFields


class GenerateWebsite(StrictModel):
    expected_version: int = Field(ge=1)


class ImageUpload(StrictModel):
    mime: Literal["image/png", "image/jpeg", "image/webp"]
    base64: str = Field(min_length=1, max_length=7_000_000)


class ConnectionInput(StrictModel):
    provider: Literal["netlify"]
    token: SecretStr | None = None  # Secret; transient unless remember=True.
    remember: bool = False
    use_remembered: bool = False
    bundle_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def token_choice(self):
        if self.use_remembered == (self.token is not None):
            raise ValueError("Choose a new token or the remembered token")
        if self.token is not None:
            raw = self.token.get_secret_value()
            if not 8 <= len(raw) <= 512 or not re.fullmatch(r"[A-Za-z0-9_.-]+", raw):
                raise ValueError("Token format is invalid")
        return self


class PublishInput(StrictModel):
    connection_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    bundle_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    approve_exact_bundle: Literal[True]
