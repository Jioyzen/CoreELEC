# S905X2 CoreELEC NO 修复版

基于 [CoreELEC](https://github.com/CoreELEC/CoreELEC) 官方 `coreelec-22` 分支，为某未知品牌 **S905X2（RTL8822CS Wi-Fi）** 盒子制作的专用修复源码。

这台盒子使用官方 Amlogic-no 出现 HDMI 4K60 和启动交接花屏、Wi-Fi 吞吐不足，以及部分 Dolby Vision Profile 7 FEL 影片 seek／续播色块、绿线。
本项目将已实机验证的修复集成进 DTB、驱动和 Kodi 源码，生成刷入后即可使用的镜像。

**不保证兼容所有 S905X2 盒子。** 同一 SoC 的不同板型可能使用不同内存、无线芯片和 framebuffer 地址。本项目不是 CoreELEC 官方发行版。

[下载最新正式版本](https://github.com/Jioyzen/CoreELEC/releases/latest) · [全部版本](https://github.com/Jioyzen/CoreELEC/releases) · [构建记录](https://github.com/Jioyzen/CoreELEC/actions/workflows/s905x2-weekly.yml) · [详细技术说明](S905X2.md)

## 修复内容

| 问题 | 修复方式 |
|---|---|
| HDMI 2160p50/60 花屏 | 修正专用 DTB 的 VPU 时钟档位，恢复 666.7MHz；没有通过降低分辨率规避 |
| 启动显示交接花屏 | framebuffer 预留地址与实际 U-Boot 配置对齐：`0x7f800000`、8MiB |
| SDIO 接口速率受限 | 专用 DTB 开启 SDR104 高速模式，使用对应控制器频率配置 |
| RTL8822CS Wi-Fi 吞吐慢 | 源码构建适配 NO 内核的厂商驱动，启用 NAPI/GRO，调整省电参数；实测约 **97.05 → 578.76 Mbps**，不同网络环境速度会变化 |
| 部分 DV P7 FEL 影片 seek 花屏、色块、绿线 | 修复增强层参考帧预解码与错误标记，在显示前成对跳过无效 BL/EL，保留有效旧帧配对 |
| 从保存进度续播出现色块 | Kodi 缓存、补送增强层 VPS/SPS/PPS，冷起播有界暂存并按原顺序回放数据与 PTS |

完整 DV/FEL 解码与合成保持启用，HDR 使用原有路径。CEC 沿用官方逻辑和默认配置。

专用 DTB 已作为镜像默认 `dtb.img`，内置已验证的 `dovi.ko`。内核、媒体模块、Wi-Fi 驱动和 Kodi 从对应源码构建；`dovi.ko` 使用已验证的 Amlogic 二进制模块，并非本项目修改或重新编译。

首个 Actions 源码镜像已由目标盒子实机确认：正常启动，HDMI、Wi-Fi、DV seek／绿线修复有效。

## 首次刷写

1. 在 Releases 下载 `*-S905X2-U212-2G-RTL8822CS.img.gz`。
2. 使用支持 gzip 镜像的刷写工具写入 U 盘或 SD 卡。
3. 按盒子已有的外部 CoreELEC 启动方式启动，无需另选 DTB 或复制 `dovi.ko`。
4. 完成 CoreELEC 初始化，连接合适的 Wi-Fi，配置自己的 SMB、音频和媒体库。

镜像不包含私人 Wi-Fi 密码、SMB 账号、媒体路径或 Kodi 数据库。对还未配置外部启动的盒子，仍需按其原有启动方式操作；本镜像不会代替盒子固件配置外部启动。

## 升级与自动更新

- **`.img.gz` 是刷机镜像，`.tar` 是升级包。**
- 手动升级：将本项目 `.tar` 复制到 `/storage/.update/`（或 SMB 的 `Update` 共享），然后重启。
- 本分支升级保留 `/storage` 中的设置、插件和媒体库，并继续使用修复后的专用 DTB。
- 目标盒子上官方 **CoreELEC 22 Amlogic-no / aarch64** 可以通过本项目 `.tar` 迁移；升级脚本会选择专用 DTB。不要用于 Amlogic-ng / 4.9 或不匹配的硬件。
- 首版尚未包含更新源，需要手动安装带自动更新功能的新 `.tar` 一次，之后无需重复配置更新地址。

新镜像的 **CoreELEC 设置 → 更新 → 检查更新** 读取本仓库最新正式 Release。设置为“自动”时，在未播放视频的检查周期中后台下载，校验文件大小和 SHA256 后暂存；可接受提示重启，或在下次正常重启时安装。不会在后台强制重启。设置为“手动”时，可检查、选择和确认下载。

更新源为 `https://github.com/Jioyzen/CoreELEC/releases/latest/download/update.json`。更新源不可用、下载不完整或校验失败时，不安装，也不自动回退到官方更新源，稍后可重试。自动检查不会将相同或更旧的构建当作新版本。

如果以前安装过运行时实验补丁，升级会保留这些文件：应清理旧 Kodi `LD_PRELOAD` 配置、无线驱动替换服务及不适用的 `/flash/dtb.xml` 覆盖项，避免覆盖本镜像原生修复。私人配置先备份。干净刷写的新镜像不需要这些步骤。

## 自动构建与发布

每周日北京时间 **03:00**，GitHub Actions 拉取官方 `coreelec-22` 并合入 `s905x2-no-fixes`，运行测试、编译和产物检查；源码无变化时跳过。通过后自动发布正式 Release，并在所有文件上传完成后更新 Latest，供盒子获取新版。

合并冲突、补丁失效、测试或编译失败时不发布，上一版继续可下载。每次发布包含镜像、升级包、`SHA256SUMS`、`build-manifest.json`、`update.json` 和发布说明。自动检查通过不等于每周都经过人工实机回归。

当前使用本机自托管 runner，保留工具链和编译缓存：**GitHub 云端定时派发任务，本机领取、构建并上传**。构建机需开机、联网、不休眠且 runner 服务正常，无需浏览器保持登录。fork 本仓库不会获得本项目的 runner，需要自行配置标签 `coreelec-s905x2`。

## 从源码构建

在安装了 CoreELEC 构建依赖的 Ubuntu 24.04 x86_64 环境中，以普通用户执行：

```sh
git clone -b s905x2-no-fixes https://github.com/Jioyzen/CoreELEC.git
cd CoreELEC
./tools/s905x2/build.sh
```

使用 `PROJECT=Amlogic-ce DEVICE=Amlogic-no ARCH=aarch64 S905X2_BOARD=yes` 调用官方构建流程。产物在 `target/s905x2-release/`。源码位置、构建并发、缓存设置及修复细节见 [S905X2.md](S905X2.md)。

## 项目来源与许可

本项目 fork 自 [CoreELEC](https://github.com/CoreELEC/CoreELEC)，CoreELEC 基于 LibreELEC。原项目及第三方组件的版权和许可证保持有效；本项目补丁按对应组件许可证发布。内置 Amlogic `dovi.ko` 保留其原有 AML 许可信息，文件校验值记录在板型 manifest 中。
