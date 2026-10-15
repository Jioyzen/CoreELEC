#!/bin/sh
# Run once per Kodi session; wizard.py owns the durable first-start decision.
set -eu
state=/storage/.cache/jioyzen-media
mkdir -p "$state"
[ ! -e "$state/wifi-setup.json" ] || exit 0
rm -f "$state/wifi-started"
for attempt in $(seq 1 24); do
  /usr/bin/kodi-send --action="RunScript(/usr/lib/jioyzen-media/wifi/wizard.py)" >/dev/null 2>&1 || true
  sleep 5
  [ ! -e "$state/wifi-started" ] || exit 0
done
exit 1
