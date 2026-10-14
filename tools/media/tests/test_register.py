import importlib.util
import pathlib
import tempfile
import unittest
import xml.etree.ElementTree as ET

from test_deploy import bundle

ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('media_register',ROOT/'register.py')
register=importlib.util.module_from_spec(spec);spec.loader.exec_module(register)


class RegisterTests(unittest.TestCase):
    def test_first_start_addons_are_enabled_optional_system_components(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);b=root/'bundle';b.mkdir()
            summary=bundle(b)
            import json
            summary['addons']={'script.demo':'1.0.0'}
            (b/'profile.json').write_text(json.dumps(summary))
            path=root/'system/usr/share/kodi/system/addon-manifest.xml';path.parent.mkdir(parents=True)
            path.write_text('<addons><addon>skin.estuary</addon></addons>')
            register.register(b,root/'system');register.register(b,root/'system')
            addons=ET.parse(path).getroot().findall('addon')
            self.assertEqual(len(addons),2)
            self.assertEqual(addons[1].text,'script.demo')
            self.assertEqual(addons[1].get('optional'),'true')

    def test_profile_identity_mismatch_prevents_registration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);b=root/'bundle';b.mkdir()
            summary=bundle(b)
            import json
            summary['addons']={'script.demo':'9.0.0'}
            (b/'profile.json').write_text(json.dumps(summary))
            with self.assertRaises(ValueError):register.register(b,root/'system')
