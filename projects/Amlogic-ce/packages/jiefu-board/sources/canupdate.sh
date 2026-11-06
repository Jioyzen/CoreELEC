#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only

# Upgrade archives are board-specific even though the CPU architecture matches.
if [ "$(tr -d '\000' < /proc/device-tree/coreelec-dt-id)" != \
     "g12a_s905x2_u212_2g_jeff2021" ]; then
  echo "This update is only for Jiefu / SEI Jeff2021; use a fresh USB image."
  exit 1
fi
case "$(uname -r)" in
  5.15.*) ;;
  *) echo "Jiefu requires the NO 5.15 kernel; NG DTBs are incompatible."; exit 1 ;;
esac
[ "${1}" = "Amlogic-no.aarch64" ] && [ "${2}" = "Amlogic-no.aarch64" ]
