"""ConnMan contract test using a private D-Bus and a fake router, never host Wi-Fi.

Run with dbussy/ravel available on PYTHONPATH; otherwise only these tests skip.
Exercises the actual serialized D-Bus signatures and the password agent callback.
"""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SERVICE_PATH = '/net/connman/service/wifi_012345_test_managed_psk'


async def fake_server():
    import dbussy
    import ravel
    sig = dbussy.DBUS.Signature
    bus = ravel.system_bus()
    bus.attach_asyncio(asyncio.get_running_loop())
    bus.request_name('net.connman', flags=dbussy.DBUS.NAME_FLAG_DO_NOT_QUEUE)
    state = {'status': 'idle', 'powered': False, 'agent': '', 'sender': '', 'auto': False}

    def properties():
        return {'Type': (sig('s'), 'wifi'), 'Name': (sig('s'), '测试网络'),
                'Security': (sig('as'), ['ieee8021x'] if os.environ.get('TEST_ENTERPRISE') else ['psk']),
                'Strength': (sig('y'), 88), 'State': (sig('s'), state['status']),
                'AutoConnect': (sig('b'), state['auto'])}

    @ravel.interface(ravel.INTERFACE.SERVER, name='net.connman.Manager')
    class Manager:
        @ravel.method(in_signature='', out_signature='a(oa{sv})', result_keyword='reply')
        def GetTechnologies(self, reply):
            reply[0] = [('/net/connman/technology/wifi', {'Type': (sig('s'), 'wifi'), 'Powered': (sig('b'), state['powered'])})]

        @ravel.method(in_signature='', out_signature='a(oa{sv})', result_keyword='reply')
        def GetServices(self, reply):
            reply[0] = [(SERVICE_PATH, properties())]

        @ravel.method(in_signature='o', out_signature='', arg_keys=['path'], message_keyword='message')
        def RegisterAgent(self, path, message):
            state.update(agent=path, sender=message.sender)

        @ravel.method(in_signature='o', out_signature='', arg_keys=['path'])
        def UnregisterAgent(self, path):
            state['agent'] = ''

    @ravel.interface(ravel.INTERFACE.SERVER, name='net.connman.Technology')
    class Technology:
        @ravel.method(in_signature='sv', out_signature='', arg_keys=['name', 'value'])
        def SetProperty(self, name, value):
            state['powered'] = bool(value[1])

        @ravel.method(in_signature='', out_signature='')
        def Scan(self):
            if not state['powered']:
                raise ravel.ErrorReturn('net.connman.Error.NotPowered', 'Not powered')

    @ravel.interface(ravel.INTERFACE.SERVER, name='net.connman.Service')
    class Service:
        @ravel.method(in_signature='', out_signature='')
        async def Connect(self):
            message = dbussy.Message.new_method_call(destination=state['sender'], path=state['agent'],
                                                     iface='net.connman.Agent', method='RequestInput')
            message.append_objects('oa{sv}', SERVICE_PATH,
                                   {'Passphrase': (sig('a{sv}'), {'Type': (sig('s'), 'psk'), 'Requirement': (sig('s'), 'mandatory')})})
            response = await bus.connection.send_await_reply(message, 5000)
            password = response.expect_return_objects('a{sv}')[0]['Passphrase'][1]
            if password == 'stall':
                state['status'] = 'association'
                await asyncio.sleep(60)
            if password != 'valid-password':
                raise ravel.ErrorReturn('net.connman.Error.InvalidKey', 'Wrong password')
            state['status'] = 'configuration'
            async def dhcp():
                await asyncio.sleep(.1)
                state['status'] = 'ready'
            asyncio.create_task(dhcp())

        @ravel.method(in_signature='', out_signature='')
        def Disconnect(self):
            state['status'] = 'idle'

        @ravel.method(in_signature='', out_signature='a{sv}', result_keyword='reply')
        def GetProperties(self, reply):
            reply[0] = properties()

        @ravel.method(in_signature='sv', out_signature='', arg_keys=['name', 'value'])
        def SetProperty(self, name, value):
            state['auto'] = bool(value[1])

    bus.register(path='/', interface=Manager(), fallback=False)
    bus.register(path='/net/connman/technology/wifi', interface=Technology(), fallback=False)
    bus.register(path=SERVICE_PATH, interface=Service(), fallback=False)
    print('READY', flush=True)
    await asyncio.Event().wait()


@unittest.skipUnless(importlib.util.find_spec('dbussy') and shutil.which('dbus-daemon'), 'requires dbussy and dbus-daemon')
class DbusTests(unittest.TestCase):
    def setUp(self):
        self.daemon = subprocess.Popen(['dbus-daemon', '--session', '--nofork', '--print-address=1'],
                                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        self.env = dict(os.environ, DBUS_SYSTEM_BUS_ADDRESS=self.daemon.stdout.readline().strip())
        self.server = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--fake-server'],
                                       env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(self.server.stdout.readline().strip(), 'READY')

    def tearDown(self):
        for process in (self.server, self.daemon):
            process.terminate()
            process.communicate(timeout=5)

    def request(self, **request):
        response = subprocess.run([sys.executable, str(ROOT/'wifi/network.py')], input=json.dumps(request),
                                  capture_output=True, text=True, env=self.env, timeout=58)
        self.assertEqual(response.returncode, 0, response.stderr)
        return json.loads(response.stdout)

    def test_scan_powers_radio_and_preserves_unicode(self):
        result = self.request(action='scan')
        self.assertTrue(result['powered'])
        self.assertEqual(result['networks'][0]['name'], '测试网络')

    def test_password_agent_and_dhcp_and_autoconnect(self):
        self.assertEqual(self.request(action='connect', path=SERVICE_PATH, password='valid-password'), {'connected': True})
        self.assertEqual(self.request(action='status')['connected'], 'wifi')

    def test_wrong_password_can_be_retried(self):
        self.assertEqual(self.request(action='connect', path=SERVICE_PATH, password='wrong-password'), {'error': 'password'})
        self.assertEqual(self.request(action='connect', path=SERVICE_PATH, password='valid-password'), {'connected': True})

    def test_cancel_cleans_up_connection_and_unregisters_agent(self):
        process = subprocess.Popen([sys.executable, str(ROOT/'wifi/network.py')], env=self.env,
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        process.stdin.write(json.dumps({'action': 'connect', 'path': SERVICE_PATH, 'password': 'stall'})+'\n')
        process.stdin.flush()
        import time
        deadline = time.monotonic()+5
        while time.monotonic()<deadline:
            # Agent registration and association happen asynchronously.
            time.sleep(.2)
            if self.request(action='status')['networks']:
                break
        time.sleep(.5)
        process.terminate()
        process.stdin.close()
        process.stdin = None
        out, err = process.communicate(timeout=8)
        self.assertEqual(json.loads(out), {'error': 'cancelled'}, err)
        self.assertEqual(self.request(action='connect', path=SERVICE_PATH, password='valid-password'), {'connected': True})


if __name__ == '__main__':
    if '--fake-server' in sys.argv:
        asyncio.run(fake_server())
    else:
        unittest.main()
