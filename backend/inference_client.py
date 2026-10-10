"""One bounded OpenAI-compatible model gateway; no silent provider fallback."""

import asyncio
import base64
import io
import json
import random
import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Literal, TypeVar
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from PIL import Image
from pydantic import BaseModel, ValidationError

from backend.config import Settings
from backend.contracts import CallRecord, Usage, utc_now
from backend.db import Store
from backend.errors import ProviderError
from backend.mock import handler
from backend.work_context import work_guard, work_id

T = TypeVar("T", bound=BaseModel)


class DomainValidationError(ValueError):
    def __init__(self, error):
        self.error = error


class Clock:
    def now(self) -> float:
        return time.perf_counter()

    async def sleep(self, seconds: float):
        await asyncio.sleep(seconds)


@dataclass
class Budget:
    deadline: float
    max_calls: int = 6
    calls: int = 0
    run_id: str = field(default_factory=lambda: uuid4().hex)

    def check(self, now: float):
        if now >= self.deadline or self.calls >= self.max_calls:
            raise ProviderError("BUDGET_EXHAUSTED", "Run time or call budget exhausted")


class Queue:
    """Single-process serialized queue; background served after at most 3 interactive calls."""

    def __init__(self):
        self.waiters: list[tuple[int, asyncio.Future]] = []
        self.active = False
        self.interactive_streak = 0

    def dispatch(self):
        self.waiters = [(p, f) for p, f in self.waiters if not f.cancelled()]
        if self.active or not self.waiters:
            return
        preferred = 1 if self.interactive_streak >= 3 else 0
        index = next((i for i, (p, _) in enumerate(self.waiters) if p == preferred), 0)
        priority, future = self.waiters.pop(index)
        self.interactive_streak = self.interactive_streak + 1 if priority == 0 else 0
        self.active = True
        future.set_result(None)

    @asynccontextmanager
    async def slot(self, priority: int):
        if sum(not future.done() for _, future in self.waiters) >= 16:
            raise ProviderError(
                "QUEUE_FULL", "Inference queue is full. Wait or cancel pending work", retryable=True
            )
        future = asyncio.get_running_loop().create_future()
        self.waiters.append((priority, future))
        self.dispatch()
        acquired = False
        try:
            await future
            acquired = True
            yield
        finally:
            # A task can be cancelled just after dispatch but before await resumes.
            if acquired or (future.done() and not future.cancelled()):
                self.active = False
            else:
                future.cancel()
            self.dispatch()


def decode_result(data: dict, strategy: str | None = None):
    """Require one complete choice; never accept partial or unexpected tool execution."""
    try:
        choices = data["choices"]
        if not isinstance(choices, list) or len(choices) != 1:
            raise ValueError
        choice = choices[0]
        message = choice["message"]
        if strategy == "tools":
            calls = message.get("tool_calls", [])
            if choice["finish_reason"] != "tool_calls" or len(calls) != 1:
                raise ValueError
            call = calls[0]
            if call["type"] != "function" or call["function"]["name"] != "deliver_result":
                raise ValueError
            if message.get("content") not in (None, ""):
                raise ValueError
            return call["function"]["arguments"]
        if choice["finish_reason"] != "stop" or message.get("tool_calls"):
            raise ValueError
        content = message["content"].strip()
        if content.startswith("```json"):
            content = content[7:]
        elif content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        if not content:
            raise ValueError
        return content
    except (KeyError, TypeError, ValueError, IndexError):
        raise ProviderError(
            "INVALID_OUTPUT", "Expected exactly one complete Configured provider result"
        ) from None


