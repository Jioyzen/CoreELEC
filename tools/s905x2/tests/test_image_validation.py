import importlib.util
import io
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('image_validation', Path(__file__).resolve().parents[1]/'image_validation.py')
image = importlib.util.module_from_spec(spec)
spec.loader.exec_module(image)


@unittest.skipUnless(shutil.which('mksquashfs') and shutil.which('unsquashfs'), 'requires squashfs tools')
class OrdinaryImageTests(unittest.TestCase):
    def exercise(self, media=False, corrupt=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root/'source'
            source.mkdir()
            (source/'ordinary-file').write_text('ordinary')
            if media:
                addon = source/'usr/share/jioyzen-media'
                addon.mkdir(parents=True)
                (addon/'payload.tar.gz').write_bytes(b'media')
            system = root/'SYSTEM'
            subprocess.run(['mksquashfs', str(source), str(system), '-noappend', '-no-progress', '-processors','1'],
                           check=True, stdout=subprocess.DEVNULL)
            data = b'corrupted-system' if corrupt else system.read_bytes()
            package = root/'update.tar'
            with tarfile.open(package,'w') as archive:
                member = tarfile.TarInfo('CoreELEC/target/SYSTEM')
                member.size = len(data)
                archive.addfile(member,io.BytesIO(data))
            return image.verify_base_system(system,package,root/'report.json',root)

    def test_flash_matches_update_and_media_payload_is_absent(self):
        self.assertTrue(self.exercise()['media_payload_absent'])

    def test_accidental_media_payload_in_ordinary_image_is_rejected(self):
        with self.assertRaises(ValueError): self.exercise(media=True)

    def test_wrong_update_system_is_rejected(self):
        with self.assertRaises(ValueError): self.exercise(corrupt=True)


if __name__=='__main__': unittest.main()
