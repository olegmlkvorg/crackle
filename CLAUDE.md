# crackle — developer notes

**Oleg, 2026-08-07:** *"work on folder specific Claude md as developer docs as there is nuances you
can only see by reading files in full"*

`RULES.md` says WHAT the rules are. `README.md` says what the parts are. **This file is the set of
things that are only visible by reading a whole file, and that have each cost a print or a wrong
claim.** Everything here was learned by being bitten, and every entry names the artifact so it can
be re-checked rather than believed.

**READ THE SOURCE IN FULL BEFORE EDITING IT.** That is the house rule (Assist/CLAUDE.md) and this
directory is where it was earned. The three files that matter are each around two thousand lines —
**run `wc -l` rather than trusting this sentence**, because a hardcoded count in a file about
hardcoded numbers going stale is the joke writing itself, and the first version of this line was
already wrong by 89 the day it was typed. Every defect below was invisible in a diff and obvious in
the file.

---

## STORE THE RELATIONSHIP, NOT THE VALUE

**Oleg, 2026-08-07, after the third one in a night:** *"Okey, natural evolution. 3rd sample now you
converting to formula"*.

Three constants failed the same way in one session, and each was **correct at the operating point it
was measured at and silently wrong everywhere else**:

| | was | is |
|---|---|---|
| first floor layer pitch | typed `2.5` | `FLOOR1_OVERLAP × w1` — a RATIO to the bead |
| the fabric membrane | a sentence asserting it fuses | `--fabric {fused,open}` declared; a state the numbers contradict is refused |
| layer 1 full flow | the stored pair `(0.10, 2.00)` | `w1·press / (bead·lh) ≥ 1.0` |

**THE TEST: does this constant's correctness depend on another parameter?** If yes, the constant is
a frozen relationship and it will be carried somewhere it does not apply. Store the relationship;
derive the value.

**A stored PAIR is the same trap wearing two numbers.** `PROVEN_LAYER1 = (0.10, 2.00)` passed R9 and
S1 on a file laying half the required flow, because both numbers matched and neither carried the
LAYER HEIGHT they were measured at. `machine.py` said so in prose — *"the body's own 0.82x0.24 bead
pressed flat"* — and prose does not fail a build. **It cost a print on 2026-08-07.**

**A CLAIM I MADE HERE AND THEN DISPROVED, kept because the correction is the more useful half.** I
wrote that `PROVEN_SEND['k2plus']['coverage']` `(2.00, 1.6)` was "the next one to bite", because its
ratio `pitch/w1 = 0.80` is the same number as `FLOOR1_OVERLAP` and it is stored as absolutes. **The
first half is true and the conclusion was wrong.** Storing coverage as absolutes means a file at
another layer height measures `(3.94, 3.15)`, which is simply NOT in the accepted set, and S2 says
so:

    FIRST-PROOF  S2 floor coverage (3.94, 3.15) is NOT proven on k2plus (accepted: (2, 1.6) | (2, 2.5))

**That is the gate working, not failing.** `PROVEN_LAYER1` bit us precisely because the pair
`(0.10, 2.00)` stayed IDENTICAL across layer heights while its meaning changed; coverage's pair
MOVES with the height, so the mismatch is visible. **Same-looking storage, opposite behaviour, and
the difference is whether the stored numbers change when the operating point does.**

**The real exposure is at ACCEPT time, not gate time:** if someone accepts `(3.94, 3.15)` without
recording the layer height it was measured at, the ledger then holds two coverage pairs whose
meanings differ and nothing says which is which. **Do not make coverage ratio-equivalent to "fix"
this** — a 3.94mm line overlapping 0.79mm is not the same physical thing as a 2.00mm line
overlapping 0.40mm, and treating equal ratios as equal evidence is the exact mistake that made
`(0.10, 2.00)` look proven at 0.48.

**What is genuinely ABSOLUTE, so the rule is not applied blindly:** `temps (210, 60)` is a property
of the filament. `cross_mms` is a speed — though the quantity that matters is `span / speed`, i.e.
time in air, and nothing stores that either. `span_mm 17.85` is empirical, but note the file records
16.80 mm of AIR inside a 17.85 mm chord and that ratio is nowhere.

## Names that are not what you would guess

