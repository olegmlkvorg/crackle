#!/usr/bin/env bash
# Watch all three printers over Moonraker and emit ONE line per state change.
# Emits on: finished, error/cancelled, paused, and started. Silent while a job just progresses —
# so it can run all day without becoming noise.
#
# Usage: ./watch-printers.sh          (intended to be run under a Monitor task)
STATE_FILE="${TMPDIR:-/tmp}/printer-watch-state"
declare -A IPS=( [k2plus]=192.168.3.140 [k1c]=192.168.3.117 [f022]=192.168.3.138 )

while true; do
  for name in "${!IPS[@]}"; do
    ip="${IPS[$name]}"
    json=$(curl -s --max-time 6 "http://$ip:7125/printer/objects/query?print_stats&display_status&extruder&heater_bed" 2>/dev/null)
    [ -z "$json" ] && cur="unreachable|-|0" || cur=$(printf '%s' "$json" | python3 -c "
import json,sys
try:
    s=json.load(sys.stdin)['result']['status']
    ps=s.get('print_stats',{}); ds=s.get('display_status',{})
    ex=s.get('extruder',{}); hb=s.get('heater_bed',{})
    # WHY a print paused, not just THAT it did. A pause you cannot diagnose from the notification
    # is one you must walk over and inspect, and an unnoticed pause is a lost print because the bed
    # cools and the part releases.
    # NOTE the signature that matters is the TARGET, not the actual temperature. On 2026-07-25 I
    # read \"nozzle 213, target 240\" as a runout; it was the hotend REHEATING after the pause, which
    # is normal for any pause at all. A real runout DROPS the target. Actual-below-target says only
    # that it is warming up.
    why=''
    if ps.get('state')=='paused':
        t=ex.get('target') or 0; c=ex.get('temperature') or 0
        msg=(ps.get('message') or '').strip()
        if msg: why=f' [{msg[:40]}]'
        elif t <= 5: why=' [target DROPPED to 0 — filament runout or a cancel in progress]'
        elif c < t-15: why=f' [reheating: nozzle {c:.0f} climbing to {t:.0f} — normal after any pause]'
        elif (hb.get('temperature') or 0) < 30: why=' [bed cold — part may have released already]'
        else: why=' [manual pause or AI detection]'
    print(f\"{ps.get('state','?')}{why}|{(ps.get('filename') or '-')[:46]}|{round((ds.get('progress') or 0)*100)}\")
except Exception: print('parse-error|-|0')" 2>/dev/null)

    state="${cur%%|*}"; rest="${cur#*|}"; file="${rest%%|*}"; pct="${rest##*|}"
    prev=$(grep "^$name=" "$STATE_FILE" 2>/dev/null | cut -d= -f2-)
    prev_state="${prev%%|*}"

    if [ "$state" != "$prev_state" ] && [ -n "$prev_state" ]; then
      case "$state" in
        complete)  echo "✅ $name FINISHED: $file" ;;
        error)     echo "🛑 $name PRINT ERROR: $file (was $pct%)" ;;
        cancelled) echo "⚠️  $name cancelled: $file" ;;
        paused*)   echo "⏸  $name PAUSED at $pct%: $file  — $(echo "$state" | sed 's/^paused *//')" ;;
        printing)  echo "▶️  $name started: $file" ;;
        unreachable) echo "❓ $name unreachable (printer off or off-network)" ;;
      esac
    fi
    # rewrite state file
    tmp="${STATE_FILE}.tmp"; grep -v "^$name=" "$STATE_FILE" 2>/dev/null > "$tmp"
    echo "$name=$state|$file|$pct" >> "$tmp"; mv "$tmp" "$STATE_FILE"
  done
  sleep 90
done
