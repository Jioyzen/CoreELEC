#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
exec "$(dirname "${0}")/../media/build.sh" "${@}"
