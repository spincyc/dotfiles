#!/bin/sh
# Pin the default audio sink to the display sink backed by a valid ELD.
#
# The HiFi__HDMI1/2/3 sink names track ALSA PCM indices, which rebind to
# physical connectors on hotplug, so a stored default sink can silently
# point at a dead pin while PulseAudio/PipeWire still report it healthy.
# The ELD monitor name is the only per-connector fact the driver exposes,
# so resolve the sink through it. Retried because the ELD is not valid
# immediately after a hotplug event.
set -u

sink=""
attempts=0
while [ "$attempts" -lt 12 ]; do
  names=$(
    for eld in /proc/asound/card*/eld*; do
      [ -f "$eld" ] || continue
      if grep -q 'eld_valid[[:space:]]*1$' "$eld"; then
        sed -n 's/^monitor_name[[:space:]]*//p' "$eld"
      fi
    done
  )
  if [ -n "$names" ]; then
    sink=$(pactl list sinks | awk -v names="$names" '
      /^Sink #/ { name = "" }
      /^\tName: / { name = $2 }
      /alsa\.name = / {
        count = split(names, valid, "\n")
        for (i = 1; i <= count; i++) {
          if (index($0, "\"" valid[i] "\"")) {
            print name
            exit
          }
        }
      }
    ')
    [ -n "$sink" ] && break
  fi
  attempts=$((attempts + 1))
  sleep 0.5
done

[ -n "$sink" ] || exit 1

# Set unconditionally: the persisted configured default can hold a stale name
# even when the effective default is already right.
pactl set-default-sink "$sink"
pactl list short sink-inputs | cut -f1 | while read -r input; do
  pactl move-sink-input "$input" "$sink"
done
