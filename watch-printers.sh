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
    json=$(curl -s --max-time 6 "http://$ip:7125/printer/objects/query?print_stats&display_status" 2>/dev/null)
    [ -z "$json" ] && cur="unreachable|-|0" || cur=$(printf '%s' "$json" | python3 -c "
import json,sys
try:
    s=json.load(sys.stdin)['result']['status']
    ps=s.get('print_stats',{}); ds=s.get('display_status',{})
    print(f\"{ps.get('state','?')}|{(ps.get('filename') or '-')[:46]}|{round((ds.get('progress') or 0)*100)}\")
except Exception: print('parse-error|-|0')" 2>/dev/null)

    state="${cur%%|*}"; rest="${cur#*|}"; file="${rest%%|*}"; pct="${rest##*|}"
    prev=$(grep "^$name=" "$STATE_FILE" 2>/dev/null | cut -d= -f2-)
    prev_state="${prev%%|*}"

    if [ "$state" != "$prev_state" ] && [ -n "$prev_state" ]; then
      case "$state" in
        complete)  echo "✅ $name FINISHED: $file" ;;
        error)     echo "🛑 $name PRINT ERROR: $file (was $pct%)" ;;
        cancelled) echo "⚠️  $name cancelled: $file" ;;
        paused)    echo "⏸  $name PAUSED at $pct%: $file  — could be AI spaghetti detection" ;;
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
