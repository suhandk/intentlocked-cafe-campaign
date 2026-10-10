import asyncio
import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import httpx
import pytest
from pydantic import ValidationError

from backend.config import Settings
from backend.contracts import SmokeResult
from backend.errors import ProviderError
from backend.inference_client import Budget, Queue, decode_result
from backend.mock import FIXTURES

TEXT = json.loads((FIXTURES / "text.json").read_text())
STRUCTURED = json.loads((FIXTURES / "structured.json").read_text())


async def test_default_mock_has_no_network_and_usage_is_separate(factory):
    client = factory()
    assert (await client.text("hello", client.budget())).startswith("MOCK")
    call = client.store.calls()[0]
    assert call.usage.total_tokens == 18
    assert call.list_price_estimate_usd > 0
    assert client.store.cost().known_list_price_estimate == 0
    assert client.store.cost().mock_calls == 1
    await client.close()


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "AUTH_FAILED"),
        (403, "AUTH_FAILED"),
        (400, "INVALID_REQUEST"),
        (422, "INVALID_REQUEST"),
    ],
)
async def test_auth_and_invalid_requests_not_retried(factory, status, code):
    client = factory(lambda _: httpx.Response(status, text="sensitive provider error"))
    with pytest.raises(ProviderError) as caught:
        await client.text("private transcript", client.budget())
    assert caught.value.body.code == code
    assert len(client.store.calls()) == 1
    assert "sensitive" not in str(caught.value)
    await client.close()


async def test_retry_after_and_rate_limit_with_fake_clock(factory):
    requests = []

    def handle(request):
        requests.append(request)
        return (
            httpx.Response(429, headers={"Retry-After": "11"})
            if len(requests) == 1
            else httpx.Response(200, json=TEXT)
        )

    client = factory(handle)
    await client.text("hello", client.budget())
    assert 11 in client.clock.sleeps
    assert len(client.store.calls()) == 2
    assert client.store.calls()[0].http_status == 429
    assert client.store.calls()[0].list_price_estimate_usd is None
    await client.close()


async def test_retry_after_http_date(factory):
    client = factory()
    date = format_datetime(datetime.now(UTC) + timedelta(seconds=15), usegmt=True)
    delay = client.retry_delay(httpx.Response(429, headers={"Retry-After": date}), 1)
    assert 13 <= delay <= 15
    await client.close()


@pytest.mark.parametrize("kind", ["500", "timeout"])
async def test_bounded_transport_retries(factory, kind):
    def handle(request):
        if kind == "timeout":
            raise httpx.ReadTimeout("secret must not appear", request=request)
        return httpx.Response(500)

    client = factory(handle)
    with pytest.raises(ProviderError, match="retry limit"):
        await client.text("hello", client.budget())
    assert len(client.store.calls()) == 3
    assert client.clock.value < 140
    await client.close()


@pytest.mark.parametrize("kind", ["timeout", "500"])
async def test_media_uncertainty_never_resubmits(factory, kind):
    def handle(request):
        if kind == "timeout":
            raise httpx.ReadTimeout("unknown outcome", request=request)
        return httpx.Response(500)

    client = factory(handle)
    with pytest.raises(ProviderError) as error:
        await client.image("art", client.budget())
    assert error.value.body.code == "SUBMISSION_UNCERTAIN"
    assert len(client.store.calls()) == 1
    await client.close()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d["choices"][0].update(finish_reason="length"),
        lambda d: d["choices"].append(deepcopy(d["choices"][0])),
        lambda d: d["choices"][0]["message"]["tool_calls"].append({}),
        lambda d: d["choices"][0]["message"]["tool_calls"][0]["function"].update(name="run_shell"),
        lambda d: d["choices"][0]["message"].update(content="extra result"),
        lambda d: d["choices"][0]["message"]["tool_calls"][0]["function"].update(arguments="{"),
        lambda d: d["choices"][0]["message"]["tool_calls"][0]["function"].update(
            arguments='{"message":"ok","lock":true}'
        ),
        lambda d: d["choices"][0]["message"]["tool_calls"][0]["function"].update(
            arguments='{"message":123}'
        ),
        lambda d: d["choices"][0]["message"]["tool_calls"][0]["function"].update(
            arguments='{"message":"one","message":"two"}'
        ),
        lambda d: d["choices"][0]["message"]["tool_calls"][0]["function"].update(arguments="[]"),
    ],
)
async def test_invalid_structured_response_bounded_repairs(factory, mutate):
    data = deepcopy(STRUCTURED)
    mutate(data)
    client = factory(lambda _: httpx.Response(200, json=data))
    with pytest.raises(ProviderError) as caught:
        await client.structured("hi", SmokeResult, client.budget())
    assert caught.value.body.code == "SCHEMA_INVALID"
    assert [c.repair for c in client.store.calls()] == [0, 1, 2]
    await client.close()


async def test_repair_receives_safe_validation_errors_and_no_bad_output(factory):
    requests = []

    def handle(request):
        requests.append(json.loads(request.content))
        data = deepcopy(STRUCTURED)
        if len(requests) == 1:
            data["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = (
                '{"message":"SECRET","injected":"Bearer SECRET"}'
            )
        return httpx.Response(200, json=data)

    client = factory(handle, inference_api_key="SECRET")
    value = await client.structured("greeting", SmokeResult, client.budget())
    assert value.message
    assert "validation_errors" in requests[1]["messages"][-1]["content"]
    assert "SECRET" not in json.dumps(requests)
    assert "SECRET" not in repr(client.store.calls())
    await client.close()


