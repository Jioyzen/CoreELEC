"""Small ConnMan client. Runs outside Kodi; passwords only cross stdin/D-Bus.

No profiles are written here: ConnMan owns credentials and DHCP configuration.
Only an explicit user connection uses an agent; status/scan never register one.
"""
import asyncio
import json
import re
import signal
import sys

READY = {'ready', 'online'}
MANAGER = 'net.connman.Manager'
SERVICE = 'net.connman.Service'
TECH = 'net.connman.Technology'
AGENT_PATH = '/org/jioyzen/wifi_agent'


def unpack(value):
    if isinstance(value, dict):
        return {k: unpack(v) for k, v in value.items()}
    if isinstance(value, tuple) and len(value) == 2 and isinstance(value[0], str):
        # DBussy Signature is a str subclass; ordinary object/property pairs
        # remain lists (their first item starts with '/').
        if not value[0].startswith('/'):
            return unpack(value[1])
    if isinstance(value, (list, tuple)):
        return [unpack(v) for v in value]
    return value


def summarize(technologies, services):
    wifi = next(((p, v) for p, v in technologies if v.get('Type') == 'wifi'), None)
    connected = next((v.get('Type') for _, v in services
                      if v.get('Type') in {'ethernet', 'wifi'} and v.get('State') in READY), '')
    connecting = any(v.get('Type') in {'ethernet', 'wifi'} and
                     v.get('State') in {'association', 'configuration'} for _, v in services)
    networks = []
    for path, props in services:
        if props.get('Type') != 'wifi' or not props.get('Name'):
            continue  # A hidden SSID cannot be connected without its name.
        security = props.get('Security', [])
        networks.append({'path': path, 'name': props['Name'],
                         'strength': max(0, min(100, int(props.get('Strength', 0)))),
                         'security': security, 'saved': bool(props.get('Favorite')),
                         'connected': props.get('State') in READY})
    networks.sort(key=lambda v: (not v['connected'], -v['strength'], v['name']))
    return {'wifi': bool(wifi), 'wifi_path': wifi[0] if wifi else '',
            'powered': bool(wifi and wifi[1].get('Powered')),
            'tethering': bool(wifi and wifi[1].get('Tethering')),
            'connected': connected, 'connecting': connecting, 'networks': networks}


def error_code(error):
    # Never return raw D-Bus exception text: it can contain network identity.
    text = str(error).lower()
    if any(s in text for s in ('invalid-key', 'invalidkey', 'auth-failed', 'authfailed', 'invalid passphrase')):
        return 'password'
    if 'alreadyconnected' in text:
        return 'already_connected'
    if 'inprogress' in text or 'in progress' in text:
        return 'busy'
    if isinstance(error, (asyncio.TimeoutError, TimeoutError)):
        return 'timeout'
    return 'failed'


