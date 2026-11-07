# Jiefu / SEI Jeff2021：CoreELEC 22 NO

本分支 `jiefu-s905x2-no` 专门维护已修复的 **S905X2 / 2GB / RTL8822CS**
盒子，基于 `s905x2-media-edition` 的提交
`483b949b0bde493cc50e88e46460d93b4e338d40`，保留离线媒体软件、中文界面及网络向导。
另一台具备 Dolby Vision 能力的 S905X2-K 继续使用原有分支。

## 分支和维护方式

使用同一仓库的长期板级分支，便于追踪共同历史、审查差异和挑选上游修复。
当前仅有少量板级差异，无需另建仓库复制整套构建系统。

- `coreelec-22`：上游来源。
- `s905x2-no-fixes` / `s905x2-media-edition`：原有 K 盒子及其发布流程。
- `jiefu-s905x2-no`：本机型的源码、手动构建和独立产物。

维护时先在本分支挑选适用的公共修复，或在临时集成分支合并上游并审查冲突，
再执行本分支测试。涉及时钟绑定、USB PHY、显示预留内存、驱动及固件的更新，
需要重新核对 DTS 和实机启动日志。避免整批导入另一机型的板级参数和发布脚本。
固定源码版本和校验值应与更新一起提交。

## 已转入源码的修复

专用设备树为 `g12a_s905x2_u212_2g_jeff2021.dtb`，由
`common_drivers/patches/1006-dts-add-jiefu-jeff2021.patch` 构建。

| 修复点 | 原因及实现 |
| --- | --- |
| ramoops 地址 | 原 `0x07400000` 落在原厂 U-Boot 扩大的 secmon 区域内，触发外部总线异常；改为 `0x09400000`，大小 1MB。 |
| USB 启动崩溃 | 未使用的 `ff400000` DWC2 SLAVE 提前访问共享 PHY 的未初始化指针；禁用此节点，保留 `ff500000` DWC3 Host、U 盘和 USB 遥控。 |
| 以太网时钟 | `stmmaceth` 改用 `CLKID_ETH`，保留另外两个时钟；本次 DHCP 故障也涉及路由器 LAN 口，不能全归因于 DTB。 |
| Wi-Fi 枚举 | RTL8822CS 在 200MHz 初始化出现 CRC `-84`；将 `max-frequency-sdio` 限制为 167MHz，沿用已验证厂商驱动和 NAPI/GRO 配置。 |
| 显示交接 | 保持 VPU `clk_level=8`、framebuffer `0x7f800000/8MB` 及 `vout_mux`，与修复版保持一致。 |
| CEC | 恢复官方默认：`aocec` 启用，不设置 CEC 启动覆盖。此前关闭仅用于维修，不作为镜像策略。 |
| 身份标识 | 使用独立 `coreelec-dt-id`；保留 `amlogic-dt-id=g12a_s905x2_u212_2g_rtl8822cs`，使已有的 U-Boot 音频 DMA 停止逻辑继续生效。 |
| 启动配置 | 使用官方 `config.ini` 和启动脚本默认值；撤回此前额外的静默、强制接管及分辨率参数。滚动文字曾由维修时启用的 `progress` 引起，不能视为官方默认故障。 |
| 蓝牙固件 | 从已固定版本的 `kernel-firmware` 复制 `rtl_bt/rtl8822cs_fw.bin` 到厂商加载器请求的 `rtlbt/rtl8822cs_fw`，修复 HCI `0x2038` 超时和复位。 |
| NFS 规则 | 使用 `systemd-sysctl --prefix` 替代 BusyBox 不支持的 `sysctl --pattern`；`nfsrahead` 使用构建配置的 `/usr/lib` 路径并加存在性检查。 |

蓝牙固件来自 `linux-firmware-20261019`，SHA256 固定为
`42db5218c54b0638e1bafdbc7d0986172288e55a9e1c879080d41206bb87dfa2`。
构建时校验字节一致性，升级固件需重新验证并更新校验值。

