"""Bounded background QA and authoritative canvas artifact production."""

import asyncio
import base64
import io
import json
import math
import random
from uuid import uuid4

from PIL import Image, ImageDraw, ImageFilter

from backend.art_context import (
    LAYOUT,
    RENDERER_VERSION,
    art_brief,
    art_key,
    font_manifest,
    image_context,
    image_prompt,
    renderer_hash,
)
from backend.art_models import SIZES, Background, BackgroundQA, CanvasInput, PosterArtifact
from backend.art_repository import ArtRepository
from backend.art_storage import ArtStorage, raster
from backend.campaign_service import prompt
from backend.canvas_worker import render_canvas
from backend.contracts import utc_now
from backend.errors import ProviderError
from backend.guardian.report import CheckRequest, Finding
from backend.guardian.rules import check
from backend.intent_rules import digest, domain_error
from backend.media import download_image
from backend.poster_copy import poster_template


def qa_passes(qa, brief=None):
    return (
        qa.recommendation == "usable"
        and qa.image_loaded
        and qa.inspected_all_regions
        and not any(
            [
                qa.lettering_or_numbers,
                qa.logos_or_watermarks,
                # R9 excludes the explicitly permitted mug from this flag. Extras still block.
                qa.products_or_extra_items,
                qa.venue_features,
                qa.promotional_implications,
            ]
        )
    )


