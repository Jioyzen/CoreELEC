#!/usr/bin/env python3
"""Verify the actual flash image SYSTEM and run its embedded installer offline."""
import argparse
import gzip
import json
import pathlib
import shutil
import struct
import subprocess
import tarfile
import tempfile
import xml.etree.ElementTree as ET
from safe_archive import sha256
from verify_offline import verify


def verify_image(release, toolchain):
    release=pathlib.Path(release);toolchain=pathlib.Path(toolchain)
    images=list(release.glob('*.img.gz'));updates=list(release.glob('*.tar'))
    assert len(images)==len(updates)==1
    mcopy=shutil.which('mcopy') or str(toolchain/'bin/mcopy')
    unsquashfs=shutil.which('unsquashfs') or str(toolchain/'bin/unsquashfs')
    with tempfile.TemporaryDirectory(prefix='media-image-check-') as tmp:
        root=pathlib.Path(tmp);raw=root/'flash.img'
        with gzip.open(images[0],'rb') as source,raw.open('wb') as destination:
            shutil.copyfileobj(source,destination)
        with raw.open('rb') as stream:mbr=stream.read(512)
        assert mbr[510:]==b'\x55\xaa'
        start,sectors=struct.unpack_from('<II',mbr,446+8)
        assert sectors*512>=1024**3, 'Media system partition is smaller than 1 GiB'
        system=root/'SYSTEM'
        subprocess.run([mcopy,'-i',str(raw)+'@@'+str(start*512),'::/SYSTEM',str(system)],check=True)
        with tarfile.open(updates[0]) as archive:
            entries=[m for m in archive if m.name.endswith('/target/SYSTEM')]
            assert len(entries)==1 and entries[0].size==system.stat().st_size
            update_system=root/'update-SYSTEM'
            with archive.extractfile(entries[0]) as source,update_system.open('wb') as destination:
                shutil.copyfileobj(source,destination)
        assert sha256(system)==sha256(update_system), 'Flash and update SYSTEM differ'
        extracted=root/'system'
        paths=['usr/share/jioyzen-media','usr/lib/jioyzen-media','usr/share/kodi/system/addon-manifest.xml',
               'usr/lib/systemd/system/jioyzen-media-seed.service','usr/lib/systemd/system/jioyzen-media-activate.service',
               'usr/lib/systemd/system/kodi.service.d/20-media-provisioning.conf',
               'usr/lib/coreelec/evrepeat-policy.sh','usr/lib/udev/rules.d/99-remote-repeat-policy.rules',
               'usr/lib/systemd/system/alist.service','usr/lib/systemd/system/openlist.service','usr/lib/systemd/system/clouddrive2.service']
        subprocess.run([unsquashfs,'-no-progress','-processors','2','-d',str(extracted),str(system),*paths],check=True,stdout=subprocess.DEVNULL)
        bundle=extracted/'usr/share/jioyzen-media'
        summary=json.loads((bundle/'profile.json').read_text())
        system_addons=ET.parse(extracted/'usr/share/kodi/system/addon-manifest.xml').getroot()
        ids={n.text for n in system_addons.findall('addon')}
        disabled=set(summary.get('default_disabled_addons',[]))
        assert (set(summary['addons'])-disabled)<=ids, 'First-start registration missing'
        assert not disabled & ids, 'Disabled addon registered for first-start activation'
        # Use the deployment code extracted from SYSTEM, not just the source tree.
        import importlib.util
        spec=importlib.util.spec_from_file_location('image_deploy',extracted/'usr/lib/jioyzen-media/deploy.py')
        image_deploy=importlib.util.module_from_spec(spec);spec.loader.exec_module(image_deploy)
        import verify_offline
        original=verify_offline.deploy
        try:
            verify_offline.deploy=image_deploy.deploy
            report=verify(bundle)
        finally:verify_offline.deploy=original
        report.update(flash_image_system_matches_update=True,system_partition_bytes=sectors*512,
                      system_sha256=sha256(system),embedded_installer='passed',first_start_registration='passed')
        (release/'offline-image-validation.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--release',required=True);p.add_argument('--toolchain',required=True)
    a=p.parse_args();verify_image(a.release,a.toolchain)
