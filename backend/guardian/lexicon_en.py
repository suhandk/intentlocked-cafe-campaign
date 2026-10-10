"""Versioned detection vocabulary. Matching uses Unicode letter/mark boundaries."""

ONES = (
    "zero one two three four five six seven eight nine ten eleven twelve thirteen "
    "fourteen fifteen sixteen seventeen eighteen nineteen"
).split()
TENS = "twenty thirty forty fifty sixty seventy eighty ninety".split()
NUMBERS = {word: i for i, word in enumerate(ONES)}
for value, word in enumerate(TENS, 2):
    NUMBERS[word] = value * 10
    for i in range(1, 10):
        NUMBERS[f"{word} {ONES[i]}"] = value * 10 + i
        NUMBERS[f"{word}-{ONES[i]}"] = value * 10 + i
NUMBERS.update({"hundred": 100, "one hundred": 100, "half": 0.5, "quarter": 0.25})
DATES = (
    "monday tuesday wednesday thursday friday saturday sunday mon tue wed thu fri sat sun "
    "january february march april may june july august september october november december "
    "jan feb mar apr jun jul aug sep sept oct nov dec today tomorrow tonight weekend"
).split()
CLAIMS = [
    "best",
    "no.1",
    "#1",
    "top",
    "finest",
    "guaranteed",
    "guarantee",
    "free",
    "unlimited",
    "lowest price",
    "cheapest",
    "award-winning",
    "healthy",
    "authentic",
    "in the city",
    "in india",
    "better",
    "fastest",
    "freshest",
    "organic",
    "exclusive",
    "only",
    "ignore all",
    "ignore previous",
    "system prompt",
    "approve now",
    "bypass",
    "override",
]
CONDITIONS = [
    "no id",
    "without id",
    "id required",
    "id needed",
    "dine-in",
    "dine in",
    "takeaway",
    "minimum purchase",
    "no minimum",
    "combine",
    "with every",
    "per cup",
    "students only",
    "everyone",
    "open to all",
    "families",
    "delivery",
    "while stocks last",
    "first come",
]
TIMES = ["all day", "24x7", "midnight", "noon", "till", "until", "after", "before"]
PRODUCTS_LOCATIONS = [
    "coffee",
    "tea",
    "cake",
    "pizza",
    "bengaluru",
    "bangalore",
    "mysuru",
    "mumbai",
]
WRAPPERS = [
    "not",
    "no",
    "never",
    "except",
    "excluding",
    "instead",
    "up to",
    "upto",
    "at least",
    "from",
    "starting",
    "maybe",
    "possibly",
    "double",
    "without",
    "unless",
    "if",
    "but",
    "expired",
    "cancelled",
    "unavailable",
    "fake",
    "joke",
    "only",
    "plus",
    "extra",
]
