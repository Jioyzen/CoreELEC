#!/usr/bin/env python3
"""Build a locked, credential-free offline payload from release assets."""
import argparse
import gzip
import hashlib
import json
import os
import pathlib
import re
import shutil
import tarfile
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
from safe_archive import sha256, extract_tar, extract_zip, check_text

ROOT=pathlib.Path(__file__).resolve().parent


def download(url, destination, digest):
    if not url.startswith('https://github.com/Jioyzen/'):
        raise ValueError('Unapproved payload source')
    if destination.is_file() and sha256(destination)==digest:return
    temporary=destination.with_suffix('.partial')
    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Jioyzen-Media-Builder'}),timeout=60) as src,temporary.open('wb') as out:
        shutil.copyfileobj(src,out)
    if sha256(temporary)!=digest:
        temporary.unlink();raise ValueError('Download checksum mismatch')
    os.replace(temporary,destination)


def assemble(lock, output, cache):
    lock=json.loads(pathlib.Path(lock).read_text())
    cache=pathlib.Path(cache);cache.mkdir(parents=True,exist_ok=True)
    output=pathlib.Path(output);output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='jioyzen-media-') as tmp:
        stage=pathlib.Path(tmp)/'payload';stage.mkdir()
        snapshot=cache/'third-party-and-runtimes.tar.gz'
        download(lock['snapshot']['url'],snapshot,lock['snapshot']['sha256'])
        extract_tar(snapshot,stage)
        addons=stage/'.kodi/addons';addons.mkdir(parents=True,exist_ok=True)
        for entry in lock['addons']:
            archive=cache/(entry['id']+'-'+entry['version']+'.zip')
            download(entry['url'],archive,entry['sha256'])
            extract_zip(archive,addons,entry['id'])
            manifest=ET.parse(addons/entry['id']/'addon.xml').getroot()
            if manifest.get('id')!=entry['id'] or manifest.get('version')!=entry['version']:
                raise ValueError('Addon identity mismatch')
        # The verified Zulu ARM64 build ships lib/arm with a local aarch64
        # alias. Use the canonical directory directly: archives intentionally
        # contain only regular files and never restore arbitrary symlinks.
        jre=addons/'tools.jre.zulu/jre/lib'
        if (jre/'arm').is_dir() and not (jre/'aarch64').exists():
            (jre/'arm').rename(jre/'aarch64')
        shutil.copytree(ROOT/'profile/defaults',stage,dirs_exist_ok=True)
        (stage/'kodi-defaults.json').write_bytes((ROOT/'profile/kodi-defaults.json').read_bytes())
        manifests={}
        for p in addons.glob('*/addon.xml'):
            m=ET.parse(p).getroot();manifests[m.get('id')]=m
        provided=dict(lock['system_addons']);provided.update({aid:m.get('version') for aid,m in manifests.items()})
        for aid,m in manifests.items():
            for d in m.findall('requires/import'):
                if d.get('optional')!='true' and d.get('addon') not in provided:
                    raise ValueError('Missing offline dependency: '+aid+' -> '+d.get('addon'))
                if d.get('optional')!='true' and d.get('version'):
                    def vparts(v):
                        parts=[int(x) for x in re.findall(r'\d+',v.split('+')[0])]
                        return tuple(parts+[0]*(8-len(parts)))
                    if vparts(provided[d.get('addon')]) < vparts(d.get('version')):
                        raise ValueError('Outdated offline dependency: '+aid+' -> '+d.get('addon'))
        files={}
        for p in sorted(stage.rglob('*')):
            if not p.is_file():continue
            rel=str(p.relative_to(stage))
            if p.suffix in ('.pyc','.pyo','.log') or p.name in ('scan_history.json','last_success.json','probe_result.json','sources.xml'):
                raise ValueError('Runtime data in payload')
            if p.suffix in {'.xml','.py','.json','.conf','.rules','.sh','.service','.md','.po','.txt'}:
                check_text(rel,p.read_bytes())
            files[rel]={'sha256':sha256(p),'size':p.stat().st_size,'mode':0o755 if p.stat().st_mode&0o111 else 0o644}
        profile={'schema':1,'edition':'media','board_id':'g12a_s905x2_u212_2g_rtl8822cs',
                 'addons':{aid:m.get('version') for aid,m in sorted(manifests.items())},
                 'files':files,'sources':lock}
        encoded=json.dumps(profile,ensure_ascii=False,sort_keys=True,indent=2).encode()+b'\n'
        (stage/'payload-manifest.json').write_bytes(encoded)
        profile_id=hashlib.sha256(encoded).hexdigest()
        archive=output/'payload.tar.gz'
        # Keep permissions deterministic and do not store developer ownership.
        with archive.open('wb') as output_stream, gzip.GzipFile(fileobj=output_stream,mode='wb',filename='',mtime=0) as compressed:
            with tarfile.open(fileobj=compressed,mode='w|') as tar:
                for p in sorted(stage.rglob('*')):
                    if p.is_file():
                        info=tarfile.TarInfo(str(p.relative_to(stage)));info.size=p.stat().st_size;info.uid=info.gid=0;info.mtime=0
                        info.mode=0o755 if p.stat().st_mode&0o111 else 0o644
                        with p.open('rb') as source:tar.addfile(info,source)
        summary={'schema':1,'edition':'media','profile_id':profile_id,'payload_sha256':sha256(archive),
                 'expanded_size':sum(v['size'] for v in files.values()),'addons':profile['addons']}
        (output/'profile.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
        print('Offline payload:',len(manifests),'addons;',summary['expanded_size'],'expanded bytes')
        return summary


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--lock',type=pathlib.Path,default=ROOT/'profile/lock.json');ap.add_argument('--output',type=pathlib.Path,required=True);ap.add_argument('--cache',type=pathlib.Path,required=True)
    args=ap.parse_args();assemble(args.lock,args.output,args.cache)
