#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-only
set -euo pipefail
cd "$(dirname "${0}")/../.."
. tools/jiefu/env.sh
mkdir -p "${BUILD_DIR}"
exec 9>"${BUILD_DIR}/.jiefu-build.lock"
flock 9
./tools/jiefu/test.sh
python3 tools/media/assemble.py --output "${JIOYZEN_MEDIA_PAYLOAD_DIR}" \
  --cache "${BUILD_DIR}/media-downloads"
python3 tools/media/verify_offline.py --bundle "${JIOYZEN_MEDIA_PAYLOAD_DIR}"
make image
python3 tools/jiefu/collect.py