| you would write | it is actually | what happens if you guess |
|---|---|---|
| `finding.name` | `Finding = namedtuple('Finding', 'rule status text')` — the field is **`rule`** | `AttributeError` **after** a 4-minute scan of a 106 MB file. Cost a print on 2026-08-07. |
| a fresh "blocking" list | `blocked` already exists 11 lines above in `send.py:cmd_send` | a parallel definition silently stops covering a rule somebody adds later |
| `machine.SLICER_LAYER_H` as the layer height | true only as a DEFAULT; `bucket_towers.py` takes `--layer-h`, checked against `machine.SLICER_LAYER_HEIGHTS` | a height no profile offers has never been laid here |

**Before writing `x.foo`, find where `x` is defined and read the fields.** A namedtuple's field list
is one grep and it is authoritative.

---

## machine.py — constants that look settled and are not

**`ZERR['k2plus'] = 0.15` is correct. `0.30` is RETRACTED.** Both numbers are in the repo and they
describe the same quantity:

- **0.30** came from a paper feeler, sheets slid under a hot nozzle.
- **0.15** came from a PRINTED LADDER: at offset −0.15 the first layer was clean, at −0.20 the
  nozzle dragged through material it had just laid.

The paper reading was wrong by 2x **because the spring-steel sheet FLEXES under the shim and absorbs
the very gap being measured.** On 2026-08-07 a session was one edit from "fixing" the correct
constant with the discredited one, on the strength of `zladder.py`'s docstring. That docstring now
carries the retraction; `machine.ZERR` is the authority.

**`SLICER_LAYER_HEIGHTS = (0.24, 0.32, 0.40, 0.48, 0.56)`** was a comment until 2026-08-07, which
meant nothing could refuse a height the machine does not offer.

**`zoff_for()` REFUSES a positive result** rather than returning it. Positive lifts the nozzle away
from the plate, and `validate.py` cannot see `SET_GCODE_OFFSET` at all — R1 would go on reading the
commanded `Z0.100` and passing a file printing half a millimetre in the air. That blindness let
three max-bucket starts through.

---

## validate.py — how a second speed regime becomes legal

R3 enforces ONE speed per print. There are four legitimate exceptions and they all work the same
way, which is the pattern to copy rather than invent around:

1. the regime is **DECLARED in the header** (`; SPEED_LAYER1=`, `; SPEED_CROSS=`, `; SPEED_POCKET=`,
   `; SPEED_CORNER=`, `; SPEED_BRIDGE=`)
2. R3 **REMOVES** those speeds from its histogram before the constancy test
3. a **separate rule verifies the declared speed actually appears on the moves that claim it**
   (R3b pocket, R3c corner, R3d bridge)

**ORDER MATTERS AND IT IS NOT OBVIOUS.** The layer-1 removal keys on `len(_spd) == 2`, so every
other regime must be removed BEFORE it. Add a new one after that test and layer 1 silently stops
being exempt.

**NEVER ADD AN EXEMPTION INSTEAD OF A DECLARATION.** R3's own comment predicted the bridge case:
*"If a generator ever slowed one to buy volume, R3 must see it rather than a bridge exemption
swallowing it."* It did see it, and failing the file was correct.

**`; SPEED_BRIDGE=` is a LIST** where the others are single values, because each flow multiplier
needs its own speed under one flow ceiling: at layer 0.48 a 4x accent lands at 34.9 mm/s and an 8x
rim at 17.5.

**A bare feedrate line may carry a comment.** Until 2026-08-07 the implied-flow parser used
`re.match(r'G1 F(\d+)\s*$', line)`, which required the line to END at the number, so
`G1 F1050 ; BRIDGE SLOWED` was invisible and **every following move was scored at a stale speed.**
It reported 157 mm³/s for moves running at 55. It failed loud there; the same staleness
UNDER-reports a move that speeds up, which is the dangerous direction.

**A guard that has not been seen to FAIL is decoration.** Force every new rule red before believing
a green, and check it fired for the RIGHT reason — a file rejected by some other guard proves
nothing about the new one.

---

## bucket_towers.py — geometry that does not transfer

**`air_span()` is MEASURED, never computed.** `towercoupon.py` computes air as
`span − one tower diameter`, correct THERE because its strands land ACROSS a tower. This file's
chords deliberately CLEAR both posts — that is what licenses a flat crossing with no lift — so
almost none of the chord is over material. **Borrowing the coupon's formula understated the span by
6 mm.** A formula carries its geometry with it and the name does not.

**`--pitch` is a MAXIMUM, and the count is `ceil`.** Rounding down would put the part outside its own
evidence to save one tower.

