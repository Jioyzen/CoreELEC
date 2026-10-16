#!/bin/sh
# First installation only. The wizard claims the attempt before checking the
# network, including skip/error paths; future boots never start it again.
set -eu
state=/storage/.cache/jioyzen-media
mkdir -p "$state"
[ ! -e "$state/wifi-setup.json" ] || exit 0
rm -f "$state/wifi-started"
for attempt in $(seq 1 120); do
  /usr/bin/kodi-send --action="RunScript(/usr/lib/jioyzen-media/wifi/wizard.py)" >/dev/null 2>&1 || true
  # EventServer becomes available during Kodi startup. Retry promptly rather
  # than adding a five-second step after the desktop has already appeared.
  for tick in 1 2 3 4 5; do
    [ ! -e "$state/wifi-started" ] || exit 0
    sleep .2
  done
done
exit 1