def deterministic_background(ratio, palette, coffee=False):
    sizes = {"1:1": (1024, 1024), "9:16": (576, 1024), "16:9": (1024, 576)}
    image = Image.new("RGB", sizes[ratio], "#24382A")
    draw = ImageDraw.Draw(image)
    w, h = image.size
    # Local illustration, not photography: quiet editorial lighting, no blocky collage.
    rng = random.Random(17)
    for _ in range(12000):
        draw.point((rng.randrange(w), rng.randrange(h)), fill=rng.choice(["#293D2D", "#30442F"]))
    light = Image.new("RGBA", image.size, (0, 0, 0, 0))
    glow = ImageDraw.Draw(light)
    glow.ellipse((w * 0.45, -h * 0.2, w * 1.25, h * 0.65), fill=(218, 159, 72, 100))
    for bx, by, radius in ((0.14, 0.24, 0.025), (0.7, 0.12, 0.045), (0.84, 0.34, 0.02)):
        r = min(w, h) * radius
        glow.ellipse((w * bx - r, h * by - r, w * bx + r, h * by + r), fill=(251, 200, 68, 115))
    light = light.filter(ImageFilter.GaussianBlur(min(w, h) * 0.035))
    image.paste(light, (0, 0), light)
    draw = ImageDraw.Draw(image)
    if coffee:
        # Local, instant fallback is still a real decorative illustration, not claimed AI art.
        cx, cy, unit = w * 0.52, h * 0.62, min(w, h) * 0.25
        cream, accent = "#FFFBF4", "#493327"
        shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
        ImageDraw.Draw(shadow).ellipse(
            (cx - unit * 1.1, cy + unit * 0.54, cx + unit * 1.5, cy + unit * 1.12),
            fill=(65, 39, 22, 65),
        )
        image.paste(
            shadow.filter(ImageFilter.GaussianBlur(unit * 0.1)),
            (0, 0),
            shadow.filter(ImageFilter.GaussianBlur(unit * 0.1)),
        )
        draw = ImageDraw.Draw(image)
        draw.ellipse(
            (cx - unit * 1.25, cy + unit * 0.65, cx + unit * 1.4, cy + unit), fill="#E7D8C4"
        )
        draw.ellipse(
            (cx + unit * 0.3, cy - unit * 0.48, cx + unit * 1.3, cy + unit * 0.48),
            outline=cream,
            width=max(4, int(unit * 0.18)),
        )
        draw.rounded_rectangle(
            (cx - unit, cy - unit * 0.65, cx + unit * 0.6, cy + unit * 0.65),
            radius=int(unit * 0.27),
            fill=cream,
        )
        draw.rounded_rectangle(
            (cx - unit * 0.92, cy - unit * 0.55, cx - unit * 0.7, cy + unit * 0.55),
            radius=max(2, int(unit * 0.08)),
            fill="#E5D4B7",
        )
        for _ in range(160):
            sx = cx + rng.uniform(-0.65, 0.48) * unit
            sy = cy + rng.uniform(-0.28, 0.5) * unit
            draw.ellipse((sx, sy, sx + 2, sy + 2), fill="#B9A68A")
        draw.ellipse((cx - unit, cy - unit * 0.82, cx + unit * 0.6, cy - unit * 0.38), fill=accent)
        draw.arc(
            (cx - unit * 0.88, cy - unit * 0.74, cx + unit * 0.48, cy - unit * 0.43),
            180,
            340,
            fill="#9D6D45",
            width=max(3, int(unit * 0.04)),
        )
        for offset in (-0.55, -0.05):
            draw.arc(
                (cx + unit * offset, cy - unit * 1.6, cx + unit * (offset + 0.45), cy - unit * 0.9),
                80,
                270,
                fill=cream,
                width=max(3, int(unit * 0.06)),
            )
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def validate_canvas(input, validation):
    if (
        not validation.passed
        or validation.reasons
        or not validation.font_loaded
        or not validation.grapheme_engine
    ):
        raise domain_error("ART_BLOCKED", "Canvas did not complete required checks")
    if validation.renderer_version != RENDERER_VERSION or validation.contrast < 7:
        raise domain_error("ART_BLOCKED", "Canvas version or contrast is invalid")
    x, y, w, h = validation.safe_area
    if not all(math.isfinite(v) for v in [x, y, w, h, validation.contrast]) or min(x, y, w, h) <= 0:
        raise domain_error("ART_BLOCKED", "Invalid safe area")
    expected = (
        [72, 200, input.width - 144, input.height - 440]
        if input.size == "story"
        else (
            [48, 48, input.width - 96, input.height - 96]
            if input.size == "landscape"
            else [64, 64, input.width - 128, input.height - 128]
        )
    )
    if validation.safe_area != expected:
        raise domain_error("ART_BLOCKED", "Safe area does not match layout policy")
    for line in validation.lines:
        values = [line.x, line.y, line.width, line.height, line.font_size]
        if (
            not all(math.isfinite(v) for v in values)
            or line.font_size < LAYOUT["min_font"][input.size]
        ):
            raise domain_error("ART_BLOCKED", "Invalid text metrics")
        if (
            line.x < x
            or line.y < y
            or line.x + line.width > x + w + 0.02
            or line.y + line.height > y + h + 0.02
        ):
            raise domain_error("TEXT_OVERFLOW", "Text crosses the measured safe area")
    for field, text in input.fields.items():
        if field == "alt_text":
            continue
        displayed = "".join(line.text for line in validation.lines if line.field == field)
        if displayed != text.replace("\n", ""):
            raise domain_error("ART_BLOCKED", "Canvas dropped or altered displayed text")
    if bool(input.logo_url) != bool(validation.logo_bounds):
        raise domain_error("ART_BLOCKED", "Logo was omitted or invented")
    if validation.logo_bounds:
        lx, ly, lw, lh = validation.logo_bounds
        if (
            not all(math.isfinite(v) for v in [lx, ly, lw, lh])
            or min(lw, lh) <= 0
            or lx < x
            or ly < y
            or lx + lw > x + w
            or ly + lh > y + h
        ):
            raise domain_error("ART_BLOCKED", "Logo crosses the safe area")


