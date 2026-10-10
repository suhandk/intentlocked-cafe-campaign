from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)
    inference_mode: Literal["mock", "live", "cached"] = "mock"
    inference_api_key: SecretStr = SecretStr("")
    image_provider: Literal["gateway", "openai"] = "gateway"
    openai_api_key: SecretStr = SecretStr("")
    inference_base_url: str = "http://127.0.0.1:20128/v1"
    # Upstream keys are for provisioning the gateway, never sent as its bearer token.
    nanobanana_api_key: SecretStr = SecretStr("")
    ollama_api_key: SecretStr = SecretStr("")
    media_allowed_hosts: list[str] = Field(default_factory=list)
    text_input_price_per_million: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    text_output_price_per_million: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    image_price_per_output: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    text_model: Literal["openai/gpt-4o-mini", "upstage/solar-mini4", "ollama/gpt-oss:120b"] = (
        "openai/gpt-4o-mini"
    )
    image_model: Literal[
        "black-forest-labs/flux-schnell",
        "bytedance-seed/seedream-5-0-flash",
        "nb/nanobanana-flash",
        "gpt-image-2.5-flare-2026-09-08",
    ] = "black-forest-labs/flux-schnell"
    video_model: Literal["disabled"] = "disabled"
    enable_video: Literal[False] = False
    video_entitlement_verified: bool = False
    enable_vision: bool = False
    local_video_enabled: bool = True
    text_rpm: int = Field(default=8, ge=1, le=10)
    image_rpm: int = Field(default=8, ge=1, le=10)
    video_rpm: Literal[1] = 1
    structured_strategy: Literal["tools", "json"] = "json"
    database_path: Path = Path("data/campaigns.sqlite3")
    asset_path: Path = Path("data/assets")
    render_origin: Literal["http://127.0.0.1:8000", "http://localhost:8000"] = (
        "http://127.0.0.1:8000"
    )
    today_override: str | None = None
    demo_fast: bool = False
    website_publish_enabled: bool = False
    website_owner_id: str = Field(default="local-owner", min_length=1, max_length=100)
    website_token_key: SecretStr = SecretStr("")
    openrouter_api_key: SecretStr = SecretStr("")
    website_ai_mode: Literal["mock", "live"] = "mock"
    website_model: Literal["qwen/qwen3-coder-flash"] = "qwen/qwen3-coder-flash"
    # Separate non-inference delivery boundary. Never exposed to the browser.
    meta_enabled: bool = False
    meta_mode: Literal["mock", "live"] = "mock"
    meta_graph_version: str = Field(default="v25.0", pattern=r"^v[0-9]+\.0$")
    meta_verified_platforms: list[Literal["whatsapp", "facebook", "instagram"]] = Field(
        default_factory=list
    )
    meta_owner_token: SecretStr = SecretStr("")
    meta_app_secret: SecretStr = SecretStr("")
    meta_webhook_verify_token: SecretStr = SecretStr("")
    meta_whatsapp_phone_id: str = Field(default="", pattern=r"^[0-9]*$")
    meta_whatsapp_business_id: str = Field(default="", pattern=r"^[0-9]*$")
    meta_whatsapp_token: SecretStr = SecretStr("")
    meta_facebook_page_id: str = Field(default="", pattern=r"^[0-9]*$")
    meta_facebook_token: SecretStr = SecretStr("")
    meta_instagram_account_id: str = Field(default="", pattern=r"^[0-9]*$")
    meta_instagram_token: SecretStr = SecretStr("")
    meta_public_origin: str = ""
    meta_request_timeout: float = Field(default=20, ge=1, le=60)
    meta_max_attempts: int = Field(default=3, ge=1, le=3)
    meta_poll_limit: int = Field(default=6, ge=1, le=12)
    # Verified static, parameter-free template: name:language -> exact approved body SHA256.
    meta_whatsapp_templates: dict[str, str] = Field(default_factory=dict)
    frontend_origin: Literal["http://127.0.0.1:3000", "http://localhost:3000"] = (
        "http://127.0.0.1:3000"
    )

    @field_validator("video_rpm", mode="before")
    @classmethod
    def parse_video_rpm(cls, value):
        # Environment values are strings; retain the exact one-per-minute policy.
        return 1 if value == "1" else value

    @property
    def image_generation_enabled(self) -> bool:
        from urllib.parse import urlsplit

        if self.image_provider == "openai":
            return self.inference_mode == "mock" or (
                self.inference_mode == "live" and bool(self.openai_api_key.get_secret_value())
            )
        return self.inference_mode == "mock" or (
            self.inference_mode == "live"
            and (
                urlsplit(self.inference_base_url).hostname != "openrouter.ai"
                or self.image_model == "bytedance-seed/seedream-5-0-flash"
            )
        )

    @property
    def vision_supported(self) -> bool:
        from urllib.parse import urlsplit

        if not self.enable_vision or self.text_model != "openai/gpt-4o-mini":
            return False
        if self.inference_mode == "mock":
            return True
        if self.image_provider == "openai":
            return bool(self.openai_api_key.get_secret_value())
        return urlsplit(self.inference_base_url).hostname == "openrouter.ai"

    @field_validator("enable_video", mode="before")
    @classmethod
    def parse_disabled_video(cls, value):
        return False if isinstance(value, str) and value.lower() in {"false", "0"} else value

    @field_validator(
        "text_input_price_per_million",
        "text_output_price_per_million",
        "image_price_per_output",
        mode="before",
    )
    @classmethod
    def unknown_price(cls, value):
        return None if value == "" else value

    @model_validator(mode="after")
    def enforce_policy(self):
        from urllib.parse import urlsplit

        self.inference_base_url = self.inference_base_url.rstrip("/")
        if (self.image_provider == "openai") != self.image_model.startswith("gpt-image-"):
            raise ValueError("Direct OpenAI image model must use IMAGE_PROVIDER=openai")
        if self.inference_base_url == "https://apihub.agnes-ai.com/v1":
            raise ValueError("Historical provider endpoints are not configured gateway endpoints")
        try:
            target = urlsplit(self.inference_base_url)
            port = target.port
        except ValueError:
            raise ValueError("Invalid INFERENCE_BASE_URL") from None
        local = target.hostname in {"127.0.0.1", "localhost", "::1"}
        if (
            not target.hostname
            or target.username
            or target.password
            or target.query
            or target.fragment
            or target.path not in {"/v1", "/api/v1"}
            or target.scheme not in {"http", "https"}
            or (target.scheme == "http" and not local)
            or (port is not None and not 1 <= port <= 65535)
        ):
            raise ValueError("Use an HTTP or HTTPS API gateway ending in /v1 or /api/v1")
        if (
            self.inference_mode == "live"
            and not local
            and not self.inference_api_key.get_secret_value()
        ):
            raise ValueError("Remote live inference requires server-side INFERENCE_API_KEY")
        for host in self.media_allowed_hosts:
            parsed = urlsplit("https://" + host)
            if not host or parsed.hostname != host or parsed.path or parsed.port or parsed.username:
                raise ValueError("MEDIA_ALLOWED_HOSTS must contain exact hostnames")
        if self.meta_public_origin:
            from urllib.parse import urlparse

            origin = urlparse(self.meta_public_origin)
            if (
                origin.scheme != "https"
                or not origin.hostname
                or origin.username
                or origin.password
                or origin.query
                or origin.fragment
                or origin.path not in {"", "/"}
                or origin.hostname in {"localhost", "127.0.0.1", "::1"}
            ):
                raise ValueError("META_PUBLIC_ORIGIN must be a public HTTPS origin")
            self.meta_public_origin = self.meta_public_origin.rstrip("/")
        if self.meta_enabled and len(self.meta_owner_token.get_secret_value()) < 32:
            raise ValueError(
                "Enabled delivery requires a private META_OWNER_TOKEN of at least 32 characters"
            )
        if self.meta_enabled and self.meta_mode == "live":
            if self.inference_mode != "live" or not self.meta_verified_platforms:
                raise ValueError(
                    "Live delivery requires live source mode and independently verified platforms"
                )
            if not self.meta_app_secret.get_secret_value():
                raise ValueError("Live delivery requires META_APP_SECRET for signing")
            for platform in self.meta_verified_platforms:
                identity, token = {
                    "whatsapp": (self.meta_whatsapp_phone_id, self.meta_whatsapp_token),
                    "facebook": (self.meta_facebook_page_id, self.meta_facebook_token),
                    "instagram": (self.meta_instagram_account_id, self.meta_instagram_token),
                }[platform]
                if not identity or not token.get_secret_value():
                    raise ValueError(
                        "Verified delivery platform is missing its account ID or token"
                    )
            if "whatsapp" in self.meta_verified_platforms and (
                not self.meta_whatsapp_business_id
                or not self.meta_webhook_verify_token.get_secret_value()
                or not self.meta_public_origin
            ):
                raise ValueError(
                    "Live WhatsApp requires business ID and public webhook configuration"
                )
            if "instagram" in self.meta_verified_platforms and not self.meta_public_origin:
                raise ValueError("Live Instagram requires a controlled public HTTPS media origin")
        if self.today_override:
            from datetime import date

            date.fromisoformat(self.today_override)
            if self.inference_mode == "live":
                raise ValueError(
                    "TODAY_OVERRIDE is only permitted in visibly labeled mock/demo mode"
                )
        return self