设备树保留实机修复版已有的 `DD22` 唤醒及 LED 参数，避免迁移时改变运行行为；
**遥控关机唤醒和 LED 状态仍待单独验证**，不能据此宣称支持另一台 K 盒子的全部功能。

NO 使用 Linux 5.15，NG 使用 Linux 4.9；二者 DTB 的绑定和驱动接口不同，不能互换。
本分支只维护 CE22 NO，不应用旧 NG 的时钟编号映射或显示内存补丁。

## Dolby Vision

此盒子的 DV 授权条件不满足。之前显示的能力值 `6` 仅说明模块状态位，不能开启 DV。

jiefu 构建选择 `jiefu-board` 包，依赖中不包含安装模块的 `s905x2-board` 包。
SYSTEM、升级包及 FAT 启动分区均检查不存在 `dovi.ko`。
**官方 `dovi-loader` 和 `opentee_linuxdriver.service` 不修改**，按官方逻辑自动探测。
加载器可能检查 Android 分区；没有兼容模块时正常退出，不以假设存在模块为由删除官方流程。

TEE 是官方服务处理的可信执行环境/可信视频固件初始化部分；同一服务先执行
`tee-loader start`，再执行 `dovi-loader start`。不打包 DV 模块与禁用 TEE 是不同操作。
本分支保留整套官方服务行为，没有新增“保留 TEE”的替代实现。


## 构建

在本分支的仓库根目录，以普通用户执行，路径不可带空格。主机依赖沿用 CoreELEC。

```bash
./tools/jiefu/test.sh
./tools/jiefu/build.sh
```

第二条命令执行完整镜像编译，耗时较长。历史入口 `tools/media/build.sh` 和
`tools/s905x2/build.sh` 在此分支也转到 jiefu 构建。

构建配置由 `tools/jiefu/env.sh` 统一设置：

```text
PROJECT=Amlogic-ce DEVICE=Amlogic-no ARCH=aarch64
JIEFU_BOARD=yes S905X2_BOARD=no JIOYZEN_MEDIA_EDITION=yes
BUILD_SUFFIX=jiefu
```

默认构建目录为 `.work/jiefu/`，输出为 `target/jiefu/jiefu-release/`。
可在 `${XDG_CONFIG_HOME:-$HOME/.config}/coreelec-jiefu/build.env` 设置独立缓存路径及并发，
例如 `BUILD_DIR`、`TARGET_DIR`、`SOURCES_DIR`。配置中不要存放令牌或设备凭据。
构建目录、后缀、锁、媒体 payload 及更新源与 K 盒子分开。

单包构建示例：

```bash
. tools/jiefu/env.sh
./scripts/build_mt jiefu-board
```

`build.sh` 在编译前测试板级逻辑和媒体功能、校验离线软件部署；编译后从实际
`.img.gz` 解出 FAT 分区及 SYSTEM，核对设备树、官方启动默认配置、固件、官方 TEE/DV 加载服务、无 DV 模块、
源码提交和升级包内容，再运行镜像中嵌入的离线安装器验证。验证通过才生成发布目录。

## GitHub Actions、产物和升级

本分支保留已注册的工作流路径 `.github/workflows/s905x2-weekly.yml`，内容改为
**Jiefu S905X2 NO media image (manual)**，只接受此分支的手动触发。
继续使用仓库已有标签 `coreelec-s905x2` 的自托管 Linux X64 runner。

```bash
gh workflow run s905x2-weekly.yml --ref jiefu-s905x2-no
```

工作流没有定时同步或分支推送；通过后上传保留 14 天的构建 artifact。
手动设置 `publish=true` 时，在产物校验成功后发布独立 jiefu 预发布版本，
不会设为 Latest，也不更新稳定频道。
现有 K 分支中的每周工作流继续按原配置运行。两个流程使用同一 Actions 并发组，
避免在同一 runner 上同时进行大型编译；构建缓存目录仍独立。

