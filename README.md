# CoreELEC 22 NO · Jiefu 媒体版

本分支适配 **Jiefu / SEI Jeff2021 / S905X2 / 2GB / RTL8822CS**。
保留完整媒体软件与官方基础默认行为，只加入已有证据支持的板级及打包修复。
不预置 `dovi.ko`，保留官方 TEE 服务和 DV 自动探测加载入口；CEC 使用官方默认值。

维护方案、DTB 来源、修复原因、构建命令及验证边界见 **[JIEFU.md](JIEFU.md)**。

```bash
./tools/jiefu/test.sh
./tools/jiefu/build.sh
```

产物示例：`CE22-Jiefu-20261107-103014.img.gz`。本分支只构建完整媒体版。
仓库已停止普通适配版镜像构建；另一台支持 DV 的 S905X2-K 使用
[`s905x2-media-edition`](https://github.com/Jioyzen/CoreELEC/tree/s905x2-media-edition)。

基于 [CoreELEC](https://github.com/CoreELEC/CoreELEC) 与本仓库原有媒体版修改，
保留原项目许可证和各媒体软件许可证。
