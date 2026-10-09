#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
cd "$(dirname "$0")/../.."
S905X2_TEST_TMP=$(mktemp -d)
trap 'python3 - "$S905X2_TEST_TMP" <<"PY"
import pathlib,shutil,sys
p=pathlib.Path(sys.argv[1]);assert p.name.startswith("tmp.");shutil.rmtree(p)
PY' EXIT
python3 - "$S905X2_TEST_TMP" <<'PY'
import sys,pathlib
p=pathlib.Path('projects/Amlogic-ce/packages/mediacenter/kodi/patches/1000-amlogic-dv-cold-resume-and-seek-headers.patch')
s=p.read_text().split('+++ b/xbmc/cores/VideoPlayer/DVDCodecs/Video/AMLDVStreamGuard.h\n',1)[1]
pathlib.Path(sys.argv[1],'AMLDVStreamGuard.h').write_text(''.join(x[1:]+'\n' for x in s.splitlines() if x.startswith('+')))
PY
c++ -std=c++17 -O1 -g -fsanitize=address,undefined \
  -I "$S905X2_TEST_TMP" -I tools/s905x2/tests/stubs \
  tools/s905x2/tests/test_dv_stream_guard.cpp -o "$S905X2_TEST_TMP/test" -pthread
"$S905X2_TEST_TMP/test"
python3 - <<'PY'
import hashlib,json,pathlib
p=pathlib.Path('projects/Amlogic-ce/packages/s905x2-board/sources')
m=json.loads((p/'manifest.json').read_text())
assert hashlib.sha256((p/'dovi.ko').read_bytes()).hexdigest()==m['dovi_sha256']
print('PASS: bundled dovi SHA256')
PY
python3 tools/s905x2/tests/test_updates.py
bash -n projects/Amlogic-ce/packages/linux-drivers/rtl88x2cs-s905x2/package.mk \
  projects/Amlogic-ce/packages/s905x2-board/package.mk
sh -n projects/Amlogic-ce/packages/linux-drivers/amlogic/opentee_linuxdriver/scripts/dovi-loader.sh
