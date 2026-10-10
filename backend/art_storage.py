"""Content-addressed, decoded raster storage. No client paths, SVG or remote serving."""

import hashlib
import io
import os
import warnings
from pathlib import Path
from uuid import uuid4

from PIL import Image, UnidentifiedImageError

from backend.errors import ProviderError

MAX_BYTES = 12 * 1024 * 1024
MAX_PIXELS = 16_000_000
MIMES = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def raster(raw: bytes, mime: str, *, logo=False, dimensions=None):
    try:
        if not raw or len(raw) > (2 * 1024 * 1024 if logo else MAX_BYTES):
            raise ValueError
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as image:
                if MIMES.get(image.format) != mime or (logo and image.format != "PNG"):
                    raise ValueError
                if image.width * image.height > MAX_PIXELS or min(image.size) < 1:
                    raise ValueError
                if getattr(image, "n_frames", 1) != 1:
                    raise ValueError
                if dimensions and image.size != dimensions:
                    raise ValueError
                image.verify()
            with Image.open(io.BytesIO(raw)) as image:
                image.load()
                # Re-encode to remove metadata, embedded profiles and trailing payloads.
                output = io.BytesIO()
                image.convert("RGBA" if logo else "RGB").save(output, "PNG")
                return output.getvalue(), image.size
    except (
        ValueError,
        OSError,
        UnidentifiedImageError,
        Image.DecompressionBombWarning,
        Image.DecompressionBombError,
    ):
        raise ProviderError("ART_INVALID", "Raster bytes, MIME or dimensions are unsafe") from None


class ArtStorage:
    def __init__(self, root):
        self.root = Path(root).resolve() / "b4"
        self.root.mkdir(parents=True, exist_ok=True)

    def write(self, raw):
        key = sha(raw)
        path = self.root / f"{key}.png"
        if not path.exists():
            temporary = self.root / f"{uuid4().hex}.tmp"
            try:
                temporary.write_bytes(raw)
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
        self.read(key)
        return key

    def read(self, key):
        if len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
            raise ProviderError("ART_INVALID", "Invalid artifact hash")
        try:
            raw = (self.root / f"{key}.png").read_bytes()
        except OSError:
            raise ProviderError("ASSET_NOT_FOUND", "Stored artifact is unavailable") from None
        if sha(raw) != key:
            raise ProviderError("ART_TAMPERED", "Stored artifact hash no longer matches")
        return raw
