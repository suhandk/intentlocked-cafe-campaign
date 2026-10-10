"""One authenticated image + visual QA probe; stores only redacted metadata in docs."""

import asyncio
import base64
import json
from pathlib import Path

from backend.art_models import BackgroundQA
from backend.art_service import qa_passes
from backend.campaign_service import prompt
from backend.config import Settings
from backend.contracts import utc_now
from backend.db import Store
from backend.errors import ProviderError
from backend.inference_client import InferenceClient
from backend.media import download_image


async def main():
    settings = Settings(database_path=Path("data/hackathon-image-probe.sqlite3"))
    store = Store(settings.database_path)
    client = InferenceClient(settings, store)
    budget = client.budget(calls=3, seconds=180)
    report = {
        "timestamp": utc_now(),
        "mode": settings.inference_mode,
        "model": settings.image_model,
        "provider": settings.image_provider,
    }
    before = {c.id for c in store.calls()}
    phase = "image"
    try:
        if settings.inference_mode != "live":
            report["status"] = "NOT_TESTED"
            report["reason"] = "This authenticated probe requires INFERENCE_MODE=live"
            return
        if settings.image_provider == "openai" and not settings.openai_api_key.get_secret_value():
            report["status"] = "NOT_TESTED"
            report["reason"] = "Add OPENAI_API_KEY to backend .env; no request was sent"
            return
        description = (
            "Photorealistic modern editorial coffee advertising background. One large "
            "unbranded speckled ceramic coffee mug, glossy coffee and subtle steam on the "
            "right. Cinematic amber light, espresso studio backdrop, full cup and handle "
            "visible. Cream paper, forest-green brush and mustard accents added later by code. "
            "Negative space upper left. No text, numbers, logos, signage, food, people, "
            "furniture, offers, badges, watermarks. Square composition."
        )
        url = await client.image(description, budget)
        item = await download_image(url, Path("data/hackathon-image-probe"))
        report["image"] = {"status": "PASS", **item}
        raw = (Path("data/hackathon-image-probe") / item["filename"]).read_bytes()
        phase = "vision"
        qa = await client.structured(
            json.dumps({"brief": {"allowed_product_illustration": True}}),
            BackgroundQA,
            budget,
            system_prompt=prompt("R9"),
            max_tokens=1024,
            vision_image="data:" + item["mime"] + ";base64," + base64.b64encode(raw).decode(),
        )
        report["vision"] = {
            "status": "PASS" if qa_passes(qa) else "REJECTED",
            "qa": qa.model_dump(),
        }
        report["status"] = "PASS" if qa_passes(qa) else "REJECTED"
    except ProviderError as exc:
        report["status"] = "FAILED"
        report["vision"] = {
            "status": "NOT_TESTED" if phase == "image" else "FAILED",
            "reason": "Image generation failed" if phase == "image" else "Visual QA failed",
        }
        report["error"] = exc.body.model_dump()
    finally:
        report["calls"] = [c.model_dump() for c in store.calls() if c.id not in before]
        report_path = Path(
            "docs/evidence/hackathon-openai-image-live.json"
            if settings.image_provider == "openai"
            else "docs/evidence/hackathon-seedream-image-live.json"
        )
        if report_path.exists():
            Path("data/hackathon-image-probe-history").mkdir(parents=True, exist_ok=True)
            Path(
                "data/hackathon-image-probe-history", utc_now().replace(":", "-") + ".json"
            ).write_bytes(report_path.read_bytes())
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
        await client.close()
        store.close()
    if report.get("status") in {"FAILED", "REJECTED"}:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
