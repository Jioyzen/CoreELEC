#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
cd "$(dirname "$0")/../.."
# Optional persistent runner cache and concurrency settings; contains no token.
if [ -f "${XDG_CONFIG_HOME:-$HOME/.config}/coreelec-s905x2/build.env" ]; then
  source "${XDG_CONFIG_HOME:-$HOME/.config}/coreelec-s905x2/build.env"
fi
export PROJECT=Amlogic-ce DEVICE=Amlogic-no ARCH=aarch64 S905X2_BOARD=yes
export THREADCOUNT=${THREADCOUNT:-2} CONCURRENCY_MAKE_LEVEL=${CONCURRENCY_MAKE_LEVEL:-3} CONCURRENCY_LOAD=${CONCURRENCY_LOAD:-4}
export BUILDER_NAME=Jioyzen BUILDER_VERSION=s905x2-fixes
export SKIP_CHECK_DEPENDENCIES=yes
mkdir -p "${BUILD_DIR:-$PWD}"
exec 9>"${BUILD_DIR:-$PWD}/.s905x2-build.lock"
flock 9
./tools/s905x2/test.sh
make image
python3 tools/s905x2/collect.py
