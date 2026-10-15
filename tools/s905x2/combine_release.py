#!/usr/bin/env python3
"""Collect two independently built editions into one verified GitHub release."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

REPOSITORY = 'Jioyzen/CoreELEC'
DOWNLOAD = 'https://github.com/' + REPOSITORY + '/releases/download/'


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def check_source(folder, edition):
    folder = Path(folder)
    manifest = read_json(folder / 'build-manifest.json')
    feed = read_json(folder / 'update.json')
    if feed.get('edition', 'base') != edition or manifest.get('edition', 'base') != edition:
        raise ValueError('Wrong source edition: ' + edition)
    revision = manifest['source_commit']
    if not re.fullmatch('[0-9a-f]{40}', revision) or feed['build_id'] != revision:
        raise ValueError('Source revision does not match feed')
    version = manifest['version']
    if feed['version'] != version or not re.fullmatch(r'22\.0-Piers_(?:devel|nightly)_\d{14}', version):
        raise ValueError('Invalid build version')
    if feed['board_id'] != manifest['dt_id'] or feed['architecture'] != 'Amlogic-no.aarch64':
        raise ValueError('Wrong board or architecture')
    stem = 'CoreELEC-Amlogic-no.aarch64-' + version
    stem += '-MEDIA' if edition == 'media' else ''
    stem += '-S905X2-U212-2G-RTL8822CS'
    expected = {stem + '.img.gz', stem + '.tar'}
    if set(manifest['artifacts']) != expected or feed['artifact']['name'] != stem + '.tar':
        raise ValueError('Unexpected edition filenames')
    for name in expected:
        path = folder / name
        if path.is_symlink() or not path.is_file() or digest(path) != manifest['artifacts'][name]:
            raise ValueError('Damaged source artifact: ' + name)
    package = folder / feed['artifact']['name']
    if digest(package) != feed['artifact']['sha256'] or package.stat().st_size != feed['artifact']['size']:
        raise ValueError('Source feed hash or size mismatch')
    validation = read_json(folder / 'offline-image-validation.json')
    if edition == 'base':
        if validation.get('edition') != 'base' or validation.get('media_payload_absent') is not True:
            raise ValueError('Base image isolation not verified')
    else:
        if (validation.get('embedded_installer') != 'passed' or
                validation.get('wifi_wizard') != 'embedded and enabled' or
                validation.get('wifi_first_start_only') is not True or
                validation.get('profile_id') != manifest['profile']['profile_id']):
            raise ValueError('Media offline deployment or first-start policy not verified')
    if validation.get('flash_image_system_matches_update') is not True:
        raise ValueError('Flash and update system verification missing')
    return manifest, feed


def combine(base, media, output):
    sources = {'base': Path(base), 'media': Path(media)}
    checked = {edition: check_source(path, edition) for edition, path in sources.items()}
    base_manifest, media_manifest = checked['base'][0], checked['media'][0]
    for key in ('dt_id', 'linux_commit', 'common_drivers_commit', 'media_modules_commit', 'kodi_commit'):
        if base_manifest[key] != media_manifest[key]:
            raise ValueError('Core source mismatch between editions: ' + key)
    tag = base_manifest['release_tag']
    if not re.fullmatch(r'[A-Za-z0-9._-]+', tag):
        raise ValueError('Invalid release tag')
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError('Combined output must be empty')
    output.mkdir(parents=True, exist_ok=True)
    for edition, folder in sources.items():
        manifest, feed = checked[edition]
        for name in manifest['artifacts']:
            shutil.copy2(folder / name, output / name)
        feed['edition'] = edition
        feed['artifact']['url'] = DOWNLOAD + tag + '/' + feed['artifact']['name']
        write_json(output / ('update.json' if edition == 'base' else 'media-update.json'), feed)
        manifest['release_tag'] = tag
        write_json(output / (edition + '-build-manifest.json'), manifest)
        shutil.copy2(folder / 'offline-image-validation.json', output / (edition + '-image-validation.json'))
    shutil.copy2(sources['media'] / 'offline-validation.json', output / 'media-offline-validation.json')
    manifest = {'schema': 1, 'release_tag': tag,
                'built_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'editions': {edition: data[0] for edition, data in checked.items()},
                'artifacts': {name: digest(output / name) for data in checked.values() for name in data[0]['artifacts']}}
    write_json(output / 'build-manifest.json', manifest)
    (output / 'RELEASE-NOTES.md').write_text(notes(manifest), encoding='utf-8')
    (output / 'SHA256SUMS').write_text(''.join(
        digest(path) + '  ' + path.name + '\n' for path in sorted(output.iterdir()) if path.name != 'SHA256SUMS'), encoding='utf-8')
    verify(output)
    return manifest


def notes(manifest):
    base = manifest['editions']['base']
    media = manifest['editions']['media']
    return f'''# S905X2 CoreELEC NO：普通版与完整版

两种镜像分别从独立分支构建，适配 S905X2 U212 / 2GB / RTL8822CS。

| 版本 | 文件名 | 内容 |
| --- | --- | --- |
| 普通版 | 不含 `-MEDIA-` | 保留原版 CoreELEC 界面和初始化流程，包含系统、驱动及 Kodi 修复 |
| 完整版 | 含 `-MEDIA-` | 系统修复加离线插件、皮肤、中文、天气卡片及服务程序，首次启动自动部署 |

- **`.img.gz`**：写入 USB / SD 首次安装。完整版系统分区 1GB，建议介质至少 4GB。
- **`.tar`**：相同版本类型的系统升级。普通版与完整版使用独立更新通道，不能互相直接升级；跨版请重新刷写新介质。
- 普通版更新索引为本 Release 的 `update.json`；完整版为 `media-update.json`，原有 `media-channel/update.json` 同步指向这里的完整版升级包。
- 红外驱动修复码表重新加载时的数组越界、设备计数错误与潜在内核崩溃；完整版补齐 DD22 红外映射。
- 完整版首次进入桌面提供独立 Wi-Fi 连接向导；已有网络或无无线模块时跳过。只触发一次，退出后不常驻，后续断网或重启不再弹出。
- Wi-Fi 向导已在开发盒子实测首次输入密码、连接、获取 IP、保存凭据与自动连接。天气卡片正常显示。
- JellyCon 预装但默认禁用，避免未配置服务器时开机弹出扫描。
- 完整版内置 37 个插件及依赖、Java 和 Alist / OpenList / CloudDrive2 程序；服务默认不自启动，不预设账号密码。
- 不包含个人 Wi-Fi、媒体库、API 密钥、云盘账号、蓝牙配对或 SSH 主机密钥。不自动安装到 eMMC 或改写 bootloader。
- 两边都通过编译、原生 DV/红外回归和实际镜像检查；完整版通过断网条件下的部署与重复部署检查。**本轮新镜像尚未重新刷写冷启动；新的红外内核修复尚未做整镜像实机回归。**

普通版源码：`{base['source_commit']}`（`s905x2-no-fixes`）

完整版源码：`{media['source_commit']}`（`s905x2-media-edition`）

离线软件配置：`{media['profile']['profile_id']}`

下载后使用 `SHA256SUMS` 校验文件；`build-manifest.json` 记录两套源码与产物散列。
'''


def verify(output):
    output = Path(output)
    sums = {}
    for line in (output / 'SHA256SUMS').read_text(encoding='utf-8').splitlines():
        sha, name = line.split('  ', 1)
        if not re.fullmatch('[0-9a-f]{64}', sha) or Path(name).name != name or name in sums:
            raise ValueError('Invalid release checksum manifest')
        sums[name] = sha
    actual = {p.name for p in output.iterdir() if p.name != 'SHA256SUMS'}
    if actual != set(sums):
        raise ValueError('Untracked or missing release assets')
    for name, sha in sums.items():
        if (output / name).is_symlink() or digest(output / name) != sha:
            raise ValueError('Release checksum mismatch: ' + name)
    manifest = read_json(output / 'build-manifest.json')
    tag = manifest['release_tag']
    for edition, name in [('base', 'update.json'), ('media', 'media-update.json')]:
        feed = read_json(output / name)
        source = manifest['editions'][edition]
        artifact = feed['artifact']
        if (feed['edition'] != edition or feed['build_id'] != source['source_commit'] or
                artifact['url'] != DOWNLOAD + tag + '/' + artifact['name'] or
                artifact['name'] not in source['artifacts'] or
                artifact['sha256'] != sums[artifact['name']] or
                artifact['size'] != (output / artifact['name']).stat().st_size):
            raise ValueError('Combined update feed mismatch: ' + edition)
    return manifest


def verify_uploaded(output, assets):
    expected = {p.name: p for p in Path(output).iterdir()}
    if {a['name'] for a in assets} != set(expected) or len(assets) != len(expected):
        raise ValueError('GitHub release asset list differs')
    for asset in assets:
        path = expected[asset['name']]
        if (asset['state'] != 'uploaded' or asset['size'] != path.stat().st_size or
                asset.get('digest') != 'sha256:' + digest(path)):
            raise ValueError('GitHub upload hash/size mismatch: ' + path.name)


def publish(output):
    output = Path(output)
    manifest = verify(output)
    tag = manifest['release_tag']
    revision = manifest['editions']['base']['source_commit']
    run = lambda *args: subprocess.run(['gh', *args], check=True)
    run('release', 'create', tag, *(str(p) for p in sorted(output.iterdir())),
        '--repo', REPOSITORY, '--target', revision, '--draft',
        '--title', 'S905X2 CoreELEC NO ' + tag + ' · 普通版 + 完整版',
        '--notes-file', str(output / 'RELEASE-NOTES.md'))
    # A draft may not have a Git tag yet. REST lookup by tag returns 404
    # even to the owner; GraphQL exposes its stable numeric REST API URL.
    draft = json.loads(subprocess.check_output(['gh', 'release', 'view', tag, '--repo', REPOSITORY,
                                              '--json', 'apiUrl,isDraft,tagName'], text=True))
    if (not draft['isDraft'] or draft['tagName'] != tag or
            not re.fullmatch(r'https://api\.github\.com/repos/Jioyzen/CoreELEC/releases/[0-9]+', draft['apiUrl'])):
        raise ValueError('Unexpected draft release identity')
    response = json.loads(subprocess.check_output(['gh', 'api', draft['apiUrl']], text=True))
    verify_uploaded(output, response['assets'])
    run('release', 'edit', tag, '--repo', REPOSITORY, '--draft=false', '--prerelease=false', '--latest')
    # Never touch the live media feed until the complete immutable release
    # has been uploaded, verified and made public. Legacy installed media
    # firmware still fetches this stable URL, whose filename is update.json.
    with tempfile.TemporaryDirectory(prefix='media-channel-') as temporary:
        feed = Path(temporary) / 'update.json'
        shutil.copy2(output / 'media-update.json', feed)
        run('release', 'upload', 'media-channel', str(feed), '--repo', REPOSITORY, '--clobber')
    print('https://github.com/' + REPOSITORY + '/releases/tag/' + tag)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base')
    parser.add_argument('--media')
    parser.add_argument('--output', required=True)
    parser.add_argument('--verify', action='store_true')
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    if args.publish:
        publish(args.output)
    elif args.verify:
        verify(args.output)
    elif args.base and args.media:
        combine(args.base, args.media, args.output)
    else:
        parser.error('specify --base and --media, or --verify/--publish')