async def test_json_strategy_is_explicit_not_automatic(factory):
    payloads = []

    def handle(request):
        payloads.append(json.loads(request.content))
        data = deepcopy(TEXT)
        data["choices"][0]["message"]["content"] = '{"message":"hello"}'
        return httpx.Response(200, json=data)

    client = factory(handle)
    assert (
        await client.structured("hi", SmokeResult, client.budget(), strategy="json")
    ).message == "hello"
    assert "tools" not in payloads[0] and "response_format" not in payloads[0]
    await client.close()


@pytest.mark.parametrize(
    "usage",
    [
        None,
        {},
        {"prompt_tokens": -1},
        {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 99},
    ],
)
async def test_unknown_usage_is_not_zero(factory, usage):
    data = deepcopy(TEXT)
    data["usage"] = usage
    client = factory(lambda _: httpx.Response(200, json=data))
    await client.text("hello", client.budget())
    assert client.store.calls()[0].usage is None
    assert client.store.calls()[0].list_price_estimate_usd is None
    await client.close()


@pytest.mark.parametrize(
    "setting,value",
    [
        ("text_model", "gpt-4"),
        ("image_model", "agnes-image-other"),
        ("video_model", "random"),
        ("inference_base_url", "http://evil.test/v1"),
        ("inference_base_url", "https://apihub.agnes-ai.com/v1/v1"),
        ("enable_video", True),
        ("text_rpm", 11),
    ],
)
def test_startup_provider_policy(setting, value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{setting: value})


async def test_runtime_model_rejected_without_request(factory):
    client = factory()
    with pytest.raises(ProviderError) as error:
        await client.request("text", {"model": "other"}, client.budget())
    assert error.value.body.code == "MODEL_REJECTED"
    assert not client.store.calls()
    await client.close()


async def test_image_wire_shape(factory):
    captured = []

    def handle(request):
        captured.append(request)
        return httpx.Response(200, json={"data": [{"url": "https://mock.invalid/background.png"}]})

    client = factory(handle)
    await client.image("no writing", client.budget())
    body = json.loads(captured[0].content)
    assert str(captured[0].url) == "http://127.0.0.1:20128/v1/images/generations"
    assert body == {
        "model": "nb/nanobanana-flash",
        "prompt": "no writing",
        "size": "1024x1024",
        "n": 1,
        "response_format": "url",
    }
    assert "authorization" not in captured[0].headers
    await client.close()


async def test_total_call_budget_includes_repairs_and_retries(factory):
    client = factory(lambda _: httpx.Response(500))
    with pytest.raises(ProviderError) as error:
        await client.structured("hi", SmokeResult, client.budget(calls=2))
    assert error.value.body.code == "BUDGET_EXHAUSTED"
    assert len(client.store.calls()) == 2
    await client.close()


async def test_retry_after_cannot_outlive_deadline(factory):
    client = factory(lambda _: httpx.Response(429, headers={"Retry-After": "300"}))
    with pytest.raises(ProviderError) as error:
        await client.text("hi", client.budget(seconds=5))
    assert error.value.body.code == "BUDGET_EXHAUSTED"
    assert 300 not in client.clock.sleeps
    await client.close()


async def test_cancellation_releases_queue_and_records_no_secrets(factory):
    entered = asyncio.Event()

    async def handle(request):
        entered.set()
        await asyncio.Event().wait()

    client = factory(handle)
    task = asyncio.create_task(client.text("private", client.budget()))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert client.queue.active is False
    assert client.store.calls()[0].status == "cancelled"
    assert "private" not in repr(client.store.calls())
    await client.close()


async def test_priority_queue_has_starvation_prevention():
    queue, order = Queue(), []

    async def worker(n, priority):
        async with queue.slot(priority):
            order.append(n)
            await asyncio.sleep(0)

    async with queue.slot(0):
        tasks = [asyncio.create_task(worker("background", 1))]
        tasks += [asyncio.create_task(worker(i, 0)) for i in range(5)]
        await asyncio.sleep(0)
    await asyncio.gather(*tasks)
    assert order.index("background") <= 3


async def test_cached_mode_rejects_inference(factory):
    client = factory(inference_mode="cached")
    with pytest.raises(ProviderError, match="cannot make inference"):
        await client.text("hi", client.budget())
    await client.close()


def test_plain_text_rejects_truncated_or_multiple_results():
    for data in [
        {},
        {"choices": []},
        {"choices": [{"finish_reason": "length", "message": {"content": "hi"}}]},
    ]:
        with pytest.raises(ProviderError):
            decode_result(data)


def test_expired_budget():
    with pytest.raises(ProviderError):
        Budget(deadline=0).check(1)


async def test_failed_call_usage_is_retained(factory):
    client = factory(lambda _: httpx.Response(400, json={"usage": TEXT["usage"]}))
    with pytest.raises(ProviderError):
        await client.text("hi", client.budget())
    assert client.store.calls()[0].usage.total_tokens == 18
    assert client.store.calls()[0].list_price_estimate_usd > 0
    await client.close()


async def test_cancelled_waiter_is_not_a_sent_or_billed_request(factory):
    client = factory()
    async with client.queue.slot(0):
        task = asyncio.create_task(client.text("hi", client.budget()))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert client.store.calls()[0].sent is False
    assert client.store.cost().calls == 0
    assert not client.queue.active
    await client.close()


async def test_video_disabled_before_transport(factory):
    client = factory()
    with pytest.raises(ProviderError) as error:
        await client.request("video", {"model": client.settings.video_model}, client.budget())
    assert error.value.body.code == "VIDEO_DISABLED"
    assert not client.store.calls()
    await client.close()
