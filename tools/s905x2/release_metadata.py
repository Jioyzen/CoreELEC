#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Generate release notes and the atomic, board-specific upgrade feed."""
import hashlib
import json
import pathlib

REPOSITORY = 'https://github.com/Jioyzen/CoreELEC'


def release_notes(revision):
    return f'''# S905X2 / RTL8822CS 专用 CoreELEC NO

镜像针对已验证的 S905X2（G12A、u212 接近板型、2GB DDR3、RTL8822CS）盒子，不保证兼容所有 S905X2 或其他型号盒子。

- 跟随官方 CoreELEC `coreelec-22` 分支同步上游代码，保留本项目修复。
- 修复板级 DTB 中的 VPU 时钟配置，解决 HDMI 2160p50/60 高刷新率输出花屏。
- 对齐 U-Boot framebuffer 地址与预留内存，修复启动显示交接阶段花屏。
- 调整 DTB 的 SDIO 高速模式配置，修复无线接口速率受限。
- 使用适配 NO 内核的 RTL8822CS 厂商驱动，启用 NAPI/GRO 并调整省电参数；实测 Wi-Fi 吞吐由约 **97.05 Mbps** 提升至最高 **578.76 Mbps**。实际速度取决于路由器、频段和信号环境。
- 修复 Dolby Vision 模式下部分 Profile 7 FEL 片源快进、快退和从保存进度续播时可能出现的花屏、色块、绿线；保留完整 DV/FEL 解码与合成。
- 默认使用修复后的专用 DTB，内置已验证的 `dovi.ko`；适配机型刷写后无需手动选择 DTB 或复制模块即可启动。
- 内置本仓库自动更新源：检查新正式版本、下载并校验升级包，重启时使用 CoreELEC 原有升级机制安装。CEC 保持官方逻辑。

## 下载与升级

- **`.img.gz`**：首次刷写 U 盘或 SD 卡使用。
- **`.tar`**：系统升级包，适用于本分支升级；同一适配盒子的官方 **CoreELEC 22 Amlogic-no / aarch64** 也可迁移至本修复版本。复制到 `/storage/.update/` 后重启，保留用户配置，并选择本镜像的专用 DTB。不是 Amlogic-ng 的跨架构升级包。
- 从首版尚未内置更新源的镜像迁移，需要手动安装本次升级包一次，之后即可使用系统“检查更新”。
- 使用过旧运行时补丁的系统，应清理残留的 `LD_PRELOAD`、无线驱动替换服务和 DTB 覆盖配置；详见仓库文档。
- `SHA256SUMS` 提供产物校验，`build-manifest.json` 记录源码版本，`update.json` 供系统更新程序使用。

镜像每周日北京时间 **03:00** 由 GitHub Actions 自动同步上游并构建；源码无变化时跳过。构建、测试和产物检查通过后自动正式发布。首版已实机验证 HDMI、Wi-Fi 和 DV seek 正常；后续版本的正式发布不代表每次都经过人工实机回归。

源码 commit：`{revision}`
'''


def write_metadata(out, version, revision, release_tag):
    out = pathlib.Path(out)
    packages = list(out.glob('*-S905X2-U212-2G-RTL8822CS.tar'))
    if len(packages) != 1:
        raise ValueError('Expected one board upgrade tar')
    package = packages[0]
    digest = hashlib.sha256(package.read_bytes()).hexdigest()
    feed = {
        'schema': 1,
        'board_id': 'g12a_s905x2_u212_2g_rtl8822cs',
        'architecture': 'Amlogic-no.aarch64',
        'version': version,
        'build_id': revision,
        'artifact': {
            'name': package.name,
            'url': f'{REPOSITORY}/releases/download/{release_tag}/{package.name}',
            'sha256': digest,
            'size': package.stat().st_size,
        },
    }
    (out / 'update.json').write_text(json.dumps(feed, ensure_ascii=False, indent=2) + '\n')
    (out / 'RELEASE-NOTES.md').write_text(release_notes(revision))
    return feed
