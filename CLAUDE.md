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
| the fabric membrane | a sentence asserting it fuses | `cross_flow ≥ π·lh / (4·bead)` |
| layer 1 full flow | the stored pair `(0.10, 2.00)` | `w1·press / (bead·lh) ≥ 1.0` |

**THE TEST: does this constant's correctness depend on another parameter?** If yes, the constant is
a frozen relationship and it will be carried somewhere it does not apply. Store the relationship;
derive the value.

**A stored PAIR is the same trap wearing two numbers.** `PROVEN_LAYER1 = (0.10, 2.00)` passed R9 and
S1 on a file laying half the required flow, because both numbers matched and neither carried the
LAYER HEIGHT they were measured at. `machine.py` said so in prose — *"the body's own 0.82x0.24 bead
pressed flat"* — and prose does not fail a build. **It cost a print on 2026-08-07.**

**KNOWN, UNFIXED, AND THE NEXT ONE TO BITE:** `PROVEN_SEND['k2plus']['coverage']` stores
`(2.00, 1.6)`, whose ratio `pitch/w1 = 0.80` is **the same number as `FLOOR1_OVERLAP`** — one fact
in two places, which is the footgun `machine.py`'s own `--tower-d` comment warns about. It is stored
as absolutes, so it goes stale at any other layer height exactly as `PROVEN_LAYER1` did.

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

**THE MEMBRANE IS A GATE, NOT A SENTENCE.** The fabric fuses into a sheet only when its rod reaches
the layer pitch:

    area = bead_w × layer_h × cross_flow ;  rod = sqrt(4·area/π) ;  fuses when rod ≥ layer_h
    ⇒  cross_flow ≥ π·layer_h / (4·bead_w)

At the shipped 0.24/0.82 the threshold is 0.230 against a 0.25 default — **8.8% margin nobody
chose.** The generator printed *"its rod exceeds the layer pitch, so strands FUSE into a membrane"*
UNCONDITIONALLY, computed from two numbers it never compared, and that sentence is FALSE at layer
0.48 with the fabric left at 0.25. It refuses now.

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

## Testing these files from a shell

**zsh does not word-split an unquoted parameter.** `python3 $CMD` sends the whole string as one
argument and the command silently does nothing; use `eval` or `${=VAR}`. **A pipeline hides the exit
status** — `$?` after `cmd | tail` is `tail`'s. Judge the STATE, not the command.

**Never grep-filter the output of a command you are testing.** A filter dropped a traceback on
2026-08-07 and turned a crash into apparent silence. Show the tail first; filter once it works.

**An empty result is the most common shape of a lying probe.** Prove the probe can return non-empty
on a case you constructed before reporting a zero.
