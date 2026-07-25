# Disabling the K2's pausers — and why coupon A almost certainly paused

## The key fact the touchscreen hides
**"AI detection" only governs the CAMERA neural net** (spaghetti AC0101, first-layer AC0117,
foreign-object AC0104, flow-quality). Two *separate* systems survive that toggle and can pause a
print with **no Klipper error** — which is exactly what we saw:
1. **Extruder/motor CLOG detection (CM2783 / FO2845)** — motor-based, not camera. **No UI off-switch.**
2. **CFS filament/material logic** (`filament_switch_sensor` + `box.cfg` BOX_CHECK_MATERIAL_REFILL).

Both are issued by Creality userland services, so Moonraker only ever sees "PAUSE".

## → Why coupon A paused at 61% (high confidence)
The clog detector trips on **unusual flow: long travels with little or no extrusion.** That is a
literal description of crackle v1 — bare `G0` moves between pillars with only tiny dabs of material.
The machine saw a flow anomaly and paused. Same root cause as the empty web: v1 wasn't extruding.
**Prediction: crackle v2 (strands DRAWN with continuous small extrusion) should trip it far less.**
If v2 still pauses, root and disable the clog monitor.

## Fixes, in order of cost
1. **No root, 2 min:** Settings → Camera → **AI Function OFF** *and* **Sensitivity → Low**. Applies
   immediately, no reboot. If it still pauses mid-print with filament present → it's clog/CFS, not the camera.
2. **Root** (Settings → *Root account information*; `root` / `creality_2024`; must be re-enabled after
   any factory reset). Config lives at **`/mnt/UDISK/creality/userdata/config/`** — note there is NO
   `/usr/data/` on the K2, unlike the K1. Then:
   - `[filament_switch_sensor filament_sensor]` → **`pause_on_runout: false`**, and neutralise
     `BOX_CHECK_MATERIAL_REFILL` in `box.cfg` → kills the silent CFS pause.
   - `[virtual_sdcard]` → **`forced_leveling: false`** → kills the forced calibration.
     *(single-user report — verify the param exists on this firmware before relying on it)*
   - `FIRMWARE_RESTART`. **Re-apply after any OTA update or factory reset.**
   - Tradeoff: implicitly voids warranty; a bad printer.cfg edit crashes the machine.
3. **Homing overhead:** `prtouch_v3` **IS** the Z endstop — there is no separate switch, so the single
   nozzle touch-off **cannot be skipped** and still give a valid Z=0. What you CAN drop is the
   re-meshing: `G28 X Y` + `BED_MESH_PROFILE LOAD=<saved>` + one `G28 Z`. **Do NOT** use
   `SET_KINEMATIC_POSITION` to fake a homed Z — that's a nozzle-into-bed crash.
   Community: jamincollins/k2-improvements (`MESH_IF_NEEDED`, stripped START_PRINT),
   sw3defy Helper Script wiki, Guilouz extracted firmwares.

## Note on our `--no-home` files
They work because the machine kept its homed position from the previous job. That's legitimate and
fast, but it is NOT a way to avoid the Z touch on a cold start — after power-off you must home once.

## Bed temperature clamps to 120 C (found 2026-07-25)
`M190 S135` is accepted without error and the machine holds target at exactly **120.0**, even though
the Klipper config reports `heater_bed.max_temp: 135`. Something above Klipper (firmware or the
print profile) caps it. **`max_temp` is not the reachable ceiling — verify the achieved target, not
the commanded one.** Silent clamp, no error, no warning: a run you believe was at 135 was at 120.

Practical: any run commanding >120 actually ran at 120, so those runs remain comparable to each
other. Check with:
    curl -s "http://192.168.3.140:7125/printer/objects/query?heater_bed"

## M190 is a MINIMUM wait — it does not cool (found 2026-07-25, the hard way)
`M190 S60` with the bed at 100 returns **immediately**. Klipper's M190 is `TEMPERATURE_WAIT
MINIMUM=`, so it only ever waits for heating. Coupon B was believed to print at bed 60 and actually
printed at ~95-100. Silent: no error, no warning, and the gcode looks correct.

**Consequence for any back-to-back series:** a passively-cooling bed means every coupon prints at a
different temperature, which silently confounds the comparison they exist to make.

**Fix:** set the target and poll until the bed has actually arrived BEFORE starting the series.
    curl -s -X POST ".../printer/gcode/script?script=M140%20S60"
    # then poll heater_bed.temperature until <= target+2, and only then start
