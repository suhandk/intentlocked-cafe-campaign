"""Isolated HTTPS wizard check with explicitly fake hosting; stop every owned process."""

import base64
import os
import socket
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from scripts.verify_workflow import stop

ROOT = Path(__file__).resolve().parents[1]


def create_app():
    # Uvicorn factory used only in this test script, never backend.main production.
    from backend.config import Settings
    from backend.main import create_app as main_app
    from backend.tests.test_generation import locked, seed
    from backend.tests.test_website import Provider
    from backend.website_provider import HostingError

    class FakeHosting(Provider):
        verification_only = True

        async def test(self, token):
            if token.get_secret_value().startswith("expired"):
                raise HostingError("TOKEN_INVALID")

    app = main_app(
        Settings(
            _env_file=None,
            inference_mode="mock",
            database_path=Path(os.environ["WEBSITE_TEST_DB"]),
            website_publish_enabled=True,
            website_token_key=os.environ["WEBSITE_TEST_KEY"],
        )
    )
    original = app.router.lifespan_context
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(app):
        async with original(app):
            seed(app.state.client, locked.__wrapped__())
            app.state.website.provider = FakeHosting()
            yield

    app.router.lifespan_context = lifespan
    return app


def main():
    for port in [3000, 3001, 8000]:
        with socket.socket() as probe:
            assert probe.connect_ex(("127.0.0.1", port)) != 0, "Stop existing app servers first"
    processes = []
    with tempfile.TemporaryDirectory(prefix="website-ui-") as folder:
        root = Path(folder)
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
        cert = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(UTC) - timedelta(minutes=1))
            .not_valid_after(datetime.now(UTC) + timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), False)
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), True)
            .sign(key, hashes.SHA256())
        )
        cert_path, key_path = root / "cert.pem", root / "tls-key.pem"
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        key_path.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        env = dict(
            os.environ,
            WEBSITE_TEST_DB=str(root / "test.sqlite3"),
            WEBSITE_TEST_KEY=base64.b64encode(os.urandom(32)).decode(),
            INFERENCE_MODE="mock",
            ENABLE_VIDEO="false",
            INFERENCE_API_KEY="",
            WEBSITE_UI_TEST="isolated-mock",
        )
        try:
            processes.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        "scripts.verify_website_ui:create_app",
                        "--factory",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        "8000",
                        "--ssl-certfile",
                        str(cert_path),
                        "--ssl-keyfile",
                        str(key_path),
                        "--no-access-log",
                    ],
                    cwd=ROOT,
                    env=env,
                )
            )
            processes.append(
                subprocess.Popen(
                    [
                        "node",
                        "node_modules/next/dist/bin/next",
                        "start",
                        "--hostname",
                        "127.0.0.1",
                        "--port",
                        "3001",
                    ],
                    cwd=ROOT / "frontend",
                    env=env,
                )
            )
            processes.append(
                subprocess.Popen(
                    ["node", "scripts/website_ui_proxy.mjs", str(cert_path), str(key_path)],
                    cwd=ROOT,
                    env=env,
                )
            )
            deadline = time.monotonic() + 30
            with httpx.Client(verify=str(cert_path), trust_env=False) as client:
                while True:
                    try:
                        if client.get("https://localhost:3000/api/ready").status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    assert time.monotonic() < deadline, "Verification server startup timed out"
                    time.sleep(0.2)
            result = subprocess.run(
                [
                    "node",
                    "node_modules/@playwright/test/cli.js",
                    "test",
                    "--config",
                    "playwright.website.config.ts",
                    "--reporter=line",
                ],
                cwd=ROOT / "frontend",
                env=env,
                timeout=150,
            )
            if result.returncode:
                raise SystemExit(result.returncode)
        finally:
            for process in reversed(processes):
                stop(process)


if __name__ == "__main__":
    main()
