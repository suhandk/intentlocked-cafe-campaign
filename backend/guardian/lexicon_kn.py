"""Draft Kannada/Kanglish vocabulary. Native review: PENDING, never certified."""

NUMBERS = dict(
    zip(
        (
            "ಸೊನ್ನೆ ಒಂದು ಎರಡು ಮೂರು ನಾಲ್ಕು ಐದು ಆರು ಏಳು ಎಂಟು ಒಂಬತ್ತು ಹತ್ತು ಹನ್ನೊಂದು ಹನ್ನೆರಡು "
            "ಹದಿಮೂರು ಹದಿನಾಲ್ಕು ಹದಿನೈದು ಹದಿನಾರು ಹದಿನೇಳು ಹದಿನೆಂಟು ಹತ್ತೊಂಬತ್ತು"
        ).split(),
        range(20),
        strict=True,
    )
)
NUMBERS.update(
    dict(
        zip(
            "ಇಪ್ಪತ್ತು ಮೂವತ್ತು ನಲವತ್ತು ಐವತ್ತು ಅರವತ್ತು ಎಪ್ಪತ್ತು ಎಂಬತ್ತು ತೊಂಬತ್ತು ನೂರು".split(),
            range(20, 101, 10),
            strict=True,
        )
    )
)
NUMBERS.update({"ಇಪ್ಪತ್ತೈದು": 25, "ಅರ್ಧ": 0.5, "ಕಾಲು": 0.25})
NUMBERS.update(
    dict(
        zip(
            "sonne ondu eradu mooru naalku aidu aaru elu entu ombattu hattu".split(),
            range(11),
            strict=True,
        )
    )
)
NUMBERS.update(
    {
        "ippattu": 20,
        "ippatthu": 20,
        "ippattaidu": 25,
        "ippatthaidu": 25,
        "ippathaidu": 25,
        "ippattu aidu": 25,
        "moovattu": 30,
        "nalavattu": 40,
        "aivattu": 50,
        "aravattu": 60,
        "eppattu": 70,
        "embattu": 80,
        "tombattu": 90,
        "nooru": 100,
        "ardha": 0.5,
    }
)
DATES = (
    "ಸೋಮವಾರ ಮಂಗಳವಾರ ಬುಧವಾರ ಗುರುವಾರ ಶುಕ್ರವಾರ ಶನಿವಾರ ಭಾನುವಾರ "
    "somavara mangalavara budhavara guruvara shukravara shanivara bhanuvara "
    "ಜನವರಿ ಫೆಬ್ರವರಿ ಮಾರ್ಚ್ ಏಪ್ರಿಲ್ ಮೇ ಜೂನ್ ಜುಲೈ ಆಗಸ್ಟ್ ಸೆಪ್ಟೆಂಬರ್ ಅಕ್ಟೋಬರ್ ನವೆಂಬರ್ ಡಿಸೆಂಬರ್ "
    "ಇಂದು ನಾಳೆ ನಾಡಿದ್ದು ವಾರಾಂತ್ಯ ivattu naale nadiddu weekend"
).split()
CLAIMS = ["ಉಚಿತ", "ಅತ್ಯುತ್ತಮ", "ಅತ್ಯಂತ", "ಖಚಿತ", "ಅನಿಯಮಿತ", "ಮಾತ್ರ", "uchita", "bestu", "maatra"]
CONDITIONS = ["ಐಡಿ ಬೇಡ", "ಐಡಿ ಬೇಕು", "ಎಲ್ಲರಿಗೂ", "ವಿದ್ಯಾರ್ಥಿಗಳಿಗೆ ಮಾತ್ರ", "ellarigu", "id beda"]
TIMES = ["ದಿನವಿಡೀ", "ಮಧ್ಯರಾತ್ರಿ", "dinavidi", "ರಾತ್ರಿ", "ಸಂಜೆ", "ಬೆಳಿಗ್ಗೆ"]
PRODUCTS_LOCATIONS = ["ಕಾಫಿ", "ಚಹಾ", "ಕೇಕ್", "ಬೆಂಗಳೂರು", "ಮೈಸೂರು"]
WRAPPERS = ["ಅಲ್ಲ", "ಇಲ್ಲ", "ಬೇಡ", "ಹೊರತು", "ಮಾತ್ರ", "alla", "illa", "beda", "maatra"]
