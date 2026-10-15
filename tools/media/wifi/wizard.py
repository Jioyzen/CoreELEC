"""First-desktop Wi-Fi dialog, independent of the CoreELEC setup wizard."""
import concurrent.futures
import fcntl
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time

import xbmc
import xbmcgui

ROOT = Path(__file__).resolve().parent
CACHE = Path('/storage/.cache/jioyzen-media')
MARKER = CACHE / 'wifi-setup.json'
MONITOR = xbmc.Monitor()


def remember(reason):
    CACHE.mkdir(parents=True, exist_ok=True)
    temporary = MARKER.with_suffix('.partial')
    temporary.write_text(json.dumps({'schema': 1, 'reason': reason, 'time': int(time.time())}), encoding='utf-8')
    os.replace(temporary, MARKER)


def needs_setup(state):
    return bool(state.get('wifi') and not state.get('connected') and not state.get('tethering'))


class Backend:
    def __init__(self):
        self.lock = threading.Lock()
        self.process = None
        self.stopped = False

    def call(self, action, **kwargs):
        with self.lock:
            if self.stopped:
                return {'error': 'cancelled'}
            process = subprocess.Popen(['/usr/bin/python3', str(ROOT / 'network.py')],
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=subprocess.DEVNULL)
            self.process = process
        try:
            output, _ = process.communicate(json.dumps({'action': action, **kwargs}).encode('utf-8'), timeout=56)
            return json.loads(output.decode('utf-8'))
        except (OSError, ValueError, subprocess.TimeoutExpired):
            process.kill()
            process.communicate()
            return {'error': 'timeout'}
        finally:
            with self.lock:
                self.process = None

    def stop(self):
        with self.lock:
            self.stopped = True
            if self.process and self.process.poll() is None:
                self.process.terminate()


ERRORS = {
    'password': '密码不正确，请重新输入。',
    'timeout': '连接超时，请检查信号或路由器后重试。',
    'enterprise': '此网络需要企业认证，请在 CoreELEC 网络设置中连接。',
    'unavailable': '此网络已不在附近，请重新扫描。',
    'busy': '系统正在连接网络，请稍候再试。',
    'failed': '未能连接，请检查密码、信号和路由器后重试。',
}


def display_name(name):
    return name.replace('[', '［').replace(']', '］')


