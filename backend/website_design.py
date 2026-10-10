"""Model chooses bounded visual structure; only code renders facts, HTML and URLs."""

import json
from typing import Literal

from backend.contracts import StrictModel, utc_now
from backend.inference_client import InferenceClient
from backend.intent_rules import digest

OPENROUTER_BASE = "https://openrouter.ai/api/v1"
PROMPT = """ROLE: WEBSITE_DESIGN v1
Choose a coherent responsive café website layout from the provided design options.
Return only the JSON object matching the supplied schema. Every field is required.
You select visual presentation only: do not write copy, facts, URLs, HTML or CSS.
Respect the owner's style. All website text and factual data are rendered elsewhere.
"""


class WebsiteDesign(StrictModel):
    layout: Literal["centered", "split", "editorial"]
    spacing: Literal["compact", "balanced", "airy"]
    heading_style: Literal["classic", "bold", "soft"]
    sections: Literal["plain", "cards"]
    photo_layout: Literal["stack", "grid"]


class WebsiteDesigner:
    def __init__(self, settings, store):
        self.settings = settings
        options = settings.model_copy(
            update={
                "inference_mode": settings.website_ai_mode,
                "inference_base_url": OPENROUTER_BASE,
                "inference_api_key": settings.openrouter_api_key,
                "text_model": settings.website_model,
                "structured_strategy": "json",
                "text_input_price_per_million": None,
                "text_output_price_per_million": None,
            }
        )
        # Trusted server-only profile override; campaign model configuration stays untouched.
        self.client = InferenceClient(options, store)

    async def close(self):
        await self.client.close()

    async def generate(self, fields):
        # Project only nonfactual preferences and section presence. No owner prose,
        # identity, offer/date/location/menu values, media URLs or provider tokens.
        context = {
            "style": fields.style,
            "languages": fields.languages,
            "sections_present": {
                "description": bool(fields.description),
                "visit": bool(fields.address or fields.hours or fields.phone or fields.whatsapp),
                "menu": bool(fields.menu),
                "social": bool(fields.social_links),
                "logo": bool(fields.logo_id),
                "photos": bool(fields.photo_ids),
            },
        }
        budget = self.client.budget(calls=2, seconds=90)
        plan = await self.client.structured(
            json.dumps(context),
            WebsiteDesign,
            budget,
            system_prompt=PROMPT,
            strategy="json",
            max_tokens=1000,
            json_mode=True,
        )
        return plan, {
            "provider": "OpenRouter",
            "model": self.settings.website_model,
            "mode": self.client.settings.inference_mode.upper(),
            "prompt_version": "website-design-v1",
            "prompt_hash": digest(PROMPT),
            "input_hash": digest(context),
            "run_id": budget.run_id,
            "calls": budget.calls,
            "captured_at": utc_now(),
            "plan": plan.model_dump(),
        }


def design_css(plan):
    # No raw strings from a model enter CSS. Enumerated choices select fixed rules.
    plan = WebsiteDesign.model_validate(plan.model_dump())
    space = {"compact": 16, "balanced": 28, "airy": 40}[plan.spacing]
    css = (
        f"main{{padding:clamp(16px,4vw,{space}px)}}"
        "section,nav{overflow-wrap:anywhere}li{flex-wrap:wrap}img{display:block}"
        ".website-photos{display:grid;gap:20px;margin-top:24px}"
        "@media(max-width:640px){main{padding:16px}h1{font-size:2rem}}"
    )
    css += {
        "centered": (
            "section{text-align:center}.logo{margin:0 auto}h1{font-size:clamp(2rem,5vw,3.5rem)}"
        ),
        "split": (
            "main{max-width:1120px}section{padding-block:32px}h1{font-size:clamp(2rem,5vw,4rem)}"
        ),
        "editorial": "main{max-width:840px}section{padding-block:36px}h1{letter-spacing:-.02em}",
    }[plan.layout]
    css += {
        "classic": "h1{font-weight:600}",
        "bold": "h1{font-weight:800}",
        "soft": "h1{font-weight:500;letter-spacing:.01em}",
    }[plan.heading_style]
    if plan.sections == "cards":
        css += "section{margin-block:16px;padding:24px;border:1px solid #d6d1c7;border-radius:16px}"
    if plan.photo_layout == "grid":
        css += ".website-photos{grid-template-columns:repeat(auto-fit,minmax(min(100%,260px),1fr))}"
    return css
