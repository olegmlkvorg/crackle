#!/usr/bin/env python3
"""ANTI-VIBRATION STAND — shared formwork/print helpers for the stand generators.

WHY THIS EXISTS. stand_tile.py proved a start sequence + pressed-floor + fused-haunch +
single-bead-wall that PASSES validate.py on both machines (see guides/printer-stand.md). The three
remaining printed parts — the column, the column cap/saddle, and the feet — must reuse THAT proven
start sequence verbatim, not re-derive it. This module carries the sequence and the geometry
primitives so a new generator cannot silently drift from the tile.

The start block is lifted line-for-line from stand_tile.py (the design authority): M109 BEFORE
G28 so the probe touches at print temp (R7), SET_GCODE_OFFSET Z=-0.05 press bias, prime + angled
break-off, and the six header stamps validate.py requires (MATERIAL / LAYER_H / FLOW / PRINTER /
PRESSED_LAYER1 / PRINT_TEMP). If you change it here, re-run validate.py on stand_tile's default and
on all three new generators before trusting it.

THE ONE HARD RULE that shapes every part in this file: validate.py fails any un-tagged G0 between
the first and last extrusion ("TRAVEL move inside the object"), and a tagged HOP must clear the
printed material — impossible inside a small part hopping over itself. So EVERY LAYER IS ONE
CONTINUOUS EXTRUDING STROKE. Islands are connected by extruding moves, never by travels. That is
why the cap is a tray (one perimeter) not a set of separate cradles, and the column is a closed
loop (circle, optionally flatted) not a wall with pillars.

Everything here follows the house doctrine: pressed 0.1 first layer (adhesion is the press, not
dwell), 50 mm/s north star, bead widened to hit the flow cap, single continuous stroke per layer."""
import math, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import machine

A_FIL = math.pi * (1.75 / 2) ** 2


