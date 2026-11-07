#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-only
set -euo pipefail
cd "$(dirname "${0}")/../.."
python3 -m unittest discover -s tools/jiefu -p 'test_*.py'
python3 -m unittest discover -s tools/media/tests -p 'test_*.py'
bash -n tools/jiefu/{build.sh,env.sh,test.sh} \
  projects/Amlogic-ce/packages/jiefu-board/package.mk \
  projects/Amlogic-ce/packages/u-boot/package.mk \
  projects/Amlogic-ce/packages/mediacenter/CoreELEC-settings/package.mk \
  projects/Amlogic-ce/packages/linux-drivers/amlogic/opentee_linuxdriver/package.mk \
  projects/Amlogic-ce/packages/linux-firmware/amlogic/rtkbt-firmware-aml/package.mk
sh -n projects/Amlogic-ce/devices/Amlogic-no/bootloader/update.sh \
  packages/sysutils/busybox/scripts/init