产物使用简短名称，如 `CE22-Jiefu-20261107-103014.img.gz` / `.tar`，包含 `.img.gz`、`.tar`、`SHA256SUMS`、
`build-manifest.json`、`offline-image-validation.json` 和 `update.json`。
首次安装刷写 USB/SD 镜像；升级包只用于同一 jiefu NO 机型。
不修改官方 initramfs 升级判断和 `canupdate.sh`；同架构手工放置错误升级包仍可能被接受，
因此必须人工选对机型。自动更新客户端使用独立板型、版别和文件名检查来隔离频道。


更新客户端仅访问 `releases/download/jiefu-channel/update.json`，并校验板型、版本、
架构、版别、文件名、下载地址、大小和 SHA256。频道尚未发布或网络不可用时返回无更新。
本轮不会建立该频道。后续每个候选构建先做 USB 实机回归，再以清单中的唯一
`release_tag` 发布该目录的产物，并设为 **prerelease / 非 Latest**。
需要开放系统更新时，将已验证版本的 `update.json` 发布到独立的 `jiefu-channel`
预发布 Release；始终保持非 Latest，避免影响原机型的发布源。

升级保留用户已有的 `/flash/config.ini`。从手工维修版迁移时，应先备份再删除临时
调试参数，使用官方默认配置；新刷写镜像直接带官方文件。

验证 runner 连接而不编译完整镜像，可执行：

```bash
gh workflow run s905x2-weekly.yml --ref jiefu-s905x2-no -f validation_only=true
```

本机 runner 位于 `/home/zeng/actions-runner`，注册名称 `s905x2-persistent-builder`，
标签含 `coreelec-s905x2,jiefu`，由 systemd 以普通用户 `zeng` 开机启动。
工作流检查主机依赖、实际板级测试及构建依赖计划。


## 固件边界和验证状态

镜像维护 CoreELEC USB/SD 系统。不会写入 Android 的 Logo 或开机动画分区；
引导及升级流程沿用官方实现，没有额外增加环境写入或固件注入策略。首次启用 USB 启动仍沿用
CoreELEC 标准的 `aml_autoscript` 多系统引导机制，可能保存必要的引导环境。
上电第一屏取决于盒子当前的原厂/已定制固件，CoreELEC 接管后播放自身动画。

个人 Wi-Fi、IP、MAC、密钥、Android 分区备份及现场日志不进入源码仓库。
原现场的 ConnMan 空代理配置通过该网络的 `proxy direct` 修复，属于用户网络状态，
没有将个人网络配置写入镜像。

2026-11-07 本次源码迁移验证：

- 使用固定版本 `common_drivers` 和 Linux 5.15 头文件编译专用 DTS，板级校验通过。
- 与本地实机最终 DTB 反编译后比较，恢复 CEC 默认后，仅 `model` 名称与 `aocec/status` 相比维修基线有预期差异；维修基线 SHA256 为
  `8d90fdfbc30112c13c14d7f357163c0ad129e6eee9d67d10a5067360a792963e`。
- 已执行真实安装钩子的隔离测试：板级包不含 DV、U-Boot 安装官方配置、TEE/DV 官方加载服务原样保留；验证自动更新拒绝其他板型和版别。
- 已执行媒体版测试和相关包元数据检查；新补丁验证可干净应用。
- **尚未编译完整新镜像，也未对本分支的新产物做实机回归。** 完整新编译产物仍待验证；本次对已有系统做恢复官方默认值的实机对照，结果记录在文末。

后续候选镜像至少检查冷启动、重启、无屏幕日志的动画交接、USB 遥控、Wi-Fi/有线 DHCP、
蓝牙扫描、视频播放及 TEE 状态，确认无 panic/Oops、存储 I/O 错误和新增服务失败。

## DTB 来源与“完全正常”的边界

