# SPDX-License-Identifier: GPL-2.0-only
PKG_NAME="jiefu-board"
PKG_VERSION="1.0"
PKG_ARCH="aarch64"
PKG_LICENSE="GPL-2.0-only"
PKG_SITE="https://github.com/Jioyzen/CoreELEC"
PKG_DEPENDS_TARGET="toolchain evrepeat"
PKG_LONGDESC="Jiefu SEI Jeff2021 S905X2 board identity and Wi-Fi defaults (no DV)"
PKG_TOOLCHAIN="manual"

make_target() {
  :
}

makeinstall_target() {
  mkdir -p ${INSTALL}/usr/lib/modprobe.d ${INSTALL}/usr/share/s905x2 \
    ${INSTALL}/usr/share/jiefu
    cp ${PKG_DIR}/sources/jiefu-wifi.conf ${INSTALL}/usr/lib/modprobe.d/
    cp ${PKG_DIR}/sources/manifest.json ${INSTALL}/usr/share/s905x2/manifest.json
    cp ${PKG_DIR}/sources/manifest.json ${INSTALL}/usr/share/jiefu/manifest.json

  mkdir -p ${INSTALL}/usr/lib/coreelec ${INSTALL}/usr/lib/udev/rules.d \
    ${INSTALL}/usr/lib/systemd/system/kodi.service.d
    cp ${PKG_DIR}/sources/35-remote-repeat-policy.conf \
      ${INSTALL}/usr/lib/systemd/system/kodi.service.d/
    cp ${PKG_DIR}/sources/99-remote-repeat-policy.rules ${INSTALL}/usr/lib/udev/rules.d/
    install -m 0755 ${PKG_DIR}/sources/evrepeat-policy.sh ${INSTALL}/usr/lib/coreelec/
}
