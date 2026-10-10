"""Install a checksum-verified Windows FFmpeg build in ignored project-local storage."""

import hashlib
import json
import os
import zipfile
from pathlib import Path

import httpx

URL = "https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-9.0.2-essentials_build.zip"


def main():
    if os.name != "nt":
        raise SystemExit(
            "Install ffmpeg and ffprobe using your system package manager on Linux/macOS"
        )
    root = Path(__file__).resolve().parents[1] / "data/video-tools"
    root.mkdir(parents=True, exist_ok=True)
    archive = root / "ffmpeg-9.0.2.zip"
    with httpx.Client(timeout=60, follow_redirects=True, trust_env=False) as client:
        response = client.get(URL + ".sha256")
        response.raise_for_status()
        expected = response.text.split()[0].lower()
        if len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
            raise SystemExit("Invalid build checksum")
        with client.stream("GET", URL) as response:
            response.raise_for_status()
            with archive.open("wb") as output:
                for chunk in response.iter_bytes():
                    output.write(chunk)
    actual = hashlib.sha256(archive.read_bytes()).hexdigest()
    if actual != expected:
        archive.unlink()
        raise SystemExit("FFmpeg build checksum mismatch")
    target = root / "installed"
    target.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive) as package:
        for member in package.infolist():
            resolved = (target / member.filename).resolve()
            if not resolved.is_relative_to(target.resolve()):
                raise SystemExit("Unsafe archive path")
        package.extractall(target)
    (root / "installation.json").write_text(
        json.dumps({"source": URL, "sha256": actual, "version": "9.0.2"}, indent=2) + "\n",
        encoding="utf-8",
    )
    print("FFmpeg/FFprobe 9.0.2 installed; published checksum matches")


if __name__ == "__main__":
    main()
