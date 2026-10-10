"""Product completeness policy, not claims about social-platform API limits."""

VERSION = "guardian-policy-2.1"
RULES = tuple(f"G{i:02}" for i in range(1, 16))
CORE_REQUIRED = frozenset({"CAFE", "LOCATION", "OFFER", "PRODUCT", "DATES", "DAYS"})
CONDITIONS = frozenset(
    {
        "ELIGIBILITY",
        "ID_RULE",
        "TIME_WINDOW",
        "DINE_IN_RULE",
        "MIN_PURCHASE_RULE",
        "COMBINE_RULE",
    }
)
# All specified conditions must be visible; hashtags/alt text never discharge disclosure.
CHANNELS = {
    "whatsapp": {"fields": ("body", "cta"), "limit": 1500},
    "instagram": {"fields": ("body", "cta", "alt_text"), "limit": 2200},
    "facebook": {"fields": ("body", "cta", "alt_text"), "limit": 3000},
    "poster": {"fields": ("headline", "body", "cta", "alt_text"), "limit": 600},
}
