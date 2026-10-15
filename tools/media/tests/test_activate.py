import importlib.util
import json
import pathlib
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT=pathlib.Path(__file__).resolve().parents[1]


class ActivationTests(unittest.TestCase):
    def exercise(self,fresh,initial,new=()):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);bundle=root/'bundle';bundle.mkdir()
            ids={'script.demo':'1.0','plugin.video.jellycon':'1.0'}
            (bundle/'profile.json').write_text(json.dumps({'profile_id':'test','addons':ids,'default_disabled_addons':['plugin.video.jellycon']}))
            for aid in ids:
                folder=root/'.kodi/addons'/aid;folder.mkdir(parents=True)
                (folder/'addon.xml').write_text('<addon id="'+aid+'" version="1.0"/>')
            cache=root/'.cache/jioyzen-media';cache.mkdir(parents=True)
            (cache/'deployment.json').write_text(json.dumps({'fresh_settings':fresh,'new_addons':list(new)}))
            state={aid:initial for aid in ids};actions=[]
            def rpc(method,params):
                if method=='Addons.GetAddonDetails':return {'addon':{'enabled':state[params['addonid']]}}
                if method=='Addons.SetAddonEnabled':
                    actions.append((params['addonid'],params['enabled']));state[params['addonid']]=params['enabled'];return 'OK'
                if method=='Settings.GetSettingValue':return {'value':''}
                raise AssertionError(method)
            fake=types.SimpleNamespace(executebuiltin=lambda value:None,log=lambda *args:None,LOGERROR=4)
            with patch.dict(sys.modules,xbmc=fake):
                spec=importlib.util.spec_from_file_location('media_activate',ROOT/'activate.py')
                module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
                module.STORAGE=root;module.BUNDLE=bundle;module.rpc=rpc;module.main()
            report=json.loads((cache/'activation.json').read_text())
            self.assertEqual(report['status'],'complete')
            return state,actions,report

    def test_fresh_install_disables_jellycon_even_if_previously_registered(self):
        state,actions,report=self.exercise(True,True)
        self.assertFalse(state['plugin.video.jellycon'])
        self.assertNotIn('plugin.video.jellycon',report['addons'])
        self.assertNotIn(('plugin.video.jellycon',True),actions)

    def test_upgrade_keeps_existing_user_enabled_choice(self):
        state,actions,report=self.exercise(False,True)
        self.assertTrue(state['plugin.video.jellycon'])
        self.assertEqual(actions,[])

    def test_upgrade_with_new_jellycon_leaves_it_disabled(self):
        state,actions,report=self.exercise(False,False,new=('plugin.video.jellycon',))
        self.assertFalse(state['plugin.video.jellycon'])
        self.assertNotIn(('plugin.video.jellycon',True),actions)
