#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Check actual flash/update contents before exposing Jiefu release artifacts."""
import datetime
import gzip
import importlib.util
import json
import os
import pathlib
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile

from validate import BOARD_ID, sha256, validate_boot_config, validate_dtb, validate_system

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/media'))
from verify_image import verify_image


def collect():
    target = pathlib.Path(os.environ['TARGET_DIR'])
    build = pathlib.Path(os.environ['BUILD_DIR']) / 'build.CoreELEC-Amlogic-no.aarch64-22-jiefu'
    stem = (build / 'BUILD_FILENAME').read_text().strip()
    assert pathlib.Path(stem).name == stem and stem.startswith('CoreELEC-Amlogic-no.aarch64-')
    image = target / (stem + '-Generic.img.gz')
    update = target / (stem + '.tar')
    assert image.is_file() and update.is_file(), 'Matching fresh image and update tar required'
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    mcopy = shutil.which('mcopy') or str(build / 'toolchain/bin/mcopy')
    unsquashfs = shutil.which('unsquashfs') or str(build / 'toolchain/bin/unsquashfs')
    with tempfile.TemporaryDirectory(prefix='jiefu-image-') as temporary:
        tmp = pathlib.Path(temporary)
        raw = tmp / 'flash.img'
        with gzip.open(image, 'rb') as source, raw.open('wb') as destination:
            shutil.copyfileobj(source, destination)
        mbr = raw.open('rb')
        with mbr:
            sector = mbr.read(512)
        assert sector[510:] == b'\x55\xaa'
        start = struct.unpack_from('<I', sector, 454)[0] * 512

        def copy_flash(name):
            destination = tmp / name
            subprocess.run([mcopy, '-i', str(raw) + '@@' + str(start),
                            '::/' + name, str(destination)], check=True)
            return destination

        dtb = copy_flash('dtb.img')
        validate_dtb(dtb)
        validate_boot_config(copy_flash('config.ini'))
        # A successful mcopy would mean a forbidden FAT-partition module exists.
        forbidden = subprocess.run([mcopy, '-i', str(raw) + '@@' + str(start),
                                    '::/dovi.ko', str(tmp / 'dovi.ko')],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        assert forbidden.returncode != 0, 'FAT partition contains dovi.ko'
        system_image = copy_flash('SYSTEM')
        kernel_image = copy_flash('kernel.img')
        extracted = tmp / 'system'
        subprocess.run([unsquashfs, '-no-progress', '-processors', '2', '-d',
                        str(extracted), str(system_image)], check=True, stdout=subprocess.DEVNULL)
        manifest = validate_system(extracted)
        assert sha256(dtb) == sha256(extracted / 'usr/share/bootloader/device_trees' / (BOARD_ID + '.dtb'))
        release = dict(line.split('=', 1) for line in
                       (extracted / 'etc/os-release').read_text().splitlines() if '=' in line)
        version = release['VERSION'].strip('"')
        assert release['BUILD_ID'].strip('"') == revision, 'Stale image/source commit mismatch'
        with tarfile.open(update) as archive:
            assert not any(pathlib.PurePosixPath(m.name).name.startswith('dovi.ko') for m in archive)
            for suffix, reference in [('/target/SYSTEM', system_image),
                                      ('/target/KERNEL', kernel_image),
                                      ('/device_trees/' + BOARD_ID + '.dtb', dtb)]:
                members = [m for m in archive if m.name.endswith(suffix)]
                assert len(members) == 1
                exported = tmp / ('tar-' + reference.name)
                with archive.extractfile(members[0]) as source, exported.open('wb') as destination:
                    shutil.copyfileobj(source, destination)
                assert sha256(exported) == sha256(reference), 'Update and flash contents differ'

    out = target / 'jiefu-release'
    # Collect into a staging directory; failed checks never look like a release.
    with tempfile.TemporaryDirectory(prefix='.jiefu-release-', dir=target) as staging:
        stage = pathlib.Path(staging)
        stamp = version.rsplit('_', 1)[1]
        name = 'CE22-Jiefu-' + stamp[:8] + '-' + stamp[8:]
        shutil.copy2(image, stage / (name + '.img.gz'))
        package = stage / (name + '.tar')
        shutil.copy2(update, package)
        verify_image(stage, build / 'toolchain')
        tag = 'jiefu-' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S') + '-' + revision[:8]
        feed = {'schema': 1, 'edition': 'jiefu-media', 'board_id': BOARD_ID,
                'architecture': 'Amlogic-no.aarch64', 'version': version, 'build_id': revision,
                'artifact': {'name': package.name, 'size': package.stat().st_size,
                             'sha256': sha256(package),
                             'url': 'https://github.com/Jioyzen/CoreELEC/releases/download/' + tag + '/' + package.name}}
        spec = importlib.util.spec_from_file_location('jiefu_updates', ROOT /
            'projects/Amlogic-ce/packages/jiefu-board/sources/s905x2_updates.py')
        updater = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(updater)
        updater.validate_feed(feed)
        (stage / 'update.json').write_text(json.dumps(feed, indent=2) + '\n')
        manifest.update(source_commit=revision, version=version, release_tag=tag,
                        hardware_tested_for_this_build=False,
                        image_validation='passed', media_offline_validation='passed')
        (stage / 'build-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        report = json.loads((stage / 'offline-image-validation.json').read_text())
        notes = (ROOT / 'tools/jiefu/RELEASE-NOTES.md').read_text(encoding='utf-8')
        (stage / 'RELEASE-NOTES.md').write_text(
            notes.format(addon_count=report['addon_count'], revision=revision), encoding='utf-8')
        (stage / 'SHA256SUMS').write_text(''.join(
            sha256(p) + '  ' + p.name + '\n' for p in sorted(stage.iterdir()) if p.is_file()))
        if out.exists():
            shutil.rmtree(out)
        shutil.copytree(stage, out)
    print(out)


if __name__ == '__main__':
    collect()
