# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2018-present Team CoreELEC (https://coreelec.org)

PKG_NAME="rtkbt-firmware-aml"
PKG_VERSION="492de5f2c6afbe51cb0ed120373ccdc4b0f36982"
PKG_SHA256=""
PKG_LICENSE="GPL"
PKG_SITE="https://github.com/CoreELEC/rtkbt-firmware-aml"
PKG_URL="https://github.com/CoreELEC/rtkbt-firmware-aml/archive/${PKG_VERSION}.tar.gz"
PKG_DEPENDS_TARGET="toolchain rtk_hciattach"
if [ "${JIEFU_BOARD}" = "yes" ]; then
  PKG_DEPENDS_TARGET+=" kernel-firmware"
fi
PKG_LONGDESC="Realtek BT Linux firmware"
PKG_TOOLCHAIN="manual"

makeinstall_target() {
  FWDIR=${INSTALL}/$(get_full_firmware_dir)/rtlbt

  mkdir -p ${FWDIR}
    cp -a ${PKG_BUILD}/* ${FWDIR}

  if [ "${JIEFU_BOARD}" = "yes" ]; then
    # rtk_hciattach requests rtlbt/, whereas linux-firmware uses rtl_bt/.
    # The newer, verified firmware avoids repeated HCI 0x2038 timeouts.
    cp "$(get_install_dir kernel-firmware)/$(get_full_firmware_dir)/rtl_bt/rtl8822cs_fw.bin" \
      ${FWDIR}/rtl8822cs_fw
    echo "42db5218c54b0638e1bafdbc7d0986172288e55a9e1c879080d41206bb87dfa2  ${FWDIR}/rtl8822cs_fw" | \
      sha256sum -c -
  fi
}