class InferenceClient:
    def __init__(
        self,
        settings: Settings,
        store: Store,
        *,
        clock: Clock | None = None,
        mock_transport: httpx.MockTransport | None = None,
    ):
        self.settings, self.store = settings, store
        self.clock = clock or Clock()
        self.queue = Queue()
        self.next_call = {"text": 0.0, "image": 0.0, "video": 0.0, "poll": 0.0}
        # Tests may inject only a MockTransport, and only in mock mode.
        if mock_transport is not None and (
            settings.inference_mode != "mock" or not isinstance(mock_transport, httpx.MockTransport)
        ):
            raise ValueError("Transport injection is restricted to offline mocks")
        transport = (
            mock_transport or httpx.MockTransport(handler)
            if settings.inference_mode == "mock"
            else None
        )
        self.http = httpx.AsyncClient(
            transport=transport,
            trust_env=False,
            follow_redirects=False,
            timeout=httpx.Timeout(30, connect=10),
        )
        self.mock_transport = transport
        self.image_capabilities = None

    @property
    def openrouter_images(self):
        return self.settings.image_provider == "gateway" and (
            urlsplit(self.settings.inference_base_url).hostname == "openrouter.ai"
        )

    async def check_image_capabilities(self, payload, budget):
        """Read endpoint capabilities before a charged submission; mocks use mock HTTP only."""
        if self.image_capabilities is None:
            try:
                async with asyncio.timeout(max(0.001, budget.deadline - self.clock.now())):
                    response = await self.http.get(
                        self.settings.inference_base_url
                        + "/images/models/"
                        + self.settings.image_model
                        + "/endpoints",
                        timeout=15,
                    )
                if response.status_code != 200:
                    raise ValueError
                document = response.json()
                if document.get("id") != self.settings.image_model:
                    raise ValueError
                endpoints = document["endpoints"]
                if not isinstance(endpoints, list) or not endpoints:
                    raise ValueError
                self.image_capabilities = [e["supported_parameters"] for e in endpoints]
            except (ValueError, KeyError, TypeError, httpx.HTTPError, TimeoutError):
                raise ProviderError(
                    "IMAGE_CAPABILITY_UNAVAILABLE", "Image endpoint capabilities unavailable"
                ) from None
        if set(payload) != {"model", "prompt", "n", "resolution", "aspect_ratio"}:
            raise ProviderError("INVALID_REQUEST", "Unsupported image transport fields")
        for capabilities in self.image_capabilities:
            for name in ("resolution", "aspect_ratio", "n"):
                descriptor = capabilities.get(name, {})
                value = payload[name]
                accepted = (
                    descriptor.get("type") == "enum" and value in descriptor.get("values", [])
                ) or (
                    descriptor.get("type") == "range"
                    and type(value) is int
                    and descriptor.get("min", 1) <= value <= descriptor.get("max", 0)
                )
                if not accepted:
                    raise ProviderError(
                        "IMAGE_PARAMETER_UNSUPPORTED", "Image endpoint rejected a capability"
                    )

    async def close(self):
        await self.http.aclose()

    def budget(self, *, calls=6, seconds=120) -> Budget:
        return Budget(self.clock.now() + seconds, calls)

    def retry_delay(self, response: httpx.Response | None, attempt: int) -> float:
        if response is not None:
            value = response.headers.get("retry-after", "")
            try:
                return max(0, float(value))
            except ValueError:
                try:
                    return max(
                        0, (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds()
                    )
                except (ValueError, TypeError, OverflowError):
                    pass
        return min(8, 2 ** (attempt - 1)) + random.uniform(0, 0.25)

    async def request(
        self,
        operation: Literal["text", "image", "video", "poll"],
        payload: dict,
        budget: Budget,
        *,
        repair=0,
        priority=0,
    ) -> dict:
        if self.settings.inference_mode == "cached":
            raise ProviderError(
                "INFERENCE_DISABLED", "Saved-output mode cannot make inference calls"
            )
        expected = {
            "text": self.settings.text_model,
            "image": self.settings.image_model,
            "video": self.settings.video_model,
            "poll": self.settings.video_model,
        }[operation]
        if payload.get("model", payload.get("model_name")) != expected:
            raise ProviderError("MODEL_REJECTED", "Model is not allowed for this operation")
        if operation in ("video", "poll") and not self.settings.enable_video:
            raise ProviderError("VIDEO_DISABLED", "Video is disabled")
        if operation == "image" and not self.settings.image_generation_enabled:
            raise ProviderError(
                "IMAGE_KEY_MISSING"
                if self.settings.image_provider == "openai"
                else "IMAGE_TRANSPORT_UNVERIFIED",
                "Add OPENAI_API_KEY to the backend .env and restart, or choose local artwork."
                if self.settings.image_provider == "openai"
                else "Configured image model has no verified adapter for this endpoint. "
                "Choose local artwork or configure a compatible image gateway.",
            )
        if self.settings.inference_mode != "mock":
            if operation in ("video", "poll"):
                raise ProviderError("VIDEO_DISABLED", "No configured video capability is verified")
            if (
                operation == "text"
                and not self.settings.vision_supported
                and any(
                    isinstance(message.get("content"), list)
                    and any(
                        part.get("type") == "image_url"
                        for part in message["content"]
                        if isinstance(part, dict)
                    )
                    for message in payload.get("messages", [])
                    if isinstance(message, dict)
                )
            ):
                raise ProviderError(
                    "VISION_UNSUPPORTED", "No configured vision capability is verified"
                )
        path = {
            "text": "/chat/completions",
            "image": "/images/generations",
            "video": "/videos",
            "poll": "",
        }[operation]
        if operation == "image" and self.openrouter_images:
            await self.check_image_capabilities(payload, budget)
            path = "/images"
        url = self.settings.inference_base_url + (
            "/mock-video-status" if operation == "poll" else path
        )
        secret = self.settings.inference_api_key.get_secret_value()
        wire_payload = payload
        has_vision = operation == "text" and any(
            isinstance(m.get("content"), list)
            and any(p.get("type") == "image_url" for p in m["content"] if isinstance(p, dict))
            for m in payload.get("messages", [])
        )
        if self.settings.image_provider == "openai" and (operation == "image" or has_vision):
            url = "https://api.openai.com/v1" + path
            secret = self.settings.openai_api_key.get_secret_value()
            if self.settings.inference_mode == "live" and not secret:
                raise ProviderError("IMAGE_KEY_MISSING", "Add OPENAI_API_KEY and restart backend")
            if has_vision:
                wire_payload = {**payload, "model": "gpt-4o-mini"}
        headers = (
            {"Authorization": "Bearer " + secret}
            if self.settings.inference_mode == "live" and secret
            else {}
        )
        provider_name = (
            "OpenAI"
            if urlsplit(url).hostname == "api.openai.com"
            else "OpenRouter"
            if urlsplit(url).hostname == "openrouter.ai"
            else "Configured gateway"
        )
        # Nine-cell multilingual batches need longer than a tiny smoke response.
        # The shared absolute budget still bounds queue waits, retries and repairs.
        timeout = (
            90
            if operation in ("image", "video")
            else 60
            if operation == "text" and payload.get("max_tokens", 0) > 4096
            else 30
        )
        for attempt in range(1, 4):
            if work_guard.get():
                work_guard.get()()
            budget.check(self.clock.now())
            queued = self.clock.now()
            response = None
            status = "failed"
            usage = None
            estimate = None
            reported_cost = None
            began = queued
            sent = False
            trace_id = uuid4().hex
            call_id = uuid4().hex
            should_retry = False
            try:
                async with asyncio.timeout(max(0.001, budget.deadline - self.clock.now())):
                    async with self.queue.slot(priority):
                        delay = (
                            0
                            if self.settings.inference_mode == "mock" and self.settings.demo_fast
                            else max(0, self.next_call[operation] - self.clock.now())
                        )
                        if self.clock.now() + delay >= budget.deadline:
                            raise ProviderError(
                                "BUDGET_EXHAUSTED", "Queue wait exceeds run deadline"
                            )
                        await self.clock.sleep(delay)
                        if work_guard.get():
                            work_guard.get()()
                        budget.check(self.clock.now())
                        began = self.clock.now()
                        budget.calls += 1
                        sent = True
                        rpm = {
                            "text": self.settings.text_rpm,
                            "image": self.settings.image_rpm,
                            "video": 1,
                            "poll": 30,
                        }[operation]
                        self.next_call[operation] = began + 60 / rpm
                        # Persist dispatch before awaiting HTTP. A crash leaves an unknown-cost
                        # attempt, rather than losing a possibly charged submission.
                        self.store.record(
                            CallRecord(
                                id=call_id,
                                trace_id=trace_id,
                                run_id=budget.run_id,
                                work_id=work_id.get(),
                                timestamp=utc_now(),
                                mode=self.settings.inference_mode,
                                model=expected,
                                provider=provider_name,
                                transport_endpoint=url,
                                operation=operation,
                                attempt=attempt,
                                repair=repair,
                                status="in_flight",
                                sent=True,
                                queue_wait_ms=max(0, began - queued) * 1000,
                                duration_ms=0,
                            )
                        )
                        response = await self.http.request(
                            "GET" if operation == "poll" else "POST",
                            url,
                            headers=headers,
                            params=payload if operation == "poll" else None,
                            json=wire_payload if operation != "poll" else None,
                            timeout=min(timeout, budget.deadline - began),
                        )
                # Usage may be returned even for a failed/charged request.
                try:
                    usage_body = response.json()
                    provider_cost = usage_body.get("usage", {}).get("cost")
                    if type(provider_cost) in (float, int) and 0 <= provider_cost < 1e6:
                        reported_cost = provider_cost
                    returned_usage = usage_body.get("usage")
                    # Providers add cost and token-detail objects to the raw usage shape.
                    # Keep only the three strict counters, without inventing absent counts.
                    usage = (
                        Usage.model_validate(
                            {
                                key: returned_usage[key]
                                for key in ("prompt_tokens", "completion_tokens", "total_tokens")
                                if key in returned_usage
                            }
                        )
                        if isinstance(returned_usage, dict)
                        else None
                    )
                    if (
                        usage
                        and usage.total_tokens != usage.prompt_tokens + usage.completion_tokens
                    ):
                        usage = None
                except (ValueError, TypeError, AttributeError):
                    usage = None
                if operation == "text" and usage:
                    input_price = self.settings.text_input_price_per_million
                    output_price = self.settings.text_output_price_per_million
                    if input_price is not None and output_price is not None:
                        estimate = (
                            usage.prompt_tokens * input_price
                            + usage.completion_tokens * output_price
                        ) / 1e6
                if response.status_code in (401, 403):
                    raise ProviderError(
                        "AUTH_FAILED", "Configured provider authentication or entitlement failed"
                    )
                if response.status_code == 402:
                    raise ProviderError("PAYMENT_REQUIRED", "Provider credits or payment required")
                if response.status_code == 429:
                    try:
                        quota = response.json().get("error", {}).get("code") == "insufficient_quota"
                    except (ValueError, AttributeError):
                        quota = False
                    if quota:
                        raise ProviderError(
                            "PAYMENT_REQUIRED", "Provider quota or credits exhausted"
                        )
                if response.status_code == 429:
                    should_retry = True
                elif response.status_code >= 500:
                    if operation in ("image", "video"):
                        raise ProviderError(
                            "SUBMISSION_UNCERTAIN", "Media submission outcome is unknown"
                        )
                    should_retry = True
                elif not response.is_success:
                    raise ProviderError(
                        "INVALID_REQUEST",
                        f"Provider rejected request (HTTP {response.status_code})",
                    )
                if not should_retry:
                    if work_guard.get():
                        work_guard.get()()
                    try:
                        data = response.json()
                        if not isinstance(data, dict):
                            raise ValueError
                    except (ValueError, TypeError):
                        raise ProviderError(
                            "INVALID_OUTPUT", "Configured provider response is not a JSON object"
                        ) from None
                    if (
                        operation == "image"
                        and isinstance(data.get("data"), list)
                        and len(data["data"]) == 1
                        and isinstance(data["data"][0], dict)
                        and (
                            isinstance(data["data"][0].get("url"), str)
                            or isinstance(data["data"][0].get("b64_json"), str)
                        )
                    ):
                        estimate = self.settings.image_price_per_output
                    status = "http_completed"
                    return data
            except asyncio.CancelledError:
                status = (
                    "cancelled_uncertain"
                    if sent and operation in ("image", "video")
                    else "cancelled"
                )
                raise
            except (httpx.TransportError, TimeoutError):
                if sent and operation in ("image", "video"):
                    status = "submission_uncertain"
                    raise ProviderError(
                        "SUBMISSION_UNCERTAIN", "Media submission outcome is unknown"
                    ) from None
                should_retry = True
            except ProviderError as exc:
                status = exc.body.code.lower()
                exc.body.trace_id = trace_id
                raise
            finally:
                self.store.record(
                    CallRecord(
                        id=call_id,
                        trace_id=trace_id,
                        run_id=budget.run_id,
                        work_id=work_id.get(),
                        timestamp=utc_now(),
                        mode=self.settings.inference_mode,
                        model=expected,
                        provider=provider_name,
                        transport_endpoint=url,
                        operation=operation,
                        attempt=attempt,
                        repair=repair,
                        status=status,
                        sent=sent,
                        http_status=response.status_code if response is not None else None,
                        queue_wait_ms=max(0, began - queued) * 1000,
                        duration_ms=max(0, self.clock.now() - began) * 1000,
                        usage=usage,
                        list_price_estimate_usd=estimate,
                        provider_reported_cost_usd=reported_cost,
                    )
                )
            if should_retry and attempt < 3:
                delay = self.retry_delay(response, attempt)
                if self.clock.now() + delay >= budget.deadline:
                    raise ProviderError("BUDGET_EXHAUSTED", "Retry-After exceeds run deadline")
                await self.clock.sleep(delay)
            else:
                raise ProviderError(
                    "PROVIDER_UNAVAILABLE",
                    "Configured provider retry limit reached",
                    retryable=True,
                )
        raise AssertionError("Unreachable")

    async def text(self, prompt: str, budget: Budget, *, image_url: str | None = None) -> str:
        content = (
            prompt
            if image_url is None
            else [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": image_url}},
            ]
        )
        data = await self.request(
            "text",
            {
                "model": self.settings.text_model,
                "messages": [{"role": "user", "content": content}],
                "temperature": 0,
                "max_tokens": 256,
            },
            budget,
        )
        return decode_result(data)

    async def structured(
        self,
        prompt: str,
        schema: type[T],
        budget: Budget,
        *,
        strategy: str | None = None,
        system_prompt: str = "",
        max_tokens: int = 1024,
        vision_image: str | None = None,
        validate: Callable[[T], None] | None = None,
        wire_schema: dict | None = None,
        json_mode: bool = False,
    ) -> T:
        strategy = strategy or self.settings.structured_strategy
        if strategy not in ("tools", "json"):
            raise ValueError("Unsupported structured strategy")
        provider_schema = wire_schema or schema.model_json_schema()
        messages = [
            {
                "role": "system",
                "content": (
                    "Return exactly one JSON object matching the schema. No markdown. "
                    if strategy == "json"
                    else "Return exactly one deliver_result function call. "
                )
                + system_prompt
                + "\n"
                + json.dumps(provider_schema),
            },
            {
                "role": "user",
                "content": json.dumps({"input": prompt})
                if vision_image is None
                else [
                    {"type": "text", "text": json.dumps({"input": prompt})},
                    {"type": "image_url", "image_url": {"url": vision_image}},
                ],
            },
        ]
        for repair in range(3):
            payload = {
                "model": self.settings.text_model,
                "messages": messages,
                "temperature": 0,
                "max_tokens": min(max(max_tokens, 1), 8192),
            }
            if strategy == "tools":
                payload.update(
                    {
                        "tools": [
                            {
                                "type": "function",
                                "function": {
                                    "name": "deliver_result",
                                    "description": "Return the validated result",
                                    "parameters": provider_schema,
                                },
                            }
                        ],
                        "tool_choice": {"type": "function", "function": {"name": "deliver_result"}},
                    }
                )
            elif json_mode:
                payload["response_format"] = {"type": "json_object"}
                if self.settings.inference_base_url == "https://openrouter.ai/api/v1":
                    payload["provider"] = {"require_parameters": True}
            try:
                data = await self.request("text", payload, budget, repair=repair)
                raw = decode_result(data, strategy)
                parsed = json.loads(raw, object_pairs_hook=unique_object)
                if not isinstance(parsed, dict):
                    raise ValueError
                # Normalize only the known result envelope, then retain strict validation.
                # No recursive coercion, duplicate keys, markdown or arbitrary JSON repair.
                if (
                    set(parsed) == {"result"}
                    and "discriminator"
                    in schema.model_json_schema()["properties"].get("result", {})
                    and isinstance(parsed["result"], str)
                ):
                    parsed["result"] = json.loads(parsed["result"], object_pairs_hook=unique_object)
                    if not isinstance(parsed["result"], dict):
                        raise ValueError
                result = schema.model_validate(parsed)
                if validate is not None:
                    try:
                        validate(result)
                    except ProviderError as error:
                        raise DomainValidationError(error) from None
                return result
            except (ValidationError, ValueError, TypeError, ProviderError) as exc:
                if isinstance(exc, ProviderError) and exc.body.code != "INVALID_OUTPUT":
                    raise
                # Error types only: no raw output, prompt, secret, or rejected input values.
                errors = (
                    [
                        {
                            "type": e["type"],
                            "path": [
                                part
                                if isinstance(part, int) or part in schema_fields(schema)
                                else "*"
                                for part in e["loc"]
                            ],
                        }
                        for e in exc.errors(include_input=False)
                    ]
                    if isinstance(exc, ValidationError)
                    else [
                        {
                            "type": "domain_validation",
                            "code": exc.error.body.code
                            if exc.error.body.code
                            in {"FORMS_INVALID", "INVALID_PROPOSAL", "INVALID_EVIDENCE"}
                            else "validation_failed",
                        }
                    ]
                    if isinstance(exc, DomainValidationError)
                    else [{"type": "invalid_structure"}]
                )
                if repair == 2:
                    if isinstance(exc, DomainValidationError):
                        raise exc.error from None
                    error = ProviderError(
                        "SCHEMA_INVALID", "Structured output failed after two repairs"
                    )
                    error.body.details = {"validation_errors": [json.dumps(e) for e in errors]}
                    raise error from None
                messages.append(
                    {"role": "user", "content": json.dumps({"validation_errors": errors})}
                )
        raise AssertionError("Unreachable")

    async def image(self, prompt: str, budget: Budget, *, ratio: str = "1:1") -> str:
        if ratio not in {"1:1", "9:16", "16:9"}:
            raise ValueError("Unsupported native ratio")
        dims = {"1:1": (1024, 1024), "9:16": (576, 1024), "16:9": (1024, 576)}[ratio]
        payload = {
            "model": self.settings.image_model,
            "prompt": prompt,
            "n": 1,
        }
        if self.settings.image_provider == "openai":
            dims = {"1:1": (1024, 1024), "9:16": (864, 1536), "16:9": (1536, 864)}[ratio]
            payload.update(size=f"{dims[0]}x{dims[1]}", quality="medium", output_format="png")
        elif self.openrouter_images:
            payload.update(resolution="1K", aspect_ratio=ratio)
        elif self.settings.image_model == "nb/nanobanana-flash":
            payload.update(size=f"{dims[0]}x{dims[1]}", response_format="url")
        else:
            payload.update(width=dims[0], height=dims[1])
        data = await self.request("image", payload, budget)
        try:
            if not isinstance(data.get("data"), list) or len(data["data"]) != 1:
                raise ValueError
            item = data["data"][0]
            url = item.get("url")
            if not url and isinstance(item.get("b64_json"), str):
                encoded = item["b64_json"]
                if len(encoded) > 16 * 1024 * 1024:
                    raise ValueError
                raw = base64.b64decode(encoded, validate=True)
                with Image.open(io.BytesIO(raw)) as im:
                    mime = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}.get(
                        im.format
                    )
                if not mime or item.get("media_type", mime) != mime:
                    raise ValueError
                url = "data:" + mime + ";base64," + encoded
            if not isinstance(url, str) or not url:
                raise ValueError
            return url
        except (KeyError, TypeError, ValueError, AttributeError, OSError):
            raise ProviderError("INVALID_OUTPUT", "Expected one generated image URL") from None


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON property")
        result[key] = value
    return result


