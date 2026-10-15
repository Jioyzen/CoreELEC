#!/usr/bin/env python3
"""Offline, resumable provisioning; never accesses a network or a block device."""
import argparse
import fcntl
import hashlib
import json
import os
import pathlib
import re
import shutil
import tempfile
import time
import xml.etree.ElementTree as ET
from safe_archive import extract_tar, sha256, safe_path
from boot_progress import Progress


def atomic_json(path, value):
    path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.partial')
    with temporary.open('w') as stream:
        os.fchmod(stream.fileno(),0o600)
        json.dump(value,stream,ensure_ascii=False,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
    os.replace(temporary,path)


def installed_version(folder):
    try:return ET.parse(folder/'addon.xml').getroot().get('version','')
    except (OSError,ET.ParseError):return ''


def newer_or_equal(installed, bundled):
    # Kodi versions use numeric components plus optional +matrix/+py suffixes.
    def parts(value):return tuple(int(x) for x in re.findall(r'\d+',value.split('+')[0]))
    return bool(installed) and parts(installed)>=parts(bundled)


def target_path(root, relative):
    path=root.joinpath(*safe_path(relative).parts)
    # A migrated installation may contain symlinks; never follow one outside
    # this storage root, including through intermediate parent directories.
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Destination escapes storage')
    return path


def install_addon(source, target, expected, progress=None):
    if newer_or_equal(installed_version(target),expected):return False
    target.parent.mkdir(parents=True,exist_ok=True)
    prepared=target.with_name('.'+target.name+'.media-new')
    previous=target.with_name('.'+target.name+'.media-old')
    if prepared.exists():shutil.rmtree(prepared)
    # Resume an interruption between moving the previous version and commit.
    if previous.exists() and not target.exists():os.replace(previous,target)
    def copy(source_file, destination_file):
        result=shutil.copy2(source_file,destination_file)
        if progress is not None:progress(pathlib.Path(source_file).stat().st_size)
        return result
    shutil.copytree(source,prepared,copy_function=copy)
    if previous.exists():shutil.rmtree(previous)
    if target.exists():os.replace(target,previous)
    try:os.replace(prepared,target)
    except OSError:
        if previous.exists() and not target.exists():os.replace(previous,target)
        raise
    if previous.exists():shutil.rmtree(previous)
    return True


def write_kodi_defaults(storage, defaults):
    path=target_path(storage,'.kodi/userdata/guisettings.xml')
    # Existing installations keep their settings, sources, passwords and UI.
    if path.exists():return
    root=ET.Element('settings',version='2')
    for key,value in sorted(defaults.items()):
        setting=ET.SubElement(root,'setting',id=key)
        if isinstance(value,list):setting.text='|'.join(str(element) for element in value)
        elif isinstance(value,bool):setting.text=str(value).lower()
        else:setting.text=str(value)
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.media-new')
    ET.ElementTree(root).write(temporary,encoding='utf-8',xml_declaration=True)
    with temporary.open('rb') as stream:os.fsync(stream.fileno())
    os.replace(temporary,path)


def deploy(bundle, storage, *, show_progress=False):
    bundle=pathlib.Path(bundle);storage=pathlib.Path(storage)
    storage.mkdir(parents=True,exist_ok=True)
    cache=target_path(storage,'.cache/jioyzen-media');cache.mkdir(parents=True,exist_ok=True)
    with (cache/'deploy.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        summary=json.loads((bundle/'profile.json').read_text())
        if summary.get('schema')!=1 or summary.get('edition')!='media':raise ValueError('Wrong bundle edition')
        state=cache/'deployment.json'
        try:
            previous=json.loads(state.read_text())
            if previous.get('status')=='complete' and previous.get('profile_id')==summary['profile_id']:
                return previous
        except (OSError,ValueError):pass
        with Progress(enabled=show_progress,first_boot=not target_path(storage,'.kodi/userdata/guisettings.xml').exists()) as progress:
            return deploy_payload(bundle,storage,cache,state,summary,progress)


def deploy_payload(bundle,storage,cache,state,summary,progress):
    archive=bundle/'payload.tar.gz'
    progress.set_stage('bundle',archive.stat().st_size)
    if sha256(archive,progress.advance)!=summary['payload_sha256']:raise ValueError('Payload SHA256 mismatch')
    # Extraction + directory commit temporarily needs two expanded copies.
    free=shutil.disk_usage(storage).free
    if free < summary['expanded_size']*2 + 64*1024**2:
        raise OSError('Insufficient storage for offline deployment')
    atomic_json(state,{'status':'deploying','profile_id':summary['profile_id']})
    with tempfile.TemporaryDirectory(prefix='stage-',dir=cache) as temp:
        stage=pathlib.Path(temp)
        progress.set_stage('unpack',summary['expanded_size'])
        extract_tar(archive,stage,progress=progress.advance,total=progress.set_total)
        manifest_file=stage/'payload-manifest.json'
        if sha256(manifest_file)!=summary['profile_id']:raise ValueError('Manifest identity mismatch')
        manifest=json.loads(manifest_file.read_text())
        progress.set_stage('verify',sum(entry['size'] for entry in manifest['files'].values()))
        addon_sizes={aid:0 for aid in manifest['addons']}
        runtime_files={}
        for name,entry in manifest['files'].items():
            path=safe_path(name)
            if path.parts[:2]==('.kodi','addons') and len(path.parts)>2 and path.parts[2] in addon_sizes:
                addon_sizes[path.parts[2]]+=entry['size']
            elif name!='kodi-defaults.json':runtime_files[name]=entry
            p=stage.joinpath(*safe_path(name).parts)
            if not p.is_file() or p.stat().st_size!=entry['size'] or sha256(p,progress.advance)!=entry['sha256']:
                raise ValueError('Payload file checksum mismatch: '+name)
        installed=[];new_addons=[]
        fresh_settings=not target_path(storage,'.kodi/userdata/guisettings.xml').exists()
        progress.set_stage('addons',sum(addon_sizes.values()))
        for aid,version in manifest['addons'].items():
            if not re.fullmatch(r'[A-Za-z0-9_.-]+',aid):raise ValueError('Unsafe addon ID')
            source=stage/'.kodi/addons'/aid
            target=target_path(storage,'.kodi/addons/'+aid)
            if not target.exists():new_addons.append(aid)
            if install_addon(source,target,version,progress.advance):installed.append(aid)
            else:progress.advance(addon_sizes[aid])
        # Standalone runtime directories have no addon.xml. Copy only
        # missing program files; the managers own subsequent upgrades.
        progress.set_stage('runtimes',sum(entry['size'] for entry in runtime_files.values()))
        for name,entry in runtime_files.items():
            path=safe_path(name)
            if path.parts[0] not in ('.kodi','.config'):raise ValueError('Unexpected payload root')
            dest=target_path(storage,name)
            if dest.exists():
                progress.advance(entry['size']);continue
            dest.parent.mkdir(parents=True,exist_ok=True)
            temporary=dest.with_name(dest.name+'.media-new')
            shutil.copyfile(stage/name,temporary);temporary.chmod(entry['mode'])
            os.replace(temporary,dest)
            progress.advance(entry['size'])
        progress.set_stage('settings')
        # Runtime accounts and databases are intentionally fresh and
        # created by each program only when the user starts it.
        for service in ('service.alist','service.openlist','service.clouddrive'):
            target_path(storage,'.kodi/userdata/addon_data/'+service).mkdir(parents=True,exist_ok=True,mode=0o700)
        config=target_path(storage,'.kodi/userdata/addon_data/service.openlist/config.json')
        if not config.exists():atomic_json(config,{'scheme':{'http_port':5245,'https_port':-1}})
        write_kodi_defaults(storage,json.loads((stage/'kodi-defaults.json').read_text()))
        report={'status':'complete','profile_id':summary['profile_id'],'installed':installed,'new_addons':new_addons,'fresh_settings':fresh_settings,
                'completed_at':int(time.time())}
        atomic_json(state,report)
        return report



if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--bundle',type=pathlib.Path,default=pathlib.Path('/usr/share/jioyzen-media'));ap.add_argument('--storage',type=pathlib.Path,default=pathlib.Path('/storage'));ap.add_argument('--progress',action='store_true',help='Show first-deployment progress on the boot framebuffer');args=ap.parse_args()
    try:print(json.dumps(deploy(args.bundle,args.storage,show_progress=args.progress),ensure_ascii=False))
    except Exception as error:
        print('Offline deployment failed:',type(error).__name__,str(error))
        raise SystemExit(1)
