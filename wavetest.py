#!/usr/bin/env python3
"""WAVE BOND MATRIX — what throw/land combination actually bonds, measured on one plate.

Oleg, 2026-07-27, after the h60 wall test FAILED and was cleared: "focus on just 2 layers. run
test with different params to find what you can actually canb reliably bond."

Round 2 spec, Oleg after reading round 1: "for k2, 3 layers at least since first one is flat.
and movement has to ve significant. and speed has to drop to 10mm."

Eight rings, each THREE laps minimum:
  lap 1    ANCHOR — a plain circle pressed to PRESS_HARD, the weld to the plate. FLAT — it
           proves nothing about wave-on-wave, which is why two laps were not enough.
  lap 2..  WAVE   — throw-and-land: LAND 20% / RISE 30% / TOP 20% / FALL 30%, with the HALF
           WAVE extra per lap so every landing of lap k+1 sits on a TOP of lap k — the actual
           bucket mechanism, now present in the test. Ends after an even number of wave laps,
           on a landing.

The matrix (H=2.4 — "movement has to be significant" — at 10 mm/s):
  columns, left to right (X):  throw 9.4 / 12.6 / 15.1 / 18.8 mm   (waves m = 16/12/10/8 on d60)
  near row (Y=120):  landing gap 0.6  — a normal layer step
  far  row (Y=230):  landing gap 0.3  — landing PRESSED in (half step)

At 10 mm/s the Z budget that forced round 1 down to H=1.2 is gone (worst slope needs ~9 mm/s
of Z against the 30 limit), and every mm of thrown strand gets 5x the air time to freeze.
Delivered flow follows the speed down (12 mm3/s at a 2.0x0.6 bead) — E per mm is unchanged.

Pass/fail is READ OFF THE PLATE by hand: a ring passes if its wave lap is attached at every
landing and its throws hang as strands (sag onto the anchor is acceptable; drops/curls/combing
off are failure). The first ring where everything holds, with the longest throw, wins.
"""
import argparse, math, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import machine


