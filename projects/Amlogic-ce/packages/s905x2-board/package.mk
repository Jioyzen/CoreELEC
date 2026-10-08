# SPDX-License-Identifier: GPL-2.0-or-later
PKG_NAME="s905x2-board"
PKG_VERSION="1.0"
PKG_ARCH="aarch64"
PKG_LICENSE="mixed"
PKG_SITE="https://github.com/Jioyzen/CoreELEC"
PKG_DEPENDS_TARGET="toolchain"
PKG_LONGDESC="Verified S905X2 u212-compatible board defaults and Dolby Vision module"
PKG_TOOLCHAIN="manual"

make_target() {
  :
}

makeinstall_target() {
  mkdir -p ${INSTALL}/usr/lib/coreelec ${INSTALL}/usr/share/bootloader ${INSTALL}/usr/lib/modprobe.d
    cp ${PKG_BUILD}/dovi.ko ${INSTALL}/usr/lib/coreelec/dovi.ko
    cp ${PKG_BUILD}/dovi.ko ${INSTALL}/usr/share/bootloader/dovi.ko
    cat > ${INSTALL}/usr/lib/modprobe.d/s905x2-wifi.conf <<'CONFIG'
blacklist rtw_8822cs
options 88x2cs rtw_power_mgnt=0 rtw_ips_mode=0 rtw_en_napi=1 rtw_en_gro=1
CONFIG
  mkdir -p ${INSTALL}/usr/share/s905x2
    cp ${PKG_DIR}/sources/manifest.json ${INSTALL}/usr/share/s905x2/manifest.json
}