class ConnMan:
    def __init__(self):
        import dbussy
        import ravel
        self.dbus = dbussy
        self.ravel = ravel
        self.bus = ravel.system_bus()
        self.bus.attach_asyncio(asyncio.get_running_loop())

    async def call(self, path, interface, method, signature='', args=(), result=''):
        message = self.dbus.Message.new_method_call(
            destination='net.connman', path=path, iface=interface, method=method)
        if signature:
            message.append_objects(signature, *args)
        reply = await self.bus.connection.send_await_reply(message, 35000)
        values = reply.expect_return_objects(result)
        return unpack(values[0]) if values else None

    async def status(self):
        techs = await self.call('/', MANAGER, 'GetTechnologies', result='a(oa{sv})')
        services = await self.call('/', MANAGER, 'GetServices', result='a(oa{sv})')
        return summarize(techs, services)

    async def scan(self):
        state = await self.status()
        if state['wifi'] and not state['tethering']:
            if not state['powered']:
                await self.call(state['wifi_path'], TECH, 'SetProperty', 'sv',
                                ('Powered', (self.dbus.DBUS.Signature('b'), True)))
            try:
                await self.call(state['wifi_path'], TECH, 'Scan')
            except Exception as error:
                if error_code(error) != 'busy':
                    raise
        return await self.status()

    async def connect(self, path, password):
        if not re.fullmatch(r'/net/connman/service/wifi_[A-Za-z0-9_]+', path):
            return {'error': 'unavailable'}
        state = await self.status()
        network = next((n for n in state['networks'] if n['path'] == path), None)
        if not network:
            return {'error': 'unavailable'}
        if network['connected']:
            return {'connected': True}
        if 'ieee8021x' in network['security']:
            return {'error': 'enterprise'}
        ravel, dbus = self.ravel, self.dbus
        agent_error = []

        @ravel.interface(ravel.INTERFACE.SERVER, name='net.connman.Agent')
        class Agent:
            @ravel.method(in_signature='', out_signature='')
            def Release(self):
                pass

            @ravel.method(in_signature='', out_signature='')
            def Cancel(self):
                agent_error.append('cancelled')

            @ravel.method(in_signature='os', out_signature='', arg_keys=['service', 'error'])
            def ReportError(self, service, error):
                agent_error.append('password' if error in {'invalid-key', 'auth-failed'} else 'failed')

            @ravel.method(in_signature='os', out_signature='', arg_keys=['service', 'url'])
            def RequestBrowser(self, service, url):
                raise ravel.ErrorReturn('net.connman.Agent.Error.Canceled', 'Unsupported')

            @ravel.method(in_signature='oa{sv}', out_signature='a{sv}',
                          args_keyword='request', result_keyword='reply')
            def RequestInput(self, request, reply):
                service, fields = unpack(request)
                if service != path or any(k not in {'Passphrase', 'WPS'} for k in fields):
                    raise ravel.ErrorReturn('net.connman.Agent.Error.Canceled', 'Unsupported')
                reply[0] = {'Passphrase': (dbus.DBUS.Signature('s'), password)}

        self.bus.register(path=AGENT_PATH, interface=Agent(), fallback=False)
        registered = False
        started = False
        connected = False
        try:
            await self.call('/', MANAGER, 'RegisterAgent', 'o', (AGENT_PATH,))
            registered = True
            try:
                started = True
                await self.call(path, SERVICE, 'Connect')
            except Exception as error:
                code = agent_error[-1] if agent_error else error_code(error)
                if code not in {'already_connected', 'busy'}:
                    return {'error': code}
            # Connect can complete before DHCP. A link-only association is not
            # success; wait for ready/online without requiring external Internet.
            for _ in range(12):
                props = await self.call(path, SERVICE, 'GetProperties', result='a{sv}')
                if props.get('State') in READY:
                    connected = True
                    await self.call(path, SERVICE, 'SetProperty', 'sv',
                                    ('AutoConnect', (dbus.DBUS.Signature('b'), True)))
                    return {'connected': True}
                if agent_error or props.get('State') == 'failure':
                    return {'error': agent_error[-1] if agent_error else 'failed'}
                await asyncio.sleep(1)
            return {'error': 'timeout'}
        finally:
            if started and not connected:
                try:
                    await asyncio.wait_for(self.call(path, SERVICE, 'Disconnect'), 2)
                except Exception:
                    pass
            if registered:
                try:
                    await asyncio.wait_for(self.call('/', MANAGER, 'UnregisterAgent', 'o', (AGENT_PATH,)), 2)
                except Exception:
                    pass
            self.bus.unregister(path=AGENT_PATH)


async def execute(request):
    task = asyncio.current_task()
    asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, task.cancel)
    client = ConnMan()
    action = request.get('action')
    if action == 'status':
        return await client.status()
    if action == 'scan':
        return await client.scan()
    if action == 'connect':
        return await client.connect(request.get('path', ''), request.get('password', ''))
    return {'error': 'unsupported'}


def main():
    try:
        request = json.loads(sys.stdin.buffer.readline(16384).decode('utf-8'))
        response = asyncio.run(asyncio.wait_for(execute(request), timeout=52))
    except asyncio.CancelledError:
        response = {'error': 'cancelled'}
    except Exception as error:
        response = {'error': error_code(error)}
    # Escaped output works with CoreELEC's ASCII process locale.
    print(json.dumps(response, ensure_ascii=True))


if __name__ == '__main__':
    main()
