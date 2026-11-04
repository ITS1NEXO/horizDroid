#!/usr/bin/env python3
"""Generate the Android launcher resource from the approved HorizDroid logo.

The approved mark has white upper H strokes, a purple crossbar, and grey lower
legs. The original artwork's two upper strokes were accidentally green; correct
only those two green regions while preserving every other part of the logo.
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


def correct_upper_h_bars(image):
    """Turn only the two green upper H bars white; leave the head and lower legs intact."""
    image = image.convert("RGBA")
    width, height = image.size
    # Coordinates are proportional to the approved 256x256 logo artwork.
    regions = (
        (0.36, 0.51, 0.45, 0.60),
        (0.55, 0.51, 0.64, 0.60),
    )
    pixels = image.load()
    for left, top, right, bottom in regions:
        x0, x1 = int(width * left), int(width * right)
        y0, y1 = int(height * top), int(height * bottom)
        for y in range(y0, y1):
            for x in range(x0, x1):
                red, green, blue, alpha = pixels[x, y]
                if alpha and green > 150 and red < 100 and blue < 150:
                    pixels[x, y] = (255, 255, 255, alpha)
    return image


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
        corrected = correct_upper_h_bars(generated)
        size = corrected.size
        if size[0] < 1 or size[1] < 1:
            raise ValueError("Generated launcher resource has invalid dimensions")
        corrected.save(PNG, format="PNG", optimize=True)
    with Image.open(PNG) as generated:
        generated.verify()
        if generated.format != "PNG" or generated.size != size:
            raise ValueError("Corrected launcher resource is not a valid PNG")
    # Remove obsolete alternate resource names so there is one authoritative icon.
    UNUSED_WEBP_RESOURCE.unlink(missing_ok=True)
    UNUSED_PNG_RESOURCE.unlink(missing_ok=True)
    print(f"Prepared corrected Android launcher resource: {PNG} ({size[0]}x{size[1]})")


if __name__ == "__main__":
    main()
