"""Verify the ordinary flash SYSTEM matches its update and excludes media data."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile


def verify_base_system(system, update, output, toolchain):
    with Path(system).open('rb') as stream:
        actual = hashlib.file_digest(stream, 'sha256').hexdigest()
    with tarfile.open(update) as archive:
        entries = [entry for entry in archive if entry.name.endswith('/target/SYSTEM')]
        if len(entries) != 1 or entries[0].size != Path(system).stat().st_size:
            raise ValueError('Ordinary update SYSTEM missing or wrong size')
        with archive.extractfile(entries[0]) as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != actual:
                raise ValueError('Ordinary flash/update SYSTEM differ')
    unsquashfs = shutil.which('unsquashfs') or str(Path(toolchain) / 'bin/unsquashfs')
    listing = subprocess.check_output([unsquashfs, '-ll', str(system)], text=True)
    for name in ('usr/share/jioyzen-media', 'usr/lib/jioyzen-media',
                 'usr/lib/systemd/system/jioyzen-media-seed.service',
                 'usr/lib/systemd/system/jioyzen-media-wifi.service'):
        if 'squashfs-root/' + name in listing:
            raise ValueError('Media provisioning leaked into ordinary image: ' + name)
    report = {'schema': 1, 'edition': 'base', 'flash_image_system_matches_update': True,
              'media_payload_absent': True, 'system_sha256': actual,
              'hardware_cold_boot': 'not_tested_for_this_build'}
    Path(output).write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return report
