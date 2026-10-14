#!/bin/sh
set -eu
# EventServer is local Kodi IPC; a network-facing JSON-RPC server is not needed.
for attempt in $(seq 1 36); do
  /usr/bin/kodi-send --action="RunScript(/usr/lib/jioyzen-media/activate.py)" >/dev/null 2>&1 || true
  if /usr/bin/python3 - <<'PY'
import json,pathlib,sys
try:
 summary=json.loads(pathlib.Path('/usr/share/jioyzen-media/profile.json').read_text())
 report=json.loads(pathlib.Path('/storage/.cache/jioyzen-media/activation.json').read_text())
 sys.exit(0 if report.get('status')=='complete' and report.get('profile_id')==summary['profile_id'] else 1)
except (OSError,ValueError):sys.exit(1)
PY
  then exit 0; fi
  sleep 5
done
exit 1
