"""Freeze audit of public source/evidence/build; private .env is intentionally excluded."""

import json
import re
import subprocess
from pathlib import Path

from backend.config import Settings
from backend.contracts import utc_now


def main():
    settings = Settings()
    secrets = [
        value.get_secret_value()
        for value in (
            settings.inference_api_key,
            settings.openai_api_key,
            settings.nanobanana_api_key,
            settings.ollama_api_key,
            settings.meta_owner_token,
            settings.meta_app_secret,
            settings.meta_instagram_token,
            settings.meta_facebook_token,
            settings.meta_whatsapp_token,
            settings.meta_webhook_verify_token,
            settings.website_token_key,
            settings.openrouter_api_key,
        )
        if value.get_secret_value()
    ]
    inventory = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard"], check=True, capture_output=True, text=True
    ).stdout.splitlines()
    assert not any(Path(p).name == ".env" for p in inventory), "Private .env is tracked"
    paths = {Path(p) for p in inventory if Path(p).is_file()}
    # Next's active dev lock is an OS coordination file, not a build artifact.
    paths.update(p for p in Path("frontend/.next").rglob("*") if p.is_file() and p.name != "lock")
    rules = {
        "provider_key_pattern": re.compile(rb"\bsk-[A-Za-z0-9_-]{24,}\b"),
        "private_key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        "literal_env_key": re.compile(
            rb"(?m)^(?:INFERENCE|OPENAI|OLLAMA|NANOBANANA)_API_KEY[ \t]*=[ \t]*[^\s#\"']{16,}"
        ),
    }
    findings = []
    for path in sorted(paths):
        raw = path.read_bytes()
        for name, pattern in rules.items():
            if pattern.search(raw):
                findings.append({"path": path.as_posix(), "rule": name})
        if any(secret.encode() in raw for secret in secrets):
            findings.append({"path": path.as_posix(), "rule": "configured_key_bytes"})
    report = {
        "timestamp": utc_now(),
        "status": "PASS" if not findings else "FAIL",
        "files_checked": len(paths),
        "configured_key_checked": bool(secrets),
        "private_env_excluded": True,
        "findings": findings,
        "limits": "Known configured key and defined patterns only; "
        "not a universal secret detector.",
    }
    Path("docs/evidence/b8-secret-scan.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report))
    if findings:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
