import shutil

from backend.errors import ProviderError
from backend.media import download_image


async def video_probe(client, settings):
    if not settings.enable_video or not settings.video_entitlement_verified:
        raise ProviderError(
            "VIDEO_DISABLED", "Enable video only after verifying account entitlement"
        )
    if not shutil.which("ffprobe"):
        raise ProviderError(
            "VIDEO_VALIDATOR_MISSING", "Install ffprobe before opting into video smoke"
        )
    budget = client.budget(calls=40, seconds=300)
    data = await client.request(
        "video",
        {
            "model": settings.video_model,
            "prompt": (
                "Abstract warm background, calm motion. No writing, numbers, logos or products."
            ),
            "mode": "text",
            "seconds": "6",
            "size": "720P",
            "aspect_ratio": "9:16",
            "n": 1,
        },
        budget,
    )
    video_id = data.get("video_id")
    if not isinstance(video_id, str) or not video_id:
        raise ProviderError("INVALID_OUTPUT", "Video submission did not return video_id")
    # Durable recovery record before polling. No signed URLs or key.
    settings.asset_path.mkdir(parents=True, exist_ok=True)
    import json

    path = settings.asset_path / f"video-job-{budget.run_id}.json"
    path.write_text(
        json.dumps({"video_id": video_id, "model": settings.video_model, "status": "submitted"}),
        encoding="utf-8",
    )
    for poll in range(36):
        delay = min(10, 2 + poll)
        if client.clock.now() + delay >= budget.deadline:
            break
        await client.clock.sleep(delay)
        result = await client.request(
            "poll", {"video_id": video_id, "model_name": settings.video_model}, budget
        )
        if result.get("status") == "failed":
            raise ProviderError("VIDEO_FAILED", "Configured provider video task failed")
        if result.get("status") == "completed":
            if not isinstance(result.get("url"), str):
                raise ProviderError("INVALID_OUTPUT", "Completed video has no download URL")
            artifact = await download_image(
                result["url"], settings.asset_path, video=True, mock_transport=client.mock_transport
            )
            path.write_text(
                json.dumps(
                    {
                        "video_id": video_id,
                        "model": settings.video_model,
                        "status": "validated",
                        "artifact": artifact,
                    }
                ),
                encoding="utf-8",
            )
            return artifact
    raise ProviderError("VIDEO_DEADLINE", "Video did not become usable before the deadline")
