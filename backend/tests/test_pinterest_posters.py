import pytest

from backend.art_context import RENDERER_VERSION, art_brief, art_key, image_prompt
from backend.guardian.policy import CORE_REQUIRED
from backend.guardian.slots import parse, render
from backend.poster_copy import poster_template
from backend.schemas import TemplateContent
from backend.tests.test_generation import locked as locked_fixture


def test_poster_projection_keeps_every_specified_fact_and_source_caption():
    campaign = locked_fixture.__wrapped__()
    source = TemplateContent(
        headline="A little pause, just for you",
        body="Long social caption {{OFFER}} {{PRODUCT}} {{CAFE}} {{LOCATION}}",
        cta="Come say hello",
        hashtags=["#CafePause"],
        alt_text="{{CAFE}} · {{PRODUCT}}",
    )
    original = source.model_dump()
    poster = poster_template(campaign, source)
    tokens = {t.key for t in parse(poster.body)}
    assert tokens == {f.key for f in campaign.facts if f.canonical}
    assert CORE_REQUIRED <= tokens
    assert not ({f.key for f in campaign.facts if not f.canonical} & tokens)
    assert not poster.hashtags and "Long social caption" not in poster.body
    assert source.model_dump() == original
    rendered = render(campaign, poster, "en")
    assert len(rendered.spans) >= len(tokens)
    assert all(s.approval_id for s in rendered.spans)
    assert poster_template(campaign, poster) == poster


def test_mandatory_owner_wording_is_preserved():
    campaign = locked_fixture.__wrapped__()
    campaign.brand.must_say = ["A friendly hello"]
    source = TemplateContent(
        headline="Pause", body="A friendly hello {{CAFE}}", cta="Visit", hashtags=[], alt_text=""
    )
    assert poster_template(campaign, source).body == source.body


@pytest.mark.parametrize("ratio", ["1:1", "9:16", "16:9"])
def test_editorial_art_direction_is_safe_and_differentiated(ratio):
    campaign = locked_fixture.__wrapped__()
    brief = art_brief(campaign, ratio)
    assert "café advertising" in brief["theme"]
    assert "large coffee hero" in brief["composition"]
    assert campaign.facts[0].canonical.value not in str(brief)
    assert len({art_key(campaign, r, "agnes") for r in ["1:1", "9:16", "16:9"]}) == 3


def test_modern_reference_changes_style_without_copying_reference_claims():
    campaign = locked_fixture.__wrapped__()
    before = campaign.model_dump()
    text = image_prompt(art_brief(campaign, "1:1"))
    assert "forest-green" in text and "cream paper" in text
    assert "full handle" in text and "on the right" in text
    assert "Reference style" in text and "No text, letters, numbers" in text
    assert "25%" not in text and "Cafe Moments" not in text
    assert "Namma Cafe" not in text and "Bengaluru" not in text
    assert RENDERER_VERSION == "canvas-modern-cafe-b1.0"
    assert campaign.model_dump() == before


def test_non_coffee_campaign_does_not_acquire_reference_coffee_subject():
    campaign = locked_fixture.__wrapped__()
    product = next(f for f in campaign.facts if f.key == "PRODUCT")
    product.canonical.value = "tea"
    brief = art_brief(campaign, "1:1")
    assert not brief["allowed_product_illustration"]
    assert "coffee" not in brief["composition"]
    assert "cup" not in brief["text_safe_region"]
    assert "no products" in brief["visual_subject"]
