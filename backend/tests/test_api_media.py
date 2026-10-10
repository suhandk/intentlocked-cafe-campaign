import hashlib

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.errors import ProviderError
from backend.main import create_app
from backend.media import download_image
from backend.mock import handler, mock_png


def test_health_ready_cost_trace_and_typed_404(tmp_path):
    app = create_app(Settings(_env_file=None, database_path=tmp_path / "db.sqlite"))
    with TestClient(app) as client:
        assert client.get("/api/health").json()["mode"] == "MOCK"
        assert client.get("/api/ready").status_code == 200
        assert client.get("/api/cost").json()["actual_billing"] == "unknown"
        assert client.get("/api/traces").json() == []
        error = client.get("/api/missing-route").json()
        assert set(error) == {"code", "message", "details", "trace_id", "retryable"}
        assert error["code"] == "NOT_FOUND"
        assert client.get("/api/openapi.json").status_code == 200
        assert client.get("/api/health", headers={"Host": "public.example"}).status_code == 400


async def test_image_download_hash_and_no_auth(tmp_path):
    def check(request):
        assert "authorization" not in request.headers
        return handler(request)

    artifact = await download_image(
        "https://mock.invalid/background.png", tmp_path, mock_transport=httpx.MockTransport(check)
    )
    assert artifact["width"] == artifact["height"] == 1024
    assert artifact["sha256"] == hashlib.sha256(mock_png()).hexdigest()
    assert (tmp_path / artifact["filename"]).read_bytes() == mock_png()


@pytest.mark.parametrize(
    "url",
    [
        "http://mock.invalid/a",
        "https://127.0.0.1/a",
        "https://localhost/a",
        "file:///etc/passwd",
        "https://evil.test/a",
        "https://user:pass@mock.invalid/a",
    ],
)
async def test_unsafe_download_url_rejected(tmp_path, url):
    with pytest.raises(ProviderError):
        await download_image(url, tmp_path, mock_transport=httpx.MockTransport(handler))


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(302, headers={"location": "http://127.0.0.1/private"}),
        httpx.Response(200, content=b"not png", headers={"content-type": "image/png"}),
        httpx.Response(200, content=b"<svg/>", headers={"content-type": "image/svg+xml"}),
        httpx.Response(200, content=mock_png(), headers={"content-type": "image/jpeg"}),
    ],
)
async def test_bad_media_or_redirect_rejected(tmp_path, response):
    with pytest.raises(ProviderError):
        await download_image(
            "https://mock.invalid/a",
            tmp_path,
            mock_transport=httpx.MockTransport(lambda _: response),
        )
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("host", ["platform-outputs.agnes-ai.space", "storage.googleapis.com"])
async def test_reviewed_live_host_pins_public_dns_tls_and_never_sends_credentials(
    tmp_path, monkeypatch, host
):
    import asyncio

    async def dns(*args, **kwargs):
        return [(2, 1, 6, "", ("93.184.216.34", 443))]

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", dns)
    original = httpx.AsyncClient

    def transport(request):
        assert request.url.host == "93.184.216.34"
        assert request.headers["Host"] == host
        assert request.extensions["sni_hostname"] == host
        assert "authorization" not in request.headers
        return httpx.Response(200, content=mock_png(), headers={"content-type": "image/png"})

    monkeypatch.setattr(
        "backend.media.httpx.AsyncClient",
        lambda **kwargs: original(**{**kwargs, "transport": httpx.MockTransport(transport)}),
    )
    art = await download_image(f"https://{host}/image.png", tmp_path)
    assert art["sha256"] == hashlib.sha256(mock_png()).hexdigest()


@pytest.mark.parametrize(
    "host",
    [
        "platform-outputs.agnes-ai.space.evil.test",
        "evil.agnes-ai.space",
        "platform-outputs-agnes-ai.space",
    ],
)
async def test_output_host_lookalikes_remain_rejected(tmp_path, host):
    with pytest.raises(ProviderError):
        await download_image(f"https://{host}/x.png", tmp_path)
