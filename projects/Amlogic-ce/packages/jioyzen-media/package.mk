# SPDX-License-Identifier: GPL-2.0-or-later
PKG_NAME="jioyzen-media"
PKG_VERSION="1.0"
PKG_ARCH="aarch64"
PKG_LICENSE="mixed"
PKG_DEPENDS_TARGET="toolchain Python3 kodi dbussy"
PKG_TOOLCHAIN="manual"
PKG_NEED_UNPACK="${JIOYZEN_MEDIA_PAYLOAD_DIR}/profile.json ${ROOT}/tools/media"
PKG_LONGDESC="Locked offline media software and first-boot provisioning"

make_target() { :; }
makeinstall_target() {
  local payload="${JIOYZEN_MEDIA_PAYLOAD_DIR:?Build the locked media payload first}"
  mkdir -p "${INSTALL}/usr/share/jioyzen-media" "${INSTALL}/usr/lib/jioyzen-media" \
    "${INSTALL}/usr/lib/systemd/system/kodi.service.d" "${INSTALL}/usr/lib/systemd/system/tz-data.service.d"
  cp "${payload}/payload.tar.gz" "${payload}/profile.json" "${INSTALL}/usr/share/jioyzen-media/"
  cp "${ROOT}/tools/media/deploy.py" "${ROOT}/tools/media/safe_archive.py" "${ROOT}/tools/media/activate.py" "${ROOT}/tools/media/activate.sh" "${INSTALL}/usr/lib/jioyzen-media/"
  mkdir -p "${INSTALL}/usr/lib/jioyzen-media/wifi"
  cp "${ROOT}/tools/media/wifi/"*.py "${ROOT}/tools/media/wifi/start.sh" "${INSTALL}/usr/lib/jioyzen-media/wifi/"
  cp -r "${ROOT}/tools/media/wifi/resources" "${INSTALL}/usr/lib/jioyzen-media/wifi/"
  cp "${PKG_DIR}/system.d/"*.service "${INSTALL}/usr/lib/systemd/system/"
  cp "${PKG_DIR}/system.d/tz-data.service.d/20-media-timezone.conf" "${INSTALL}/usr/lib/systemd/system/tz-data.service.d/"
  cp "${PKG_DIR}/system.d/20-media-provisioning.conf" "${INSTALL}/usr/lib/systemd/system/kodi.service.d/"
}
post_install() {
  python3 "${ROOT}/tools/media/register.py" --bundle "${JIOYZEN_MEDIA_PAYLOAD_DIR}" --system "${INSTALL}"
  enable_service jioyzen-media-seed.service
  enable_service jioyzen-media-activate.service
  enable_service jioyzen-media-wifi.service
}
