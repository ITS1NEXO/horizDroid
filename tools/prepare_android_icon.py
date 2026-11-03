#!/usr/bin/env python3
"""Create the Android PNG launcher resource from the original HorizDroid WebP logo.

The generated PNG is a build input, not a separately edited or redesigned icon.
"""
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "horizdroid-logo.webp"
RESOURCE_DIR = ROOT / "packaging/android/res/drawable-nodpi"
PNG = RESOURCE_DIR / "launcher_icon_horizdroid.png"
WEBP_RESOURCE = RESOURCE_DIR / "launcher_icon_horizdroid.webp"


def main():
    if not SOURCE.is_file():
        raise FileNotFoundError(f"Original HorizDroid logo is missing: {SOURCE}")
    RESOURCE_DIR.mkdir(parents=True, exist_ok=True)
    with Image.open(SOURCE) as original:
        original.seek(0)
        original.load()
        # PNG launcher resources are static; use the first frame if the source is animated.
        icon = original.convert("RGBA")
        icon.save(PNG, format="PNG", optimize=True)
    # Android cannot package two drawable files with the same resource name.
    WEBP_RESOURCE.unlink(missing_ok=True)
    with Image.open(PNG) as generated:
        generated.verify()
    print(f"Prepared PNG launcher resource: {PNG} ({icon.width}x{icon.height})")


if __name__ == "__main__":
    main()
