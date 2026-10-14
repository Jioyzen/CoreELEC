#!/usr/bin/env python3
"""Publishable media artifacts and an edition-specific authenticated-by-hash feed."""
import datetime
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from safe_archive import sha256

ROOT=pathlib.Path(__file__).resolve().parents[2]
TARGET=pathlib.Path(os.environ.get('TARGET_DIR',ROOT/'target'))
BUILD=pathlib.Path(os.environ.get('BUILD_DIR',ROOT))/'build.CoreELEC-Amlogic-no.aarch64-22'
SYSTEM=BUILD/'image/system'


def collect():
    profile=json.loads((SYSTEM/'usr/share/jioyzen-media/profile.json').read_text())
    assert sha256(SYSTEM/'usr/share/jioyzen-media/payload.tar.gz')==profile['payload_sha256']
    assert (SYSTEM/'usr/lib/systemd/system/kodi.service.d/20-media-provisioning.conf').is_file()
    assert (SYSTEM/'usr/lib/jioyzen-media/deploy.py').is_file()
    assert (SYSTEM/'usr/lib/jioyzen-media/activate.py').is_file()
    binary=(SYSTEM/'usr/lib/kodi/kodi.bin').read_bytes()
    assert b'KODI_REMOTE_REPEAT_PERIOD_MS' in binary, 'Input policy not compiled into Kodi'
    updater=(SYSTEM/'usr/share/kodi/addons/service.coreelec.settings/resources/lib/s905x2_updates.pyc').read_bytes()
    assert b'media-channel/update.json' in updater, 'Dedicated media update feed missing'
    source=TARGET/'s905x2-release';out=TARGET/'s905x2-media-release'
    if out.exists():shutil.rmtree(out)
    out.mkdir()
    base=json.loads((source/'build-manifest.json').read_text())
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    tag='media-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M')+'-'+revision[:8]
    package=None
    for path in source.iterdir():
        if path.name.endswith(('.img.gz','.tar')):
            name=path.name.replace('-S905X2-U212-2G-RTL8822CS','-MEDIA-S905X2-U212-2G-RTL8822CS')
            shutil.copy2(path,out/name)
            if name.endswith('.tar'):package=out/name
    assert package is not None
    feed={'schema':1,'edition':'media','board_id':base['dt_id'],'architecture':'Amlogic-no.aarch64',
          'version':base['version'],'build_id':revision,'profile_id':profile['profile_id'],
          'artifact':{'name':package.name,'url':'https://github.com/Jioyzen/CoreELEC/releases/download/'+tag+'/'+package.name,
                      'size':package.stat().st_size,'sha256':sha256(package)}}
    (out/'update.json').write_text(json.dumps(feed,indent=2)+'\n')
    validation=json.loads((pathlib.Path(os.environ['JIOYZEN_MEDIA_PAYLOAD_DIR'])/'offline-validation.json').read_text())
    assert validation['profile_id']==profile['profile_id'] and validation['payload_sha256']==profile['payload_sha256']
    (out/'offline-validation.json').write_text(json.dumps(validation,indent=2)+'\n')
    base.update(edition='media',release_tag=tag,profile=profile,artifacts={p.name:sha256(p) for p in out.iterdir() if p.name.endswith(('.img.gz','.tar'))})
    (out/'build-manifest.json').write_text(json.dumps(base,ensure_ascii=False,indent=2)+'\n')
    (out/'RELEASE-NOTES.md').write_text('''# Jioyzen 完整播放器固件

适配 S905X2 U212 / 2GB / RTL8822CS。独立媒体版，使用 media-channel 更新源。

- `.img.gz` 用于首次刷写 USB / SD。系统分区 1GB，首次启动扩展数据分区并离线部署软件；建议使用至少 4GB 的介质。
- `.tar` 用于同一媒体版升级，保留用户账号、媒体库、设置和较新的插件。基础版不会自动升级到此媒体版。
- 内置37个插件及依赖、Java、Alist / OpenList / CloudDrive2 程序、遥控默认配置。10个维护插件固定为已验证发布版本。
- 自动启用 Embuary Mod、中文和天气卡片；默认定位城市。媒体来源、云盘及服务器账号、AI密钥由用户自己配置。
- 网络工具主程序已安装，默认未启用自启动，不预设账号密码和挂载。
- 不包含个人 userdata、媒体库、缩略图、网络凭据、蓝牙配对、设备 SSH 密钥，不执行 eMMC 安装或写入 bootloader。
- 替换诊断阶段的 Kodi 绑定挂载，以原生源码包含界面、遥控及 HDMI 修复。

'''+f'系统源码：{revision}\n离线软件配置：{profile["profile_id"]}\n')
    (out/'SHA256SUMS').write_text(''.join(sha256(p)+'  '+p.name+'\n' for p in sorted(out.iterdir()) if p.name!='SHA256SUMS'))
    print(out)


if __name__=='__main__':collect()
