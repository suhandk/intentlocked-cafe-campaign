"""One trusted headless-browser renderer, shared with browser verification."""

import asyncio
import json
import shutil
import tempfile
from pathlib import Path

from backend.art_context import ROOT
from backend.art_models import CanvasValidation
from backend.errors import ProviderError


async def render_canvas(canvas_input, origin):
    node = shutil.which("node")
    if not node:
        raise ProviderError(
            "RENDER_UNAVAILABLE", "Node and Chrome are required for canvas rendering"
        )
    with tempfile.TemporaryDirectory(prefix="campaign-canvas-") as directory:
        folder = Path(directory)
        source, result, png = folder / "input.json", folder / "result.json", folder / "poster.png"
        source.write_text(canvas_input.model_dump_json(), encoding="utf-8")
        process = await asyncio.create_subprocess_exec(
            node,
            str(ROOT / "frontend/scripts/render-poster.mjs"),
            str(source),
            str(result),
            str(png),
            origin,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            async with asyncio.timeout(45):
                await process.wait()
            response = json.loads(result.read_text(encoding="utf-8")) if result.exists() else {}
            if process.returncode != 0 or "error" in response:
                code = response.get("error", "RENDER_FAILED")
                if code not in {
                    "FONT_TIMEOUT",
                    "FONT_UNAVAILABLE",
                    "IMAGE_UNAVAILABLE",
                    "TEXT_OVERFLOW",
                    "GRAPHEME_OVERFLOW",
                    "CANVAS_TAINTED",
                    "CROSS_ORIGIN_ASSET",
                }:
                    code = "RENDER_FAILED"
                raise ProviderError(code, "Poster rendering failed; no artifact was authorized")
            return png.read_bytes(), CanvasValidation.model_validate(response)
        except (OSError, ValueError, TimeoutError):
            raise ProviderError(
                "RENDER_FAILED", "Canvas output is unavailable or invalid"
            ) from None
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()
