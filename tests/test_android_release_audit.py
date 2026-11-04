import importlib.util
import io
from pathlib import Path
import struct
import tempfile
import unittest
import zipfile
import zlib
import sys
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('android_release_audit', Path(__file__).resolve().parents[1] / 'tools/check_android_release.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def archive(files):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as z:
        for name, data in files.items():
            z.writestr(name, data)
    return output.getvalue()


def png(width, height, color, rows, depth=8, palette=b'', transparency=b''):
    def chunk(kind, body):
        return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body))
    raw = b''.join(b'\x00' + bytes(row) for row in rows)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, depth, color, 0, 0, 0))
            + (chunk(b'PLTE', palette) if palette else b'') + (chunk(b'tRNS', transparency) if transparency else b'')
            + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))


# The same 2x2 picture as straight RGBA and as a 2-bit palette image with a different
# colour under the transparent pixel, which an encoder is free to rewrite.
PICTURE_RGBA = png(2, 2, 6, [[255, 0, 0, 255, 0, 255, 0, 255], [0, 0, 255, 128, 9, 9, 9, 0]])
PICTURE_PALETTE = png(2, 2, 3, [[0x10], [0xB0]], depth=2, palette=bytes([255, 0, 0, 0, 255, 0, 0, 0, 255, 0, 0, 0]),
                      transparency=bytes([255, 255, 128, 0]))
OTHER_PICTURE = png(2, 2, 6, [[255, 0, 0, 255, 0, 255, 0, 255], [0, 0, 254, 128, 9, 9, 9, 0]])
BADGING = ("package: name='{app_id}'\napplication-label:'HorizDroid'\n"
           "application-icon-160:'res/drawable-nodpi-v4/launcher_icon.png'\n")


