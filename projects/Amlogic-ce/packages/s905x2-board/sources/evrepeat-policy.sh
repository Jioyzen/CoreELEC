#!/bin/sh
set -eu
# Hardware repeat configuration for evdev devices that support EV_REP.
# Kodi supplies the matching fallback policy for devices such as meson IR.
node=${1:-}
case "$node" in /dev/input/event[0-9]*) ;; *) exit 0 ;; esac
name=$(cat "/sys/class/input/${node##*/}/device/name")
name_lc=$(printf '%s' "$name" | tr '[:upper:]' '[:lower:]')
case "$name_lc" in *cec*|eventlircd) exit 0 ;; esac
[ -r /storage/.config/input-repeat.conf ] || exit 0
. /storage/.config/input-repeat.conf
case "$KODI_REMOTE_REPEAT_DELAY_MS:$KODI_REMOTE_REPEAT_PERIOD_MS" in *[!0-9:]*|:*) exit 0 ;; esac
exec /usr/bin/evrepeat -q -d "$KODI_REMOTE_REPEAT_DELAY_MS" -p "$KODI_REMOTE_REPEAT_PERIOD_MS" "$node"
