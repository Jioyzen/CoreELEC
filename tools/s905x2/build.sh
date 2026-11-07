#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
media_build="$(dirname "${0}")/../media/build.sh"
if [ ! -x "${media_build}" ]; then
  echo "Ordinary builds are retired. Use s905x2-media-edition or jiefu-s905x2-no." >&2
  exit 1
fi
exec "${media_build}" "${@}"
