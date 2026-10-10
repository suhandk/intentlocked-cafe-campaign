"""Shadow normalization. Offsets are half-open Python Unicode code-point offsets."""

import unicodedata as ud
from dataclasses import dataclass

# Deliberately not O/l -> digits. Only visually confusable Latin-like letters.
CONFUSABLES = str.maketrans("аеросхуіΑΒΕΖΗΙΚΜΝΟΡΤΥΧ", "aepocxyiABEZHIKMNOPTYX")


@dataclass(frozen=True)
class Shadow:
    text: str
    offsets: tuple[tuple[int, int], ...]

    def original_span(self, start: int, end: int) -> tuple[int, int]:
        if not 0 <= start < end <= len(self.text):
            raise ValueError("Nonempty shadow span required")
        return self.offsets[start][0], self.offsets[end - 1][1]


def normalize(original: str) -> Shadow:
    output: list[str] = []
    offsets: list[tuple[int, int]] = []
    i = 0
    while i < len(original):
        start = i
        i += 1
        while i < len(original) and ud.category(original[i]).startswith("M"):
            i += 1
        cluster = ud.normalize("NFKC", original[start:i]).translate(CONFUSABLES).casefold()
        for char in cluster:
            if ud.category(char) == "Cf" or char == "\u034f":
                continue
            if char.isdecimal():
                char = str(ud.decimal(char))
            if char.isspace():
                char = " "
                if output and output[-1] == " ":
                    offsets[-1] = (offsets[-1][0], i)
                    continue
            output.append(char)
            offsets.append((start, i))
    return Shadow("".join(output), tuple(offsets))
