#!/usr/bin/env python3
"""Generate the Android launcher resource from the approved HorizDroid logo.

AndroidManifest references @drawable/launcher_icon. Generate that exact resource
name so the approved black-background HorizDroid H artwork replaces the stale
legacy launcher icon instead of creating an unused drawable.
"""
from pathlib import Path
import shutil
import subprocess

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "horizdroid-logo.webp"
RESOURCE_DIR = ROOT / "packaging/android/res/drawable-nodpi"
PNG = RESOURCE_DIR / "launcher_icon.png"
UNUSED_WEBP_RESOURCE = RESOURCE_DIR / "launcher_icon_horizdroid.webp"
UNUSED_PNG_RESOURCE = RESOURCE_DIR / "launcher_icon_horizdroid.png"


def main():
    if not SOURCE.is_file():
        raise FileNotFoundError(f"Original HorizDroid logo is missing: {SOURCE}")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg is required to extract the PNG launcher frame")
    RESOURCE_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(SOURCE),
        "-map", "0:v:0", "-frames:v", "1", "-pix_fmt", "rgba", str(PNG),
    ], check=True, timeout=60)
    with Image.open(PNG) as generated:
        generated.verify()
    with Image.open(PNG) as generated:
        size = generated.size
        if generated.format != "PNG" or size[0] < 1 or size[1] < 1:
            raise ValueError("Generated launcher resource is not a valid PNG")
    # Remove the obsolete alternate resource names so there is one authoritative icon.
    UNUSED_WEBP_RESOURCE.unlink(missing_ok=True)
    UNUSED_PNG_RESOURCE.unlink(missing_ok=True)
    print(f"Prepared Android launcher resource: {PNG} ({size[0]}x{size[1]})")


if __name__ == "__main__":
    main()
