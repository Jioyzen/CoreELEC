import ctypes
import gzip
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import boot_progress as bp
import deploy
from test_deploy import bundle


class FakeDisplay:
    def __init__(self):
        self.frames = []
        self.closed = False

    def present(self, pixels):
        self.frames.append(bytes(pixels))

    def close(self):
        self.closed = True


class Tracker(bp.Progress):
    def __init__(self, **kwargs):
        super().__init__(enabled=False)
        self.events = []
        self.samples = []
        self.error = None

    def set_stage(self, name, total=1):
        super().set_stage(name, total)
        self.events.append(name)
        self.samples.append(self.percent)

    def advance(self, count):
        super().advance(count)
        self.samples.append(self.percent)

    def __exit__(self, kind, error, traceback):
        self.error = error
        super().__exit__(kind, error, traceback)


class ProgressTests(unittest.TestCase):
    def test_font_has_all_labels_and_runtime_is_standard_library_only(self):
        data = json.loads(gzip.decompress((ROOT/'boot/font.json.gz').read_bytes()))
        labels = ''.join(value[2] for value in bp.STAGES.values())
        labels += '首次启动 · 正在部署离线组件部署失败，可重启重试请查看系统日志已用时 0123456789:%请勿断电'
        for glyphs in data['sizes'].values():
            self.assertTrue(set(labels) <= glyphs.keys())
            for _, _, _, width, height, encoded in glyphs.values():
                self.assertEqual(len(bp.base64.b64decode(encoded)), width*height)
        subprocess.run([sys.executable, '-S', '-c',
                        'import sys;sys.path.insert(0,sys.argv[1]);import boot_progress', str(ROOT)], check=True)

    def test_progress_uses_bytes_not_time_and_never_goes_backwards(self):
        p = bp.Progress()
        p.set_stage('unpack', 1000)
        p.advance(500)
        percent = p.percent
        self.assertEqual(percent, 32)
        p.started -= 300
        self.assertEqual(p.percent, percent)
        p.advance(100000)
        self.assertEqual(p.percent, 55)
        p.set_stage('verify', 1000)
        self.assertEqual(p.percent, 55)
        p.advance(1000)
        self.assertEqual(p.percent, 75)

    def test_elapsed_changes_without_inventing_progress_and_thread_exits(self):
        display = FakeDisplay()
        with patch.object(bp, 'Framebuffer', return_value=display), patch.object(bp, 'stop_splash') as stop:
            with bp.Progress(enabled=True) as p:
                p.set_stage('addons', 1000)
                p.advance(500)
                p.draw()
                first = display.frames[-1]
                percent = p.percent
                p.started -= 7
                p.draw()
                self.assertNotEqual(display.frames[-1], first)
                self.assertEqual(p.percent, percent)
            stop.assert_called_once()
        self.assertEqual(p.percent, 100)
        self.assertFalse(p.thread.is_alive())
        self.assertTrue(display.closed)

    def test_unavailable_or_broken_display_never_blocks_deployment(self):
        with patch.object(bp, 'Framebuffer', side_effect=FileNotFoundError):
            with bp.Progress(enabled=True) as p:
                p.set_stage('settings')
        self.assertEqual(p.percent, 100)
        display = FakeDisplay()
        display.present = lambda pixels: (_ for _ in ()).throw(OSError('display gone'))
        display.close = lambda: (_ for _ in ()).throw(OSError('close failed'))
        with patch.object(bp, 'Framebuffer', return_value=display), patch.object(bp, 'stop_splash'):
            with self.assertRaisesRegex(ValueError, 'payload invalid'):
                with bp.Progress(enabled=True):
                    raise ValueError('payload invalid')

    def test_framebuffer_writes_only_panel_and_honors_stride_and_panning(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'fb'
            v = bp.VariableInfo()
            v.xres, v.yres, v.xres_virtual, v.yres_virtual = 640, 480, 656, 960
            v.xoffset, v.yoffset, v.bits_per_pixel = 7, 480, 32
            v.red, v.green, v.blue, v.transp = (bp.Bitfield(n, 8, 0) for n in (16, 8, 0, 24))
            f = bp.FixedInfo()
            f.line_length = v.xres_virtual*4+16
            f.smem_len = f.line_length*v.yres_virtual
            original = b'\x5a'*f.smem_len
            path.write_bytes(original)
            def info(fd, request, kind):
                return v if request == 0x4600 else f
            with patch.object(bp, 'screen_info', side_effect=info):
                fb = bp.Framebuffer(path)
                width, height, x, y = fb.width, fb.height, fb.x, fb.y
                fb.present(bytes((1, 2, 3, 255))*bp.Canvas.WIDTH*bp.Canvas.HEIGHT)
                fb.close()
                fb.close()  # Cleanup must be safe after a drawing failure too.
            actual = path.read_bytes()
            for row in range(v.yres_virtual):
                start, end = row*f.line_length, (row+1)*f.line_length
                if y+v.yoffset <= row < y+v.yoffset+height:
                    left = start+(x+v.xoffset)*4
                    right = left+width*4
                    self.assertEqual(actual[start:left], original[start:left])
                    self.assertEqual(actual[right:end], original[right:end])
                    self.assertEqual(actual[left:right], bytes((1, 2, 3, 255))*width)
                else:
                    self.assertEqual(actual[start:end], original[start:end])

    def test_invalid_framebuffer_fails_before_mapping_or_writing(self):
        v, f = bp.VariableInfo(), bp.FixedInfo()
        with tempfile.NamedTemporaryFile() as file:
            with patch.object(bp, 'screen_info', side_effect=[v, f]), patch.object(bp.mmap, 'mmap') as mapping:
                with self.assertRaises(OSError):
                    bp.Framebuffer(file.name)
                mapping.assert_not_called()

    def test_animation_is_released_before_first_frame_is_written(self):
        events = []
        display = FakeDisplay()
        display.present = lambda frame: events.append('draw')
        with patch.object(bp, 'Framebuffer', return_value=display), patch.object(bp, 'stop_splash', side_effect=lambda: events.append('stop')):
            with bp.Progress(enabled=True):
                pass
        self.assertEqual(events[0:2], ['stop', 'draw'])

    def test_linux_framebuffer_abi(self):
        # Linux fb_var_screeninfo is architecture independent. The fixed ABI
        # uses native unsigned longs; runtime and aarch64 share the LP64 layout.
        self.assertEqual(ctypes.sizeof(bp.VariableInfo), 160)
        if ctypes.sizeof(ctypes.c_ulong) == 8:
            self.assertEqual(ctypes.sizeof(bp.FixedInfo), 80)
            self.assertEqual(bp.FixedInfo.line_length.offset, 48)


class DeploymentProgressTests(unittest.TestCase):
    def test_real_installer_progress_and_fast_path_on_next_boot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root/'bundle'
            source.mkdir()
            bundle(source)
            tracker = Tracker()
            with patch.object(deploy, 'Progress', return_value=tracker):
                result = deploy.deploy(source, root/'storage', show_progress=True)
            self.assertEqual(result['status'], 'complete')
            self.assertEqual(tracker.events, ['bundle', 'unpack', 'verify', 'addons', 'runtimes', 'settings', 'complete'])
            self.assertEqual(tracker.samples, sorted(tracker.samples))
            self.assertEqual(tracker.percent, 100)
            with patch.object(deploy, 'Progress', side_effect=AssertionError('Completed boot must not touch the display')):
                self.assertEqual(result, deploy.deploy(source, root/'storage', show_progress=True))

    def test_failed_payload_does_not_show_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root/'bundle'
            source.mkdir()
            bundle(source)
            with (source/'payload.tar.gz').open('ab') as stream:
                stream.write(b'corrupt')
            tracker = Tracker()
            with patch.object(deploy, 'Progress', return_value=tracker):
                with self.assertRaises(ValueError):
                    deploy.deploy(source, root/'storage', show_progress=True)
            self.assertIsInstance(tracker.error, ValueError)
            self.assertNotIn('complete', tracker.events)
            self.assertLess(tracker.percent, 100)
            self.assertFalse((root/'storage/.kodi/userdata/guisettings.xml').exists())


if __name__ == '__main__':
    unittest.main()