class Build:
    """Carries the machine operating point + the emitted gcode + a running extruder position.

    Construct once per part, call preamble(), lay geometry with the helpers, call finish() + save().
    """

    def __init__(self, printer, material=None, layer_h=0.6, bed=None, bead=None):
        self.printer = printer
        self.material = machine.check_spool(printer, material or machine.LOADED[printer])
        self.flow = machine.flow_cap(self.material, printer)          # 60 k2 / 45 k1c at pla-matte
        self.lh = layer_h
        # BEAD OVERRIDE = the wide-bead crawl. Wall thickness is set by the bead width; a wider bead
        # keeps flow AT the cap by dropping speed below the north star (machine.speed_for_flow),
        # which R3/R8 accept as a declared constant. This is the in-doctrine way to thicken a
        # single-stroke wall — a second concentric loop would print in the first's XY shadow and the
        # dive guard (correctly) refuses it.
        self.bw = bead if bead else machine.bead_for_flow(self.flow, self.lh)   # 2.0 k2 / 1.5 k1c
        self.speed = machine.speed_for_flow(self.flow, self.bw, self.lh)   # 50, or lower for a fat bead
        self.temp = machine.temp_for(self.material)
        self.bed = (min(bed, machine.BED_MAX.get(printer, machine.BED_MAX_DEFAULT))
                    if bed is not None else machine.bed_for(self.material, printer))
        self.bx, self.by = machine.BED[printer]
        self.cx, self.cy = self.bx / 2.0, self.by / 2.0
        self.e_mm = self.bw * self.lh / A_FIL                          # E per mm of PATH (3D)
        self.f = round(self.speed * 60)
        self.land = self.bw * self.lh / machine.PRESS_HARD             # pressed layer-1 landed width
        self.z1 = machine.PRESS_HARD                                   # pressed first layer
        self.z2 = machine.PRESS_HARD + self.lh                         # second (normal) layer
        self.L = []
        self.e = 0.0
        self.qx = self.qy = self.qz = None

    # ---- output ----
    def w(self, s):
        self.L.append(s)

    def emit(self, X, Y, Z):
        """One extruding move, metered on 3D path length (so climbing moves keep flow EXACTLY
        constant — R4). Micro-segments under 0.2mm are decimated or Klipper stalls its lookahead."""
        d3 = math.hypot(math.hypot(X - self.qx, Y - self.qy), Z - self.qz)
        if d3 < 0.2:
            return
        self.e += d3 * self.e_mm
        self.w(f"G1 X{X:.3f} Y{Y:.3f} Z{Z:.3f} E{self.e:.5f}")
        self.qx, self.qy, self.qz = X, Y, Z

    # ---- the proven start/finish sequence (verbatim from stand_tile.py) ----
    def preamble(self, title, total_layers, extra_stamps=()):
        """Header stamps + heat + PROBE-HOT-THEN-HOME + press bias + prime + break-off + BODY_START.

        `title` MUST be free of the word 'bead'; this method appends 'bead {w}x{h}' which the
        overhang and fill-ratio checks parse for the nominal bead width."""
        w = self.w
        w(f"; MATERIAL={self.material}")
        w(f"; LAYER_H={self.lh}")
        w(f"; FLOW={self.bw * self.lh * self.speed:.4f}")
        w(f"; PRINTER={self.printer}")
        w(f"; PRESSED_LAYER1={machine.PRESS_HARD:g}")
        w(f"; PRINT_TEMP={self.temp}")
        w("; ARGV: " + " ".join(sys.argv))
        w(f"; {title} bead {self.bw:.2f}x{self.lh:g}")
        for s in extra_stamps:
            w(s)
        der = machine.flow_derate_stamp(self.material, self.printer, self.bw * self.lh * self.speed)
        if der:
            w(der)
        w("; HEADER_BLOCK_START")
        w(f"; total layer number: {total_layers}")
        w("; HEADER_BLOCK_END")
        w("M82")
        w(f"M140 S{self.bed:.0f}")
        w(f"M104 S{self.temp}")
        _wait = self.bed if self.printer == "k2plus" else machine.bed_start(self.material, self.bed)
        w(f"M190 S{_wait:.0f}")
        w(f"M109 S{self.temp}")                 # NOZZLE HOT BEFORE G28 — probe at print-temp length (R7)
        w("G28")
        w("SET_GCODE_OFFSET Z=-0.05             ; first-layer press insurance (K2 datum ~0.1 high)")
        w("M106 S0")                            # part fan off for the pressed first layer (PLA)
        for line in machine.aux_fans(self.printer, 0.0):
            w(line)
        w("G92 E0")
        px, py = 20.0, 16.0
        w(f"G1 F600 Z{machine.PRESS_HARD:.3f}")
        w(f"G0 F9000 X{px:.3f} Y{py:.3f}")
        w("G1 E20 F300                      ; PRIME stationary purge")
        w(f"G1 F1200 X{px + 40:.3f} Y{py:.3f} E30   ; PRIME line")
        w(f"G0 F3000 X{px + 52:.3f} Y{py + 12:.3f}  ; PRIME break-off — angled wipe, no extrusion")
        w("G92 E0")
        w("; BODY_START")

    def begin_at(self, X, Y, Z, tag="; PRIME-TRAVEL to start"):
        """Position the head at the geometry start (the one licensed travel, before any extrusion)."""
        self.w(f"G0 F9000 X{X:.3f} Y{Y:.3f} {tag}")
        self.w(f"G1 F600 Z{Z:.3f}")
        self.w(f"G1 F{self.f}")
        self.qx, self.qy, self.qz = X, Y, Z

    def hop_to(self, X, Y, Z, clear_z):
        """Lift clear of everything printed, travel (dry, no retract), descend — the ONE licensed
        in-part travel. Tagged '; HOP over' so validate.py counts it as a lift-clear hop and its
        plough/no-travel checks pass (the lift makes the XY move sit ABOVE all printed material)."""
        self.w(f"G1 F1800 Z{clear_z:.3f}")           # lift straight up, no extrusion
        self.w(f"G0 F9000 X{X:.3f} Y{Y:.3f} ; HOP over printed hoop")
        self.w(f"G1 F600 Z{Z:.3f}")                  # descend onto empty ground
        self.w(f"G1 F{self.f}")
        self.qx, self.qy, self.qz = X, Y, Z

    def relevel_z(self, Z):
        """Bare Z move to a new solid-layer height. Used only between constant-Z solid layers, so
        validate.py reads it as a layer change (the floating-line / R2 check keys on bare Z moves)."""
        self.w(f"G1 F1800 Z{Z:.3f}")
        self.w(f"G1 F{self.f}")
        self.qz = Z

    def finish(self, top_z):
        self.w("M107")
        self.w("M104 S0")
        self.w("M140 S0")
        self.w(f"G0 Z{top_z + 10:.0f} F900")
        self.w(f"G0 X{min(10.0, self.bx - 10):.0f} Y{self.by - 10:.0f} F9000")

    def text(self):
        return "\n".join(self.L) + "\n"

    def grams(self):
        return self.e * A_FIL * 1.24 / 1000.0

    def minutes(self):
        return self.e / self.e_mm / self.speed / 60.0

    def fits(self, w, h):
        """Refuse a part wider than the plate (with the tile's 3mm clearance rule)."""
        return w <= self.bx - 6 and h <= self.by - 6

    # ---- geometry primitives (all leave the head on the loop so the next call chains) ----
    def rect_ring(self, cx, cy, ix, iy, z):
        """One rectangle ring, inset (ix,iy) from centre, starting/ending at +x,+y so rings chain."""
        x0, x1 = cx - ix, cx + ix
        y0, y1 = cy - iy, cy + iy
        self.emit(x1, y1, z)
        self.emit(x0, y1, z)
        self.emit(x0, y0, z)
        self.emit(x1, y0, z)
        self.emit(x1, y1, z)

    def rect_pts(self, cx, cy, ix, iy, seg=1.5):
        """Closed rectangle loop, edges subdivided to ~seg mm, starting/ending at +x,+y so loops
        chain. Subdivision (vs bare corners) keeps every move short: it holds the move rate sane on
        the climbing wall AND keeps the first body moves under the starved-move guard's 2mm floor,
        which a long bare edge trips on a small part (the guard reads the prime's leftover E because
        it does not honour the G92 reset). Corner-only rects are fine on a large part (the tile);
        this is for the smaller rectangular parts."""
        x0, x1 = cx - ix, cx + ix
        y0, y1 = cy - iy, cy + iy
        corners = [(x1, y1), (x0, y1), (x0, y0), (x1, y0), (x1, y1)]
        pts = [corners[0]]
        for (ax, ay), (bx, by) in zip(corners, corners[1:]):
            d = math.hypot(bx - ax, by - ay)
            n = max(1, int(d / max(seg, 0.2)))
            for i in range(1, n + 1):
                t = i / n
                pts.append((ax + (bx - ax) * t, ay + (by - ay) * t))
        return pts

    @staticmethod
    def _radius_at(theta, r, chords):
        """Radius of a circle-with-flats at angle theta. Each chord is (phi, d): a flat whose
        outward normal points at phi, at perpendicular distance d<r from centre. A ray at theta is
        clipped onto the flat where it would otherwise pass beyond it."""
        rr = r
        for phi, d in chords:
            c = math.cos(theta - phi)
            if c > 1e-6:
                rr = min(rr, d / c)
        return rr

    def circle_pts(self, cx, cy, r, seg=1.0, chords=()):
        """Closed loop of points around a circle (optionally flatted by `chords`), pts[-1]==pts[0]."""
        n = max(48, int(2 * math.pi * r / max(seg, 0.2)))
        pts = []
        for i in range(n + 1):
            th = 2 * math.pi * i / n
            rr = self._radius_at(th, r, chords)
            pts.append((cx + rr * math.cos(th), cy + rr * math.sin(th)))
        pts[-1] = pts[0]
        return pts

    def loop(self, pts, z):
        """Emit one closed loop at constant z (pts already closed)."""
        for X, Y in pts:
            self.emit(X, Y, z)

    def climb_loop(self, pts, z_start, z_top):
        """Spiral a closed loop upward, climbing exactly one layer height per lap (single-bead wall).
        Z is metered on accumulated path length so the seam climbs smoothly; flow stays constant
        because emit() meters E on the 3D distance."""
        perim = sum(math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
                    for i in range(len(pts) - 1))
        if perim < 1e-6:
            return
        # start the head at pts[0] at z_start (the caller has usually just laid the top solid ring
        # ending near here; emit() will draw the short connector)
        self.emit(pts[0][0], pts[0][1], z_start)
        t = 0.0
        Z = z_start
        guard = 0
        maxlaps = int((z_top - z_start) / self.lh) + 4
        while Z < z_top - 1e-6 and guard < maxlaps + 4:
            guard += 1
            for i in range(1, len(pts)):
                X, Y = pts[i]
                seg = math.hypot(X - self.qx, Y - self.qy)
                t += seg
                Z = min(z_top, z_start + self.lh * t / perim)
                self.emit(X, Y, Z)

    def solid_annulus_layer(self, cx, cy, r_out, r_in, z, pitch, outward=False):
        """Fill an annulus (r_in..r_out) with concentric rings at `pitch`, at constant z. Rings chain
        by a short extruding radial step (never a travel). `outward` fills r_in->r_out ending at the
        rim; else r_out->r_in ending at the hole/centre. Alternate it layer-to-layer so consecutive
        layers meet where the last ended — no stacked radial welt. Returns the radius the head ends
        at (0.0 for a closed centre)."""
        rs = []
        r = r_in
        while r < r_out - 1e-6:
            rs.append(max(r, 0.0))
            r += pitch
        rs.append(r_out)
        if not outward:
            rs = rs[::-1]
        end_r = rs[-1]
        for rr in rs:
            if rr <= 1e-6:
                self.emit(cx, cy, z)
            else:
                self.loop(self.circle_pts(cx, cy, rr, seg=1.0), z)
        return end_r


def stamp_dependencies():
    """One place to state, in the emitted file's own comments, what is PROVEN vs PROVISIONAL, so the
    honesty travels with the artifact (publish-as-we-go). Callers append these to preamble()."""
    return [
        "; STAND PART — structure is tile-independent and validated; the SINGLE-BEAD WALL + FILL",
        ";   mechanics are PROVISIONAL pending the knock-test tile (wall may need more beads/liner;",
        ";   fill depth/mix may change). Those are parameters here, not rewrites.",
        "; FIT CLEARANCES (spine hole, foot collar, cap register) are PROVISIONAL — calibrate on a",
        ";   coupon at the real machine+bead+material before cutting the fleet (see memory: fit",
        ";   constants are conditional; a printed hole comes out ~6mm under-diameter).",
    ]