**Gate 3 no longer discriminates for a C-channel.** For a closed loop only 12.75 of 360 degrees of
seam offset passed, so it genuinely licensed the flat crossing. For a C the chord starts near the
tangent points and it refuses only below `--wrap-deg 360/n` — about 347 of 360 degrees pass. It
still measures a true property; **it must not be quoted as the reason the arc form is safe.**

**Derived quantities exist because a typed one drifts.** `--floor-pitch-1` is
`FLOOR1_OVERLAP × w1`, a RATIO, because what decides whether two lines touch is pitch against BEAD
WIDTH — a fixed millimetre goes silently wrong the moment `--w1` changes. Same reason `--tower-d`
derives from `--stick-d + --bore-allow`.

**THE FABRIC'S STATE IS DECLARED (`--fabric {fused,open}`), AND THE GATE HAS NOW BEEN WRONG IN
BOTH DIRECTIONS — the second cost a print.** Fusion is physics:

    area = bead_w × layer_h × cross_flow ;  rod = sqrt(4·area/π) ;  fuses when rod ≥ layer_h
    ⇒  fusion needs cross_flow ≥ π·layer_h / (4·bead_w)   (0.230 at 0.24 ; 0.460 at 0.48)

First the header claimed fusion UNCONDITIONALLY — false at 0.48/0.25. Then the gate **required**
fusion unconditionally, so the 0.48 regen went out at `--cross-flow 0.50` to satisfy it: the walls
came out SOLID and, because every crossing and lap lands on the mouth lips, the stick stopped
entering (2026-08-07, cancelled at 37.8%). **Fused-and-light is impossible at a doubled pitch** —
fusion at 0.48 is 2× the 0.24 membrane's material by construction. So neither state is "correct":
they are different parts, the file must SAY which (`; FABRIC=`), a declaration the numbers
contradict is refused as a lie, and an undeclared open net is refused as an accident.

