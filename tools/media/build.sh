#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
cd "$(dirname "$0")/../.."
if [ -f "${XDG_CONFIG_HOME:-$HOME/.config}/coreelec-s905x2/build.env" ]; then
  source "${XDG_CONFIG_HOME:-$HOME/.config}/coreelec-s905x2/build.env"
fi
export PROJECT=Amlogic-ce DEVICE=Amlogic-no ARCH=aarch64 S905X2_BOARD=yes
export JIOYZEN_MEDIA_EDITION=yes
export THREADCOUNT=${THREADCOUNT:-2} CONCURRENCY_MAKE_LEVEL=${CONCURRENCY_MAKE_LEVEL:-3} CONCURRENCY_LOAD=${CONCURRENCY_LOAD:-4}
export BUILDER_NAME=Jioyzen BUILDER_VERSION=s905x2-media
export SKIP_CHECK_DEPENDENCIES=yes
export JIOYZEN_MEDIA_PAYLOAD_DIR=${JIOYZEN_MEDIA_PAYLOAD_DIR:-${BUILD_DIR:-$PWD}/media-payload}
mkdir -p "${BUILD_DIR:-$PWD}"
exec 9>"${BUILD_DIR:-$PWD}/.s905x2-build.lock"
flock 9
python3 tools/media/assemble.py --output "$JIOYZEN_MEDIA_PAYLOAD_DIR" --cache "${BUILD_DIR:-$PWD}/media-downloads"
python3 tools/media/verify_offline.py --bundle "$JIOYZEN_MEDIA_PAYLOAD_DIR"
python3 -m unittest discover -s tools/media/tests -p 'test_*.py'
./tools/s905x2/test.sh
make image
python3 tools/s905x2/collect.py
python3 tools/media/verify_image.py --release "${TARGET_DIR:-$PWD/target}/s905x2-release" --toolchain "${BUILD_DIR:-$PWD}/build.CoreELEC-Amlogic-no.aarch64-22/toolchain"
python3 tools/media/collect.py
