#!/usr/bin/env python3
"""Which gcode line is the printer executing RIGHT NOW.

Moonraker exposes virtual_sdcard.file_position — the byte offset into the running file. Map that
onto the local copy and you get the exact statement, plus the surrounding context.
Usage: python3 where.py [--ip 192.168.3.140] [--ctx 3]
"""
import json, sys, urllib.request, urllib.parse, argparse, os
ap = argparse.ArgumentParser(); ap.add_argument("--ip", default="192.168.3.140")
ap.add_argument("--ctx", type=int, default=3); a = ap.parse_args()
q = json.load(urllib.request.urlopen(
    f"http://{a.ip}:7125/printer/objects/query?virtual_sdcard&print_stats&gcode_move", timeout=8))["result"]["status"]
vs, ps, gm = q.get("virtual_sdcard", {}), q.get("print_stats", {}), q.get("gcode_move", {})
name = os.path.basename(ps.get("filename") or "")
pos, size = vs.get("file_position", 0), vs.get("file_size", 0)
print(f"{name}  [{ps.get('state')}]  byte {pos:,}/{size:,}  ({(pos/size*100 if size else 0):.1f}%)")
p = gm.get("gcode_position") or [0,0,0,0]
print(f"head X{p[0]:.1f} Y{p[1]:.1f} Z{p[2]:.2f}   speed factor {gm.get('speed_factor',1)*100:.0f}%")
# Fetch the file FROM THE PRINTER, never the local copy: local files get regenerated and the byte
# offset would then map onto the wrong line — a silently wrong answer, which is the worst kind.
try:
    data = urllib.request.urlopen(f"http://{a.ip}:7125/server/files/gcodes/{urllib.parse.quote(name)}", timeout=20).read()
except Exception as e:
    print(f"(could not fetch the running file from the printer: {e})"); sys.exit(0)
if size and len(data) != size:
    print(f"(warning: fetched {len(data):,} bytes but printer reports {size:,} — mapping may be off)")
line_no = data[:pos].count(b"\n") + 1
lines = data.decode("utf-8", "replace").splitlines()
lo, hi = max(0, line_no - 1 - a.ctx), min(len(lines), line_no + a.ctx)
print(f"\nline {line_no} of {len(lines)}:")
for i in range(lo, hi):
    print(("  ->" if i == line_no - 1 else "    ") + f" {i+1:>6}  {lines[i]}")
# nearest preceding structural comment tells you WHERE in the design you are
for i in range(line_no - 1, -1, -1):
    if lines[i].startswith("; ") and any(k in lines[i] for k in ("layer", "band", "base")):
        print(f"\nsection: {lines[i][2:]}"); break