现场 DTB 来自用户 CE22 NO 媒体镜像中的专用设备树（它是通用 S905X2 树的扩展），
通过 `fdtput` 修改后启动验证；没有把 Android 原厂 DTB 直接交给 NO 内核。
原厂 Android DTS、U-Boot 输出及内核绑定用于核对内存区间、显示缓冲和硬件资源。
源码分支将同样的修改固化为专用 DTS，使用符号时钟而非复制某份二进制的 phandle。

已确认启动、USB 存储/遥控、桌面和所测短时播放；不代表所有休眠唤醒、音频透传、
HDMI 模式和长时间负载均已测试。ramoops 冲突与本机 U-Boot 内存布局有关，
SDIO 频率与本机硬件稳定性有关，USB 则有明确共享 PHY 初始化崩溃堆栈。
这些优先通过本机 DTB 修正，不据此泛称官方代码“错误”。
蓝牙 HCI 超时和 NFS 规则/程序路径失败有单独日志及对照结果，不能由 DTB 单独解决，
因此保留相应的小范围固件映射和打包兼容修复。

全仓库停止普通适配版构建，仅维护 K 与 jiefu 各自的完整媒体构建；
普通分支可继续作为公共源码维护来源，但不再产出普通镜像。

## 恢复官方默认值的实机对照结果（2026-11-07）

本次没有重新编译内核。现有 SYSTEM 仅移除两个额外打包的 `dovi.ko` 副本，
保留原版 `dovi-loader`、TEE 服务和其他系统文件，通过官方升级流程安装。
实机 `aocec` 恢复启用、`config.ini` 恢复与仓库官方模板字节一致，
并删除维修用服务覆盖，撤回此前临时添加的全局 `cecconfig=cec0` 环境键。
既有 TV BOX 静态 Logo 和显示环境保持当前已验证状态，未恢复/重刷原厂整套 U-Boot。

- 普通启动后，用户确认已正常进入桌面；CEC 为 `0x7f`，Kodi 注册 AOCEC 设备。
- 官方 TEE 脚本自行判断本 SoC 不需要该 TEE 流程；DV 加载器输出 `dovi not supported`，
  服务成功，没有加载 DV 模块。通用加载器检查不存在的 `/dev/super` 会留下探测日志，
  这里没有为了消除这条信息而修改官方代码。
- framebuffer 约 1.5 秒开始接管，约 3 秒建立图形控制台，约 6.3 秒加载 bootsplash；
  Kodi active、NRestarts=0，失败服务 0，无新的 panic/Oops。
- 应用户要求为观察再临时关闭 CEC 并重启，其他启动参数仍为官方默认。
  用户确认“一切正常，没有滚动文字，正常进入桌面”。观察后已恢复默认设置文件；
  CEC 只在该次运行临时关闭，不进入构建参数。

实机恢复 CEC 的 DTB SHA256 为
`266c706231ed90902d29a703b335bfa9412b70a491497fe383b78a436e16e294`。
官方配置 SHA256 为
`c8795832fccf111d82a36f844dade1fc70c8f98afaccd6d59210ac36296e9e39`。
这些是现有镜像的实机对照，不替代新编译完整镜像的实机回归。

本机 runner 真实接收并完成了
[GitHub Actions 验证任务](https://github.com/Jioyzen/CoreELEC/actions/runs/42330293067)，
执行主机为 `zeng-ubuntu-ai02`，包含主机依赖检查、板级/媒体测试和构建依赖解析。
完整镜像编译尚未执行。默认分支与 K 媒体分支均已停止普通版构建。

## 固定源码构建并发布

```bash
gh workflow run s905x2-weekly.yml --ref jiefu-s905x2-no \
  -f validation_only=false -f publish=true
```

工作流固定使用触发时的分支提交，不合并上游。发布前再次校验 SHA256、板型、
源码提交、升级包与镜像的对应关系及离线部署报告；先上传到 draft，
全部上传完成后才转为公开 prerelease。正式稳定频道仍需新镜像实机验证后单独开放。
