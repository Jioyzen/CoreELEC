#!/usr/bin/env python3
"""Exercise the real bundled installer with network access disabled."""
import argparse
import json
import pathlib
import socket
import tempfile
import xml.etree.ElementTree as ET
from unittest.mock import patch
from deploy import deploy
from safe_archive import sha256


def verify(bundle):
    bundle=pathlib.Path(bundle)
    summary=json.loads((bundle/'profile.json').read_text())
    with tempfile.TemporaryDirectory(prefix='media-offline-check-') as tmp:
        storage=pathlib.Path(tmp)
        with patch.object(socket,'socket',side_effect=AssertionError('Network forbidden during offline deployment')):
            first=deploy(bundle,storage)
            second=deploy(bundle,storage)
        assert first==second and first['status']=='complete' and first['fresh_settings']
        actual={m.get('id'):m.get('version') for p in (storage/'.kodi/addons').glob('*/addon.xml') for m in [ET.parse(p).getroot()]}
        assert actual==summary['addons']
        for binary in ('service.alist/alist','service.openlist/openlist','service.clouddrive/clouddrive','tools.jre.zulu/jre/bin/java'):
            path=storage/'.kodi/addons'/binary
            assert path.is_file() and path.stat().st_mode & 0o111, binary
        assert (storage/'.kodi/addons/tools.jre.zulu/jre/lib/aarch64/jli/libjli.so').is_file()
        config=json.loads((storage/'.kodi/userdata/addon_data/service.openlist/config.json').read_text())
        assert config['scheme']['http_port']==5245
        gui=ET.parse(storage/'.kodi/userdata/guisettings.xml')
        assert gui.find("setting[@id='lookandfeel.skin']").text=='skin.embuary.mod.jioyzen'
        assert gui.find("setting[@id='weather.addon']").text=='weather.jioyzen'
        assert not (storage/'.kodi/userdata/Database').exists()
        assert not (storage/'.kodi/userdata/Thumbnails').exists()
    report={'schema':1,'profile_id':summary['profile_id'],'payload_sha256':sha256(bundle/'payload.tar.gz'),
            'addon_count':len(actual),'fresh_offline_deployment':'passed','repeated_deployment':'passed',
            'network_forbidden':True,'hardware_cold_boot':'not_tested_no_removable_media'}
    (bundle/'offline-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report));return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--bundle',required=True)
    args=parser.parse_args();verify(args.bundle)
