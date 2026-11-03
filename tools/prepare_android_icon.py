#!/usr/bin/env python3
"""Create the Android PNG launcher resource from the original HorizDroid WebP logo.

The generated PNG preserves the original artwork and uses the first frame for a
static launcher icon. It is a build input, not a separately redesigned icon.
"""
from pathlib import Path
import shutil
import subprocess

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "horizdroid-logo.webp"
RESOURCE_DIR = ROOT / "packaging/android/res/drawable-nodpi"
PNG = RESOURCE_DIR / "launcher_icon_horizdroid.png"
WEBP_RESOURCE = RESOURCE_DIR / "launcher_icon_horizdroid.webp"


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
    # Android cannot package two drawable files with the same resource name.
    WEBP_RESOURCE.unlink(missing_ok=True)
    print(f"Prepared PNG launcher resource: {PNG} ({size[0]}x{size[1]})")


if __name__ == "__main__":
    main()
