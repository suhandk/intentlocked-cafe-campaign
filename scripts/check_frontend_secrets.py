"""Do not output credentials. Scan build bytes using private server configuration."""

from pathlib import Path

from backend.config import Settings


def main():
    config = Settings()
    needles = [b"B7_FRONTEND_SECRET_SENTINEL_DO_NOT_EXPOSE"]
    for secret in (
        config.inference_api_key,
        config.openai_api_key,
        config.nanobanana_api_key,
        config.ollama_api_key,
        config.meta_owner_token,
        config.meta_app_secret,
        config.meta_whatsapp_token,
        config.meta_facebook_token,
        config.meta_instagram_token,
        config.meta_webhook_verify_token,
        config.website_token_key,
        config.openrouter_api_key,
    ):
        if secret.get_secret_value():
            needles.append(secret.get_secret_value().encode())
    files = list(Path("frontend/.next").rglob("*"))
    assert files, "Build the frontend first"
    checked = 0
    for path in files:
        if path.is_file() and path.suffix in {".js", ".json", ".html", ".map", ".txt"}:
            checked += 1
            data = path.read_bytes()
            assert not any(needle in data for needle in needles), (
                "Credential appeared in frontend build"
            )
    print(f"PASS: {checked} frontend build files scanned; no credential contents emitted")


if __name__ == "__main__":
    main()
