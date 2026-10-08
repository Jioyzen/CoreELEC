# SPDX-License-Identifier: GPL-2.0-or-later
PKG_NAME="rtl88x2cs-s905x2"
PKG_VERSION="f4263fc6ecd11465bf60ce142aa76e2e85e2cbf3"
PKG_SHA256=""
PKG_ARCH="aarch64"
PKG_LICENSE="GPL"
PKG_SITE="https://github.com/jethome-ru/rtl88x2cs"
PKG_URL="https://github.com/jethome-ru/rtl88x2cs/archive/${PKG_VERSION}.tar.gz"
PKG_DEPENDS_TARGET="toolchain linux"
PKG_NEED_UNPACK="${LINUX_DEPENDS}"
PKG_LONGDESC="RTL8822CS SDIO vendor driver with CoreELEC 5.15 cfg80211 compatibility"
PKG_IS_KERNEL_PKG="yes"
PKG_TOOLCHAIN="manual"

make_target() {
  kernel_make -C ${PKG_BUILD} \
    M=${PKG_BUILD} KSRC=$(kernel_path) \
    USER_ccflags-y=-DRTW_CE_CFG80211_BACKPORT \
    CONFIG_RTW_NAPI=y CONFIG_RTW_GRO=y modules
}

makeinstall_target() {
  mkdir -p ${INSTALL}/$(get_full_module_dir)/${PKG_NAME}
    cp ${PKG_BUILD}/88x2cs.ko ${INSTALL}/$(get_full_module_dir)/${PKG_NAME}/
}
