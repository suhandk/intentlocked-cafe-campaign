"""Explicit offline R3/R4 fixtures; never a live or cached fallback."""


def strategy_fixture(data):
    segments = data["eligible_segments"]
    preferred = [s for s in ["students", "professionals", "families"] if s in segments]
    if len(preferred) < 3:
        preferred = [segments[0]] * 3
    return {
        "result": {
            "status": "success",
            "audiences": [
                {
                    "segment": preferred[i],
                    "motivation": motivation,
                    "angle": angle,
                    "tone": tone,
                    "preferred_channel": data["channels"][i % len(data["channels"])],
                }
                for i, (motivation, angle, tone) in enumerate(
                    [
                        ("connection", "shared_pause", "playful"),
                        ("routine", "personal_ritual", "calm"),
                        ("pause", "catch_up", "warm"),
                    ]
                )
            ],
            "personas": [
                {
                    "audience_index": i % 3,
                    "priority": priority,
                    "reading_style": ["quick_scan", "detail_reader", "visual_first"][i % 3],
                    "decision_style": ["spontaneous", "planner", "cautious"][i % 3],
                }
                for i, priority in enumerate(["connection", "routine", "pause", "value", "focus"])
            ],
            "message_hierarchy": ["OFFER", "PRODUCT", "LOCATION", "DATES"],
            "hero_index": 0,
        }
    }


def copy_fixture(data):
    hooks = {
        "en": [
            "Make room for a shared pause",
            "Your ritual, your rhythm",
            "Let the conversation linger",
            "A pause between pages",
            "Let your mind unwind",
        ],
        "kn": [
            "ಜೊತೆಯಾಗಿ ವಿರಾಮ ಮಾಡೋಣ",
            "ನಿಮ್ಮದೇ ಪುಟ್ಟ ವಿರಾಮ",
            "ಮಾತುಕತೆಗೆ ಸಮಯ ಕೊಡೋಣ",
            "ಓದಿನ ನಡುವೆ ವಿರಾಮ",
            "ಮನಸ್ಸಿಗೆ ವಿರಾಮ",
        ],
        "kn-Latn": [
            "Jotheyagi break thagona",
            "Nimma viraama, nimma rhythm",
            "Maathukathe munduvariyali",
            "Odina naduve viraama",
            "Manassige viraama",
        ],
    }
    angles = ["shared_pause", "personal_ritual", "catch_up", "study_reset", "unwind"]
    openings = {
        "en": {
            "instagram": "A little space to reconnect.",
            "whatsapp": "Shall we meet?",
            "facebook": "Leave room for a conversation and a pause.",
        },
        "kn": {
            "instagram": "ನಗುವಿಗೆ ಜಾಗ ಕೊಡೋಣ.",
            "whatsapp": "ಭೇಟಿಯಾಗೋಣವೇ?",
            "facebook": "ಮಾತುಕತೆಗಾಗಿ ಸಮಯ ಮಾಡಿಕೊಳ್ಳೋಣ.",
        },
        "kn-Latn": {
            "instagram": "Naguvige jaaga kodona.",
            "whatsapp": "Bheti aagona?",
            "facebook": "Maathukathege samaya maadona.",
        },
    }
    ctas = {"en": "Come along!", "kn": "ಬನ್ನಿ, ಜೊತೆಯಾಗೋಣ!", "kn-Latn": "Banni, jothe aagona!"}
    entries = []
    language = data["language"]
    for item in data["combinations"]:
        audience = next(a for a in data["audiences"] if a["id"] == item["audience_id"])
        slots = " · ".join("{{" + key + "}}" for key in data["required_visible_slots"])
        entries.append(
            {
                **item,
                "template": {
                    "headline": hooks[language][angles.index(audience["angle"])],
                    "body": openings[language][item["channel"]] + "\n" + slots,
                    "cta": ctas[language],
                    "hashtags": [],
                    "alt_text": "{{CAFE}} · {{PRODUCT}} · {{OFFER}}",
                },
            }
        )
    return {"result": {"status": "success", "language": language, "entries": entries}}
