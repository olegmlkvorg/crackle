#!/usr/bin/env bash
# Build the weld-fraction ladder at a MEASURED flow. One argument: max flow in mm3/s.
#
# SIDE EFFECT, READ THIS FIRST: this script REWRITES the FLOW constant inside machine.py.
# machine.py is the single source of truth every generator reads, so running this changes
# the flow used by every other tool in the repo until you change it back. That is deliberate
# (the ladder must run at YOUR measured flow) but it is not obvious, and it will silently
# alter unrelated prints. Commit machine.py first, or note its current FLOW value.
#
#   ./make-ladder.sh 52
#
# Five rungs, identical in every respect except how many crossings are left unwelded. Laid out
# across the plate so all five print in ONE session at one bed temperature — a drifting bed
# already spoiled one coupon comparison today.
set -e
FLOW="${1:?usage: ./make-ladder.sh <measured max flow mm3/s>}"
WORK=$(python3 -c "print(round($FLOW*0.9,1))")   # 90% of measured, not at the edge
python3 - "$WORK" <<'PY'
import sys, re
w=sys.argv[1]
s=open('machine.py').read()
s=re.sub(r'^FLOW = [\d.]+', f'FLOW = {w}', s, count=1, flags=re.M)
open('machine.py','w').write(s)
print(f"  machine.FLOW -> {w} (90% of measured {sys.argv[1]})")
PY
rm -f out/vladder_*.gcode
i=0
for W in 1 0.75 0.5 0.25 0; do
  O=$((20 + i*65))
  python3 nucleon.py --no-home --vase --N 6 --weld "$W" --lift 0.5 --lift-win 2 \
      --layer_h 1.2 --strand_w 2.0 --z-step 1.57 --layers 6 --origin "$O" >/dev/null
  cp "out/nucleon_nohome_vase_N6_weld${W}_T210.gcode" "out/vladder_${i}_weld${W}.gcode"
  i=$((i+1))
done
python3 notravel.py out/vladder_*.gcode
python3 validate.py out/vladder_*.gcode 2>&1 | grep -cE "✅ passes" | xargs -I{} echo "  {}/5 validate clean"
echo "  push with: for f in out/vladder_*.gcode; do python3 push.py \$f --force; done"