def prof(x):
    """z fraction within one wave: LAND 0-0.2 flat, RISE 0.2-0.5 cosine, TOP 0.5-0.7 flat
    (airborne), FALL 0.7-1.0 cosine into the next landing."""
    if x < 0.2:
        return 0.0
    if x < 0.5:
        return 0.5 * (1.0 - math.cos(math.pi * (x - 0.2) / 0.3))
    if x < 0.7:
        return 1.0
    return 0.5 * (1.0 + math.cos(math.pi * (x - 0.7) / 0.3))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dia", type=float, default=60.0, help="test ring diameter, mm")
    ap.add_argument("--wave-h", type=float, default=2.4, help="wave height H, mm")
    ap.add_argument("--wave-laps", type=int, default=2,
                    help="wave laps per ring (even, so the strand ends on a landing)")
    ap.add_argument("--speed", type=float, default=10.0,
                    help="head speed mm/s — ONE speed for the whole print (R3); slow buys the "
                         "throws air time to freeze and frees the Z budget")
    ap.add_argument("--printer", default="k2plus", choices=sorted(machine.BED))
    ap.add_argument("--material", default=None)
    ap.add_argument("--layer-h", type=float, default=0.6)
    ap.add_argument("--out", default="out")
    a = ap.parse_args()

    a.material = machine.check_spool(a.printer, a.material or machine.LOADED[a.printer])
    flow = machine.flow_cap(a.material, a.printer)
    bw = machine.bead_for_flow(flow, a.layer_h)
    speed = min(a.speed, machine.speed_for_flow(flow, bw, a.layer_h))
    if a.wave_laps % 2:
        raise SystemExit("--wave-laps must be even: an odd count ends the strand on a TOP, "
                         "hanging in air, instead of welded on a landing")
    temp = machine.temp_for(a.material)
    lh = a.layer_h
    H = a.wave_h
    r = a.dia / 2.0
    C = 2 * math.pi * r

    # the matrix: (waves per lap, landing gap), laid out on the plate as described above
    throws = [16, 12, 10, 8]              # m -> throw = 0.8 * C/m: 9.4 / 12.6 / 15.1 / 18.8
    rows = [(120.0, 0.6), (230.0, 0.3)]   # (Y, landing gap)
    xs = [70.0, 150.0, 230.0, 310.0]
    bx, by = machine.BED[a.printer]
    assert max(xs) + r < bx - 4 and rows[-1][0] + r < by - 4

    # Z speed guard per the steepest ring (shortest lambda)
    lam_min = C / max(throws)
    slope = H * math.pi / (0.6 * lam_min)
    zv = slope * speed / math.sqrt(1 + slope * slope)
    if zv > machine.MAX_Z_V * 0.85:
        raise SystemExit(f"steepest ring needs {zv:.1f} mm/s of Z — over budget. Lower --wave-h "
                         f"or drop the shortest throw.")

    A = math.pi * (1.75 / 2) ** 2
    e_per_mm = bw * lh / A
    f = round(speed * 60)
    seg = max(0.25, speed / 250.0)
    n_ring = max(64, int(C / seg))

    L = []
    w = L.append
    w(f"; MATERIAL={a.material}")
    w(f"; LAYER_H={lh}")
    w(f"; FLOW={bw*lh*speed:.4f}")
    if bw * lh * speed < 0.8 * flow:
        # R8: derating must be DECLARED, in the file and on the console, never silent
        w(f"; FLOW_DERATE=operator speed cap {a.speed:g} mm/s (bond test: air time for the "
          f"throws) takes flow {flow:g} -> {bw*lh*speed:g} mm3/s")
        print(f"  !! FLOW DERATED {flow:g} -> {bw*lh*speed:g} mm3/s by the {a.speed:g} mm/s "
              f"speed cap — declared in the file (R8). Deposit per mm is unchanged.")
    w(f"; PRINTER={a.printer}")
    w(f"; PRESSED_LAYER1={machine.PRESS_HARD:g}")
    w("; SEQUENTIAL=8 rings, hop between")
    w("; ARGV: " + " ".join(sys.argv))
    w(f"; wave bond matrix: d{a.dia:g} rings, H={H:g}, bead {bw:.2f}x{lh} at {speed:.1f} mm/s")
    w(f"; ARCH_LIFT={H + 0.6:.3f}")
    w(f"; WAVE_SLOPE={slope:.3f}")
    w("; HEADER_BLOCK_START"); w("; total layer number: 2"); w("; HEADER_BLOCK_END")
    w("M82")
    w(f"M140 S{machine.bed_for(a.material, a.printer):.0f}")
    w(f"M104 S{temp}")
    w("G28")
    w(f"M190 S{machine.bed_start(a.material, machine.bed_for(a.material, a.printer)):.0f}")
    w(f"M140 S{machine.bed_for(a.material, a.printer):.0f}")
    w(f"M109 S{temp}")
    w("G92 E0")
    px0, py0 = 20.0, 20.0
    w(f"G1 Z{machine.PRESS_HARD:.3f} F600")
    w(f"G0 F9000 X{px0:.3f} Y{py0:.3f}")
    w("G1 E20 F300                      ; PRIME stationary purge")
    w(f"G1 F1200 X{px0+40:.3f} Y{py0:.3f} E30   ; PRIME line, in the clear")
    w(f"G0 F3000 X{px0+52:.3f} Y{py0+12:.3f}  ; PRIME break-off — angled wipe, no extrusion")
    w("G92 E0")
    w("; BODY_START")
    w("; WALL_START — the whole plate is wave wall; validate reads WAVE_SLOPE from here")

    e = 0.0
    report = []
    for (Y, gap) in rows:
        for xi, m in zip(xs, throws):
            lam = C / m
            cx, cy = xi, Y
            pts = [(cx + r * math.cos(2*math.pi*k/n_ring), cy + r * math.sin(2*math.pi*k/n_ring))
                   for k in range(n_ring + 1)]
            w(f"; ---- part ring m{m} gap{gap:g}: throw {0.8*lam:.1f}mm, land {0.2*lam:.1f}mm "
              f"at ({cx:.0f},{cy:.0f})")
            # hop in: lifted, flow suspended, no retract
            w("G0 Z5.0 F1800")
            w(f"G0 F9000 X{pts[0][0]:.3f} Y{pts[0][1]:.3f} ; HOP over to the next ring")
            # ANCHOR lap — layer 1, pressed, fan off while it bonds
            w("M107                              ; anchor is layer 1: no cooling")
            w(f"G1 F1800 Z{machine.PRESS_HARD:.3f}")
            w(f"G1 F{f}")
            qx, qy = pts[0]
            for X2, Y2 in pts[1:]:
                d = math.hypot(X2 - qx, Y2 - qy)
                if d < 0.02:
                    continue
                e += d * e_per_mm
                w(f"G1 X{X2:.3f} Y{Y2:.3f} Z{machine.PRESS_HARD:.3f} E{e:.5f}")
                qx, qy = X2, Y2
            # WAVE laps — m+1/2 waves per lap staggers the phase so every landing of lap k+1
            # sits on a TOP of lap k (the bucket's actual mechanism). THE FIRST WAVE LAP RAMPS
            # ITS AMPLITUDE 0->H with its landings PINNED to the anchor: the bucket's constant-
            # amplitude climb made lap 1's landings lift linearly off the base — welded at the
            # start, 3mm in the air by the end — a progressive detachment that is the likeliest
            # mechanism of the h60 wall failure. Construction, exact at every seam and landing:
            #     z(t) = press + gap + gap*t/C + R(u) + A(t)*prof(x)
            # A = H*u/C on lap 1 (ramp), H after; R(u) accumulates each finished lap's A at
            # this ring position (landing of lap k+1 sits exactly `gap` above lap k's top,
            # INCLUDING over the ramp); the per-lap gap is a continuous tilt, so lap seams are
            # continuous. Even lap count -> the strand ends on a landing, welded.
            w("M106 S51                          ; wave laps: 20% fan to freeze the throws")
            zbase = machine.PRESS_HARD + gap
            w(f"G1 F1800 Z{zbase:.3f}")
            # F IS STICKY: without this the whole wave lap inherits the Z move's F1800 —
            # caught by R4 (6024 moves at 60% of declared flow) on the first cut
            w(f"G1 F{f}")
            qz = zbase
            t = 0.0
            npts = len(pts) - 1
            Rlift = [0.0] * npts
            for lap in range(a.wave_laps):
                u = 0.0
                Acur = [0.0] * npts
                for i, (X2, Y2) in enumerate(pts[1:]):
                    d = math.hypot(X2 - qx, Y2 - qy)
                    if d < 0.02:
                        Acur[i] = Acur[i - 1] if i else 0.0
                        continue
                    t += d
                    u += d
                    A = H * min(u / C, 1.0) if lap == 0 else H
                    Acur[i] = A
                    Z = zbase + gap * t / C + Rlift[i] + A * prof(((m + 0.5) * t / C) % 1.0)
                    d3 = math.hypot(d, Z - qz)   # E on TRUE 3D length: constant flow on ramps
                    e += d3 * e_per_mm
                    w(f"G1 X{X2:.3f} Y{Y2:.3f} Z{Z:.3f} E{e:.5f}")
                    qx, qy, qz = X2, Y2, Z
                for i in range(npts):
                    Rlift[i] += Acur[i]
            report.append((m, gap, 0.8 * lam, cx, cy))

    w("M107"); w("M104 S0"); w("M140 S0")
    w("G0 Z40 F900")
    w(f"G0 X10 Y{by-10:.0f} F9000")
    g = "\n".join(L) + "\n"

    grams = e * A * 1.24 / 1000.0
    print(f"  8 rings d{a.dia:g}, H={H:g}, {speed:g} mm/s; max Z speed {zv:.1f} (limit "
          f"{machine.MAX_Z_V:g}); ~{grams:.0f} g")
    print(f"  near row Y=120: landing gap 0.6 (normal step) | far row Y=230: gap 0.3 (pressed)")
    print(f"  columns left->right: throw " +
          " / ".join(f"{0.8*C/m:.1f}" for m in throws) + " mm")
    os.makedirs(a.out, exist_ok=True)
    fn = os.path.join(a.out, f"wavetest_{a.printer}_d{a.dia:g}_H{H:g}_T{temp:g}.gcode")
    open(fn, "w").write(g)
    print(f"{fn}")


if __name__ == "__main__":
    main()
