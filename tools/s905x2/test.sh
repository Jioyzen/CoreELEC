#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
# This branch validates the non-DV Jiefu profile.
set -euo pipefail
exec "$(dirname "${0}")/../jiefu/test.sh" "${@}"
