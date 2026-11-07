# SPDX-License-Identifier: GPL-2.0-only
"""Exercise real packaging hooks, updater rejection and early upgrade checks."""
import importlib.util
import json
import os
import pathlib
import subprocess
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

from validate import BOARD_ID, validate_boot_config

ROOT = pathlib.Path(__file__).resolve().parents[2]
BOARD = ROOT / 'projects/Amlogic-ce/packages/jiefu-board'
spec = importlib.util.spec_from_file_location('jiefu_updates', BOARD / 'sources/s905x2_updates.py')
updates = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updates)


def feed():
    name = 'CE22-Jiefu-20261101-073014.tar'
    return {'schema': 1, 'edition': 'jiefu-media', 'board_id': BOARD_ID,
            'architecture': 'Amlogic-no.aarch64', 'version': '22.0-Piers_devel_20261101073014',
            'build_id': 'a' * 40, 'artifact': {'name': name, 'size': 100,
            'sha256': 'b' * 64, 'url': updates.RELEASE_BASE + 'jiefu-test/' + name}}


class UpdateTests(unittest.TestCase):
    def test_own_feed(self):
        self.assertEqual(updates.validate_feed(feed()), feed())

    def test_cross_board_arch_edition_and_filename(self):
        for key, value in [('board_id', 'g12a_s905x2_u212_2g_rtl8822cs'),
                           ('architecture', 'Amlogic-ng.aarch64'), ('edition', 'media')]:
            bad = feed()
            bad[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                updates.validate_feed(bad)
        bad = feed()
        bad['artifact']['name'] = 'CoreELEC-Amlogic-no.aarch64-22.0-Piers_devel_20261101073014-MEDIA-S905X2-U212-2G-RTL8822CS.tar'
        with self.assertRaises(ValueError):
            updates.validate_feed(bad)

    def test_reject_untrusted_url_and_bad_hash(self):
        for field, value in [('url', 'https://example.invalid/image.tar'),
                             ('sha256', 'x' * 64), ('size', -1)]:
            bad = feed()
            bad['artifact'][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                updates.validate_feed(bad)

    def test_channel_unpublished_or_offline(self):
        with patch.object(updates.urllib.request, 'urlopen', side_effect=urllib.error.URLError('offline')):
            self.assertIsNone(updates.fetch_feed())
        self.assertEqual(updates.manual_response(None), {})
        self.assertEqual(json.loads(updates.automatic_response(None, {})), {'data': {}})

    def test_download_integrity(self):
        with tempfile.TemporaryDirectory() as tmp:
            package = pathlib.Path(tmp) / 'update.tar'
            package.write_bytes(b'wrong bytes')
            with self.assertRaises(ValueError):
                updates.verify_download(package, feed(), feed()['artifact']['url'])


class PackageTests(unittest.TestCase):
    def run_bash(self, script, *arguments, cwd=ROOT):
        return subprocess.run(['bash', '-e', '-c', script, 'test', *map(str, arguments)],
                              cwd=cwd, check=True, capture_output=True, text=True)

    def test_profile_selects_jiefu_and_excludes_k_board_package(self):
        options = ROOT / 'projects/Amlogic-ce/devices/Amlogic-no/options'
        self.run_bash('''
TARGET_ARCH=aarch64; JIEFU_BOARD=yes; S905X2_BOARD=no; JIOYZEN_MEDIA_EDITION=yes
. "$1"
[ "$DTBIMG" = "g12a_s905x2_u212_2g_jeff2021.dtb" ]
case " $ADDITIONAL_PACKAGES " in *" jiefu-board "*) ;; *) exit 1 ;; esac
case " $ADDITIONAL_PACKAGES " in *" s905x2-board "*) exit 1 ;; esac
case " $ADDITIONAL_PACKAGES " in *" jioyzen-media "*) ;; *) exit 1 ;; esac
''', options)
        bad = subprocess.run(['bash', '-c',
            'JIEFU_BOARD=yes; S905X2_BOARD=yes; . "$1"', 'test', str(options)],
            capture_output=True)
        self.assertNotEqual(bad.returncode, 0)

    def test_board_install_contains_identity_and_no_dv(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.run_bash('PKG_DIR="$1"; INSTALL="$2"; . "$1/package.mk"; makeinstall_target',
                          BOARD, tmp)
            path = pathlib.Path(tmp)
            manifest = json.loads((path / 'usr/share/jiefu/manifest.json').read_text())
            self.assertEqual(manifest['dt_id'], BOARD_ID)
            self.assertFalse(manifest['dolby_vision'])
            self.assertFalse(list(path.rglob('dovi*')))
            self.assertTrue((path / 'usr/lib/coreelec/evrepeat-policy.sh').is_file())

    def test_official_tee_and_dv_loader_are_unchanged(self):
        package = ROOT / 'projects/Amlogic-ce/packages/linux-drivers/amlogic/opentee_linuxdriver'
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp)
            (path / 'tee-dummy-rpmb.so').touch()
            self.run_bash('''
PKG_DIR="$1"; INSTALL="$2/image"; JIEFU_BOARD=yes; ARCH=aarch64; TEE_SOC=""
get_pkg_directory() { echo "$PKG_DIR"; }
enable_service() { :; }
. "$PKG_DIR/package.mk"
makeinstall_target
mkdir -p "$INSTALL/usr/lib/systemd/system"
cp "$PKG_DIR/system.d/opentee_linuxdriver.service" "$INSTALL/usr/lib/systemd/system/"
post_install
''', package, path, cwd=path)
            image = path / 'image'
            self.assertTrue((image / 'usr/lib/coreelec/tee-loader').is_file())
            self.assertTrue((image / 'usr/lib/coreelec/dovi-loader').is_file())
            service = (image / 'usr/lib/systemd/system/opentee_linuxdriver.service').read_text()
            self.assertIn('ExecStart=/usr/lib/coreelec/dovi-loader start', service)
            self.assertEqual(service, (package / 'system.d/opentee_linuxdriver.service').read_text())
            self.assertIn('ExecStart=/usr/lib/coreelec/tee-loader start', service)
            self.assertIn('ExecStop=/usr/lib/coreelec/tee-loader stop', service)

    def test_bootloader_installs_official_defaults(self):
        package = ROOT / 'projects/Amlogic-ce/packages/u-boot'
        boot = ROOT / 'projects/Amlogic-ce/devices/Amlogic-no/bootloader'
        with tempfile.TemporaryDirectory() as tmp:
            self.run_bash('''
JIEFU_BOARD=yes; PKG_DIR="$1"; INSTALL="$2"; PROJECT_DIR="$3/projects"
PROJECT=Amlogic-ce; DEVICE=Amlogic-no; SUBDEVICES=""; ARCH=aarch64
JIEFU_TEST_ROOT="$3"; JIEFU_TEST_BOOT="$4"
get_pkg_directory() { echo "$JIEFU_TEST_ROOT/projects/Amlogic-ce/packages/$1"; }
find_file_path() { FOUND_PATH="$JIEFU_TEST_BOOT/${1#bootloader/}"; [ -f "$FOUND_PATH" ]; }
. "$PKG_DIR/package.mk"
makeinstall_target
''', package, tmp, ROOT, boot)
            validate_boot_config(pathlib.Path(tmp) / 'usr/share/bootloader/config.ini')
            self.assertEqual((pathlib.Path(tmp) / 'usr/share/bootloader/config.ini').read_bytes(),
                             (boot / 'config.ini').read_bytes())



if __name__ == '__main__':
    unittest.main()
