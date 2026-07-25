#!/usr/bin/env python3
"""Audit: zero non-extruding moves between the first and last extrusion."""
import re, sys
bad = 0
for f in sys.argv[1:]:
    lines = [l.rstrip() for l in open(f)]
    ext = [i for i, l in enumerate(lines) if re.match(r'G1 .*E[\d.]', l)]
    if not ext:
        print(f"  {f}: no extrusion at all"); bad += 1; continue
    inside = [i for i, l in enumerate(lines) if l.startswith('G0 ') and ext[0] < i < ext[-1]]
    tag = "OK" if not inside else f"FAIL — {len(inside)} travels inside the object"
    print(f"  {f.split('/')[-1][:40]:<42} {tag}")
    bad += bool(inside)
sys.exit(1 if bad else 0)
