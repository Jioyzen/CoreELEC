#!/usr/bin/env python3
"""Validate actual image dependencies and register bundled optional addons."""
import argparse
import json
import pathlib
import re
import tarfile
import xml.etree.ElementTree as ET


def version(value):
    parts=[int(x) for x in re.findall(r'\d+',value.split('+')[0])]
    return tuple(parts+[0]*(8-len(parts)))


def register(bundle, system):
    bundle=pathlib.Path(bundle);system=pathlib.Path(system)
    summary=json.loads((bundle/'profile.json').read_text())
    provided={m.get('id'):m.get('version') for p in (system/'usr/share/kodi/addons').glob('*/addon.xml') for m in [ET.parse(p).getroot()]}
    bundled={}
    with tarfile.open(bundle/'payload.tar.gz') as tar:
        for item in tar:
            path=pathlib.PurePosixPath(item.name)
            if len(path.parts)==4 and path.parts[:2]==('.kodi','addons') and path.name=='addon.xml':
                bundled[path.parts[2]]=ET.fromstring(tar.extractfile(item).read())
    if {aid:m.get('version') for aid,m in bundled.items()}!=summary['addons']:
        raise ValueError('Bundle addon manifest mismatch')
    disabled=set(summary.get('default_disabled_addons',[]))
    if disabled-set(bundled):raise ValueError('Unknown disabled addon ID')
    provided.update(summary['addons'])
    for aid,m in bundled.items():
        for dep in m.findall('requires/import'):
            if dep.get('optional')=='true':continue
            did=dep.get('addon');minimum=dep.get('version','0')
            if did not in provided or version(provided[did])<version(minimum):
                raise ValueError('Incompatible image dependency: '+aid+' -> '+did)
    path=system/'usr/share/kodi/system/addon-manifest.xml'
    tree=ET.parse(path);root=tree.getroot();known={n.text for n in root.findall('addon')}
    for node in list(root.findall('addon')):
        if node.text in disabled and node.get('optional')=='true':root.remove(node)
    for aid in sorted(bundled):
        if aid not in known and aid not in disabled:ET.SubElement(root,'addon',optional='true').text=aid
    tree.write(path,encoding='utf-8',xml_declaration=True)
    print('Registered',len(bundled),'offline addons; image dependencies verified')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--bundle',required=True);parser.add_argument('--system',required=True)
    args=parser.parse_args();register(args.bundle,args.system)
