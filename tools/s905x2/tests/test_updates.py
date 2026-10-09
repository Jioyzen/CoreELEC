#!/usr/bin/env python3
"""Test feed policy and the actual patched CoreELEC check/download flow."""
import copy
import hashlib
import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[3]
HELPER = ROOT / 'projects/Amlogic-ce/packages/s905x2-board/sources/s905x2_updates.py'
spec = importlib.util.spec_from_file_location('s905x2_updates', HELPER)
u = importlib.util.module_from_spec(spec)
spec.loader.exec_module(u)
sys.modules['s905x2_updates'] = u
PAYLOAD = b'S905X2 test upgrade bytes'
VERSION = '22.0-Piers_devel_20261010010000'
NAME = f'CoreELEC-Amlogic-no.aarch64-{VERSION}-S905X2-U212-2G-RTL8822CS.tar'
FEED = dict(schema=1, board_id=u.BOARD_ID, architecture=u.ARCHITECTURE,
            version=VERSION, build_id='a' * 40,
            artifact=dict(name=NAME, url=u.RELEASE_BASE + 'test/' + NAME,
                          sha256=hashlib.sha256(PAYLOAD).hexdigest(), size=len(PAYLOAD)))
LOCAL = dict(VERSION='22.0-Piers_devel_20261009052551', BUILD_ID='b' * 40)


