#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
# The historical entry point must not accidentally build the K profile here.
set -euo pipefail
exec "$(dirname "${0}")/../jiefu/build.sh" "${@}"
