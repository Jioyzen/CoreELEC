"""Optional first-deployment display. No Kodi, network, Pillow or daemon needed."""
import base64
import ctypes
import fcntl
import gzip
import json
import math
import mmap
import os
from pathlib import Path
import signal
import threading
import time


# Stage weights describe work completed, never a timer pretending to be work.
STAGES = {
    'prepare': (0, 1, '准备部署'),
    'bundle': (1, 10, '校验安装包'),
    'unpack': (10, 55, '解压离线组件'),
    'verify': (55, 75, '校验组件文件'),
    'addons': (75, 90, '安装插件'),
    'runtimes': (90, 97, '安装服务程序'),
    'settings': (97, 99, '保存配置'),
    'complete': (100, 100, '部署完成，正在启动桌面'),
}


class Bitfield(ctypes.Structure):
    _fields_ = [(key, ctypes.c_uint32) for key in ('offset', 'length', 'msb_right')]


class VariableInfo(ctypes.Structure):
    _fields_ = [(key, ctypes.c_uint32) for key in (
        'xres', 'yres', 'xres_virtual', 'yres_virtual', 'xoffset', 'yoffset',
        'bits_per_pixel', 'grayscale')]
    _fields_ += [(key, Bitfield) for key in ('red', 'green', 'blue', 'transp')]
    _fields_ += [(key, ctypes.c_uint32) for key in (
        'nonstd', 'activate', 'height', 'width', 'accel_flags', 'pixclock',
        'left_margin', 'right_margin', 'upper_margin', 'lower_margin',
        'hsync_len', 'vsync_len', 'sync', 'vmode', 'rotate', 'colorspace')]
    _fields_ += [('reserved', ctypes.c_uint32 * 4)]


class FixedInfo(ctypes.Structure):
    _fields_ = [('id', ctypes.c_char * 16), ('smem_start', ctypes.c_ulong)]
    _fields_ += [(key, ctypes.c_uint32) for key in ('smem_len', 'type', 'type_aux', 'visual')]
    _fields_ += [(key, ctypes.c_uint16) for key in ('xpanstep', 'ypanstep', 'ywrapstep')]
    _fields_ += [('line_length', ctypes.c_uint32), ('mmio_start', ctypes.c_ulong)]
    _fields_ += [(key, ctypes.c_uint32) for key in ('mmio_len', 'accel')]
    _fields_ += [('capabilities', ctypes.c_uint16), ('reserved', ctypes.c_uint16 * 2)]


def screen_info(fd, request, kind):
    data = bytearray(ctypes.sizeof(kind))
    fcntl.ioctl(fd, request, data, True)
    return kind.from_buffer_copy(data)


def stop_splash(proc=Path('/proc'), timeout=1.0):
    """Finish the stock animation before becoming the sole framebuffer writer."""
    pending = []
    for entry in proc.iterdir():
        if not entry.name.isdecimal():
            continue
        try:
            if (entry/'comm').read_text().strip() != 'splash-image':
                continue
            os.kill(int(entry.name), signal.SIGUSR1)
            pending.append(entry)
        except (FileNotFoundError, ProcessLookupError):
            pass
    deadline = time.monotonic() + timeout
    while pending:
        alive = []
        for entry in pending:
            try:
                # A zombie can no longer draw, even before init reaps it.
                status = (entry/'stat').read_text().rsplit(')', 1)[1].split()[0]
                if status != 'Z':
                    alive.append(entry)
            except FileNotFoundError:
                pass
        pending = alive
        if pending and time.monotonic() >= deadline:
            raise OSError('Boot animation did not release the framebuffer')
        if pending:
            time.sleep(0.02)


