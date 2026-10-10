"""Compact poster presentation from owner-approved slots, never inferred facts."""

from backend.schemas import TemplateContent

POSTER_COPY_VERSION = "poster-editorial-b1.0"


def poster_template(campaign, source):
    """Keep the hook/CTA; group every specified fact without caption prose/hashtags."""
    specified = {f.key for f in campaign.facts if f.canonical is not None}
    groups = [
        ("OFFER", "PRODUCT"),
        ("CAFE", "LOCATION"),
        ("DATES",),
        ("DAYS",),
        ("ELIGIBILITY", "ID_RULE"),
        ("TIME_WINDOW", "DINE_IN_RULE"),
        ("MIN_PURCHASE_RULE", "COMBINE_RULE"),
    ]
    rows = [" · ".join("{{" + key + "}}" for key in group if key in specified) for group in groups]
    # Preserve owner-mandated expression in the source body rather than silently lose it.
    body = source.body if campaign.brand.must_say else "\n".join(row for row in rows if row)
    return TemplateContent(
        headline=source.headline,
        body=body,
        cta=source.cta,
        hashtags=[],
        alt_text=source.alt_text,
    )
