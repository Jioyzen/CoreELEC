import hashlib
import importlib.util
import io
import json
import pathlib
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import deploy
import safe_archive


def bundle(folder, version='1.0.0', defaults=None):
    content={'.kodi/addons/script.demo/addon.xml':f'<addon id="script.demo" version="{version}"/>'.encode(),
             '.kodi/addons/script.demo/main.py':b'print("offline")\n',
             '.kodi/addons/service.demo/demo':b'program',
             '.config/input-repeat.conf':b'KODI_REMOTE_REPEAT_PERIOD_MS=200\n',
             'kodi-defaults.json':json.dumps(defaults or {'lookandfeel.skin':'skin.demo','locale.keyboardlayouts':['English QWERTY','Chinese BasePY']}).encode()}
    files={name:{'sha256':hashlib.sha256(data).hexdigest(),'size':len(data),'mode':0o644} for name,data in content.items()}
    manifest={'addons':{'script.demo':version},'files':files}
    encoded=json.dumps(manifest).encode();content['payload-manifest.json']=encoded
    with tarfile.open(folder/'payload.tar.gz','w:gz') as tar:
        for name,data in content.items():
            info=tarfile.TarInfo(name);info.size=len(data);info.mode=0o644;tar.addfile(info,io.BytesIO(data))
    summary={'schema':1,'edition':'media','profile_id':hashlib.sha256(encoded).hexdigest(),
             'payload_sha256':safe_archive.sha256(folder/'payload.tar.gz'),'expanded_size':sum(map(len,content.values()))}
    (folder/'profile.json').write_text(json.dumps(summary));return summary


class DeployTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.temp.name)
        self.bundle=self.root/'bundle';self.bundle.mkdir();self.storage=self.root/'storage'
        self.summary=bundle(self.bundle)
    def tearDown(self):self.temp.cleanup()

    def test_offline_first_boot_and_repeated_boot(self):
        first=deploy.deploy(self.bundle,self.storage)
        self.assertEqual(first['installed'],['script.demo'])
        self.assertTrue((self.storage/'.kodi/addons/service.demo/demo').is_file())
        xml=(self.storage/'.kodi/userdata/guisettings.xml').read_text()
        self.assertIn('English QWERTY|Chinese BasePY',xml)
        with patch.object(deploy,'extract_tar',side_effect=AssertionError('Must not redeploy')):
            self.assertEqual(deploy.deploy(self.bundle,self.storage),first)

    def test_upgrade_preserves_user_settings_and_newer_addons(self):
        deploy.deploy(self.bundle,self.storage)
        settings=self.storage/'.kodi/userdata/guisettings.xml';settings.write_text('private-settings')
        addon=self.storage/'.kodi/addons/script.demo/addon.xml';addon.write_text('<addon id="script.demo" version="3.0.0"/>')
        bundle(self.bundle,'2.0.0')
        result=deploy.deploy(self.bundle,self.storage)
        self.assertEqual(result['installed'],[])
        self.assertEqual(settings.read_text(),'private-settings')
        self.assertEqual(deploy.installed_version(addon.parent),'3.0.0')

    def test_damaged_payload_does_not_write_defaults_or_install(self):
        with (self.bundle/'payload.tar.gz').open('ab') as f:f.write(b'corrupt')
        with self.assertRaises(ValueError):deploy.deploy(self.bundle,self.storage)
        self.assertFalse((self.storage/'.kodi/userdata/guisettings.xml').exists())
        self.assertFalse((self.storage/'.kodi/addons/script.demo').exists())

    def test_interruption_before_directory_commit_can_retry(self):
        real=deploy.os.replace
        def replace(source,target):
            if pathlib.Path(target).name=='script.demo':raise OSError('power failure')
            return real(source,target)
        with patch.object(deploy.os,'replace',side_effect=replace):
            with self.assertRaises(OSError):deploy.deploy(self.bundle,self.storage)
        self.assertFalse((self.storage/'.kodi/userdata/guisettings.xml').exists())
        self.assertEqual(deploy.deploy(self.bundle,self.storage)['status'],'complete')

    def test_existing_remote_config_is_not_overwritten(self):
        path=self.storage/'.config/input-repeat.conf';path.parent.mkdir(parents=True);path.write_text('custom')
        deploy.deploy(self.bundle,self.storage)
        self.assertEqual(path.read_text(),'custom')

    def test_symlink_outside_storage_is_rejected(self):
        self.storage.mkdir();(self.storage/'.kodi').symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(ValueError):deploy.deploy(self.bundle,self.storage)
        self.assertFalse((self.root/'addons/script.demo').exists())

    def test_low_disk_space_keeps_existing_system(self):
        with patch.object(deploy.shutil,'disk_usage',return_value=type('Disk',(),{'free':1})()):
            with self.assertRaises(OSError):deploy.deploy(self.bundle,self.storage)
        self.assertFalse((self.storage/'.kodi/userdata/guisettings.xml').exists())


class ArchiveTests(unittest.TestCase):
    def test_unsafe_paths_and_credentials(self):
        for name in ('/etc/shadow','../../outside','a/../b','a\\b'):
            with self.assertRaises(ValueError):safe_archive.safe_path(name)
        with self.assertRaises(ValueError):safe_archive.check_text('main.py',b'sk-'+b'a'*32)
        with self.assertRaises(ValueError):safe_archive.check_text('settings.xml',b'smb://user:password@host/share')

    def test_special_tar_members_rejected_before_extract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);archive=root/'bad.tar'
            with tarfile.open(archive,'w') as tar:
                member=tarfile.TarInfo('link');member.type=tarfile.SYMTYPE;member.linkname='/etc';tar.addfile(member)
            with self.assertRaises(ValueError):safe_archive.extract_tar(archive,root/'out')
            self.assertFalse((root/'out/link').exists())


if __name__=='__main__':unittest.main()
