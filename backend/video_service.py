"""Optional Configured provider footage jobs. Draft files never confer campaign/export approval."""

import asyncio
import hashlib
import json
import shutil
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from backend.contracts import utc_now
from backend.inference_client import InferenceClient
from backend.intent_rules import domain_error
from backend.local_video import LocalVideoMixin
from backend.media import download_image
from backend.schemas import RevisionRequest
from backend.work_context import work_guard


class VideoInput(RevisionRequest):
    duration: Literal[24, 30]
    generated_seconds: Literal[18, 24]
    confirm_clip_count: Literal[True]
    confirm_possible_charges: Literal[True]
    confirm_video_access: Literal[True]
    poster_id: str | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def exact_count(self):
        if self.generated_seconds != self.duration - 6:
            raise ValueError(
                "Generated seconds must equal final duration minus six-second end card"
            )
        return self


STYLE = (
    "Cinematic conceptual coffee commercial, warm golden highlights, navy-teal shadows, "
    "soft grain, gentle camera motion, rich coffee browns and creamy whites. "
    "Abstract imagery, no depiction of the actual business premises. "
    "No text, letters, numbers, signs, menus, price tags, logos, watermarks or screens. "
    "No people, faces, hands, ice, branded cups, extra products or venue features."
)
SHOTS = [
    "Warm amber light slowly moves across abstract coffee-brown shapes. Slow cinematic push-in.",
    "Macro conceptual coffee liquid swirling gently, golden reflections, no containers visible.",
    "Gentle steam against deep navy-teal, flowing coffee-brown abstract forms, shallow focus.",
    "Warm golden light opens across creamy-white and coffee-brown abstract waves, calm motion.",
]


def binary(name):
    found = shutil.which(name)
    if found:
        return found
    found = list(Path("data/video-tools/installed").glob(f"*/bin/{name}.exe"))
    if not found:
        raise domain_error("VIDEO_VALIDATOR_MISSING", "Install ffmpeg and ffprobe first")
    return str(found[0].resolve())


