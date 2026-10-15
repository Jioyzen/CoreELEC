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

## 版本区别

| 版本 | 文件名 | 内容 |
| --- | --- | --- |
| 普通版 | 不含 `-MEDIA-` | 保留原版 CoreELEC 界面和初始化流程，包含系统、驱动及 Kodi 修复 |
| 完整版 | 含 `-MEDIA-` | 包含普通版修复，以及插件、皮肤、中文、天气卡片和服务程序，首次启动自动部署 |

## 本版更新

- 修复红外码表重新加载时的数组越界、设备计数错误与潜在内核崩溃；完整版补齐 DD22 红外映射。
- 完整版首次启动在 Logo 下方显示离线部署阶段、进度条和已用时间，部署完成后进入桌面。
- 完整版首次进入桌面提供 Wi-Fi 连接向导；已有网络或无无线模块时跳过，连接后刷新天气。向导只在首次启动时触发，后续断网或重启不再弹出。
- JellyCon 预装但默认禁用，避免未配置服务器时开机弹出扫描。
- 完整版内置 37 个插件及依赖、Java 和 Alist / OpenList / CloudDrive2 程序；这些服务默认不自启动。

## 系统基础更新与修复

镜像针对已验证的 S905X2（RTL8822CS）盒子，不保证兼容所有 S905X2 或其他型号盒子。

- 跟随官方 CoreELEC `coreelec-22` 分支同步上游代码。
- 修复板级 DTB 中的 VPU 时钟配置，解决 HDMI 2160p50/60 高刷新率输出花屏。
- 对齐 U-Boot framebuffer 地址与预留内存，修复启动 Logo 交接阶段花屏。
- 调整 DTB 的 SDIO 高速模式配置，修复无线接口速率受限。
- 使用适配 NO 内核的 RTL8822CS 厂商驱动，启用 NAPI/GRO，实测 Wi-Fi 吞吐由 **97.05 Mbps** 提升至 **578.76 Mbps**。
- 修复 Dolby Vision 模式下部分 Profile 7 FEL 片源快进、快退时可能出现的花屏、色块、绿线，保留完整 DV/FEL 解码与合成。
- 修复 Kodi GUI 中文长文本换行耗时扫描导致的异常卡顿，解决连续操作海报、设置菜单时卡住数秒的问题。
- 修复 HDMI 切换信号源后 4K 错误回落到 1080p，以及 HDMI 热插拔后无法恢复信号的问题。
- 内置本仓库自动更新源，支持检查新正式版本、下载并校验升级包；每周自动同步上游代码、构建和发布更新。
- 默认使用修复后的专用 DTB，内置已验证的 `dovi.ko`；适配机型刷写后无需手动选择 DTB 或复制模块即可启动。
- 其他修复详见 [commits 提交记录](https://github.com/Jioyzen/CoreELEC/commits/s905x2-no-fixes)。

## 下载与升级

- **`.img.gz`**：首次刷写 U 盘或 SD 卡使用。完整版系统分区为 1GB，建议使用至少 4GB 的介质。
- **`.tar`**：系统升级包，适用于同一版本类型升级。普通版与完整版使用独立更新通道，不能互相直接升级；跨版请重新刷写介质。
- 同一适配盒子的官方 **CoreELEC 22 Amlogic-no / aarch64** 可迁移至普通修复版。将普通版 `.tar` 复制到 `/storage/.update/` 后重启，保留用户配置，并使用本镜像的专用 DTB；不适用于 Amlogic-ng 跨架构升级。
- 从首版尚未内置更新源的镜像迁移，需要手动安装本次升级包一次，之后即可使用系统“检查更新”。
- 使用过旧运行时补丁的系统，应清理残留的 `LD_PRELOAD`、无线驱动替换服务和 DTB 覆盖配置；详见 [仓库文档](https://github.com/Jioyzen/CoreELEC/blob/s905x2-no-fixes/S905X2.md)。
- `SHA256SUMS` 提供产物校验，`build-manifest.json` 记录两套源码版本与产物散列。
- 普通版更新索引为 `update.json`，完整版为 `media-update.json`；原有 `media-channel/update.json` 同步指向本 Release 的完整版升级包。

## 每周构建

镜像每周日北京时间 **03:00** 由 GitHub Actions 自动同步上游并构建；两边源码均无变化时跳过。构建、测试和产物检查通过后，普通版与完整版在同一个 Release 中正式发布；合并冲突时自动停止。

首版已实机验证 HDMI、Wi-Fi 和 DV seek 正常；后续版本的正式发布不代表每次都经过人工实机回归。

## 源码版本

| 版本 | 分支 | 提交 |
| --- | --- | --- |
| 普通版 | `s905x2-no-fixes` | [`{base['source_commit'][:8]}`](https://github.com/Jioyzen/CoreELEC/commit/{base['source_commit']}) |
| 完整版 | `s905x2-media-edition` | [`{media['source_commit'][:8]}`](https://github.com/Jioyzen/CoreELEC/commit/{media['source_commit']}) |
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
