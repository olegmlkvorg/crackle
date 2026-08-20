# R4 flow-band: what actually violates it, 2026-08-20

Derived from a full `python3 gate_coverage.py --all` over the 302-file corpus, after the coverage and
R4 selection corrections landed. **Re-derive it rather than quoting these names later** — the point of
this file is the SPLIT and the method, not the list.

## The split, and it is the whole finding

    159  R4 rows reporting FAIL with moves examined
    151  of those carry NO `; FLOW=` stamp -- R4 cannot evaluate them at all
      8  are stamped and genuinely outside the band

The 197 that this began as, and the 234 the coverage summary reported before that, counted neither
defects nor files. A rule that cannot read a declaration is reporting MISSING EVIDENCE, and folding
that into a failure count makes the corpus look broken while hiding the few files that are.

**Method, so the number can be reproduced instead of trusted:** the classification here was not taken
from the report's own fields. Each failing file was opened and matched for `^; FLOW=`. That is a
different route than the one that produced the verdict, which is the only reason it is worth writing
down.

## The eight, and two of them are supposed to fail

    FORCE_attach.gcode          DELIBERATE KNOWN-BAD, emitted by tools/force_art_gates.py
    FORCE_pile.gcode            DELIBERATE KNOWN-BAD, same source
    bucket_towers_k2plus_pla_d339.5_h304.8_n16t6.48_w287.5os3.175_b20_bb5x5_m1
    cleavage_k1c_s6.35_w5_T210.gcode
    hangerpole_k1c_x12_h5_T210.gcode
    hangerpole_k1c_x12_h5_T230.gcode
    hangerpole_k1c_x9_h5_T210.gcode
    zladder_k2plus_pla_6cell_w2_p1.6.gcode

The two FORCE files exist to prove the gates fire. Counting them as defects would repeat the exact
error this whole correction was about. That leaves **six real candidates**, and three of those are one
hangerpole geometry at two temperatures.

## What this does NOT say

Nothing here has been printed and nothing may be claimed about how any of these behave on a machine —
the print lane has been paused since 2026-08-09. R4 asserts that ordinary body extrusion stays within
a tolerance of each file's OWN declared flow. That tolerance is 0.80-1.20 and it carries no
measurement behind it: `machine.py` records that it was inherited before 2026-07-27 with no machine,
nozzle, coupon or observed scatter. A file failing R4 is a file disagreeing with its own header, which
is worth looking at before printing and is not by itself proof it prints badly.

## The 151 are the bigger number and the smaller problem

They are legacy artifacts from before the mandatory header emitter, which now refuses to write a file
without a real flow, material and layer height. 140 of them map to current generator families and
could be regenerated if the lane reopens; 11 have no current source path (five spira2, five vladder,
one quasi). They were NOT regenerated, because replacing measured historical records with unexamined
output destroys the evidence.