class ArtService:
    def __init__(self, store, client, settings):
        self.store = store
        self.repo, self.client, self.settings = ArtRepository(store), client, settings
        self.storage = ArtStorage(settings.asset_path)
        self.lock = asyncio.Lock()
        self.renderer = render_canvas

    async def background(self, campaign_id, request):
        async with self.lock:
            campaign = self.repo.generation.locked(campaign_id, request.expected_revision)
            ratio = SIZES[request.size][2]
            context = image_context(self.client.settings)
            key = art_key(campaign, ratio, request.source, context)
            existing = self.repo.reusable(campaign_id, key)
            if existing and existing.status == "ready":
                self.storage.read(existing.sha256)
                if existing.provenance != "deterministic" and (
                    not existing.qa or not qa_passes(existing.qa)
                ):
                    raise domain_error("ART_BLOCKED", "Background has no passing QA")
                return existing
            brief = art_brief(campaign, ratio)
            if (
                request.source != "deterministic"
                and not self.client.settings.image_generation_enabled
            ):
                raise domain_error(
                    "IMAGE_KEY_MISSING"
                    if self.client.settings.image_provider == "openai"
                    else "IMAGE_TRANSPORT_UNVERIFIED",
                    "Add OPENAI_API_KEY and restart backend, or choose local artwork"
                    if self.client.settings.image_provider == "openai"
                    else "Choose local artwork or configure a verified compatible image endpoint",
                )
            reasons = []
            budget = self.client.budget(calls=6, seconds=240)
            if request.source == "provider":
                for _ in range(2):
                    try:
                        url = await self.client.image(image_prompt(brief), budget, ratio=ratio)
                        downloaded = await download_image(
                            url,
                            self.storage.root,
                            mock_transport=self.client.mock_transport,
                            allowed_hosts=self.client.settings.media_allowed_hosts,
                        )
                        path = self.storage.root / downloaded["filename"]
                        try:
                            raw, (w, h) = raster(path.read_bytes(), downloaded["mime"])
                        finally:
                            path.unlink(missing_ok=True)
                        target_ratio = {"1:1": 1, "9:16": 9 / 16, "16:9": 16 / 9}[ratio]
                        if max(w, h) < 768 or abs(w / h / target_ratio - 1) > 0.04:
                            raise domain_error(
                                "ART_INVALID", "Generated native ratio or resolution is invalid"
                            )
                        key_bytes = self.storage.write(raw)
                        qa = None
                        qa_error = None
                        if (
                            self.client.settings.inference_mode != "mock"
                            and not self.client.settings.vision_supported
                        ):
                            qa_error = "VISION_UNSUPPORTED"
                        else:
                            try:
                                qa = await self.client.structured(
                                    json.dumps({"brief": brief}),
                                    BackgroundQA,
                                    budget,
                                    system_prompt=prompt("R9"),
                                    max_tokens=1024,
                                    vision_image=(
                                        "data:image/png;base64," + base64.b64encode(raw).decode()
                                    ),
                                )
                            except ProviderError as exc:
                                if exc.body.code == "REVISION_CONFLICT":
                                    raise
                                qa_error = exc.body.code
                        status = "ready" if qa and qa_passes(qa, brief) else "blocked"
                        item = Background(
                            id=uuid4().hex,
                            campaign_id=campaign_id,
                            art_key=key,
                            ratio=ratio,
                            status=status,
                            provenance=self.client.settings.inference_mode,
                            source=request.source,
                            sha256=key_bytes,
                            byte_count=len(raw),
                            width=w,
                            height=h,
                            captured_at=utc_now(),
                            brief=brief,
                            qa=qa,
                            reasons=(
                                []
                                if status == "ready"
                                else [qa_error, "IMAGE_QA_REQUIRED"]
                                if qa_error
                                else ["R9_REJECTED_OR_UNCERTAIN"]
                            ),
                            calls_used=budget.calls,
                            run_id=budget.run_id,
                            generation_model=self.client.settings.image_model,
                            qa_model=self.client.settings.text_model if qa else None,
                        )
                        self.repo.save_background(item, request.expected_revision)
                        if item.status == "ready" or qa_error == "VISION_UNSUPPORTED":
                            return item
                        if qa_error:
                            raise domain_error(qa_error, "Background visual QA is unavailable")
                        reasons.append("R9_REJECTED_OR_UNCERTAIN")
                    except ProviderError as exc:
                        if exc.body.code == "REVISION_CONFLICT":
                            raise
                        reasons.append(exc.body.code)
                        # Failed/uncertain submission, download or QA is never silently resubmitted.
                        break
            raw = deterministic_background(
                ratio, brief["palette"], brief["allowed_product_illustration"]
            )
            raw, (w, h) = raster(raw, "image/png")
            item = Background(
                id=uuid4().hex,
                campaign_id=campaign_id,
                art_key=key,
                ratio=ratio,
                status="ready",
                provenance="deterministic",
                source=request.source,
                sha256=self.storage.write(raw),
                byte_count=len(raw),
                width=w,
                height=h,
                captured_at=utc_now(),
                brief=brief,
                qa=None,
                reasons=sorted(set(reasons)) or ["OWNER_SELECTED_DETERMINISTIC"],
                calls_used=budget.calls,
                run_id=budget.run_id,
                generation_model=self.client.settings.image_model
                if any(
                    c.run_id == budget.run_id and c.model == self.client.settings.image_model
                    for c in self.client.store.calls()
                )
                else None,
                qa_model=self.client.settings.text_model
                if any(
                    c.run_id == budget.run_id and c.model == self.client.settings.text_model
                    for c in self.client.store.calls()
                )
                else None,
            )
            return self.repo.save_background(item, request.expected_revision)

    async def render(self, campaign_id, request):
        async with self.lock:
            campaign = self.repo.generation.locked(campaign_id, request.expected_revision)
            variant = self.repo.variant(campaign, request.variant_id)
            if self.repo.generation.plan(campaign_id, campaign.revision) is None:
                raise domain_error(
                    "ART_BLOCKED", "Plan eligible audience strategies before rendering"
                )
            background = self.repo.background(request.background_id)
            if (
                background.campaign_id != campaign_id
                or background.status != "ready"
                or background.ratio != SIZES[request.size][2]
            ):
                raise domain_error(
                    "ART_BLOCKED", "Choose a validated background for this campaign and ratio"
                )
            # Allow numeric facts to change without new art, but never changed visual inputs.
            context = image_context(self.client.settings)
            if background.art_key != art_key(
                campaign, background.ratio, background.source, context
            ):
                raise domain_error("REVISION_CONFLICT", "Background art dependencies changed")
            if background.provenance != "deterministic" and (
                not background.qa or not qa_passes(background.qa)
            ):
                raise domain_error("ART_BLOCKED", "Background QA is incomplete or rejected")
            self.storage.read(background.sha256)
            logo = self.repo.logo(request.logo_id, campaign_id) if request.logo_id else None
            if logo:
                self.storage.read(logo["sha256"])
            report = check(
                campaign,
                CheckRequest(
                    campaign_id=campaign_id,
                    expected_revision=campaign.revision,
                    mode="asset",
                    language=variant.language,
                    channel=variant.channel,
                    template=poster_template(campaign, variant.template),
                    audience=next(
                        (
                            a.segment
                            for a in self.repo.generation.plan(
                                campaign_id, campaign.revision
                            ).audiences
                            if a.id == variant.audience_id
                        ),
                        "",
                    ),
                ),
            )
            if report.rendered is None or any(
                c.passed is False and (c.severity == "BLOCK" or c.rule == "G11")
                for c in report.checks
            ):
                raise domain_error("ART_BLOCKED", "Guardian blocks this copy")
            w, h, _ = SIZES[request.size]
            value = CanvasInput(
                width=w,
                height=h,
                size=request.size,
                language=variant.language,
                fields=report.rendered.fields,
                offer_forms=sorted(
                    {s.approved_form for s in report.rendered.spans if s.key == "OFFER"}
                ),
                background_url=f"/api/assets/{background.id}",
                logo_url=f"/api/assets/{request.logo_id}" if logo else None,
                font_urls={
                    "latin": "/api/render/fonts/NotoSans.ttf",
                    "kannada": "/api/render/fonts/NotoSansKannada.ttf",
                },
                font_hash=font_manifest(),
                renderer_version=RENDERER_VERSION,
                renderer_hash=renderer_hash(),
                background_hash=background.sha256,
                logo_hash=logo["sha256"] if logo else None,
                layout_hash=digest(LAYOUT),
            )
            render_hash = digest(
                [
                    value.model_dump(),
                    variant.dependency_hash,
                    report.content_hash,
                    report.dependency_hash,
                ]
            )
            cached = self.repo.by_render_hash(render_hash)
            if cached:
                if cached.status != "ready":
                    raise domain_error(
                        "ART_BLOCKED", "Previous render failed; review its recorded reasons"
                    )
                self.storage.read(cached.sha256)
                return cached
            raw, validation = await self.renderer(value, self.settings.render_origin)
            if font_manifest() != value.font_hash or renderer_hash() != value.renderer_hash:
                raise domain_error("REVISION_CONFLICT", "Font or renderer changed while rendering")
            validate_canvas(value, validation)
            raw, dimensions = raster(raw, "image/png", dimensions=(w, h))
            # Re-encoding is canonical: preview and future export both use these exact bytes.
            dependencies = variant.dependencies.model_copy(
                update={
                    "renderer_version": RENDERER_VERSION,
                    "font_hash": value.font_hash,
                    "background_hash": background.sha256,
                    "layout_hash": value.layout_hash,
                }
            )
            pixel_check = next(c for c in report.checks if c.rule == "G12")
            pixel_check.findings.append(
                Finding(
                    field="*",
                    source="policy",
                    message="Measured canvas bounds validated against safe areas; "
                    "artifact bound to render hash",
                )
            )
            artifact = PosterArtifact(
                id=uuid4().hex,
                campaign_id=campaign_id,
                variant_id=variant.id,
                campaign_revision=campaign.revision,
                status="ready",
                width=w,
                height=h,
                byte_count=len(raw),
                sha256=self.storage.write(raw),
                fact_hash=campaign.fact_hash or "",
                dependency_hash=digest([variant.dependency_hash, value.model_dump(), logo]),
                content_hash=report.content_hash,
                render_hash=render_hash,
                dependencies=dependencies,
                provenance=background.provenance,
                copy_provenance=variant.mode,
                captured_at=utc_now(),
                render_input=value,
                validation=validation,
                guardian=report,
                background_id=background.id,
                logo_id=request.logo_id,
            )
            return self.repo.save_poster(artifact)

    async def upload_logo(self, campaign_id, revision, raw, mime):
        campaign = self.repo.generation.locked(campaign_id, revision)
        raw, dimensions = raster(raw, mime, logo=True)
        item = {
            "id": uuid4().hex,
            "campaign_id": campaign_id,
            "sha256": self.storage.write(raw),
            "width": dimensions[0],
            "height": dimensions[1],
            "owner_reviewed": True,
            "captured_at": utc_now(),
            "campaign_revision": revision,
        }
        with self.repo.db:
            self.repo.generation.locked(campaign.id, revision)
            self.repo.db.execute(
                "INSERT INTO campaign_logos VALUES(?,?,?,?)",
                (item["id"], campaign_id, item["sha256"], json.dumps(item)),
            )
        return item["id"]

    def bytes(self, asset_id):
        for getter in [self.repo.poster, self.repo.background, self.repo.logo]:
            try:
                item = getter(asset_id)
            except ProviderError as exc:
                if exc.body.code == "ASSET_NOT_FOUND":
                    continue
                raise
            if not isinstance(item, dict) and item.status != "ready":
                raise domain_error("ART_BLOCKED", "Unchecked or stale artifacts cannot be served")
            return self.storage.read(item["sha256"] if isinstance(item, dict) else item.sha256)
        raise domain_error("ASSET_NOT_FOUND", "Artifact not found")

    def approved_bytes(self, asset_id):
        from backend.approval_service import ApprovalService

        poster = self.repo.poster(asset_id)
        campaign = self.repo.generation.campaigns.get(poster.campaign_id)
        boundary = ApprovalService(self.store, self.client)
        item = next((i for i in boundary.ledger.active(campaign) if i.id == asset_id), None)
        if item is None or not item.approval_id:
            raise domain_error("APPROVAL_PENDING", "Current owner approval is pending")
        pack, files = boundary.export(campaign.id, campaign.revision, [asset_id])
        return files[pack.files[0].filename]
