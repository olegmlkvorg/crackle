#!/usr/bin/env python3
"""Gate solid.emit layer changes against the file's own R4 flow declaration."""
import os
from pathlib import Path
import sys
import tempfile

from shapely.affinity import translate
from shapely.geometry import box

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import gate_coverage
import machine
import solid


def r4_ratios(text):
    """Return the exact R4 flow ratios for diagnostics; analyze_text decides the verdict."""
    declared = gate_coverage.stamped_float(text, "FLOW")
    pressed = gate_coverage.stamped_float(text, "PRESSED_LAYER1")
    bridge_declared = gate_coverage.stamp(text, "BRIDGE_MM2") is not None
    ratios = []
    for move in gate_coverage.moves(text):
        if not move["body"] or move["distance"] <= 0.05 or not move["de"] or move["de"] <= 0:
            continue
        if pressed is not None and move["z"] is not None and abs(move["z"] - pressed) <= 1e-6:
            continue
        upper = move["raw"].upper()
        if ("LINK" in upper or "THIN CROSS" in upper
                or ("BRIDGE" in upper and bridge_declared) or "PRIME" in upper):
            continue
        flow = move["de"] * gate_coverage.AREA * move["feed"] / move["distance"]
        ratios.append((flow / declared, move))
    return ratios


def direct_gcode(region, name):
    return solid.emit(
        region, machine.PRESS_HARD + 2 * 0.6, 1.2, 0.6, 36.0, 210, 90, 1.75,
        machine.BED["k1c"], True, machine.PRESS_HARD, 100, 7.2, 0.2, "k1c", name,
        material="pla", centre=False)[0]


def check(label, text, expected_layer_changes):
    row = next(rule for rule in gate_coverage.analyze_text(text) if rule["rule"] == "R4")
    motion = gate_coverage.moves(text)
    changes = [move for move in motion
               if move["body"] and move["code"].startswith("G1 ")
               and "Z" in move["code"] and "X" not in move["code"] and "Y" not in move["code"]
               and move["distance"] > 0.05 and move["z"] > machine.PRESS_HARD + 1e-6
               and move["z"] <= machine.PRESS_HARD + 2 * 0.6 + 1e-6]
    ratios = r4_ratios(text)
    bad = [(ratio, move) for ratio, move in ratios
           if ratio < machine.R4_FLOW_MIN_RATIO or ratio > machine.R4_FLOW_MAX_RATIO]
    if len(changes) != expected_layer_changes:
        raise AssertionError(f"{label}: saw {len(changes)} layer changes, want {expected_layer_changes}")
    if row["moves_examined"] == 0:
        raise AssertionError(f"{label}: R4 examined zero real moves")
    if row["verdict"] != "PASS":
        ratio, move = min(bad, key=lambda item: item[0])
        raise AssertionError(
            f"{label}: R4 {row['verdict']}; {len(bad)} unlabelled moves outside "
            f"{machine.R4_FLOW_MIN_RATIO:.2f}-{machine.R4_FLOW_MAX_RATIO:.2f}, "
            f"minimum ratio {ratio:.6f} at line {move['line']}: {move['code']}")
    metered_changes = [move for move in changes if move["de"] is not None and move["de"] > 0]
    if metered_changes:
        raise AssertionError(
            f"{label}: {len(metered_changes)} Z-only layer changes still advance E; "
            "a label must not exempt stationary seam extrusion")
    print(f"PASS {label}: R4 moves={row['moves_examined']}, layer_changes={len(changes)}, "
          f"ratio={min(r for r, _ in ratios):.6f}..{max(r for r, _ in ratios):.6f}")


def main():
    one = box(20, 20, 32, 32)
    check("solid.emit", direct_gcode(one, "LAYER CHANGE DIRECT"), 2)

    class Args:
        cavity = 0
        floor = 0.0
        height = machine.PRESS_HARD + 2 * 0.6
        layer_h = 0.6
        bead_w = 1.2
        flow = 36.0
        temp = 210
        bed = 90
        material = "pla"
        printer = "k1c"
        no_home = False
        press = machine.PRESS_HARD
        first_w = 7.2
        fan = 100
        brim = 0
        aux = 0.2

    with tempfile.TemporaryDirectory(prefix="crackle-solid-layer-") as tmp:
        path = os.path.join(tmp, "sequential.gcode")
        solid.emit_sequential(
            [("one", one), ("two", translate(one, xoff=30))], Args(), "two", path)
        check("solid.emit_sequential", Path(path).read_text(), 4)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