async def command(*args):
    process = await asyncio.create_subprocess_exec(
        *map(str, args), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        async with asyncio.timeout(60):
            output, _ = await process.communicate()
        if process.returncode:
            raise domain_error("VIDEO_COMPOSE_FAILED", "Video tool rejected the artifact")
        return output
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


class VideoService(LocalVideoMixin):
    def __init__(self, app):
        self.app = app
        self.db = app.state.store.connection
        self.client = None
        self.root = app.state.settings.asset_path / "video"

    async def close(self):
        if self.client:
            await self.client.close()

    def save(self, value):
        value["updated_at"] = utc_now()
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO campaign_videos VALUES(?,?,?)",
                (
                    value["id"],
                    value["campaign_id"],
                    json.dumps(value),
                ),
            )

    def get(self, video_id):
        row = self.db.execute(
            "SELECT payload FROM campaign_videos WHERE id=?", (video_id,)
        ).fetchone()
        if not row:
            raise domain_error("VIDEO_NOT_FOUND", "Video draft not found")
        return json.loads(row[0])

    def snapshot(self, campaign_id):
        self.app.state.work.campaigns.repo.get(campaign_id)
        values = [
            json.loads(r[0])
            for r in self.db.execute(
                "SELECT payload FROM campaign_videos WHERE campaign_id=? ORDER BY rowid DESC",
                (campaign_id,),
            )
        ]
        revision = self.app.state.work.campaigns.repo.get(campaign_id).revision
        for value in values:
            if value["revision"] != revision:
                value["status"] = "stale"
            elif self.app.state.work.get(value["id"]).status in {
                "failed",
                "cancelled",
                "interrupted",
                "stale",
            }:
                value["status"] = self.app.state.work.get(value["id"]).status
        return values

    def current(self, value):
        if work_guard.get():
            work_guard.get()()
        campaign = self.app.state.work.campaigns.repo.get(value["campaign_id"])
        if campaign.revision != value["revision"] or campaign.fact_hash != value["fact_hash"]:
            raise domain_error("REVISION_CONFLICT", "Video facts changed; draft is stale")

    async def execute(self, job, body):
        settings = self.app.state.settings
        if not settings.enable_video:
            raise domain_error(
                "VIDEO_DISABLED", "Neither configured model supports video generation"
            )
        if settings.inference_mode != "live":
            raise domain_error(
                "VIDEO_LIVE_REQUIRED", "Video generation requires live Configured provider mode"
            )
        campaign = self.app.state.work.campaigns.repo.get(job.campaign_id)
        if campaign.status != "locked":
            raise domain_error("FACTS_INCOMPLETE", "Lock and review facts before video generation")
        binary("ffmpeg")
        binary("ffprobe")
        # Explicit per-job owner access attestation, not catalogue-derived entitlement.
        # Historical video tests isolate their offline queue from text and image work.
        if self.client is None:
            config = settings.model_copy(
                update={
                    "enable_video": True,
                    "video_entitlement_verified": body.confirm_video_access,
                }
            )
            self.client = InferenceClient(config, self.app.state.store)
        response = await self.client.http.get(
            settings.inference_base_url + "/models",
            headers={"Authorization": "Bearer " + settings.inference_api_key.get_secret_value()},
        )
        if response.status_code != 200:
            raise domain_error(
                "VIDEO_ACCESS_UNVERIFIED", "Configured provider model access check failed"
            )
        advertised = response.json().get("data", [])
        models_list = {m.get("id") for m in advertised if isinstance(m, dict)}
        if settings.video_model not in models_list:
            raise domain_error(
                "VIDEO_ACCESS_UNVERIFIED", "Configured model is absent from the provider catalogue"
            )
        count = body.generated_seconds // 6
        indices = [0, 2, 3] if count == 3 else [0, 1, 2, 3]
        value = {
            "id": job.id,
            "campaign_id": campaign.id,
            "revision": campaign.revision,
            "fact_hash": campaign.fact_hash,
            "mode": "live",
            "model": settings.video_model,
            "requested_duration": body.duration,
            "generated_seconds": body.generated_seconds,
            "status": "running",
            "approval": "UNAPPROVED",
            "qa": "NOT_VERIFIED",
            "created_at": utc_now(),
            "clips": [{"index": i, "state": "queued", "video_id": None} for i in indices],
            "filename": None,
            "sha256": None,
            "reasons": ["Generated footage OCR/claim QA and owner video approval are pending"],
        }
        self.root.mkdir(parents=True, exist_ok=True)
        self.save(value)
        if body.poster_id:
            poster = self.app.state.art.repo.poster(body.poster_id)
            if (
                poster.campaign_id != campaign.id
                or poster.campaign_revision != campaign.revision
                or not poster.validation.passed
                or poster.guardian.status == "BLOCKED"
                or poster.render_input.size != "story"
            ):
                raise domain_error(
                    "VIDEO_ENDCARD_INVALID", "Select a current validated story poster"
                )
            raw = self.app.state.art.bytes(body.poster_id)
            endcard = self.root / f"{job.id}-endcard.png"
            endcard.write_bytes(raw)
            value["endcard_hash"] = hashlib.sha256(raw).hexdigest()
            value["overlay_text_hash"] = hashlib.sha256(
                json.dumps(poster.render_input.fields, sort_keys=True).encode()
            ).hexdigest()
        else:
            endcard = None
            value["reasons"].append("No story end card selected: footage draft only")
        slots = asyncio.Semaphore(2)

        async def clip(item):
            async with slots:
                self.current(value)
                budget = self.client.budget(calls=20, seconds=300)
                budget.run_id = job.id
                item["state"] = "submitted"
                self.save(value)
                result = await self.client.request(
                    "video",
                    {
                        "model": settings.video_model,
                        "prompt": SHOTS[item["index"]] + " " + STYLE,
                        "mode": "text",
                        "seconds": "6",
                        "size": "720P",
                        "aspect_ratio": "9:16",
                        "n": 1,
                    },
                    budget,
                    priority=1,
                )
                if not isinstance(result.get("video_id"), str):
                    raise domain_error(
                        "VIDEO_INVALID", "Configured provider did not return a video ID"
                    )
                item["video_id"], item["state"] = result["video_id"], "polling"
                self.save(value)
                if result.get("status") != "completed":
                    for attempt in range(16):
                        self.current(value)
                        await self.client.clock.sleep(min(15, 3 + attempt))
                        result = await self.client.request(
                            "poll",
                            {
                                "video_id": item["video_id"],
                                "model_name": settings.video_model,
                            },
                            budget,
                            priority=1,
                        )
                        if result.get("status") in {"completed", "failed"}:
                            break
                    if result.get("status") == "failed":
                        raise domain_error(
                            "VIDEO_FAILED", "Configured provider clip generation failed"
                        )
                    if result.get("status") == "completed":
                        if not isinstance(result.get("url"), str):
                            raise domain_error(
                                "VIDEO_INVALID", "Completed clip has no download URL"
                            )
                        artifact = await download_image(
                            result["url"], self.root, video=True, video_ffprobe=binary("ffprobe")
                        )
                        probe = json.loads(
                            await command(
                                binary("ffprobe"),
                                "-v",
                                "error",
                                "-show_streams",
                                "-show_format",
                                "-of",
                                "json",
                                self.root / artifact["filename"],
                            )
                        )
                        source = [s for s in probe["streams"] if s.get("codec_type") == "video"]
                        if (
                            len(source) != 1
                            or min(source[0].get("width", 0), source[0].get("height", 0)) < 360
                            or max(source[0]["width"], source[0]["height"]) > 1920
                            or not 5.75 <= float(probe["format"]["duration"]) <= 10
                        ):
                            raise domain_error(
                                "VIDEO_SPEC_INVALID", "Raw clip dimensions/duration rejected"
                            )
                        self.current(value)
                        item.update(artifact, state="downloaded")
                        self.save(value)
                        return
                raise domain_error("VIDEO_TIMEOUT", "Clip polling limit reached")

        tasks = [asyncio.create_task(clip(item)) for item in value["clips"]]
        try:
            await asyncio.gather(*tasks)
            value["status"] = "composing"
            self.save(value)
            pieces = []
            for i, item in enumerate(value["clips"]):
                self.current(value)
                target = self.root / f"{job.id}-{i}.mp4"
                await command(
                    binary("ffmpeg"),
                    "-y",
                    "-i",
                    self.root / item["filename"],
                    "-f",
                    "lavfi",
                    "-i",
                    "anullsrc=r=48000:cl=stereo",
                    "-t",
                    "6",
                    "-vf",
                    "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280",
                    "-map",
                    "0:v:0",
                    "-map",
                    "1:a:0",
                    "-r",
                    "30",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    "-movflags",
                    "+faststart",
                    target,
                )
                item["state"] = "composed"
                pieces.append(target)
                self.save(value)
            if endcard:
                target = self.root / f"{job.id}-endcard.mp4"
                await command(
                    binary("ffmpeg"),
                    "-y",
                    "-loop",
                    "1",
                    "-i",
                    endcard,
                    "-f",
                    "lavfi",
                    "-i",
                    "anullsrc=r=48000:cl=stereo",
                    "-t",
                    "6",
                    "-vf",
                    "scale=720:1280",
                    "-r",
                    "30",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    target,
                )
                pieces.append(target)
            listing = self.root / f"{job.id}-concat.txt"
            listing.write_text("\n".join(f"file '{p.name}'" for p in pieces), encoding="utf-8")
            final = self.root / f"{job.id}.mp4"
            await command(
                binary("ffmpeg"),
                "-y",
                "-f",
                "concat",
                "-safe",
                "1",
                "-i",
                listing,
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                final,
            )
            probe = json.loads(
                await command(
                    binary("ffprobe"),
                    "-v",
                    "error",
                    "-show_streams",
                    "-show_format",
                    "-of",
                    "json",
                    final,
                )
            )
            videos = [s for s in probe["streams"] if s.get("codec_type") == "video"]
            expected = body.duration if endcard else body.generated_seconds
            if (
                len(videos) != 1
                or videos[0].get("width") != 720
                or videos[0].get("height") != 1280
                or videos[0].get("codec_name") != "h264"
                or videos[0].get("pix_fmt") != "yuv420p"
                or videos[0].get("avg_frame_rate") != "30/1"
                or not any(s.get("codec_name") == "aac" for s in probe["streams"])
                or abs(float(probe["format"]["duration"]) - expected) > 0.4
            ):
                raise domain_error("VIDEO_SPEC_INVALID", "Final video does not meet encoding specs")
            self.current(value)
            value.update(
                status="unapproved",
                filename=final.name,
                sha256=hashlib.sha256(final.read_bytes()).hexdigest(),
                duration=expected,
                spec_verified=True,
            )
            self.save(value)
            return value
        except BaseException as exc:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            value["status"] = "cancelled" if isinstance(exc, asyncio.CancelledError) else "failed"
            value["reasons"].append(getattr(getattr(exc, "body", None), "code", "VIDEO_STOPPED"))
            self.save(value)
            raise

    def artifact(self, video_id, clip_index=None):
        value = self.get(video_id)
        if value.get("source") == "local_animation":
            self.local_source(value)
        campaign = self.app.state.work.campaigns.repo.get(value["campaign_id"])
        if campaign.revision != value["revision"] or campaign.fact_hash != value["fact_hash"]:
            raise domain_error("REVISION_CONFLICT", "Video facts changed; download is stale")
        work = self.app.state.work.get(video_id)
        if value.get("source") == "local_animation" and work.status != "completed":
            raise domain_error("VIDEO_UNAVAILABLE", "Animation job is not complete")
        if work.status in {"cancelled", "interrupted", "stale"}:
            raise domain_error("VIDEO_UNAVAILABLE", "This job was cancelled or interrupted")
        artifact = (
            value
            if clip_index is None
            else next((c for c in value["clips"] if c["index"] == clip_index), {})
        )
        if not artifact.get("filename") or not artifact.get("sha256"):
            raise domain_error("VIDEO_UNAVAILABLE", "Video bytes are not available")
        path = self.root / artifact["filename"]
        if (
            path.parent.resolve() != self.root.resolve()
            or not path.is_file()
            or (hashlib.sha256(path.read_bytes()).hexdigest() != artifact["sha256"])
        ):
            raise domain_error("VIDEO_INVALID", "Video bytes changed")
        return path
