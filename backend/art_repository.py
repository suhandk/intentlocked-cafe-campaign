import json

from backend.art_models import ArtSnapshot, Background, PosterArtifact
from backend.generation_repository import GenerationRepository
from backend.intent_rules import digest, domain_error


class ArtRepository:
    def __init__(self, store):
        self.db = store.connection
        self.generation = GenerationRepository(store)

    def background(self, asset_id):
        row = self.db.execute(
            "SELECT payload FROM art_backgrounds WHERE id=?", (asset_id,)
        ).fetchone()
        if not row:
            raise domain_error("ASSET_NOT_FOUND", "Background not found")
        return Background.model_validate_json(row[0])

    def reusable(self, campaign_id, key):
        row = self.db.execute(
            "SELECT payload FROM art_backgrounds WHERE campaign_id=? AND art_key=? "
            "ORDER BY rowid DESC",
            (campaign_id, key),
        ).fetchone()
        return Background.model_validate_json(row[0]) if row else None

    def save_background(self, background, revision):
        with self.db:
            self.generation.locked(background.campaign_id, revision)
            self.db.execute(
                "INSERT INTO art_backgrounds VALUES(?,?,?,?)",
                (
                    background.id,
                    background.campaign_id,
                    background.art_key,
                    background.model_dump_json(),
                ),
            )
        return background

    def variant(self, campaign, variant_id):
        row = self.db.execute(
            "SELECT payload FROM baseline_variants WHERE id=?", (variant_id,)
        ).fetchone()
        if not row:
            from backend.generation_models import BaselineVariant

            delivery = self.db.execute(
                "SELECT i.payload FROM delivery_items i JOIN delivery_links l ON i.id=l.item_id "
                "WHERE l.campaign_id=? AND l.revision=? AND i.id=? AND l.state='pending'",
                (campaign.id, campaign.revision, variant_id),
            ).fetchone()
            if delivery:
                from backend.delivery_models import DeliveryItem

                item = DeliveryItem.model_validate_json(delivery[0])
                if item.kind == "text" and item.source_table == "derived":
                    return BaselineVariant(
                        **item.variant.model_dump(), report=item.report, mode=item.mode
                    )
            from backend.optimization_models import OptimizationRun, OptimizedVariant

            for (payload,) in self.db.execute(
                "SELECT payload FROM optimization_runs WHERE campaign_id=? AND status='completed' "
                "ORDER BY rowid DESC",
                (campaign.id,),
            ):
                run = OptimizationRun.model_validate_json(payload)
                if run.campaign_revision != campaign.revision:
                    continue
                for group in run.groups:
                    if group.current_id != variant_id or group.current_id == group.baseline.id:
                        continue
                    if not group.final_audit or group.final_audit.status != "PASS":
                        raise domain_error("ART_BLOCKED", "Retained candidate lacks complete audit")
                    baseline, report = group.baseline, group.final_audit.guardian
                    return OptimizedVariant(
                        id=group.current_id,
                        campaign_id=campaign.id,
                        campaign_revision=campaign.revision,
                        audience_id=baseline.audience_id,
                        language=baseline.language,
                        channel=baseline.channel,
                        template=group.current_template,
                        slots_used=report.rendered.slots_used,
                        fact_hash=baseline.fact_hash,
                        dependency_hash=digest(
                            [report.dependency_hash, run.context_hash, run.prompt_hashes]
                        ),
                        content_hash=report.content_hash,
                        render_hash=None,
                        status="pending",
                        parent_id=baseline.id,
                        dependencies=baseline.dependencies.model_copy(
                            update={"prompt_version": "b5.1"}
                        ),
                        report=report,
                        mode=run.mode,
                    )
            raise domain_error("ASSET_NOT_FOUND", "Stored current variant not found")
        from backend.generation_models import BaselineVariant

        variant = BaselineVariant.model_validate_json(row[0])
        if variant.campaign_id != campaign.id or variant.campaign_revision != campaign.revision:
            raise domain_error("REVISION_CONFLICT", "Variant belongs to another campaign revision")
        if variant.status != "pending":
            raise domain_error("ART_BLOCKED", "Only validated current drafts can be rendered")
        return variant

    def poster(self, asset_id):
        row = self.db.execute(
            "SELECT payload FROM poster_artifacts WHERE id=?", (asset_id,)
        ).fetchone()
        if not row:
            raise domain_error("ASSET_NOT_FOUND", "Poster not found")
        return PosterArtifact.model_validate_json(row[0])

    def by_render_hash(self, key):
        row = self.db.execute(
            "SELECT payload FROM poster_artifacts WHERE render_hash=?", (key,)
        ).fetchone()
        return PosterArtifact.model_validate_json(row[0]) if row else None

    def save_poster(self, asset):
        with self.db:
            self.generation.locked(asset.campaign_id, asset.campaign_revision)
            self.db.execute(
                "INSERT OR IGNORE INTO poster_artifacts VALUES(?,?,?,?)",
                (asset.id, asset.campaign_id, asset.render_hash, asset.model_dump_json()),
            )
        return self.by_render_hash(asset.render_hash)

    def logo(self, asset_id, campaign_id=None):
        row = self.db.execute(
            "SELECT campaign_id,sha256,payload FROM campaign_logos WHERE id=?", (asset_id,)
        ).fetchone()
        if not row or (campaign_id and row[0] != campaign_id):
            raise domain_error("ASSET_NOT_FOUND", "Approved logo not found for this campaign")
        return json.loads(row[2])

    def snapshot(self, campaign_id):
        campaign = self.generation.campaigns.get(campaign_id)
        backgrounds = [
            Background.model_validate_json(r[0])
            for r in self.db.execute(
                "SELECT payload FROM art_backgrounds WHERE campaign_id=?", (campaign_id,)
            )
        ]
        posters = [
            PosterArtifact.model_validate_json(r[0])
            for r in self.db.execute(
                "SELECT payload FROM poster_artifacts WHERE campaign_id=?", (campaign_id,)
            )
        ]
        for poster in posters:
            from backend.art_context import LAYOUT, RENDERER_VERSION, renderer_hash

            if (
                poster.campaign_revision != campaign.revision
                or poster.render_input.renderer_version != RENDERER_VERSION
                or poster.render_input.renderer_hash != renderer_hash()
                or poster.render_input.layout_hash != digest(LAYOUT)
            ):
                poster.status = "stale"
        return ArtSnapshot(
            backgrounds=backgrounds,
            posters=posters,
            logos=[
                r[0]
                for r in self.db.execute(
                    "SELECT id FROM campaign_logos WHERE campaign_id=?", (campaign_id,)
                )
            ],
        )
