#!/usr/bin/env python3
"""Install the approved HorizDroid PNG artwork as the Android launcher icon.

The artwork is user-supplied and must be copied byte-for-byte: no recolouring,
redrawing, resizing, format conversion, or generated effects.
"""
from pathlib import Path
import shutil
import struct


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "horizdroid-logo.png"
RESOURCE_DIR = ROOT / "packaging/android/res/drawable-nodpi"
PNG = RESOURCE_DIR / "launcher_icon.png"
LEGACY_WEBP_SOURCE = ROOT / "horizdroid-logo.webp"
LEGACY_WEBP_RESOURCE = RESOURCE_DIR / "launcher_icon_horizdroid.webp"
LEGACY_PNG_RESOURCE = RESOURCE_DIR / "launcher_icon_horizdroid.png"


def validate_png(path: Path) -> tuple[int, int]:
    """Validate the PNG signature and IHDR dimensions without modifying bytes."""
    data = path.read_bytes()
    if len(data) < 33 or data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"Not a valid PNG file: {path}")
    if data[12:16] != b"IHDR":
        raise ValueError(f"PNG is missing its IHDR header: {path}")
    width, height = struct.unpack(">II", data[16:24])
    if width <= 0 or height <= 0:
        raise ValueError(f"PNG has invalid dimensions: {width}x{height}")
    return width, height


def main() -> None:
    if not SOURCE.is_file():
        raise FileNotFoundError(f"Approved HorizDroid PNG is missing: {SOURCE}")
    dimensions = validate_png(SOURCE)
    RESOURCE_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SOURCE, PNG)
    if PNG.read_bytes() != SOURCE.read_bytes():
        raise RuntimeError("Launcher icon copy differs from the approved source PNG")
    if validate_png(PNG) != dimensions:
        raise RuntimeError("Launcher icon dimensions changed during copying")
    # Remove obsolete alternatives so the Android package has one clear icon.
    LEGACY_WEBP_SOURCE.unlink(missing_ok=True)
    LEGACY_WEBP_RESOURCE.unlink(missing_ok=True)
    LEGACY_PNG_RESOURCE.unlink(missing_ok=True)
    print(f"Prepared exact HorizDroid PNG launcher icon: {PNG} ({dimensions[0]}x{dimensions[1]})")


if __name__ == "__main__":
    main()
