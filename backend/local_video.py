"""Real local MP4 animation with source, revision and exact-byte approval boundaries."""

import asyncio
import hashlib
import json
from typing import Literal

from pydantic import Field

from backend.contracts import utc_now
from backend.intent_rules import digest, domain_error
from backend.schemas import RevisionRequest


class LocalVideoInput(RevisionRequest):
    poster_id: str = Field(min_length=1, max_length=100)
    duration: Literal[12, 18, 24] = 12


class LocalVideoApproval(RevisionRequest):
    observed_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    owner_approves: Literal[True]
    idempotency_key: str = Field(min_length=8, max_length=128)


class LocalVideoMixin:
    def local_source(self, value, approved=False, transaction_owned=False, saved_view=False):
        self.current(value)
        campaign = self.app.state.work.campaigns.repo.get(value["campaign_id"])
        poster = self.app.state.art.repo.poster(value["poster_id"])
        if digest(poster.model_dump()) != value["poster_record_hash"]:
            raise domain_error("VIDEO_INVALID", "Source poster changed; regenerate the animation")
        item = self.app.state.approvals.current_item(campaign, value["source_item_id"])
        self.app.state.approvals.verify(campaign, item)
        if approved:
            pack, _ = self.app.state.approvals.export(
                campaign.id,
                campaign.revision,
                [item.id],
                saved_view=saved_view,
                transaction_owned=transaction_owned,
            )
            return pack.model_dump()

    async def execute_local(self, job, body):
        """Animate exact validated pixels; no remote footage or inference calls."""
        from backend.video_service import binary, command

        if not self.app.state.settings.local_video_enabled:
            raise domain_error("VIDEO_DISABLED", "Local animation is disabled")
        campaign = self.app.state.work.campaigns.repo.get(job.campaign_id)
        if campaign.status != "locked" or campaign.revision != body.expected_revision:
            raise domain_error(
                "REVISION_CONFLICT", "Lock the current facts before video generation"
            )
        poster = self.app.state.art.repo.poster(body.poster_id)
        if poster.campaign_id != campaign.id or poster.campaign_revision != campaign.revision:
            raise domain_error("VIDEO_ENDCARD_INVALID", "Select a current campaign poster")
        items = self.app.state.approvals.ledger.sync(campaign)
        item = next((i for i in items if i.poster_id == poster.id), None)
        if not item:
            raise domain_error("VIDEO_ENDCARD_INVALID", "Source poster is not a current asset")
        self.app.state.approvals.verify(campaign, item)
        encoder, validator = binary("ffmpeg"), binary("ffprobe")
        value = {
            "id": job.id,
            "campaign_id": campaign.id,
            "revision": campaign.revision,
            "fact_hash": campaign.fact_hash,
            "mode": job.mode,
            "model": "local-poster-animation-v1",
            "source": "local_animation",
            "poster_id": poster.id,
            "poster_record_hash": digest(poster.model_dump()),
            "source_item_id": item.id,
            "source_provenance": poster.copy_provenance,
            "poster_sha256": poster.sha256,
            "status": "composing",
            "approval": "UNAPPROVED",
            "qa": "SOURCE_AND_ENCODING_VERIFIED",
            "created_at": utc_now(),
            "clips": [],
            "filename": None,
            "sha256": None,
            "reasons": [
                "Local animation of exact poster pixels; no AI footage or provider charges",
                "Approve the source poster, then review and approve this animation",
            ],
        }
        self.root.mkdir(parents=True, exist_ok=True)
        source = self.root / f"{job.id}-source.png"
        source.write_bytes(self.app.state.art.bytes(poster.id))
        final = self.root / f"{job.id}-animated.mp4"
        self.save(value)
        try:
            await command(
                encoder,
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=0x20150F:s=720x1280:r=30",
                "-loop",
                "1",
                "-framerate",
                "30",
                "-i",
                source,
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=48000:cl=stereo",
                "-filter_complex",
                "[1:v]scale=660:1160:force_original_aspect_ratio=decrease[poster];"
                "[0:v][poster]overlay=x='(W-w)/2+8*sin(2*PI*t/12)':"
                "y='(H-h)/2+8*cos(2*PI*t/12)':shortest=1,format=yuv420p[v]",
                "-map",
                "[v]",
                "-map",
                "2:a:0",
                "-t",
                str(body.duration),
                "-r",
                "30",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-threads",
                "2",
                "-crf",
                "20",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-movflags",
                "+faststart",
                final,
            )
            probe = json.loads(
                await command(
                    validator, "-v", "error", "-show_streams", "-show_format", "-of", "json", final
                )
            )
            streams = probe.get("streams", [])
            videos = [s for s in streams if s.get("codec_type") == "video"]
            if (
                len(videos) != 1
                or videos[0].get("codec_name") != "h264"
                or videos[0].get("width") != 720
                or videos[0].get("height") != 1280
                or videos[0].get("pix_fmt") != "yuv420p"
                or videos[0].get("avg_frame_rate") != "30/1"
                or not any(s.get("codec_name") == "aac" for s in streams)
                or abs(float(probe["format"]["duration"]) - body.duration) > 0.4
            ):
                raise domain_error("VIDEO_SPEC_INVALID", "Animation encoding failed validation")
            self.local_source(value)
            value.update(
                status="unapproved",
                filename=final.name,
                sha256=hashlib.sha256(final.read_bytes()).hexdigest(),
                duration=body.duration,
                spec_verified=True,
            )
            self.save(value)
            return value
        except BaseException as exc:
            value["status"] = "cancelled" if isinstance(exc, asyncio.CancelledError) else "failed"
            value["reasons"].append(getattr(getattr(exc, "body", None), "code", "VIDEO_STOPPED"))
            self.save(value)
            raise

    def approve_local(self, video_id, body):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            value = self.get(video_id)
            if (
                value.get("source") != "local_animation"
                or not value.get("spec_verified")
                or value["status"] not in {"unapproved", "approved"}
                or value["revision"] != body.expected_revision
                or value["sha256"] != body.observed_hash
            ):
                raise domain_error("APPROVAL_INVALID", "Review the current complete animation")
            self.artifact(video_id)
            self.local_source(value, approved=True, transaction_owned=True)
            request_hash = digest(body.model_dump())
            if value.get("approval_request_hash") not in {None, request_hash}:
                raise domain_error("IDEMPOTENCY_CONFLICT", "Video has a different approval request")
            value.update(
                status="approved",
                approval="APPROVED",
                approved_at=utc_now(),
                approved_hash=value["sha256"],
                approval_request_hash=request_hash,
            )
            self.db.execute(
                "UPDATE campaign_videos SET payload=? WHERE id=?", (json.dumps(value), video_id)
            )
            self.db.commit()
            return value
        except BaseException:
            self.db.rollback()
            raise

    def local_manifest(self, video_id, saved_view=False):
        value = self.get(video_id)
        if value.get("source") != "local_animation" or value.get("approval") != "APPROVED":
            raise domain_error("APPROVAL_INVALID", "Approve the exact animation before export")
        if value.get("approved_hash") != value.get("sha256"):
            raise domain_error("APPROVAL_INVALID", "Animation hash changed after approval")
        self.artifact(video_id)
        pack = self.local_source(value, approved=True, saved_view=saved_view)
        return {
            "schema_version": "local-video-v1",
            "video_id": video_id,
            "sha256": value["sha256"],
            "approved_hash": value["approved_hash"],
            "source": value["source"],
            "mode": "cached" if saved_view else value["mode"],
            "source_mode": value["mode"],
            "source_provenance": value["source_provenance"],
            "model": value["model"],
            "duration": value["duration"],
            "revision": value["revision"],
            "fact_hash": value["fact_hash"],
            "source_poster_hash": value["poster_sha256"],
            "source_manifest": pack,
        }
