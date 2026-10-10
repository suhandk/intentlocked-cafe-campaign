"""Raw Meta HTTP, finite reads/explicit throttling, no ambiguous POST replay."""

import hashlib
import hmac
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from uuid import uuid4

import httpx

from backend.inference_client import Clock
from backend.intent_rules import domain_error


def mock_handler(request):
    path = request.url.path
    if request.method == "GET":
        if "status_code" in request.url.params.get("fields", ""):
            return httpx.Response(200, json={"status_code": "FINISHED"})
        return httpx.Response(200, json={"id": "mock-account"})
    if path.endswith("/messages"):
        return httpx.Response(200, json={"messages": [{"id": "mock-wamid-" + uuid4().hex}]})
    return httpx.Response(200, json={"id": "mock-" + path.rsplit("/", 1)[-1] + "-" + uuid4().hex})


class MetaClient:
    def __init__(self, settings, *, clock=None, mock_transport=None):
        self.settings, self.clock = settings, clock or Clock()
        if mock_transport is not None and not isinstance(mock_transport, httpx.MockTransport):
            raise ValueError("Mock delivery accepts only an isolated MockTransport")
        # Even accidental test injection cannot enable networking in mock mode.
        self.http = httpx.AsyncClient(
            transport=(mock_transport or httpx.MockTransport(mock_handler))
            if settings.meta_mode == "mock"
            else None,
            trust_env=False,
            follow_redirects=False,
            timeout=settings.meta_request_timeout,
        )

    async def close(self):
        await self.http.aclose()

    def credentials(self, platform):
        s = self.settings
        return {
            "whatsapp": (s.meta_whatsapp_phone_id, s.meta_whatsapp_token),
            "facebook": (s.meta_facebook_page_id, s.meta_facebook_token),
            "instagram": (s.meta_instagram_account_id, s.meta_instagram_token),
        }[platform]

    async def request(
        self,
        platform,
        method,
        node,
        edge="",
        *,
        data=None,
        params=None,
        before=None,
        after=None,
        guard=None,
    ):
        identity, secret = self.credentials(platform)
        token = secret.get_secret_value()
        if self.settings.meta_mode == "live" and not (identity and token):
            raise domain_error("META_CONFIGURATION", "Configure this platform before delivery")
        if not node or any(ch not in "0123456789_abcdefghijklmnopqrstuvwxyz-" for ch in node):
            raise domain_error("META_PROTOCOL", "Provider returned an invalid identifier")
        if edge not in {"", "messages", "feed", "photos", "media", "media_publish"}:
            raise domain_error("META_PROTOCOL", "Unsupported provider operation")
        url = f"https://graph.facebook.com/{self.settings.meta_graph_version}/{node}"
        if edge:
            url += "/" + edge
        query = dict(params or {})
        if self.settings.meta_app_secret.get_secret_value():
            query["appsecret_proof"] = hmac.new(
                self.settings.meta_app_secret.get_secret_value().encode(),
                token.encode(),
                hashlib.sha256,
            ).hexdigest()
        deadline = self.clock.now() + 120
        for attempt in range(1, self.settings.meta_max_attempts + 1):
            if guard:
                guard()
            if self.clock.now() >= deadline:
                raise domain_error("META_DEADLINE", "Provider retry deadline reached")
            attempt_id = before(attempt) if before else None
            try:
                response = await self.http.request(
                    method,
                    url,
                    params=query,
                    headers={"Authorization": f"Bearer {token}"},
                    json=data if platform == "whatsapp" else None,
                    data=data if platform != "whatsapp" else None,
                )
            except (httpx.TimeoutException, httpx.TransportError):
                if after:
                    after(attempt_id, "unknown" if method == "POST" else "failed", None)
                raise domain_error(
                    "META_DELIVERY_UNKNOWN" if method == "POST" else "META_TIMEOUT",
                    "Submission may have been accepted; do not resend."
                    if method == "POST"
                    else "Provider read timed out; retry the read explicitly.",
                ) from None
            if after:
                after(attempt_id, "response", response.status_code)
            if response.status_code == 429:
                # Retry only an explicit rate-limit rejection, never a timeout or POST 5xx.
                try:
                    delay = float(response.headers.get("Retry-After", "1"))
                except ValueError:
                    try:
                        delay = (
                            parsedate_to_datetime(response.headers["Retry-After"])
                            - datetime.now(UTC)
                        ).total_seconds()
                    except (KeyError, ValueError, TypeError):
                        delay = 1
                if delay < 0:
                    delay = 0
                if not delay < 120 or self.clock.now() + delay >= deadline:
                    raise domain_error(
                        "META_RATE_LIMIT", "Rate limit exceeds the finite run budget"
                    )
                if attempt < self.settings.meta_max_attempts:
                    await self.clock.sleep(delay)
                    continue
                raise domain_error("META_RATE_LIMIT", "Rate limit attempt budget reached")
            if response.status_code >= 500:
                if method == "POST":
                    raise domain_error(
                        "META_DELIVERY_UNKNOWN", "Provider submission outcome is uncertain"
                    )
                if attempt < self.settings.meta_max_attempts:
                    await self.clock.sleep(float(attempt))
                    continue
                raise domain_error("META_UNAVAILABLE", "Provider read attempt budget reached")
            try:
                result = response.json()
            except ValueError:
                result = None
            if response.status_code >= 400 or isinstance(result, dict) and "error" in result:
                # Never echo Graph messages/headers: they can contain private destinations/tokens.
                code = (result.get("error") or {}).get("code") if isinstance(result, dict) else None
                name = (
                    "META_AUTH"
                    if response.status_code == 401 or code == 190
                    else (
                        "META_PERMISSION"
                        if response.status_code == 403 or code in {10, 200}
                        else "META_REJECTED"
                    )
                )
                raise domain_error(
                    name, "Provider rejected the request; check account permissions/configuration"
                )
            if response.status_code >= 300 or not isinstance(result, dict):
                raise domain_error(
                    "META_DELIVERY_UNKNOWN" if method == "POST" else "META_PROTOCOL",
                    "Provider returned an unexpected response; do not assume success",
                )
            return result
        raise domain_error("META_UNAVAILABLE", "Finite provider budget exhausted")
