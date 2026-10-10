"""Safe visual input projection and versioned art/font/layout dependencies."""

import json
from pathlib import Path

from backend.art_storage import sha
from backend.errors import ProviderError
from backend.intent_rules import digest

ROOT = Path(__file__).resolve().parents[1]

PUBLIC = ROOT / "frontend/public"

RENDERER_VERSION = "canvas-modern-cafe-b1.0"

LAYOUT = {
    "version": "layout-modern-cafe-b1.0",
    "copy": "poster-editorial-b1.0",
    "text_plate": "cream_paper_forest_brush",
    "scrim": "#F8EDD7",
    "text": "#123C2B",
    "min_contrast": 7,
    "square_margin": 64,
    "story_top": 200,
    "story_bottom": 240,
    "landscape_margin": 48,
    "min_font": {"feed": 26, "square": 26, "story": 30, "landscape": 24},
}


def font_manifest():
    try:
        manifest = json.loads((PUBLIC / "fonts/manifest.json").read_text())

        for item in manifest["files"]:
            if sha((PUBLIC / "fonts" / item["file"]).read_bytes()) != item["sha256"]:
                raise ValueError

        return digest(manifest)

    except (OSError, ValueError, KeyError):
        raise ProviderError(
            "FONT_UNAVAILABLE", "Bundled font or license is missing or altered"
        ) from None


def art_brief(campaign, ratio):
    # Project only a supported visual category, never brand/offer/date/venue literals.

    product = next((f.canonical for f in campaign.facts if f.key == "PRODUCT"), None)

    coffee = bool(
        product
        and product.kind == "text"
        and product.value.casefold().strip()
        in {
            "coffee",
            "ಕಾಫಿ",
            "kaapi",
            "kaafi",
            "kapi",
        }
    )

    return {
        "visual_subject": (
            "one unbranded ceramic coffee mug, visible coffee and subtle steam; "
            "photorealistic commercial beverage photography, rich reflections and depth; "
            "no extra food, gifts or unsupported menu items"
            if coffee
            else "warm amber studio lighting, rich espresso textures and "
            "abstract decorative shadows; no products"
        ),
        "palette": campaign.brand.colors or ["#20150F", "#FBC844", "#FFF4DF", "#A56A39"],
        "theme": {
            "1:1": "premium café advertising photograph with cinematic warm amber light",
            "9:16": "vertical café advertising photograph with dramatic depth and warm light",
            "16:9": "wide café advertising still life with cinematic directional light",
        }[ratio],
        "composition": (
            "large coffee hero on the right, filling the lower-right half; "
            "close-up editorial beverage photography with a tactile speckled ceramic mug, "
            "realistic coffee surface, subtle steam and soft warm amber highlights; "
            "anonymous espresso studio backdrop and softly lit wood-textured surface; "
            "keep the entire cup and handle visible inside the central 70 percent; "
            "no flat vector cartoon, isolated icon, extra products or blank gradient"
            if coffee
            else "editorial espresso texture on the right with softly lit anonymous "
            "studio shadows; no identifiable products or menu items"
        ),
        "aspect_ratio": ratio,
        "text_safe_region": "quiet left space; code adds textured cream paper on the left, "
        "a forest-green brush offer panel and mustard accents; keep the main cup on "
        "the right so the paper does not hide it; do not generate typography or badges"
        if coffee
        else "quiet left space for code-owned cream paper and typography; "
        "keep decorative textures on the right; no products or generated lettering",
        "allowed_product_illustration": coffee,
        "visual_version": "modern-cafe-b1.0",
    }


def art_key(campaign, ratio, source, provider_context=None):
    return digest(
        {
            "brief": art_brief(campaign, ratio),
            "source": source,
            "provider_context": provider_context,
            "mode": campaign.mode,
            "t1": sha((ROOT / "backend/prompts/T1.txt").read_bytes()),
            "qa": sha((ROOT / "backend/prompts/R9.md").read_bytes()),
        }
    )


def image_context(settings):
    # Preserve existing gateway keys; direct-provider transport is a new dependency.
    context = {
        "endpoint": settings.inference_base_url,
        "image": settings.image_model,
        "qa": settings.text_model,
    }
    if settings.image_provider == "openai":
        context.update(
            endpoint="https://api.openai.com/v1",
            image_provider="openai",
            qa_endpoint="https://api.openai.com/v1" if settings.enable_vision else None,
        )
    return context


def image_prompt(brief):
    return (
        (ROOT / "backend/prompts/T1.txt")
        .read_text(encoding="utf-8")
        .format(**{**brief, "palette": ", ".join(brief["palette"])})
    )


def renderer_hash():
    return sha((PUBLIC / "renderer/canvas.js").read_bytes())
