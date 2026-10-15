import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


network = load('wifi_network', ROOT / 'wifi/network.py')


class WifiTests(unittest.TestCase):
    def setUp(self):
        fake = types.SimpleNamespace(Monitor=lambda: None)
        with patch.dict(sys.modules, xbmc=fake, xbmcgui=types.SimpleNamespace(WindowXMLDialog=object)):
            self.wizard = load('wifi_wizard', ROOT / 'wifi/wizard.py')

    def test_connected_wired_and_wifi_are_skipped(self):
        for link in ('ethernet', 'wifi'):
            for state in ('ready', 'online'):
                info = network.summarize([('/wifi', {'Type': 'wifi'})],
                                         [('/service', {'Type': link, 'State': state})])
                self.assertFalse(self.wizard.needs_setup(info))

    def test_no_wireless_hardware_is_skipped(self):
        info = network.summarize([('/wired', {'Type': 'ethernet'})], [])
        self.assertFalse(self.wizard.needs_setup(info))

    def test_disconnected_and_dhcp_in_progress_need_setup(self):
        for state in ('idle', 'failure', 'association', 'configuration'):
            info = network.summarize([('/wifi', {'Type': 'wifi', 'Powered': False})],
                                     [('/service', {'Type': 'wifi', 'State': state})])
            self.assertTrue(self.wizard.needs_setup(info))

    def test_existing_hotspot_is_not_reconfigured(self):
        info = network.summarize([('/wifi', {'Type': 'wifi', 'Tethering': True})], [])
        self.assertFalse(self.wizard.needs_setup(info))

    def test_visible_networks_have_stable_path_identity_and_signal_order(self):
        info = network.summarize([], [
            ('/a', {'Type': 'wifi', 'Name': 'Same SSID', 'Strength': 20}),
            ('/b', {'Type': 'wifi', 'Name': 'Same SSID', 'Strength': 90}),
            ('/c', {'Type': 'wifi', 'Name': '中文网络', 'Strength': 50}),
            ('/hidden', {'Type': 'wifi', 'Strength': 100}),
            ('/wired', {'Type': 'ethernet', 'Name': 'Wired'}),
        ])
        self.assertEqual([n['path'] for n in info['networks']], ['/b', '/c', '/a'])

    def test_error_details_and_passwords_are_not_returned(self):
        self.assertEqual(network.error_code(ValueError('private secret 123')), 'failed')
        self.assertEqual(network.error_code(ValueError('net.connman.Error.Invalid-key')), 'password')
        self.assertEqual(network.error_code(asyncio.TimeoutError()), 'timeout')

    def test_invalid_service_paths_never_reach_dbus(self):
        client = object.__new__(network.ConnMan)
        self.assertEqual(asyncio.run(client.connect('/net/connman/service/ethernet_x', 'secret')),
                         {'error': 'unavailable'})

    def test_no_credentials_or_network_identity_in_completion_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(self.wizard, 'CACHE', root), patch.object(self.wizard, 'MARKER', root/'wifi-setup.json'):
                self.wizard.remember('connected')
                report = json.loads((root/'wifi-setup.json').read_text())
                self.assertEqual(set(report), {'schema', 'reason', 'time'})
                self.assertFalse((root/'wifi-setup.partial').exists())

    def test_ssid_cannot_inject_kodi_label_formatting(self):
        self.assertEqual(self.wizard.display_name('[COLOR red]Router[/COLOR]'), '［COLOR red］Router［/COLOR］')

    def test_dialog_has_required_controls_and_no_stale_focus_border(self):
        root = ET.parse(ROOT/'wifi/resources/skins/Default/1080i/wifi.xml').getroot()
        ids = {c.get('id') for c in root.findall('.//control')}
        self.assertTrue({'4', '10', '20', '21', '30'} <= ids)
        focused = root.find('.//focusedlayout')
        self.assertIn('Control.HasFocus(10)', [n.text for n in focused.findall('.//visible')])

    def test_backend_password_uses_stdin_not_command_arguments(self):
        fake_process = types.SimpleNamespace(communicate=lambda *a, **kw: (b'{"connected":true}', b''))
        with patch.object(self.wizard.subprocess, 'Popen', return_value=fake_process) as popen:
            result = self.wizard.Backend().call('connect', path='/net/connman/service/wifi_test', password='DO_NOT_LOG')
            self.assertTrue(result['connected'])
            self.assertNotIn('DO_NOT_LOG', str(popen.call_args))

    def startup(self, state, *, home=True, existing=False):
        clock = [0]
        shown = []
        def wait(seconds):
            clock[0] += seconds
            return False
        class InlineExecutor:
            def __init__(self, **kwargs): pass
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def submit(self, function, *args):
                value = function(*args)
                return types.SimpleNamespace(done=lambda: True, result=lambda: value)
        fake_backend = types.SimpleNamespace(call=lambda *a: state, stop=lambda: None)
        fake_xbmc = types.SimpleNamespace(getCondVisibility=lambda cond: home if cond=='Window.IsActive(home)' else False,
                                         executebuiltin=lambda *a: None, log=lambda *a: None, LOGERROR=4)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            if existing:
                (root/'wifi-setup.json').write_text(json.dumps({'reason': existing if isinstance(existing, str) else 'deferred'}))
            with patch.object(self.wizard, 'CACHE', root), patch.object(self.wizard, 'MARKER', root/'wifi-setup.json'), \
                 patch.object(self.wizard, 'Backend', return_value=fake_backend), \
                 patch.object(self.wizard, 'MONITOR', types.SimpleNamespace(waitForAbort=wait)), \
                 patch.object(self.wizard, 'xbmc', fake_xbmc), \
                 patch.object(self.wizard.time, 'monotonic', side_effect=lambda: clock[0]), \
                 patch.object(self.wizard.concurrent.futures, 'ThreadPoolExecutor', InlineExecutor), \
                 patch.object(self.wizard, 'WifiDialog', side_effect=lambda *a, **k: types.SimpleNamespace(run=lambda: shown.append(True))):
                self.wizard.main()
            marker = root/'wifi-setup.json'
            return shown, json.loads(marker.read_text()) if marker.exists() else None, clock[0]

    def test_actual_startup_skips_connected_network(self):
        shown, marker, _ = self.startup({'wifi': True, 'connected': 'ethernet'})
        self.assertFalse(shown)
        self.assertEqual(marker['reason'], 'already_connected')

    def test_actual_startup_waits_for_hardware_then_skips_missing_radio(self):
        shown, marker, elapsed = self.startup({'wifi': False})
        self.assertFalse(shown)
        self.assertEqual(marker['reason'], 'no_wifi')
        self.assertGreaterEqual(elapsed, 20)

    def test_actual_startup_opens_once_when_network_is_needed(self):
        shown, marker, elapsed = self.startup({'wifi': True})
        self.assertEqual(shown, [True])
        self.assertEqual(marker['reason'], 'started')
        self.assertEqual(elapsed, 8)

    def test_unavailable_daemon_consumes_first_start_without_claiming_success(self):
        shown, marker, _ = self.startup({'error': 'failed'})
        self.assertFalse(shown)
        self.assertEqual(marker['reason'], 'started')

    def test_restart_respects_completed_or_deferred_setup(self):
        shown, marker, elapsed = self.startup({'wifi': True}, existing=True)
        self.assertFalse(shown)
        self.assertEqual(elapsed, 0)
        self.assertEqual(marker['reason'], 'deferred')

    def test_subsequent_offline_boot_never_reopens_even_after_interruption(self):
        for reason in ('started', 'connected', 'deferred', 'no_wifi', 'already_connected'):
            with self.subTest(reason=reason):
                shown, marker, elapsed = self.startup({'wifi': True, 'connected': ''}, existing=reason)
                self.assertFalse(shown)
                self.assertEqual(elapsed, 0)
                self.assertEqual(marker['reason'], reason)

    def test_startup_never_forces_home_or_opens_over_another_window(self):
        shown, marker, _ = self.startup({'wifi': True}, home=False)
        self.assertFalse(shown)
        self.assertEqual(marker['reason'], 'started')

    def test_background_status_does_not_disable_list_or_reset_focus(self):
        dialog = object.__new__(self.wizard.WifiDialog)
        dialog.busy = True
        dialog.update('status', {'wifi': True})
        self.assertFalse(dialog.busy)

    def test_network_ready_refreshes_kodi_and_custom_weather_provider(self):
        actions = []
        fake = types.SimpleNamespace(executebuiltin=actions.append, getCondVisibility=lambda cond: True)
        with patch.object(self.wizard, 'xbmc', fake):
            self.wizard.refresh_weather()
        self.assertEqual(actions, ['Weather.Refresh', 'RunScript(/storage/.kodi/addons/weather.jioyzen/default.py)'])


if __name__ == '__main__':
    unittest.main()