class WifiDialog(xbmcgui.WindowXMLDialog):
    def __init__(self, *args, backend=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.backend = backend
        self.events = queue.Queue()
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix='wifi-setup')
        self.closed = False
        self.initialized = False
        self.busy = False
        self.networks = []
        self.connecting = ''
        self.next_status = 0
        self.success_until = 0

    def onInit(self):
        if self.initialized:
            return
        self.initialized = True
        self.setFocusId(20)
        self.submit('scan')

    def status(self, text):
        self.getControl(4).setLabel(text)

    def submit(self, action, **kwargs):
        if self.busy or self.closed:
            return
        self.busy = True
        if action == 'scan':
            self.status('正在查找附近的 Wi-Fi…')
        elif action == 'connect':
            self.connecting = kwargs['path']
            self.status('正在连接，请稍候…')
        if action != 'status':
            self.getControl(20).setEnabled(False)
            self.getControl(10).setEnabled(False)
        def work():
            try:
                result = self.backend.call(action, **kwargs)
            except Exception:
                result = {'error': 'failed'}
            self.events.put((action, result))
        self.executor.submit(work)

    def onClick(self, control):
        if control == 21:
            self.finish('deferred')
        elif control == 20:
            self.submit('scan')
        elif control == 10 and not self.busy:
            index = self.getControl(10).getSelectedPosition()
            if not 0 <= index < len(self.networks):
                return
            network = self.networks[index]
            if network['connected']:
                self.connected()
                return
            if 'ieee8021x' in network['security']:
                self.status(ERRORS['enterprise'])
                return
            password = ''
            if any(s != 'none' for s in network['security']):
                keyboard = xbmc.Keyboard('', '输入 Wi-Fi 密码', True)
                keyboard.doModal()
                if not keyboard.isConfirmed():
                    return
                password = keyboard.getText()
                # Saved networks may reconnect using ConnMan's stored secret.
                if not password and not network['saved']:
                    self.status('请输入网络密码。')
                    return
            self.submit('connect', path=network['path'], password=password)

    def onAction(self, action):
        if action.getId() in {9, 10, 92, 216}:
            self.finish('deferred')

    def finish(self, reason):
        if self.closed:
            return
        if reason:
            remember(reason)
        self.closed = True
        self.close()

    def connected(self):
        self.status('已连接，可以开始使用了。')
        remember('connected')
        xbmc.executebuiltin('Weather.Refresh')
        if xbmc.getCondVisibility('System.AddonIsEnabled(weather.jioyzen)'):
            xbmc.executebuiltin('RunScript(/storage/.kodi/addons/weather.jioyzen/default.py)')
        self.success_until = time.monotonic() + 1.5

    def update(self, action, result):
        self.busy = False
        if action != 'status':
            self.getControl(20).setEnabled(True)
            self.getControl(10).setEnabled(True)
        self.next_status = time.monotonic() + 5
        if result.get('connected'):
            self.connected()
            return
        if result.get('error'):
            self.status(ERRORS.get(result['error'], ERRORS['failed']))
            if action == 'connect':
                self.setFocusId(10)
            return
        if not result.get('wifi'):
            self.finish('no_wifi')
            return
        if action == 'status':
            return
        previous = self.getControl(10).getSelectedPosition()
        self.networks = result.get('networks', [])
        items = []
        for network in self.networks:
            item = xbmcgui.ListItem(display_name(network['name']))
            encrypted = any(s != 'none' for s in network['security'])
            item.setLabel2(('已保存 · ' if network['saved'] else '') + ('需要密码' if encrypted else '开放网络'))
            item.setProperty('signal', str(ROOT / 'resources/skins/Default/media' / ('signal%d.png' % min(3, network['strength'] // 26))))
            items.append(item)
        listing = self.getControl(10)
        listing.reset()
        listing.addItems(items)
        if items:
            listing.selectItem(max(0, min(previous, len(items) - 1)))
            self.setFocusId(10)
            self.status('选择 Wi-Fi，按确定键连接。')
        else:
            self.setFocusId(20)
            self.status('未发现可用网络，请靠近路由器后重新扫描。')

    def run(self):
        try:
            self.show()
            while not self.closed and not MONITOR.abortRequested():
                try:
                    action, result = self.events.get_nowait()
                    if not self.closed:
                        self.update(action, result)
                except queue.Empty:
                    pass
                now = time.monotonic()
                if self.success_until:
                    if now >= self.success_until:
                        self.finish(None)
                elif self.initialized and not self.busy and now >= self.next_status:
                    self.submit('status')
                MONITOR.waitForAbort(.1)
        finally:
            self.closed = True
            self.backend.stop()
            self.executor.shutdown(wait=True, cancel_futures=True)
            self.close()


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    with (CACHE / 'wifi-setup.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        (CACHE / 'wifi-started').touch()
        preview = '--preview' in sys.argv
        if MARKER.exists() and not preview:
            return
        backend = Backend()
        try:
            # EventServer can be ready before the skin. Never interrupt a movie
            # or an existing dialog, nor force users back from another window.
            deadline = time.monotonic() + 90
            while not (xbmc.getCondVisibility('Window.IsActive(home)') and
                       not xbmc.getCondVisibility('System.HasActiveModalDialog')):
                if MONITOR.waitForAbort(.5) or time.monotonic() >= deadline:
                    return
            deadline = time.monotonic() + 20
            settle = time.monotonic() + 8
            while True:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(backend.call, 'status')
                    while not future.done():
                        if MONITOR.waitForAbort(.1):
                            backend.stop()
                            return
                    state = future.result()
                if state.get('error'):
                    # A late ConnMan startup is transient. Do not persist an
                    # unavailable daemon as "no wireless hardware".
                    if time.monotonic() >= deadline or MONITOR.waitForAbort(2):
                        return
                    continue
                if preview:
                    break
                if state.get('connected'):
                    remember('already_connected')
                    return
                now = time.monotonic()
                if now >= deadline or (state.get('wifi') and now >= settle):
                    if not needs_setup(state):
                        remember('no_wifi' if not state.get('wifi') else 'hotspot')
                        return
                    break
                if MONITOR.waitForAbort(2):
                    return
            # Recheck Home after the hardware grace period; do not steal focus
            # from an application launched while automatic networking settled.
            if not xbmc.getCondVisibility('Window.IsActive(home)') or xbmc.getCondVisibility('System.HasActiveModalDialog'):
                return
            window = WifiDialog('wifi.xml', str(ROOT), 'Default', '1080i', backend=backend)
            window.run()
            del window
        except Exception as error:
            xbmc.log('[Jioyzen Wi-Fi] Setup unavailable: ' + type(error).__name__, xbmc.LOGERROR)
        finally:
            backend.stop()


if __name__ == '__main__':
    main()
