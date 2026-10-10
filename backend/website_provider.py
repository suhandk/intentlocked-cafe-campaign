"""Netlify only. Secrets never enter exception messages, redirects or AI clients."""

import asyncio
import re
from typing import Protocol

import httpx
from pydantic import SecretStr


class HostingError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


MESSAGES = {
    "TOKEN_INVALID": "The token is invalid or expired. Enter a new Netlify token.",
    "TOKEN_SCOPE": "This token does not have permission for this operation.",
    "PROVIDER_LIMIT": "Netlify rate limited this request. No automatic retry was made.",
    "PROVIDER_FAILED": "Netlify operation failed. Preview and zip remain available.",
    "PUBLISH_UNCERTAIN": "The publish outcome is uncertain. Check Netlify before submitting again.",
    "URL_UNVERIFIED": "The deployed website could not be verified. It is not marked Published.",
}


class HostingProvider(Protocol):
    async def test(self, token: SecretStr) -> None: ...
    async def deploy(self, token: SecretStr, bundle: bytes) -> str: ...
    async def ready_url(self, token: SecretStr, deploy_id: str) -> str: ...
    async def verify(self, url: str, expected_html: bytes) -> None: ...


class NetlifyProvider:
    API = "https://api.netlify.com/api/v1"

    def __init__(self, transport=None, sleep=asyncio.sleep):
        self.transport, self.sleep = transport, sleep

    async def call(self, method, path, token, **kwargs):
        try:
            async with httpx.AsyncClient(
                transport=self.transport, timeout=20, follow_redirects=False, trust_env=False
            ) as client:
                response = await client.request(
                    method,
                    self.API + path,
                    headers={
                        "Authorization": "Bearer " + token.get_secret_value(),
                        "Content-Type": "application/zip"
                        if method == "POST"
                        else "application/json",
                    },
                    **kwargs,
                )
                if response.status_code == 401:
                    raise HostingError("TOKEN_INVALID")
                if response.status_code == 403:
                    raise HostingError("TOKEN_SCOPE")
                if response.status_code == 429:
                    raise HostingError("PROVIDER_LIMIT")
                if not 200 <= response.status_code < 300:
                    raise HostingError("PROVIDER_FAILED")
                return response.json()
        except (httpx.HTTPError, ValueError):
            raise HostingError(
                "PUBLISH_UNCERTAIN" if method == "POST" else "PROVIDER_FAILED"
            ) from None

    async def test(self, token):
        # Read-only. Successful listing cannot establish deploy permission.
        value = await self.call("GET", "/sites?per_page=1&page=1", token)
        if not isinstance(value, list):
            raise HostingError("PROVIDER_FAILED")

    async def deploy(self, token, bundle):
        value = await self.call("POST", "/sites", token, content=bundle)
        site_id = value.get("id")
        if not isinstance(site_id, str) or not re.fullmatch(r"[a-zA-Z0-9-]{1,100}", site_id):
            raise HostingError("PUBLISH_UNCERTAIN")
        return site_id

    async def ready_url(self, token, site_id):
        for _ in range(12):
            value = await self.call("GET", f"/sites/{site_id}", token)
            deployed = value.get("published_deploy") or {}
            if deployed.get("state") == "ready":
                url = value.get("ssl_url")
                if isinstance(url, str) and re.fullmatch(
                    r"https://[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.netlify\.app/?", url
                ):
                    return url
                raise HostingError("URL_UNVERIFIED")
            if value.get("state") in {"error", "failed"}:
                raise HostingError("PROVIDER_FAILED")
            await self.sleep(2)
        raise HostingError("URL_UNVERIFIED")

    async def verify(self, url, expected_html):
        # Separate client: no Authorization header, redirects or owner-supplied URL.
        if not re.fullmatch(r"https://[a-z0-9-]+\.netlify\.app/?", url):
            raise HostingError("URL_UNVERIFIED")
        try:
            async with httpx.AsyncClient(
                transport=self.transport, timeout=20, follow_redirects=False, trust_env=False
            ) as client:
                async with client.stream("GET", url) as response:
                    if response.status_code != 200:
                        raise HostingError("URL_UNVERIFIED")
                    received = bytearray()
                    async for chunk in response.aiter_bytes():
                        received.extend(chunk)
                        if len(received) > 2_000_000:
                            raise HostingError("URL_UNVERIFIED")
                    if bytes(received) != expected_html:
                        raise HostingError("URL_UNVERIFIED")
        except httpx.HTTPError:
            raise HostingError("URL_UNVERIFIED") from None
