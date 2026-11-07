# SPDX-License-Identifier: GPL-2.0-only
"""Exercise release provenance and prevent publication after validation failures."""
import json
import pathlib
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import publish
from validate import BOARD_ID, sha256


class PublishTests(unittest.TestCase):
    revision = 'a' * 40

    def sums(self, root):
        (root / 'SHA256SUMS').write_text(''.join(
            sha256(p) + '  ' + p.name + '\n' for p in sorted(root.iterdir())
            if p.name != 'SHA256SUMS'))

    def fixture(self, root):
        tag = 'jiefu-20261107-120000-aaaaaaaa'
        version = '22.0-Piers_devel_20261107120000'
        package = root / 'CE22-Jiefu-20261107-120000.tar'
        package.write_bytes(b'test upgrade')
        (root / 'CE22-Jiefu-20261107-120000.img.gz').write_bytes(b'test flash image')
        manifest = {'dt_id': BOARD_ID, 'edition': 'jiefu-media', 'dolby_vision': False,
                    'source_commit': self.revision, 'version': version, 'release_tag': tag,
                    'image_validation': 'passed', 'media_offline_validation': 'passed'}
        feed = {'schema': 1, 'edition': 'jiefu-media', 'board_id': BOARD_ID,
                'architecture': 'Amlogic-no.aarch64', 'build_id': self.revision, 'version': version,
                'artifact': {'name': package.name, 'size': package.stat().st_size,
                             'sha256': sha256(package),
                             'url': f'https://github.com/Jioyzen/CoreELEC/releases/download/{tag}/{package.name}'}}
        (root / 'build-manifest.json').write_text(json.dumps(manifest))
        (root / 'update.json').write_text(json.dumps(feed))
        (root / 'offline-image-validation.json').write_text(json.dumps(
            {'embedded_installer': 'passed', 'flash_image_system_matches_update': True}))
        (root / 'RELEASE-NOTES.md').write_text('Hardware validation pending.\n')
        self.sums(root)

    def test_draft_assets_before_public_prerelease(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self.fixture(root)
            with patch.object(publish.subprocess, 'run') as run:
                publish.publish(root, self.revision)
            self.assertEqual(run.call_count, 2)
            create = run.call_args_list[0].args[0]
            edit = run.call_args_list[1].args[0]
            self.assertIn('--draft', create)
            self.assertIn('--draft=false', edit)
            for command in (create, edit):
                self.assertIn('--prerelease', command)
                self.assertIn('--latest=false', command)
                self.assertNotIn('jiefu-channel', command)

    def test_checksum_mismatch_prevents_any_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self.fixture(root)
            (root / 'CE22-Jiefu-20261107-120000.tar').write_bytes(b'changed')
            with patch.object(publish.subprocess, 'run') as run, self.assertRaises(ValueError):
                publish.publish(root, self.revision)
            run.assert_not_called()

    def test_stale_source_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self.fixture(root)
            with self.assertRaises(ValueError):
                publish.verify(root, 'b' * 40)

    def test_wrong_board_and_failed_validation_rejected(self):
        for key, value in [('dt_id', 'g12a_s905x2_u212_2g_rtl8822cs'),
                           ('image_validation', 'failed'), ('dolby_vision', True)]:
            with tempfile.TemporaryDirectory() as tmp:
                root = pathlib.Path(tmp)
                self.fixture(root)
                path = root / 'build-manifest.json'
                manifest = json.loads(path.read_text())
                manifest[key] = value
                path.write_text(json.dumps(manifest))
                self.sums(root)
                with self.subTest(key=key), self.assertRaises(ValueError):
                    publish.verify(root, self.revision)

    def test_failed_upload_never_publishes_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self.fixture(root)
            with patch.object(publish.subprocess, 'run',
                              side_effect=subprocess.CalledProcessError(1, 'gh')) as run:
                with self.assertRaises(subprocess.CalledProcessError):
                    publish.publish(root, self.revision)
            self.assertEqual(run.call_count, 1)


if __name__ == '__main__':
    unittest.main()