class ReleaseAuditTests(unittest.TestCase):
    def test_dev_package_does_not_relax_stable_identity_or_debuggable_check(self):
        with tempfile.TemporaryDirectory() as temporary:
            apk = Path(temporary) / 'test.apk'
            apk.write_bytes(b'test')
            payload = {'findings': []}
            with patch.object(audit, 'inspect_payload', return_value=payload), patch.object(
                    audit, 'check_icon', return_value=True), patch.object(
                    audit.subprocess, 'check_output', return_value=BADGING.format(app_id='dev.horizdroid.android')):
                with self.assertRaises(ValueError):
                    audit.audit(apk, 'aapt2')
                report = audit.audit(apk, 'aapt2', app_id='dev.horizdroid.android')
                self.assertTrue(report['passed'])
                self.assertEqual((report['package'], report['label'], report['icon_matches_source']),
                                 ('dev.horizdroid.android', 'HorizDroid', True))
            with patch.object(audit, 'inspect_payload', return_value={'findings': []}), patch.object(
                    audit, 'check_icon', return_value=True), patch.object(
                    audit.subprocess, 'check_output', return_value=BADGING.format(app_id='dev.horizdroid.android') + 'application-debuggable\n'):
                self.assertFalse(audit.audit(apk, 'aapt2', app_id='dev.horizdroid.android')['passed'])

    def test_wrong_application_label_or_icon_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            apk = Path(temporary) / 'test.apk'
            apk.write_bytes(b'test')
            badging = BADGING.format(app_id='dev.horizdroid.android')
            with patch.object(audit, 'inspect_payload', return_value={'findings': []}), patch.object(
                    audit.subprocess, 'check_output', return_value=badging.replace("'HorizDroid'", "'Horizon Android'")), patch.object(
                    audit, 'check_icon', return_value=True):
                with self.assertRaises(ValueError):
                    audit.audit(apk, 'aapt2', app_id='dev.horizdroid.android')
            with patch.object(audit, 'inspect_payload', return_value={'findings': []}), patch.object(
                    audit.subprocess, 'check_output', return_value=badging), patch.object(
                    audit, 'check_icon', return_value=False):
                with self.assertRaises(ValueError):
                    audit.audit(apk, 'aapt2', app_id='dev.horizdroid.android')

    def test_launcher_icon_must_match_source_pixels_not_encoding(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            source = folder / 'launcher_icon.png'
            source.write_bytes(PICTURE_RGBA)
            badging = BADGING.format(app_id='dev.horizdroid.android')
            apk = folder / 'a.apk'
            for packaged, expected in [(PICTURE_PALETTE, True), (PICTURE_RGBA, True), (OTHER_PICTURE, False)]:
                apk.write_bytes(archive({'res/drawable-nodpi-v4/launcher_icon.png': packaged}))
                self.assertEqual(audit.check_icon(apk, badging, source), expected)
            apk.write_bytes(archive({'res/drawable-nodpi-v4/launcher_icon.png': PICTURE_RGBA}))
            with self.assertRaises(ValueError):
                audit.check_icon(apk, "package: name='x'\n", source)
            with self.assertRaises(ValueError):
                audit.check_icon(apk, badging.replace('.png', '.xml'), source)

    def test_public_apk_accepts_generated_tables_and_rejects_original_assets(self):
        build_spec = importlib.util.spec_from_file_location('android_build', Path(__file__).resolve().parents[1] / 'tools/android_build.py')
        build = importlib.util.module_from_spec(build_spec)
        build_spec.loader.exec_module(build)
        self.assertTrue(build.generated_engine_file('worldgen/blocks/structure-blocks.json'))
        self.assertFalse(build.generated_engine_file('worldgen/structure/minecraft/village/test.nbt'))
        with tempfile.TemporaryDirectory() as folder, patch.dict(sys.modules, {'android_build': build}):
            path = Path(folder) / 'public.apk'
            files = {'AndroidManifest.xml': b'test', 'assets/engine-data.zip': archive({'facts.json': b'{}'})}
            path.write_bytes(archive(files))
            self.assertEqual(audit.inspect_payload(path, public=True)['findings'], [])
            for name in ['worldgen/structure/minecraft/test.nbt', 'worldgen/biomes.json', 'raw.jar', 'unknown.json']:
                files['assets/engine-data.zip'] = archive({name: b'original content'})
                path.write_bytes(archive(files))
                self.assertIn('original_game_resource', {f['kind'] for f in audit.inspect_payload(path, public=True)['findings']})
            files['assets/bedrock-controls.zip'] = archive({'ui/jump.png': b'texture'})
            path.write_bytes(archive(files))
            with self.assertRaises(ValueError):
                audit.inspect_payload(path, public=True)
    def inspect(self, engine=None, extra=None):
        files = {'AndroidManifest.xml': b'test manifest',
                 'assets/engine-data.zip': archive(engine or {'blocks.json': b'{}'}),
                 'assets/bedrock-controls.zip': archive({'LICENSE.md': b'license'}),
                 **(extra or {})}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'test.apk'
            path.write_bytes(archive(files))
            return audit.inspect_payload(path)

    def test_resource_only_apk_has_no_private_findings(self):
        self.assertEqual(self.inspect()['findings'], [])

    def test_androidx_build_profiles_are_allowed(self):
        self.assertEqual(self.inspect(extra={'assets/dexopt/baseline.prof': b'compiled profile'})['findings'], [])

    def test_nested_player_data_and_unexpected_asset_are_rejected(self):
        report = self.inspect({'profiles/account.json': b'{}'}, {'assets/settings.json': b'{}'})
        self.assertEqual({f['kind'] for f in report['findings']}, {'private_file', 'unexpected_asset'})

    def test_credential_in_native_library_is_rejected_without_reporting_value(self):
        token = b'ghp_' + b'X' * 36
        report = self.inspect(extra={'lib/arm64-v8a/libtest.so': b'ELF\x00' + token})
        self.assertEqual(report['findings'][0]['kind'], 'github_token')
        self.assertNotIn(token.decode(), str(report))

    def test_personal_build_path_and_private_key_are_rejected(self):
        key = b'-----BEGIN ' + b'PRIVATE KEY-----'
        report = self.inspect(extra={'lib/arm64-v8a/libtest.so': b'C:/Users/example/.cargo/source.rs\x00' + key})
        self.assertEqual({f['kind'] for f in report['findings']}, {'personal_build_path', 'private_key'})

    def test_nested_traversal_is_rejected(self):
        with self.assertRaises(ValueError):
            self.inspect({'../account.json': b'{}'})


    def test_manifest_uses_the_launcher_resource_generated_by_ci(self):
        root = Path(__file__).resolve().parents[1]
        manifest = (root / 'packaging/android/AndroidManifest.xml').read_text()
        generator = (root / 'tools/prepare_android_icon.py').read_text()
        self.assertIn('android:icon="@drawable/launcher_icon"', manifest)
        self.assertNotIn('android:icon="@drawable/launcher_icon_horizdroid"', manifest)
        self.assertIn('launcher_icon.png', generator)