**THE LIP BUDGET IS THE GATE THAT CAME OUT OF IT** (`machine.PROVEN_LIP`): mm³ per mm² of wall
landing on the C-channel's mouth lips, per regime — `bead × (1 + 2·merge_flow + cross_flow +
mult/N_layers)`, lh-invariant, so it survives layer-height changes that every mm-spacing rule
silently does not. No file may exceed the 1.763 of the only part whose 359mm insertion was ever
attempted (bore 4.20, "near to impossible"), and insertion margin is bought with `--bore-allow`,
never with lip headroom. The cancelled 15:44 file (1.63×) is its red proof.

---

## send.py — the gate on the DECISION to print

`validate.py` gates the FILE. `send.py` gates the choice to send it. They are different failures:
on 2026-08-06 four file-gates all PASSED on files that then failed on the plate, because the
unguarded step was pressing start.

- **`scan(path)` is a pure function that measures everything the gate measures and spends nothing.**
  Run it before the one real dry run. Discovering that after a grant was spent cost a coupon.
- **Rule 6 grants ONE FILE per unproven value, forever.** A grant is bound to the file's sha256, so
  re-running the same bytes keeps it; a different artifact with the same value gets nothing.
- **`accept` does not write the ledger.** It PRINTS the row a human pastes, deliberately: the actor
  that decides to print must not hold the key to the set it is checked against.
- **`accept` proposes ONE `--observed` string for coverage, prime, temps and layer1 alike.** Pasting
  it as offered files bore evidence as prime evidence. Give each value its own story.
- **`--oleg-said "<verbatim>"` overrules a LEDGER refusal and is RECORDED.** It cannot reach
  `validate.py` — proven by injecting an R10 defect and watching it stay refused. His word overrules
  UNPROVEN, never MALFORMED.

---

## Every generator stamps `; CMD=`

`sys.argv` verbatim, **not** a reconstruction from parsed args — a reconstruction prints what the
parser DECIDED, which is exactly the layer that turns an omitted flag into a default and hides the
omission. Proven by regenerating a plate from its own stamp and diffing byte-for-byte.

**A DEFAULT IS A CLAIM.** On 2026-08-07 three of them had outlived their evidence at once:
`--floor-pitch 2.5` (0.50 mm of bare plate under a 2.00 mm bead), `--bore-allow 0.25` (measured on a
**metal** shaft, condemned ~21 parts), `--wrap-deg 210` (mouth wider than the stick at every bore, so
it could never grip). Each had a proven replacement in a ledger or a docstring. **The proven value
cannot fail; the default wins every regeneration.** Fix the default, derive it where a relationship
exists, and refuse the impossible rather than defaulting to it.

**Anything that changes the part goes in the FILENAME.** Regenerating with a stronger base on
2026-08-05 silently OVERWROTE the gcode of a part that had already printed. Layer height was missing
from the name until 2026-08-07.

---

## The K2's 20-minute calibration is NOT in our gcode

Oleg, 2026-08-07: *"why you executing clibration again?"* on a 3-minute coupon. Traced, because the
obvious answer (our `G28`) is wrong and three pieces of evidence say so:

1. **`grep -cE "BED_MESH|G29|CALIBRATE|LEVEL|PROBE"` on the emitted file returns 0.** The only thing
   any generator here asks for is `G28`.
2. **The probe temperatures are not ours.** During that block the nozzle holds **140** and the bed
   **50**; our files command `M104 S210` / `M140 S60`. So the routine runs BEFORE our first line
   takes effect — it is the machine's print-start handler, outside the file.
3. **`homing_override` contains `BED_MESH_CLEAR` and no calibrate.** `G28` WIPES the active mesh;
   the firmware then rebuilds it.

**The cost:** `bed_mesh` is `probe_count [9, 9]` over `mesh_min [5,5]` to `mesh_max [345,345]` — 81
points, and on a large footprint that is ~20 minutes, six times the runtime of a 3-minute coupon.

**A saved profile called `default` ALREADY EXISTS on the machine and goes unused**, because `G28`
clears the active mesh every print.

**IF AUTO-LEVEL IS EVER TURNED OFF MACHINE-SIDE, ADD `BED_MESH_PROFILE LOAD=default` AFTER `G28`.**
Without that line, disabling the calibration leaves the part printing on NO mesh at all, on a bed
measured to vary 0.652mm — much worse than the delay it saves. `gcode_macro
bed_mesh_calibrate_start_print` also accepts a `PROBE_COUNT` parameter, so a coarser mesh is a
middle option nobody has tried.

**The general point, and it is why this belongs here:** when the machine does something the file did
not ask for, prove which one owns it before changing either. The temperatures settled this in one
reading — 140/50 appear nowhere in our code.

## A VENDOR'S OWN SLICER PROFILE OUTRANKS THE VENDOR'S OWN PRODUCT PAGE

**Creality say two different things about one spool of Hyper PC, and they differ by 40 C
on the number that decides whether the part sticks.**

| source | bed |
|---|---|
| the product listing (`makerparts3d`, and the spec block Creality distributes) | 50-80 C |
| `Hyper PC @Creality K2 Plus 0.8 nozzle.json`, shipped inside Creality Print | **110 C**, first layer and after |

The page number was published in a build's README and its assembly PDF on 2026-09-01 and
was very likely the cause of the adhesion failure that followed. **The profile is the one
that prints; the page is copy.** The same profile also carries `chamber_temperature 50`,
`activate_chamber_temp_control 1` and `close_fan_the_first_x_layers 3`, none of which the
page mentions at all.

Cross-check against this repo before believing either: `machine.BED_TEMP` has no PC row,
but its nearest analogue ABS is bed 100 with `FAN_MAX` 0.10, which agrees with the profile
and not with the page. `machine.BED_MAX['k2plus']` is 120.0 measured under load, so 110 is
inside what the machine actually holds.

**The profiles are on disk and they are readable — read them.**

    /Applications/Creality Print.app/Contents/Resources/profiles/Creality/filament/
    /Applications/Creality Print.app/Contents/Resources/profiles/Creality/process/

The same directory settled a second question the same day: `line_width 0.82`,
`wall_loops 2`, `layer_height 0.4` for the 0.8 nozzle. A wall typed as 2.4 mm is 2.93
lines at that width, and the slicer fills the remainder as GAP INFILL — 53.65 g and
48m57s, a quarter of that print's duration. **A wall thickness is a relationship to the
profile's line width, not a number to type**, which is the same lesson as STORE THE
RELATIONSHIP above, arriving through the slicer instead of through the plate.

## Testing these files from a shell

**zsh does not word-split an unquoted parameter.** `python3 $CMD` sends the whole string as one
argument and the command silently does nothing; use `eval` or `${=VAR}`. **A pipeline hides the exit
status** — `$?` after `cmd | tail` is `tail`'s. Judge the STATE, not the command.

**Never grep-filter the output of a command you are testing.** A filter dropped a traceback on
2026-08-07 and turned a crash into apparent silence. Show the tail first; filter once it works.

**An empty result is the most common shape of a lying probe.** Prove the probe can return non-empty
on a case you constructed before reporting a zero.
