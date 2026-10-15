# 完整播放器离线配置

- 只包含软件、依赖、服务主程序和公开默认配置，不导出 userdata、账号、媒体库、缓存、蓝牙配对、网络配置或 SSH 主机密钥。
- 管理的10个插件来自固定的 kodi-addons Release，其他插件和独立主程序来自已实测盒子的只读软件快照，校验 SHA256 后组合成部署包。
- Kodi 原生设置和遥控配置采用白名单；不复制硬件 EDID、固定显示模式或音频设备名。
- 插件更新默认通知，由用户决定，避免同 ID 官方语言包自动覆盖维护版；Jioyzen 仓库保留安装和更新入口。
- 服务程序预装，Alist / OpenList / CloudDrive2 默认保持当前的“未启用自启动”状态；不复制挂载、登录及管理密码。OpenList 新配置使用 5245 端口，避免与 Alist 的 5244 冲突。
- JellyCon（Jellyfin 客户端）预装但默认禁用，避免未配置服务器时开机弹出局域网扫描；用户可按需启用。
- 跳过原版多步骤初始化。首次进入桌面后，独立 Wi-Fi 向导列出附近网络并输入密码连接；已有可用有线或 Wi-Fi 连接、无无线模块时自动跳过。连接成功后立即刷新天气。
- 红外预置通用 ff00 和本机遥控 DD22 两套码表，由 CoreELEC 原生 remote-config 加载；不依赖额外的 CEBOX 服务。
- 第一次离线部署在 Kodi 启动前完成；原生源码修复替代诊断时的临时绑定挂载，不携带旧 Kodi 二进制替换器。
- 仅为 S905X2 U212 / 2GB / RTL8822CS 目标构建。刷写 USB / SD 不写 eMMC bootloader，不自动执行 ceemmc。

## 构建和发布

独立开发分支 `s905x2-media-edition`；普通版保留在 `s905x2-no-fixes`，不合并完整媒体内容。
统一工作流 `S905X2 ordinary and complete images` 固定两个分支提交后依次构建，两种
镜像的 `.img.gz` 和 `.tar` 放入同一个正式 Release。文件名含 `-MEDIA-` 的为完整版。
普通版使用 Release 内的 `update.json`；完整版使用 `media-update.json`，发布成功后
才将它复制到旧镜像兼容的 `media-channel/update.json`。镜像内标记决定更新通道，
基础版和媒体版互相拒绝对方的升级包。修改离线内容需先发布固定版本资产并更新 `lock.json`。

```sh
./tools/media/build.sh
```

需要 Linux x86_64 CoreELEC 编译环境；默认复用本机工具链缓存，镜像产物保存在
当前源码工作目录的 `target/s905x2-media-release/`。构建自动验证依赖版本、软件散列、
DTB、DV、遥控原生修复和更新通道。系统分区为 1GB，首次安装使用 `.img.gz` 刷写
至少 4GB 的 USB / SD；同媒体版后续更新使用 `.tar`。不把完整媒体升级包安装到
系统分区较小的基础版；跨版首次安装应刷写新介质。

离线首次部署可用 `deploy.py --bundle <部署包目录> --storage <隔离测试目录>` 验证，
它不会联网，也不会访问块设备。Kodi 的 optional system addon 清单使预置插件首次启动
即可启用，后续部署保留已有插件启用状态、较新版本和用户配置。

2026-10-15 已实测首版 USB 首启扩容、离线部署和进入桌面，首轮部署约3分50秒。
后续构建仍独立记录离线验证与冷启动验证状态；实际 `.tar` 升级尚未验证。
天气需要网络连接，首次 Wi-Fi 向导帮助配置用户自己的网络；镜像不包含 Wi-Fi 账号。
每周日北京时间 03:00 自动同步、构建并发布，手动运行也默认勾选 `sync_upstream` 与
`publish`；取消发布则只保存测试产物。两个分支的合并及预检均成功后才原子推送；
合并冲突或预检失败即停止，不推送、不发布；构建或镜像校验失败时也不发布。

## Wi-Fi 向导

`jioyzen-media-wifi.service` 是 `Type=oneshot` 一次性启动服务，在 Kodi 就绪后运行
`/usr/lib/jioyzen-media/wifi/wizard.py`；启动器退出后服务回到 inactive，不常驻、不随
Kodi 重启而重启、不在后台监听断网。systemd 根据首次触发标记跳过后续启动。
界面使用独立圆角深色对话框，网络扫描、D-Bus 认证和 DHCP 等待在后台完成；
不依赖 Kodi 的 HTTP 服务、不调用外网来判断连接。连接成功以 ConnMan `ready/online`
为准；附近网络包含信号和加密提示。密码通过标准输入传入独立进程，再由 ConnMan
agent 传递给系统网络服务，不作为命令行参数、不写入向导日志和完成标记。

已联网时不抢占界面；启动时等待无线设备与自动连接稳定，无无线模块时不弹窗。
可“稍后设置”，此后通过 CoreELEC 网络设置连接；首次触发即记录于
`/storage/.cache/jioyzen-media/wifi-setup.json`，包括异常、中断、无网卡、已有网络等
路径，升级、系统重启和 Kodi 重启均不再自动弹出，后续断网也不触发。
调试预览可运行 `RunScript(/usr/lib/jioyzen-media/wifi/wizard.py,--preview)`。
不在出厂配置中携带此标记或任何网络凭据。
