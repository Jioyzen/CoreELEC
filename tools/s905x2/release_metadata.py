#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Generate release notes and the atomic, board-specific upgrade feed."""
import hashlib
import json
import pathlib

REPOSITORY = 'https://github.com/Jioyzen/CoreELEC'


def release_notes(revision):
    return f'''# S905X2 / RTL8822CS 专用 CoreELEC NO

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
- 修复电视或功放关闭时启动后，HDMI 有信号但画面黑屏的问题。
- 支持 DD22 红外遥控关机唤醒，使用原厂 BL30 的 SCPI/mailbox 配置，无需注入引导固件。
- 修正本机型电源指示灯极性：运行时蓝灯，关机待机时红灯。
- 内置本仓库自动更新源，支持检查新正式版本、下载并校验升级包；每周自动同步上游代码、构建和发布更新。
- 默认使用修复后的专用 DTB，内置已验证的 `dovi.ko`；适配机型刷写后无需手动选择 DTB 或复制模块即可启动。
- 其他修复详见 [commits 提交记录](https://github.com/Jioyzen/CoreELEC/commits/s905x2-no-fixes)。
- 修复红外码表重新加载时的输入设备数组越界、重复计数和注册顺序问题，避免遥控失效及潜在内核崩溃。

## 下载与升级

- **`.img.gz`**：首次刷写 U 盘或 SD 卡使用。
- **`.tar`**：系统升级包，适用于普通修复版升级；同一适配盒子的官方 **CoreELEC 22 Amlogic-no / aarch64** 也可迁移至本修复版本。复制到 `/storage/.update/` 后重启，保留用户配置，并使用本镜像的专用 DTB；不适用于 Amlogic-ng 跨架构升级。
- 普通版与完整版使用独立更新通道，不能互相直接升级；跨版请重新刷写介质。
- 从首版尚未内置更新源的镜像迁移，需要手动安装本次升级包一次，之后即可使用系统“检查更新”。
- 使用过旧运行时补丁的系统，应清理残留的 `LD_PRELOAD`、无线驱动替换服务和 DTB 覆盖配置；详见 [仓库文档](https://github.com/Jioyzen/CoreELEC/blob/s905x2-no-fixes/S905X2.md)。
- `SHA256SUMS` 提供产物校验，`build-manifest.json` 记录源码版本，`update.json` 供普通版系统更新程序使用。

## 每周构建

镜像每周日北京时间 **03:00** 由 GitHub Actions 自动同步上游并构建；两边源码均无变化时跳过。构建、测试和产物检查通过后，普通版与完整版在同一个 Release 中正式发布；合并冲突时自动停止。

首版已实机验证 HDMI、Wi-Fi 和 DV seek 正常；后续版本的正式发布不代表每次都经过人工实机回归。

源码提交：[`{revision[:8]}`](https://github.com/Jioyzen/CoreELEC/commit/{revision})
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
        'edition': 'base',
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
