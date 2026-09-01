# heatbox — 110 C hot-air chamber for two copper shoes

**STAGE: DESIGNED, NOT PRINTED. Nothing below is verified on hardware.** Two inputs are
stated guesses and both change the part: the shoe's real dimensions (modeled 20 x 40 x 10 mm,
only "2 by 4" was given) and the heat source (modeled as a temperature-adjustable gun,
setpoint 140-160 C, round nozzle into a 20 mm duct). Confirm both, regenerate, then print.

Three copper shoes rotate: one in use, two resting in the chamber at 110 C, either one
removable at any moment. The chamber is a printed double-wall box fed by the 2 cm hot-air
inlet. Air enters a plenum under a perforated deck, rises as jets flanking each shoe's
faces, and leaves through the cap standoffs and two lid vents. Each shoe stands in its own
open-top pocket and lifts straight out with tongs through its own lid slot.

## Parts

| piece | count | file |
|---|---|---|
| body (double wall, plenum, inlet socket, probe port, feet) | 1 | `out/heatbox_body_shoe20x40x10_in20.stl` |
| deck (drop-in, jet holes, pocket ribs) | 1 | `out/heatbox_deck_shoe20x40x10_in20.stl` |
| lid (two slots, two vents) | 1 | `out/heatbox_lid_shoe20x40x10_in20.stl` |
| cap (floats on 2 mm nubs = calibrated exhaust) | 2 | `out/heatbox_cap_shoe20x40x10_in20.stl` |

Assembly is gravity only: deck drops onto its ledges, lid sits on the rim, caps sit in the
slots. No fastener crosses a hot printed part, because at 110 C every clamped or screwed
PC feature creeps.

BOM beyond prints: aluminum tube 20 mm ID x 1 mm wall x ~60 mm (the inlet liner — the gun
couples to metal, never to PC), a K-type bead thermocouple with any reader for the 6.5 mm
probe port, tongs, and optionally a small aluminum sheet bent into an L for the plenum
deflector groove if the source runs above 160 C. Outer size 118 x 52 x 92 mm plus lid.

## The material is at its limit — design consequences

Creality's page for Hyper PC claims it "maintains structural integrity at temperatures
above 111.2 C" (makerparts3d.com listing, no test load stated). The comparable blended-PC
datasheet number found (Ultimaker PC, via search snippet only — the TDS PDF itself refused
the fetch) is HDT 104.5 C at 0.455 MPa, Vicat 114.7 C. So a 110 C chamber runs this
material AT its rating, not under it. Everything follows from that:

1. **No printed feature carries load at temperature.** Shoes stand on the deck, parts
   stack by gravity, the liner is guided by three 0.5 mm ribs, and the gun's weight must
   NEVER rest on the socket — park the gun on its own stand.
2. **The jet lands on metal.** Source air is necessarily hotter than 110 C, so it enters
   through the aluminum liner, which protrudes 25 mm into the plenum. The liner runs near
   source temperature end to end, which is why it touches PC only on rib lines.
3. **110 C is proven by the probe port, never by this file.** See the first-run gate.
4. The deck is the hottest printed piece and the cheapest — it is the telltale. If
   anything warps first, it is the deck, and it reprints in an hour.

## Numbers (relationships, not values)

Air at 150 C: rho 0.83 kg/m3, cp 1.01 J/gK, so mdot[g/s] = 0.0138 x flow[L/min] and each
L/min carries 0.014 W per K of temperature drop.

- **Required source temperature:** T_in = T_chamber + Q_walls / (mdot x cp). Double-wall
  loss estimate Q_walls ≈ U x A x dT ≈ 3 W/m2K x 0.043 m2 x 85 K ≈ 11 W, so at 30 L/min
  (0.42 W/K): T_in ≈ 110 + 26 ≈ **136 C**. Half the flow needs ~160 C. Recommended
  setpoint window 140-160 C; the SCAD refuses a declared source above 200 C, and above
  140 C without the liner.
- **Shoe energy:** m = 8.96 g/cm3 x 8 cm3 ≈ 72 g, E = m x 0.385 J/gK x 85 K ≈ 2.4 kJ from
  cold.
