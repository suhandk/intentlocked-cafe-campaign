"""Download provider-returned images only, pin DNS to public IP, never send credentials."""

import asyncio
import base64
import hashlib
import io
import ipaddress
import json
import shutil
import socket
from pathlib import Path
from uuid import uuid4

import httpx
from PIL import Image, UnidentifiedImageError

from backend.errors import ProviderError

MAX_BYTES = 12 * 1024 * 1024
MAX_PIXELS = 16_000_000


async def download_image(
    url: str,
    destination: Path,
    *,
    mock_transport=None,
    video=False,
    video_ffprobe=None,
    allowed_hosts=(),
) -> dict:
    try:
        if not isinstance(url, str):
            raise ValueError
        if url.startswith("data:"):
            if video or len(url) > (MAX_BYTES * 4 // 3) + 100:
                raise ValueError
            header, encoded = url.split(",", 1)
            if header not in {
                "data:image/png;base64",
                "data:image/jpeg;base64",
                "data:image/webp;base64",
            }:
                raise ValueError
            raw = base64.b64decode(encoded, validate=True)
            return save_raster(raw, header[5:].split(";")[0], destination)
        parsed = httpx.URL(url)
        if (
            parsed.scheme != "https"
            or parsed.username
            or parsed.password
            or parsed.port not in (443, None)
        ):
            raise ValueError
        if mock_transport is not None:
            if not isinstance(mock_transport, httpx.MockTransport) or parsed.host != "mock.invalid":
                raise ValueError
            request_url, headers, extensions = parsed, {}, {}
        else:
            # Exact Configured provider output host observed in authenticated B8 image response.
            # TLS/public-IP pinning, credential exclusion and redirect rejection still apply.
            if parsed.host not in {
                *allowed_hosts,
                "storage.googleapis.com",
                "platform-outputs.agnes-ai.space",
            } and not parsed.host.endswith(".storage.googleapis.com"):
                raise ValueError
            addresses = await asyncio.get_running_loop().getaddrinfo(
                parsed.host, 443, type=socket.SOCK_STREAM
            )
            ips = [a[4][0] for a in addresses]
            if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
                raise ValueError
            request_url = parsed.copy_with(host=ips[0])
            headers = {"Host": parsed.host}
            extensions = {"sni_hostname": parsed.host}
        async with httpx.AsyncClient(
            transport=mock_transport,
            trust_env=False,
            follow_redirects=False,
            timeout=30,
        ) as client:
            async with asyncio.timeout(45):
                async with client.stream(
                    "GET", request_url, headers=headers, extensions=extensions
                ) as response:
                    if response.status_code != 200:
                        raise ValueError
                    mime = response.headers.get("content-type", "").split(";")[0]
                    if mime not in (
                        ("video/mp4",) if video else ("image/png", "image/jpeg", "image/webp")
                    ):
                        raise ValueError
                    raw = bytearray()
                    async for chunk in response.aiter_bytes():
                        raw.extend(chunk)
                        if len(raw) > MAX_BYTES:
                            raise ValueError
        if video:
            return await validate_video(raw, destination, ffprobe_path=video_ffprobe)
        return save_raster(raw, mime, destination)
    except (
        ValueError,
        KeyError,
        TypeError,
        httpx.HTTPError,
        OSError,
        TimeoutError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
    ):
        raise ProviderError("MEDIA_INVALID", "Media download or validation failed") from None


def save_raster(raw, mime, destination):
    if len(raw) > MAX_BYTES:
        raise ValueError
    with Image.open(io.BytesIO(raw)) as im:
        if im.width * im.height > MAX_PIXELS or min(im.size) < 1 or getattr(im, "n_frames", 1) != 1:
            raise ValueError
        expected = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}
        if expected.get(im.format) != mime:
            raise ValueError
        width, height = im.size
        im.verify()
    with Image.open(io.BytesIO(raw)) as im:
        im.load()
    extension = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}[mime]
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / f"{uuid4().hex}.{extension}"
    path.write_bytes(raw)
    return {
        "filename": path.name,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
        "width": width,
        "height": height,
        "mime": mime,
    }


async def validate_video(raw: bytes, destination: Path, *, ffprobe_path=None) -> dict:
    ffprobe = ffprobe_path or shutil.which("ffprobe")
    if not ffprobe:
        raise ProviderError(
            "VIDEO_VALIDATOR_MISSING", "ffprobe is required before a video smoke test"
        )
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / f"{uuid4().hex}.mp4"
    path.write_bytes(raw)
    process = None
    try:
        process = await asyncio.create_subprocess_exec(
            ffprobe,
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        async with asyncio.timeout(20):
            stdout, _ = await process.communicate()
        result = json.loads(stdout)
        streams = [s for s in result["streams"] if s.get("codec_type") == "video"]
        if process.returncode != 0 or not streams or float(result["format"]["duration"]) <= 0:
            raise ValueError
        return {
            "filename": path.name,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw),
            "duration": result["format"]["duration"],
            "mime": "video/mp4",
        }
    except BaseException:
        if process and process.returncode is None:
            process.kill()
            await process.wait()
        path.unlink(missing_ok=True)
        raise
