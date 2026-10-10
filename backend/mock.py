import base64
import io
import json
from pathlib import Path

import httpx
from PIL import Image

FIXTURES = Path(__file__).parent / "fixtures"


def mock_png(ratio="1:1") -> bytes:
    buffer = io.BytesIO()
    sizes = {"1:1": (1024, 1024), "9:16": (576, 1024), "16:9": (1024, 576)}
    Image.new("RGB", sizes[ratio], "#eee2cb").save(buffer, format="PNG")
    return buffer.getvalue()


def handler(request: httpx.Request) -> httpx.Response:
    """Explicit development fixtures. This transport cannot open a network connection."""
    if request.url.host == "mock.invalid" and request.url.path == "/background.png":
        return httpx.Response(200, content=mock_png(), headers={"content-type": "image/png"})
    if request.url.host == "mock.invalid" and request.url.path.startswith("/background-"):
        ratio = {"/background-story.png": "9:16", "/background-landscape.png": "16:9"}.get(
            request.url.path, "1:1"
        )
        return httpx.Response(200, content=mock_png(ratio), headers={"content-type": "image/png"})
<<<<<<< HEAD
    # Both supported gateway API prefixes retain completely offline fixture routing.
    path = request.url.path
    if path.startswith("/api/v1/"):
        path = path.removeprefix("/api")
    if (
        request.method == "GET"
        and path == "/v1/images/models/bytedance-seed/seedream-5-0-flash/endpoints"
    ):
        return httpx.Response(
            200, json=json.loads((FIXTURES / "seedream_capabilities.json").read_text())
        )
    if request.method == "POST" and path == "/v1/images":
        payload = json.loads(request.content)
        if (
            set(payload) != {"model", "prompt", "n", "resolution", "aspect_ratio"}
            or payload.get("model") != "bytedance-seed/seedream-5-0-flash"
            or payload.get("n") != 1
            or payload.get("resolution") != "1K"
            or payload.get("aspect_ratio") not in {"1:1", "9:16", "16:9"}
        ):
            return httpx.Response(400, json={"error": "Unsupported mock image payload"})
        encoded = base64.b64encode(mock_png(payload["aspect_ratio"])).decode()
        return httpx.Response(
            200, json={"data": [{"b64_json": encoded, "media_type": "image/png"}]}
        )
    if path == "/v1/chat/completions":
=======
    if request.url.path in {"/v1/chat/completions", "/api/v1/chat/completions"}:
>>>>>>> e1bceadbfb88804d229fe0898f7d41be4bd5116f
        body = json.loads(request.content)
        system = body["messages"][0]["content"]
        if "ROLE: WEBSITE_DESIGN" in system:
            context = json.loads(json.loads(body["messages"][1]["content"])["input"])
            style = context["style"]
            result = {
                "layout": "split" if style == "modern" else "centered",
                "spacing": "airy" if style == "warm" else "balanced",
                "heading_style": "bold" if style == "modern" else "classic",
                "sections": "cards" if style == "warm" else "plain",
                "photo_layout": "grid",
            }
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {"message": {"content": json.dumps(result)}, "finish_reason": "stop"}
                    ]
                },
            )
        if any(f"ROLE: R{i}" in system for i in [5, 6, 7]):
            from backend.mock_optimization import critique_fixture, judge_fixture, reader_fixture

            inputs = json.loads(json.loads(body["messages"][1]["content"])["input"])
            role = next(i for i in [5, 6, 7] if f"ROLE: R{i}" in system)
            result = {5: judge_fixture, 6: critique_fixture, 7: reader_fixture}[role](inputs)
            data = json.loads((FIXTURES / "structured.json").read_text())
            if "tools" in body:
                data["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = (
                    json.dumps(result, ensure_ascii=False)
                )
            else:
                data["choices"][0] = {
                    "message": {"content": json.dumps(result, ensure_ascii=False)},
                    "finish_reason": "stop",
                }
            return httpx.Response(200, json=data)
        if "ROLE: R8" in system:
            from backend.mock_change import change_fixture

            inputs = json.loads(json.loads(body["messages"][1]["content"])["input"])
            result = change_fixture(inputs)
            data = json.loads((FIXTURES / "structured.json").read_text())
            if "tools" in body:
                data["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = (
                    json.dumps(result)
                )
            else:
                data["choices"][0] = {
                    "message": {"content": json.dumps(result)},
                    "finish_reason": "stop",
                }
            return httpx.Response(200, json=data)
        if "ROLE: R9" in system:
            result = {
                "recommendation": "usable",
                "image_loaded": True,
                "inspected_all_regions": True,
                "lettering_or_numbers": False,
                "logos_or_watermarks": False,
                "products_or_extra_items": False,
                "venue_features": False,
                "promotional_implications": False,
                "evidence": ["MOCK QA: explicit solid-color fixture contains no objects or marks."],
            }
            data = json.loads((FIXTURES / "structured.json").read_text())
            if "tools" in body:
                data["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = (
                    json.dumps(result)
                )
            else:
                data["choices"][0] = {
                    "message": {"content": json.dumps(result)},
                    "finish_reason": "stop",
                }
            return httpx.Response(200, json=data)
        if any(f"ROLE: R{i}" in system for i in range(1, 5)):
            from backend.mock_generation import copy_fixture, strategy_fixture
            from backend.mock_roles import intent_fixture, surface_fixture

            inputs = json.loads(json.loads(body["messages"][1]["content"])["input"])
            role = next(i for i in range(1, 5) if f"ROLE: R{i}" in system)
            result = {1: intent_fixture, 2: surface_fixture, 3: strategy_fixture, 4: copy_fixture}[
                role
            ](inputs)
            data = json.loads((FIXTURES / "structured.json").read_text())
            if "tools" in body:
                data["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = (
                    json.dumps(result, ensure_ascii=False)
                )
            else:
                data["choices"][0] = {
                    "message": {"content": json.dumps(result, ensure_ascii=False)},
                    "finish_reason": "stop",
                }
            return httpx.Response(200, json=data)
        name = "structured.json" if "tools" in body else "text.json"
        data = json.loads((FIXTURES / name).read_text())
        if "Return exactly one JSON object" in body["messages"][0]["content"]:
            data["choices"][0]["message"]["content"] = '{"message":"MOCK JSON result"}'
        return httpx.Response(200, json=data)
    if path == "/v1/images/generations":
        payload = json.loads(request.content)
        size = payload.get("size") or f"{payload.get('width', 1024)}x{payload.get('height', 1024)}"
        if payload.get("model", "").startswith("gpt-image-"):
            if size not in {"1024x1024", "864x1536", "1536x864"}:
                return httpx.Response(400, json={"error": "Unsupported mock size"})
            width, height = map(int, size.split("x"))
            buffer = io.BytesIO()
            Image.new("RGB", (width, height), "#eee2cb").save(buffer, format="PNG")
            return httpx.Response(
                200, json={"data": [{"b64_json": base64.b64encode(buffer.getvalue()).decode()}]}
            )
        ratio = {"1024x1024": "1:1", "576x1024": "9:16", "1024x576": "16:9"}[size]
        name = {"1:1": "background", "9:16": "background-story", "16:9": "background-landscape"}[
            ratio
        ]
        return httpx.Response(200, json={"data": [{"url": f"https://mock.invalid/{name}.png"}]})
    return httpx.Response(400, json={"error": "Unsupported mock operation"})
