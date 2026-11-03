#!/usr/bin/env python3
"""Audit a release-candidate APK's payload and require a non-debuggable Android manifest.

This is a bounded credential/data check, not a guarantee against every secret
format. Reports contain counts and paths, never suspected credential values.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import struct
import subprocess
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
APP_LABEL = 'HorizDroid'
APP_IDS = ['dev.horizon.android', 'dev.horizdroid.android']
ICON_SOURCE = ROOT / 'packaging/android/res/drawable-nodpi/launcher_icon.png'
ASSETS ={'assets/engine-data.zip', 'assets/bedrock-controls.zip'}
# AndroidX build-time optimization profiles, not player/account profiles.
BUILD_ASSETS = {'assets/dexopt/baseline.prof', 'assets/dexopt/baseline.profm'}
LICENSE_ASSETS = {'assets/LICENSE.txt', 'assets/THIRD_PARTY_NOTICES.md'}
PRIVATE_PARTS = {'accounts', 'accounts.json', 'session.json', 'session-file.json',
                 'control.json', 'servers.dat', 'level.dat', 'options.txt',
                 'android-launch.json', 'android-launcher.json', 'saves', 'profiles',
                 'logs', 'crash-reports', 'credentials', 'key.properties'}
PRIVATE_SUFFIXES = {'.keystore', '.jks', '.p12', '.pfx', '.log', '.hprof'}
PATTERNS = {
    'private_key': re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'github_token': re.compile(rb'gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{60,}'),
    'aws_key': re.compile(rb'AKIA[A-Z0-9]{16}'),
    'jwt': re.compile(rb'eyJ[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}'),
    'saved_token': re.compile(rb'"(?:access_token|refresh_token|minecraft_token)"\s*:\s*"[A-Za-z0-9._~+/-]{24,}"'),
    'personal_build_path': re.compile(rb'[A-Za-z]:[\\/]+Users[\\/]+[^\\/\x00\r\n ]+[\\/]'),
}


def inspect_payload(path, public=False):
    findings = []
    totals = {'entries': 0, 'uncompressed_bytes': 0}

    def walk(archive, prefix='', depth=0):
        if depth > 3:
            raise ValueError('Unexpected archive nesting')
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Duplicate archive entries')
        for entry in archive.infolist():
            name = entry.filename
            full = prefix + name
            parts = PurePosixPath(name).parts
            if '\\' in name or name.startswith('/') or '..' in parts or re.match(r'^[A-Za-z]:', name):
                raise ValueError('Unsafe archive path')
            if entry.flag_bits & 1 or (entry.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('Encrypted or symbolic-link archive entry')
            if entry.is_dir():
                continue
            totals['entries'] += 1
            totals['uncompressed_bytes'] += entry.file_size
            if entry.file_size > 256 * 1024 * 1024 or totals['uncompressed_bytes'] > 1024 * 1024 * 1024:
                raise ValueError('APK exceeds audit decompression limits')
            if any(part.lower() in PRIVATE_PARTS for part in parts) or PurePosixPath(name).suffix.lower() in PRIVATE_SUFFIXES:
                findings.append({'path': full, 'kind': 'private_file'})
            if depth == 0 and name.startswith('assets/') and name not in ASSETS | BUILD_ASSETS | LICENSE_ASSETS:
                findings.append({'path': full, 'kind': 'unexpected_asset'})
            data = archive.read(entry)
            for kind, pattern in PATTERNS.items():
                if pattern.search(data):
                    findings.append({'path': full, 'kind': kind})
            if name.lower().endswith('.zip'):
                with zipfile.ZipFile(io.BytesIO(data)) as nested:
                    if public and name == 'assets/engine-data.zip':
                        from android_build import generated_engine_file
                        for item in nested.namelist():
                            if not generated_engine_file(item):
                                findings.append({'path': full + '!/' + item, 'kind': 'original_game_resource'})
                    walk(nested, full + '!/', depth + 1)

    with zipfile.ZipFile(path) as archive:
        missing = ({'assets/engine-data.zip'} if public else ASSETS).difference(archive.namelist())
        if missing:
            raise ValueError('Required resource archives are absent')
        if public and 'assets/bedrock-controls.zip' in archive.namelist():
            raise ValueError('Public APK must download original control textures, not bundle them')
        walk(archive)
    return {**totals, 'findings': findings}


def decode_png(data):
    """Decode a PNG to (width, height, RGBA bytes) so a build tool's lossless re-encoding still compares equal."""
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('Launcher icon is not a PNG')
    position, header, palette, transparency, compressed = 8, None, b'', b'', []
    while position + 8 <= len(data):
        length, kind = struct.unpack('>I4s', data[position:position + 8])
        body = data[position + 8:position + 8 + length]
        position += 12 + length
        if kind == b'IHDR':
            header = struct.unpack('>IIBBBBB', body)
        elif kind == b'PLTE':
            palette = body
        elif kind == b'tRNS':
            transparency = body
        elif kind == b'IDAT':
            compressed.append(body)
        elif kind == b'IEND':
            break
    if header is None:
        raise ValueError('Launcher icon PNG has no header')
    width, height, depth, color, _, _, interlace = header
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color)
    if interlace or channels is None or depth not in (1, 2, 4, 8) or (depth < 8 and color not in (0, 3)) or (
            transparency and color in (0, 2)):
        raise ValueError('Unsupported launcher icon PNG encoding')
    stride = (width * depth * channels + 7) // 8
    step = max(1, depth * channels // 8)
    raw = zlib.decompress(b''.join(compressed))
    if len(raw) != height * (stride + 1):
        raise ValueError('Launcher icon PNG data is corrupt')
    pixels, previous = bytearray(), bytearray(stride)
    for y in range(height):
        base = y * (stride + 1)
        mode, line = raw[base], bytearray(raw[base + 1:base + 1 + stride])
        if mode > 4:
            raise ValueError('Launcher icon PNG data is corrupt')
        for i in range(stride):
            left = line[i - step] if i >= step else 0
            up = previous[i]
            corner = previous[i - step] if i >= step else 0
            if mode == 1:
                line[i] = (line[i] + left) & 255
            elif mode == 2:
                line[i] = (line[i] + up) & 255
            elif mode == 3:
                line[i] = (line[i] + (left + up) // 2) & 255
            elif mode == 4:
                estimate = left + up - corner
                by_left, by_up, by_corner = abs(estimate - left), abs(estimate - up), abs(estimate - corner)
                near = left if by_left <= by_up and by_left <= by_corner else up if by_up <= by_corner else corner
                line[i] = (line[i] + near) & 255
        previous = line
        if depth == 8:
            values = line
        else:
            values = [(byte >> (8 - depth * (n + 1))) & ((1 << depth) - 1) for byte in line for n in range(8 // depth)]
        for x in range(width):
            if color == 6:
                pixel = tuple(values[x * 4:x * 4 + 4])
            elif color == 2:
                pixel = (*values[x * 3:x * 3 + 3], 255)
            elif color == 4:
                pixel = (values[x * 2],) * 3 + (values[x * 2 + 1],)
            elif color == 0:
                gray = values[x] * 255 // ((1 << depth) - 1)
                pixel = (gray, gray, gray, 255)
            else:
                index = values[x]
                pixel = (*palette[index * 3:index * 3 + 3], transparency[index] if index < len(transparency) else 255)
            # Fully transparent pixels carry no colour; encoders may rewrite it.
            pixels += bytes(pixel) if pixel[3] else b'\x00\x00\x00\x00'
    return width, height, bytes(pixels)


def check_icon(path, badging, source=ICON_SOURCE):
    """The launcher icon the APK declares must be the repository's icon, pixel for pixel."""
    icons = re.findall(r"^application-icon-(\d+):'([^']+)'$", badging, re.MULTILINE)
    if not icons:
        raise ValueError('APK declares no launcher icon')
    resource = max(icons, key=lambda item: int(item[0]))[1]
    if not resource.endswith('.png'):
        raise ValueError('Launcher icon is not a PNG resource')
    with zipfile.ZipFile(path) as archive:
        packaged = archive.read(resource)
    return decode_png(packaged) == decode_png(Path(source).read_bytes())


def audit(path, aapt2, public=False, app_id='dev.horizon.android', app_label=APP_LABEL, icon_source=ICON_SOURCE):
    report = inspect_payload(path, public)
    badging = subprocess.check_output([str(aapt2), 'dump', 'badging', str(path)], text=True)
    if f"package: name='{app_id}'" not in badging:
        raise ValueError('Unexpected Android package identity')
    if not re.search(rf"^application-label:'{re.escape(app_label)}'$", badging, re.MULTILINE):
        raise ValueError('Unexpected Android application label')
    if not check_icon(path, badging, icon_source):
        raise ValueError('Launcher icon does not match packaging/android/res/drawable-nodpi/launcher_icon.png')
    report['package'], report['label'], report['icon_matches_source'] = app_id, app_label, True
    report['debuggable'] = 'application-debuggable' in badging
    if report['debuggable']:
        report['findings'].append({'path': 'AndroidManifest.xml', 'kind': 'debuggable'})
    report['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    report['bytes'] = path.stat().st_size
    report['passed'] = not report['findings']
    report['payload_mode'] = 'generated-tables-and-official-downloads' if public else 'private-development'
    report['bundled_game_resources'] = ['assets/engine-data.zip (generated tables)'] if public else sorted(ASSETS)
    report['distribution_clearance'] = 'Technical payload audit; no legal certification.'
    report['scope'] = 'Archive paths, packaged assets, known credential patterns, personal compiler paths and manifest debuggability; no exhaustive secret-format guarantee.'
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk', type=Path)
    parser.add_argument('--aapt2', required=True, type=Path)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--public', action='store_true')
    parser.add_argument('--app-id', choices=APP_IDS, default='dev.horizon.android')
    args = parser.parse_args()
    report = audit(args.apk, args.aapt2, args.public, args.app_id)
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report['passed'] else 1)


if __name__ == '__main__':
    main()
