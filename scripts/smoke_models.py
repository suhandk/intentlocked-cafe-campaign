"""Run with python -m scripts.smoke_models; mock is offline, live is explicit."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.config import Settings
from backend.contracts import SmokeResult, utc_now
from backend.db import Store
from backend.errors import ProviderError
from backend.inference_client import InferenceClient, decode_result
from backend.media import download_image


async def run(args) -> int:
    # Validate settings without ever printing a ValidationError containing environment inputs.
    try:
        settings = Settings(inference_mode=args.mode)
    except ValueError:
        print("Configuration invalid or live key missing. No inference request was made.")
        return 2
    store = Store(settings.database_path)
    client = InferenceClient(settings, store)
    existing_call_ids = {call.id for call in store.calls()}
    results = []
    report = {
        "timestamp": utc_now(),
        "mode": args.mode,
        "schema_version": "b0.1",
        "text_endpoint": settings.inference_base_url,
        "image_provider": settings.image_provider,
        "capabilities": results,
        "calls": [],
    }
    budget = client.budget(calls=16, seconds=300)
    passed = "MOCK_PASSED" if args.mode == "mock" else "VERIFIED"

    async def probe(name, model, action):
        try:
            details = await action()
            results.append(
                {"capability": name, "model": model, "status": passed, "details": details}
            )
            return details
        except ProviderError as exc:
            results.append(
                {
                    "capability": name,
                    "model": model,
                    "status": "FAILED",
                    "code": exc.body.code,
                    "message": exc.body.message,
                }
            )
            return None

    try:

        async def text_probe():
            answer = await client.text(
                "Reply with a short greeting. Do not include personal data.", budget
            )
            return {"nonempty_text": bool(answer.strip()), "response_text_omitted": True}

        await probe("text", settings.text_model, text_probe)

        async def structured_probe(strategy):
            value = await client.structured(
                "Return a greeting in message.", SmokeResult, budget, strategy=strategy
            )
            return {"strategy": strategy, "validated": bool(value.message)}

        structured = await probe(
            "structured_tools", settings.text_model, lambda: structured_probe("tools")
        )
        if structured is None:
            # Explicit capability negotiation; not a provider or cached-output fallback.
            await probe("structured_json", settings.text_model, lambda: structured_probe("json"))

        try:
            decode_result({"choices": [{"finish_reason": "length", "message": {"content": "{"}}]})
        except ProviderError:
            results.append({"capability": "local_truncation_rejection", "status": "LOCAL_PASSED"})
        else:
            raise AssertionError("Truncation accepted")

        image_url = None

        async def image_probe():
            nonlocal image_url
            image_url = await client.image(
                "Commercial coffee photograph: an unbranded ceramic coffee mug in warm amber "
                "light, dark espresso studio backdrop, cup visible at lower right, creative "
                "depth and subtle steam. No text, lettering, numbers, logos, extra food, "
                "signs or watermarks. Negative space upper left.",
                budget,
            )
            artifact = await download_image(
                image_url,
                settings.asset_path,
                mock_transport=client.mock_transport,
                allowed_hosts=settings.media_allowed_hosts,
            )
            if (artifact["width"], artifact["height"]) != (1024, 1024):
                raise ProviderError(
                    "IMAGE_DIMENSIONS", "1K square output dimensions differ from expected"
                )
            return artifact

        if args.mode == "live" and not settings.image_generation_enabled:
            results.append(
                {
                    "capability": "image_1k_download",
                    "model": settings.image_model,
                    "status": "NOT_TESTED",
                    "reason": "Image key or supported transport is missing",
                }
            )
        else:
            await probe("image_1k_download", settings.image_model, image_probe)

        if args.vision and image_url and (args.mode == "mock" or settings.vision_supported):

            async def vision_probe():
                answer = await client.text(
                    "Describe whether this background has visible lettering.",
                    budget,
                    image_url=image_url,
                )
                return {"nonempty_response": bool(answer.strip()), "quality_approval": False}

            await probe("public_image_vision", settings.text_model, vision_probe)
        else:
            results.append(
                {
                    "capability": "public_image_vision",
                    "status": "NOT_TESTED" if not args.vision or not image_url else "UNSUPPORTED",
                    "reason": "Vision needs --vision, an image and supported configured vision",
                }
            )
        results.append(
            {
                "capability": "video",
                "status": "UNSUPPORTED",
                "reason": "No video model is configured",
            }
        )
        calls = [c for c in store.calls() if c.id not in existing_call_ids]
        results.append(
            {
                "capability": "usage",
                "status": passed if any(c.usage for c in calls) else "NOT_TESTED",
                "returned_usage_calls": sum(c.usage is not None for c in calls),
                "unknown_usage_calls": sum(c.usage is None for c in calls),
            }
        )
        report["calls"] = [c.model_dump() for c in calls]
        report["authenticated_status"] = "NOT_TESTED" if args.mode == "mock" else "SEE_CAPABILITIES"
        output = Path(args.output or f"docs/evidence/models-smoke-{args.mode}.json")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        for result in results:
            print(f"{result['capability']}: {result['status']}")
        print(f"Redacted report: {output}")
        return 1 if any(r["status"] == "FAILED" for r in results) else 0
    finally:
        await client.close()
        store.close()


def main():
    parser = argparse.ArgumentParser(
        description="Explicit Configured provider capability smoke; mock is offline"
    )
    parser.add_argument("--mode", choices=["mock", "live"], default="mock")
    parser.add_argument(
        "--vision", action="store_true", help="Probe using the just-generated public image"
    )
    parser.add_argument(
        "--video", action="store_true", help="Opt-in; requires verified entitlement and ffprobe"
    )
    parser.add_argument("--output")
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