def schema_fields(schema):
    """Whitelist schema-owned names so repair paths cannot echo hostile values."""
    document = schema.model_json_schema()
    names = set(document.get("properties", {}))
    for definition in document.get("$defs", {}).values():
        names.update(definition.get("properties", {}))
    return names


def success_wire_schema(schema, success_name):
    """Inline the known success contract for providers with weak union/$ref support.

    This is a wire hint only. Original strict result/failure schemas still validate
    returned data; this cannot invent fields, grant approval or coerce a bad value.
    """
    document = schema.model_json_schema()
    definitions = document["$defs"]

    def inline(value):
        if isinstance(value, list):
            return [inline(v) for v in value]
        if not isinstance(value, dict):
            return value
        if "$ref" in value:
            return inline(definitions[value["$ref"].split("/")[-1]])
        result = {k: inline(v) for k, v in value.items() if k not in {"$defs", "discriminator"}}
        # Pydantic defaults make status optional in JSON Schema, but the public
        # discriminated result union requires the tag in the returned JSON.
        if "status" in result.get("properties", {}):
            result["required"] = list(dict.fromkeys([*result.get("required", []), "status"]))
        return result

    result = inline(definitions[success_name])
    return {
        "type": "object",
        "properties": {"result": result},
        "required": ["result"],
        "additionalProperties": False,
    }