class Canvas:
    WIDTH, HEIGHT = 920, 160

    def __init__(self, font):
        self.font = font
        self.pixels = bytearray(bytes((23, 21, 20, 255)) * self.WIDTH * self.HEIGHT)

    def rounded(self, x, y, width, height, radius, color):
        pixel = bytes((*reversed(color), 255))
        for row in range(height):
            distance = max(radius-row-0.5, row-(height-radius-0.5), 0)
            inset = math.ceil(radius-math.sqrt(max(0, radius*radius-distance*distance))) if distance else 0
            start = ((y+row)*self.WIDTH+x+inset)*4
            self.pixels[start:start+(width-2*inset)*4] = pixel*(width-2*inset)

    def text(self, text, x, y, size=22, color=(220, 225, 228), align='left'):
        glyphs = self.font[str(size)]
        width = sum(glyphs[char][0] for char in text)
        if align == 'center':
            x -= width//2
        elif align == 'right':
            x -= width
        for char in text:
            advance, left, top, w, h, mask = glyphs[char]
            for gy in range(h):
                py = y+top+gy
                if not 0 <= py < self.HEIGHT:
                    continue
                for gx in range(w):
                    px = x+left+gx
                    alpha = mask[gy*w+gx]
                    if alpha and 0 <= px < self.WIDTH:
                        offset = (py*self.WIDTH+px)*4
                        for channel, value in enumerate(reversed(color)):
                            old = self.pixels[offset+channel]
                            self.pixels[offset+channel] = (old*(255-alpha)+value*alpha)//255
                        self.pixels[offset+3] = 255
            x += advance

    def render(self, stage, percent, elapsed, first_boot=True, failed=False):
        self.rounded(0, 0, self.WIDTH, self.HEIGHT, 20, (23, 26, 28))
        title = '首次启动 · 正在部署离线组件' if first_boot else '正在部署离线组件'
        self.text(title, self.WIDTH//2, 5, size=28, align='center', color=(245, 245, 245))
        label = '部署失败，可重启重试' if failed else STAGES[stage][2]
        self.text(label, 28, 48, color=(247, 122, 113) if failed else (220, 225, 228))
        self.text(f'{percent}%', self.WIDTH-28, 48, align='right')
        self.rounded(28, 94, self.WIDTH-56, 10, 5, (65, 69, 71))
        filled = round((self.WIDTH-56)*percent/100)
        if filled >= 10:
            self.rounded(28, 94, filled, 10, 5, (206, 62, 53))
        footer = '请查看系统日志' if failed else '请勿断电'
        minutes, seconds = divmod(int(elapsed), 60)
        self.text(f'已用时 {minutes:02}:{seconds:02} · {footer}', self.WIDTH//2, 120,
                  align='center', color=(159, 168, 172))
        return self.pixels


class Framebuffer:
    def __init__(self, path='/dev/fb0'):
        self.fd = os.open(path, os.O_RDWR | os.O_CLOEXEC)
        self.mapping = None
        try:
            self.variable = v = screen_info(self.fd, 0x4600, VariableInfo)
            fixed = screen_info(self.fd, 0x4602, FixedInfo)
            # Match the BGRA32 mode already established by splash-image.
            # Never change HDMI mode, pixel format, panning or blanking here.
            if (v.bits_per_pixel != 32 or v.grayscale or v.nonstd or
                    [(v.red.offset, v.red.length, v.red.msb_right),
                     (v.green.offset, v.green.length, v.green.msb_right),
                     (v.blue.offset, v.blue.length, v.blue.msb_right)] !=
                    [(16, 8, 0), (8, 8, 0), (0, 8, 0)] or
                    v.transp.length not in (0, 8) or
                    (v.transp.length == 8 and (v.transp.offset != 24 or v.transp.msb_right))):
                raise OSError('Unsupported boot framebuffer format')
            self.stride = fixed.line_length
            length = self.stride*(v.yoffset+v.yres)
            if (not 320 <= v.xres <= 7680 or not 240 <= v.yres <= 4320 or
                    v.xoffset+v.xres > v.xres_virtual or v.yoffset+v.yres > v.yres_virtual or
                    self.stride < (v.xoffset+v.xres)*4 or length > fixed.smem_len or
                    length > 128*1024**2):
                raise OSError('Invalid boot framebuffer geometry')
            scale = min(v.xres/1920, v.yres/1080)
            self.width, self.height = round(Canvas.WIDTH*scale), round(Canvas.HEIGHT*scale)
            self.x = (v.xres-self.width)//2
            self.y = v.yres-self.height-max(8, round(24*scale))
            self.mapping = mmap.mmap(self.fd, length, flags=mmap.MAP_SHARED,
                                     prot=mmap.PROT_READ | mmap.PROT_WRITE)
        except Exception:
            self.close()
            raise

    def present(self, pixels):
        current = screen_info(self.fd, 0x4600, VariableInfo)
        if bytes(current) != bytes(self.variable):
            raise OSError('Display mode changed during offline deployment')
        v = self.variable
        for y in range(self.height):
            sy = y*Canvas.HEIGHT//self.height
            row = pixels[sy*Canvas.WIDTH*4:(sy+1)*Canvas.WIDTH*4]
            if self.width != Canvas.WIDTH:
                row = b''.join(row[(x*Canvas.WIDTH//self.width)*4:(x*Canvas.WIDTH//self.width)*4+4]
                               for x in range(self.width))
            start = (self.y+y+v.yoffset)*self.stride+(self.x+v.xoffset)*4
            self.mapping[start:start+len(row)] = row

    def close(self):
        mapping, self.mapping = self.mapping, None
        fd, self.fd = self.fd, None
        try:
            if mapping is not None:
                mapping.close()
        finally:
            if fd is not None:
                os.close(fd)


def log(message):
    try:
        print(message, flush=True)
    except OSError:
        pass


class Progress:
    """Display failures must never prevent installation or block Kodi startup."""
    def __init__(self, enabled=False, first_boot=True):
        self.enabled, self.first_boot = enabled, first_boot
        self.stage, self.done, self.total, self.percent = 'prepare', 0, 1, 0
        self.lock, self.stop = threading.Lock(), threading.Event()
        self.started = time.monotonic()
        self.thread = self.display = None

    def __enter__(self):
        if self.enabled:
            try:
                data = json.loads(gzip.decompress((Path(__file__).parent/'boot/font.json.gz').read_bytes()))
                self.font = data['sizes']
                for glyphs in self.font.values():
                    for glyph in glyphs.values():
                        glyph[5] = base64.b64decode(glyph[5])
                self.display = Framebuffer()
                stop_splash()
                self.draw()
                self.thread = threading.Thread(target=self.heartbeat, daemon=True)
                self.thread.start()
            except Exception as error:
                self.disable(error)
        return self

    def set_stage(self, name, total=1):
        with self.lock:
            self.stage, self.total, self.done = name, max(1, total), 0
            self.percent = max(self.percent, STAGES[name][0])
        if self.enabled:
            log('Offline deployment: '+name)

    def set_total(self, total):
        with self.lock:
            self.total = max(1, total)

    def advance(self, size):
        with self.lock:
            self.done += size
            low, high, _ = STAGES[self.stage]
            self.percent = max(self.percent, min(high, low+int((high-low)*self.done/self.total)))

    def draw(self, failed=False):
        if self.display is None:
            return
        with self.lock:
            stage, percent = self.stage, self.percent
        pixels = Canvas(self.font).render(stage, percent, time.monotonic()-self.started,
                                          self.first_boot, failed)
        self.display.present(pixels)

    def disable(self, error):
        log('Offline deployment display unavailable: '+type(error).__name__)
        display, self.display = self.display, None
        if display is not None:
            try:
                display.close()
            except Exception:
                pass

    def heartbeat(self):
        while not self.stop.wait(1):
            try:
                self.draw()
            except Exception as error:
                self.disable(error)
                return

    def __exit__(self, error_type, error, traceback):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=2)
        if error_type is None:
            self.set_stage('complete')
        try:
            self.draw(failed=error_type is not None)
        except Exception as display_error:
            self.disable(display_error)
        finally:
            if self.display is not None:
                try:
                    self.display.close()
                except Exception as display_error:
                    self.disable(display_error)