- **Recovery time is convection-limited, and this is the design constraint.** Time
  constant tau = m x c / (h x A) with A ≈ 0.0028 m2. Impinging/washing jets give h ≈
  20-60 W/m2K, so tau ≈ 3-8 min. A shoe returned at ~70 C is within 5 K of chamber at
  ~2.1 tau ≈ **6-17 min**. With two resting per one in use, each shoe rests twice its
  out-time, so swaps every 3-8 min sustain the rotation. The spread is honest: measure it
  once with the probe strapped to a shoe, and that measurement sets the swap rhythm.
- **Warm-up from cold:** ~300 g of PC plus two shoes ≈ 25 kJ of structure, roughly
  10-20 min before the probe settles. Trust the probe, not this estimate.

## First-run gate (do not skip, do not run unattended before it passes)

1. Bead probe into the port, chamber empty, caps on, source at 140 C setpoint.
2. Soak 30 min. PASS: probe steady at 105-115 C, no visible change in the deck or walls.
   Probe below 105: raise setpoint toward 160 or raise flow. Probe above 115: lower
   setpoint — do not "let it settle".
3. Shoes in, soak, then time one real recovery: pull a shoe, let it cool ~40 K, return
   it, record minutes back to 105 C. That number is the swap interval, written on the box.

## Printing (K2 Plus, Hyper PC)

Vendor page: nozzle 240-260 C, bed 50-80 C. Chamber heat on, filament dried first
(generic PC practice — the vendor page is silent on drying). All parts print upright as
modeled, no supports: the body bridges its top rim and the bore roof by design, and the
bore deliberately has no locating rib at top dead center so bridge sag lands on open
clearance. Walls are 2.4 mm solid skins (6 x 0.4 perimeters).

## Guards in the SCAD, each proven able to fire

| guard | refuses | forced red with |
|---|---|---|
| A1 | chamber target above 115 C in this material | `-D chamber_target=120` |
| A2 | source above 140 C with no liner, or above 200 C at all | `-D liner=false`, `-D source_temp=210` |
| A3 | exhaust area below inlet area (pressurized joints) | `-D cap_standoff=0.3` |
| A4 | plenum too low to pass the liner tube | `-D plenum_h=20` |
| A5 | pocket with no tong room | `-D tong_jaw=4` |
| A6 | jet holes touching tangent (non-manifold mesh) | `-D jets_per_row=6` |

All six fired with the right message on 2026-09-01 before the first green render
(`openscad -o /dev/null` swallows the assert — use a real output path when re-proving).
A6 exists because the first deck shipped six 4 mm holes over 20 mm: centers exactly one
diameter apart, tangent circles, non-manifold STL.

Regenerate: `openscad -o out/heatbox_<part>_shoe<WxHxT>_in<inlet>.stl -D 'part="<part>"'
heatbox.scad` for body, deck, lid, cap. Shoe dims and inlet stay in the filename because a
regenerated part that silently overwrites a printed one's gcode already bit this repo once.

## References examined

- **makerparts3d.com Hyper PC listing** (opened): the only spec sheet found — print temps,
  density 1.19, and the 111.2 C claim quoted above. Adopted as the material bound.
- **store.creality.com Hyper PC page** (opened): no technical specs at all. Nothing to adopt.
- **RepRap wiki, Heated Build Chamber** (opened): duct-fed hot air as the heat source
  adopted (it is this design's premise). Manual sliding-vent throttling rejected — fixed
  orifice areas sized against the inlet (guard A3) instead, no moving hot parts. MDF box
  with glued cardboard insulation rejected — printed double skin needs no adhesive at 110 C.
- **Ultimaker PC TDS**: not opened (server 403), numbers taken from the search snippet and
  labeled as such above. Used only as the comparable for where PC blends actually sit.
- **Regad-style heated creasing stations**: named prior art for the two-hot-one-working
  rotation. Not examined — no open design found in this pass.

Future options, deliberately not built: an inline PID on the source side if the gun's own
thermostat proves sloppy, and a hanging-shank deck v2 if the real shoes turn out to carry
handles (the caps already pass an 8 mm shank).