class FeedTests(unittest.TestCase):
    def test_new_same_older_builds(self):
        self.assertTrue(u.is_newer(FEED, LOCAL))
        self.assertFalse(u.is_newer(FEED, dict(LOCAL, BUILD_ID='a' * 40)))
        self.assertFalse(u.is_newer(FEED, dict(LOCAL, VERSION=VERSION)))
        self.assertFalse(u.is_newer(FEED, dict(LOCAL, VERSION='22.0-Piers_devel_20261011010000')))
        self.assertTrue(u.is_newer(FEED, dict(LOCAL, VERSION='22.0-Piers_nightly_20261008')))
        with self.assertRaises(ValueError):
            u.is_newer(FEED, dict(LOCAL, VERSION='unknown'))

    def test_reject_incompatible_or_invalid_feeds(self):
        cases = [('board_id', 'other'), ('architecture', 'Amlogic-ng.arm'),
                 ('schema', 2), ('version', '23.0'), ('build_id', 'bad')]
        for key, value in cases:
            data = copy.deepcopy(FEED); data[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                u.validate_feed(data)
        for key, value in [('url', 'https://example.org/' + NAME),
                           ('url', u.RELEASE_BASE + 'test/' + NAME + '?x=1'),
                           ('name', '../bad.tar'), ('sha256', 'bad'), ('size', -1)]:
            data = copy.deepcopy(FEED); data['artifact'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                u.validate_feed(data)
        self.assertEqual(u.validate_feed(json.dumps(FEED)), FEED)

    def test_response_protocols(self):
        response = json.loads(u.automatic_response(FEED, LOCAL))['data']
        self.assertEqual('https://%s/%s/%s' % (response['host'], response['folder'], response['update']), FEED['artifact']['url'])
        manual = u.manual_response(FEED)[u.CHANNEL]
        self.assertEqual(manual['url'] + manual['project'][u.ARCHITECTURE]['releases']['1']['file']['name'], FEED['artifact']['url'])
        self.assertEqual(json.loads(u.automatic_response(FEED, dict(LOCAL, VERSION=VERSION))), {'data': {}})

    def test_verify_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = pathlib.Path(tmp) / 'update'; p.write_bytes(PAYLOAD)
            u.verify_download(p, FEED, FEED['artifact']['url'])
            p.write_bytes(b'X' * len(PAYLOAD))
            with self.assertRaises(ValueError): u.verify_download(p, FEED, FEED['artifact']['url'])
            p.write_bytes(PAYLOAD[:-1])
            with self.assertRaises(ValueError): u.verify_download(p, FEED, FEED['artifact']['url'])
            with self.assertRaises(ValueError): u.verify_download(p, FEED, 'https://wrong')


class UpdaterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        # Snapshot of the pinned official settings updater, retaining its GPL header.
        # Build-time patch application also checks the actual upstream source.
        dest = pathlib.Path(cls.tmp.name) / 'src/resources/lib/modules/updates.py'
        dest.parent.mkdir(parents=True)
        dest.write_bytes((ROOT / 'tools/s905x2/tests/fixtures/updates.py.source').read_bytes())
        patch_file = ROOT / 'projects/Amlogic-ce/packages/mediacenter/CoreELEC-settings/patches/1000-s905x2-release-updates.patch'
        subprocess.run(['patch', '-p1', '-i', str(patch_file)], cwd=cls.tmp.name, check=True, stdout=subprocess.DEVNULL)
        for name in ['xbmc', 'xbmcgui', 'oeWindows']:
            sys.modules[name] = types.ModuleType(name)
        dialog = types.SimpleNamespace(yesno=lambda *a: False)
        sys.modules['xbmcgui'].Dialog = lambda: dialog
        spec = importlib.util.spec_from_file_location('patched_updates', dest)
        cls.module = importlib.util.module_from_spec(spec); spec.loader.exec_module(cls.module)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.storage = tempfile.TemporaryDirectory()
        self.addCleanup(self.storage.cleanup)
        self.temp = pathlib.Path(self.storage.name)
        self.loaded_urls = []; self.logs = []; self.notifications = []
        self.oe = types.SimpleNamespace(
            ARCHITECTURE=u.ARCHITECTURE, BUILD='Jioyzen', LOGDEBUG=0, TEMP=str(self.temp) + '/',
            dbg_log=lambda *a: self.logs.append(a), notify=lambda *a: self.notifications.append(a),
            load_url=lambda url: self.loaded_urls.append(url), _=lambda x: str(x))
        self.updater = self.module.updates.__new__(self.module.updates)
        self.updater.oe = self.oe
        self.updater.LOCAL_UPDATE_DIR = str(self.temp / 'staged') + '/'
        self.updater.UPDATE_DOWNLOAD_URL = 'https://%s/%s/%s'
        self.updater.struct = {'update': {'settings': {'UpdateNotify': {'value': '1'}, 'AutoUpdate': {'value': 'manual'}}}}
        real_isfile = self.module.os.path.isfile
        self.marker = patch.object(self.module.os.path, 'isfile', side_effect=lambda p: p == u.MARKER or real_isfile(p))
        self.marker.start(); self.addCleanup(self.marker.stop)

    def test_check_manual_prompts_for_custom_build(self):
        with patch.object(u, 'fetch_feed', return_value=FEED), patch.object(u, 'read_os_release', return_value=LOCAL), patch.object(self.module.xbmcgui, 'Dialog') as dialog:
            dialog.return_value.yesno.return_value = False
            self.updater.check_updates_v2(force=True)
        dialog.return_value.yesno.assert_called_once()
        self.assertEqual(self.updater.update_file, FEED['artifact']['url'])
        self.assertEqual(self.loaded_urls, [])

    def test_network_failure_never_falls_back_to_official(self):
        with patch.object(u, 'fetch_feed', side_effect=OSError('offline')):
            self.updater.check_updates_v2()
        self.assertFalse(hasattr(self.updater, 'update_file'))
        self.assertEqual(self.loaded_urls, [])

    def test_auto_download_verifies_and_stages_without_reboot(self):
        self.updater.struct['update']['settings']['AutoUpdate']['value'] = 'auto'
        def download(url, dest, silent):
            pathlib.Path(dest).write_bytes(PAYLOAD); return dest
        self.oe.download_file = download
        with patch.object(u, 'fetch_feed', return_value=FEED), patch.object(u, 'read_os_release', return_value=LOCAL), patch.object(self.module.subprocess, 'call'), patch.object(self.module.xbmc, 'restart', create=True) as restart:
            self.updater.check_updates_v2()
        self.assertEqual((self.temp / 'staged' / NAME).read_bytes(), PAYLOAD)
        restart.assert_not_called()
        self.assertEqual(self.loaded_urls, [])
        # A service restart does not download the same pending tar again.
        del self.updater.update_in_progress
        with patch.object(u, 'fetch_feed') as fetch:
            self.updater.check_updates_v2()
        fetch.assert_not_called()

    def test_bad_download_removed_and_retry_possible(self):
        self.updater.s905x2_feed = FEED
        self.updater.update_file = FEED['artifact']['url']
        self.updater.update_in_progress = True
        def download(url, dest, silent):
            pathlib.Path(dest).write_bytes(b'corrupt'); return dest
        self.oe.download_file = download
        self.updater.do_autoupdate(silent=True)
        self.assertFalse(list((self.temp / 'staged').iterdir()))
        self.assertFalse((self.temp / 'update_file').exists())
        self.assertFalse(hasattr(self.updater, 'update_in_progress'))


if __name__ == '__main__':
    unittest.main()
