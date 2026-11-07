"""Validate the standalone media release before any GitHub mutation."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('publish_media', ROOT / 'tools/s905x2/publish_media.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class MediaPublishTests(unittest.TestCase):
    def fixture(self, root):
        package = root / 'media.tar'
        package.write_bytes(b'test upgrade')
        tag = 'media-20261107-aaaa'
        manifest = {'edition':'media', 'release_tag':tag, 'source_commit':'a'*40}
        feed = {'edition':'media', 'board_id':'g12a_s905x2_u212_2g_rtl8822cs',
                'architecture':'Amlogic-no.aarch64', 'build_id':'a'*40,
                'artifact':{'name':package.name, 'size':package.stat().st_size,
                            'sha256':module.digest(package),
                            'url':f'https://github.com/Jioyzen/CoreELEC/releases/download/{tag}/{package.name}'}}
        (root / 'build-manifest.json').write_text(json.dumps(manifest))
        (root / 'update.json').write_text(json.dumps(feed))
        (root / 'offline-image-validation.json').write_text(json.dumps({'embedded_installer':'passed'}))
        self.sums(root)

    def sums(self, root):
        (root / 'SHA256SUMS').write_text(''.join(module.digest(p)+'  '+p.name+'\n'
            for p in sorted(root.iterdir()) if p.name != 'SHA256SUMS'))

    def test_media_needs_no_base_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.fixture(root)
            self.assertEqual(module.verify(root)['edition'],'media')

    def test_modified_package_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.fixture(root);(root/'media.tar').write_bytes(b'changed')
            with self.assertRaises(ValueError):module.verify(root)

    def test_cross_board_rejected_even_with_matching_checksums(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.fixture(root)
            path=root/'update.json';feed=json.loads(path.read_text());feed['board_id']='g12a_s905x2_u212_2g_jeff2021'
            path.write_text(json.dumps(feed));self.sums(root)
            with self.assertRaises(ValueError):module.verify(root)

    def test_offline_image_validation_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.fixture(root)
            (root/'offline-image-validation.json').write_text(json.dumps({'embedded_installer':'failed'}));self.sums(root)
            with self.assertRaises(ValueError):module.verify(root)


if __name__=='__main__':unittest.main()
