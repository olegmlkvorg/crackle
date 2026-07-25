#!/usr/bin/env python3
"""ARCH TEST — how big an arc can the plastic actually hold? Oleg, 2026-07-25:
"we first will have to find out empirically how big arcs we can produce".

The Z axis will happily move 2.5mm in a 3mm window. That says nothing about whether the STRAND
survives: it leaves the surface, spans a gap in mid-air, and lands. Too tall or too long and it
sags, thins, or snaps. That is a material limit, and only the plate can report it.

GEOMETRY: one continuous spiral (no travels, no corners — the same base the flow tests use), single
layer, with an ARC every `pitch` mm of path. Arc height ramps linearly outward, so the plate is a
ladder of arcs from barely-there to as tall as the axis allows.

    arc height  = ramp from a_lo at the centre to a_hi at the rim
    arc span    = 2 * win  (the horizontal distance the strand is airborne)

READ IT: run a fingernail outward along the spiral.
  · too small  -> a bump you can feel but not see
  · working    -> a clean raised loop, plastic continuous over the top
  · too big    -> the top thins, then breaks; the strand lands as two stubs with a gap
Note the radius where the tops first break. That is the empirical arc ceiling, and it will be
BELOW what the axis permits.

MAX COOLING throughout: an arc that does not freeze in flight sags into a droop and the test
measures the fan instead of the geometry.
"""
import argparse, math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import machine


def win_for(amp, speed, aspect):
    """Half-span for a hoop of height `amp`, respecting the Z axis at both ends of the ladder.

    A hoop should scale as ONE thing — height and span together — so "hoop size" is a single
    variable and a failure is unambiguous. But pure proportional scaling breaks at the small end:
    acceleration goes as amp/win^2, so a short narrow hoop demands MORE acceleration than a tall
    wide one. The span is therefore the larger of the proportional span and the accel-safe minimum.
    """
    prop = aspect * amp
    a_min = math.sqrt((math.pi ** 2) * amp * speed ** 2 / (2 * machine.MAX_Z_A))
    v_min = math.pi * amp * speed / (2 * machine.MAX_Z_V)
    return max(prop, a_min, v_min)


def emit(a_lo, a_hi, aspect, pitch, flow, line_w, layer_h, temp, bed, fil_d, r0, margin,
         bed_xy, home, spacing, fan, squish, anchor, weld_dab, petal_v, lean, reach,
         petal_w, petal_h, touches, prelift, swing, heart_mm, heart_z, petal_wide,
         land_wave, n_layers, amp_clear, tip_gap):
    area = math.pi * (fil_d / 2) ** 2
    e_per_mm = (line_w * layer_h) / area
    speed = flow / (line_w * layer_h)
    f_mm_min = round(speed * 60)
    cx, cy = bed_xy[0] / 2, bed_xy[1] / 2
    r_max = min(cx, cy) - margin
    b = spacing / (2 * math.pi)         # solid base: spacing under the landed width
    th_max = (r_max - r0) / b

    # With STAPLE hops the span is chosen, not forced by the Z axis — XY is stopped while Z moves,
    # so height no longer drags span with it. The only requirement is that a staple finishes before
    # the next one begins.
    if reach and r_max + reach > min(cx, cy) - 4:
        raise SystemExit(
            f"a {reach}mm throw from the outer base radius {r_max:.0f}mm reaches "
            f"{r_max + reach:.0f}mm — past the {min(cx,cy):.0f}mm bed edge.\n"
            f"  Raise --margin so the base spiral stays inside {min(cx,cy) - reach - 4:.0f}mm, "
            f"or shorten --reach below {min(cx,cy) - r_max - 4:.0f}.")
    # With petal_w = 0 the strand is DERIVED from flow/speed, so speed is the input and there is
    # nothing to clamp — the flow is at target by construction. The clamp only applies when a
    # strand width is stated, where speed and width together imply a rate that could exceed the cap.
    _xp = petal_w * petal_h
    _vmax = (flow / _xp) if _xp > 0 else petal_v
    if _xp > 0 and petal_v > _vmax * 0.9:
        # 10% margin: E is written to 5 decimals and the petal has short segments, so rounding
        # alone put the measured strand 10% over the stated one and the flow with it.
        petal_v = _vmax * 0.9
    span_hi = aspect * a_hi
    if span_hi > pitch * 0.8:
        raise SystemExit(f"largest staple carries {span_hi:.1f}mm against a {pitch}mm pitch — they "
                         f"would run into each other.\n  Raise --pitch above {span_hi/0.8:.0f}.")
    # Z axis check on the pure vertical move (this is the only axis constraint left)
    t_up = math.sqrt(2 * a_hi / machine.MAX_Z_A)
    if machine.MAX_Z_A * t_up > machine.MAX_Z_V:
        t_up = a_hi / machine.MAX_Z_V + machine.MAX_Z_V / machine.MAX_Z_A
    w_note = f"tallest staple rises {a_hi}mm in ~{t_up:.2f}s of stalled XY"

    L = []; w = L.append
    w(f"; ARCH TEST — arcs every {pitch}mm of path, height {a_lo} -> {a_hi}mm outward")
    w(f"; STAPLE hops: XY stalls, Z rises, carry {aspect}x height, XY stalls, Z descends")
    w(f"; flow={flow} at {speed:.0f} mm/s, line {line_w}x{layer_h}, base spacing {spacing}")
    w(f"; hoops every {pitch}mm of path, base spacing {spacing}mm (< 1.53 landed = solid)")
    w(f"; {w_note}")
    w("; HEADER_BLOCK_START"); w("; total layer number: 1"); w("; HEADER_BLOCK_END")
    w(f"M140 S{bed}"); w(f"M104 S{temp}"); w("G90")
    w("G28" if home else "; NO HOME — direct to print (fails safely if the machine lost home)")
    w(f"M190 S{bed}"); w(f"M109 S{temp}")
    w("M204 S8000")
    # FANS OFF while the base bonds, then low. Max cooling froze the arcs beautifully and detached
    # the part at 46% (2026-07-25) — and adhesion is the PREREQUISITE for measuring anything, since
    # a part that lifts reports the fan rather than the hoop. Oleg: "also fans off. 20%".
    # Trade-off, stated: less cooling means the hoop tops droop more, so this reads as a
    # CONSERVATIVE height ceiling. Raise it once the height is known.
    w("M107                            ; fans off while the base bonds")
    w("M82"); w("G92 E0")
    _sx, _sy = cx + r0, cy
    w(f"G1 Z{layer_h*squish:.3f} F600")
    w(f"G0 F9000 X{_sx - 60:.3f} Y{_sy:.3f}")
    w(f"G1 F1200 X{_sx:.3f} Y{_sy:.3f} E12"); w("G92 E0")
    w("; Z_MODULATED"); w("; BODY_START")

    # STAPLE HOPS — XY STALLS while Z moves. Oleg: "when z moves the xy movement need to stall
    # then resume then stall again when it moves back".
    #
    # This is a different animal from a smooth arc, and better in three ways:
    #   · height and span become INDEPENDENT. A smooth arc has to widen as it grows, because the Z
    #     axis can only climb so fast while XY carries on — which is why tall arcs forced a huge
    #     pitch and hoops could not be frequent. With XY stopped, Z has all the time it needs.
    #   · the vertical strand is drawn STRAIGHT UP, in free air, anchored at the bottom. That is a
    #     genuinely new element: a post, not a bulge in a line.
    #   · the shape is legible — a rectangular staple reads as deliberate, an arc reads as a wobble.
    #
    # Each hop is five moves: run along the base, stall and rise, carry across at height, stall and
    # descend, continue. Extrusion continues through the vertical moves or the strand snaps.
    seg = 0.6
    e = 0.0; th = 0.0; s = 0.0
    px, py = _sx, _sy
    next_arc = pitch
    arcs = []
    fan_on = False
    fan_after = 2 * math.pi * r0
    z_base = layer_h * squish
    # MULTIPLE LAYERS OF OVERLAPPING PETALS. Oleg: "allow multiple layers of overlapping petals but
    # each layer you fly in the air higher not to hit prev one and always land on uniq spot to glue
    # furthest petal point".
    #
    # Two constraints, and they pull in opposite directions:
    #   · FLY HIGHER each layer, or the new arc sweeps through the one below it and knocks it off.
    #   · but still LAND on the plate, because a foot glued to a previous petal is glued to
    #     something that is itself only held by a foot.
    # Both are satisfiable because the landings are OFFSET: each layer's feet are rotated into the
    # gaps between the previous layer's, so every descent finds bare plate. Unique spot, clear path.
    layer_gap = amp_clear
    tips_placed = []
    for _layer in range(n_layers):
      th = 0.0; s = 0.0
      # PHASE-OFFSET each layer along the spiral by a fraction of the foot pitch. Same pitch, same
      # spiral, but layer k starts k/n of the way into the first gap — so its feet interleave into
      # the bare plate between the previous layers' feet instead of landing on them. A foot glued to
      # an earlier foot is a foot glued to nothing.
      next_arc = pitch * _layer / max(n_layers, 1)
      lift_layer = _layer * layer_gap
      # ALTERNATE THE SPIRAL DIRECTION. A layer that always restarts at the inner radius leaves the
      # nozzle parked at the outer edge, and the first move of the next layer drags a 103mm bead
      # straight back across everything just built. Reversing odd layers means each one ENDS where
      # the next BEGINS: outward, inward, outward. No jump, no travel, and the return sweep lays its
      # feet between the outbound ones instead of on top of them.
      ths = []
      _t = 0.0
      while _t < th_max:
          _t += seg / max(r0 + b * _t, 1.0)
          ths.append(_t)
      if _layer % 2:
          ths.reverse()
      # NEST EACH LAYER'S SPIRAL IN THE PREVIOUS ONE'S GAP. Every layer re-walked the identical
      # spiral at the identical z_base, so the nozzle re-traced a bead already standing at full
      # height — ploughing it, not adding to it. Shifting the radius by a fraction of the turn
      # spacing puts each layer on bare plate between the previous turns, which also carries the
      # petal feet onto fresh spots for free: a different radius is a different landing.
      r_off = spacing * _layer / max(n_layers, 1)
      for th in ths:
          r = r0 + b * th + r_off
          x, y = cx + r * math.cos(th), cy + r * math.sin(th)
          d = math.dist((px, py), (x, y)); s += d
          if fan and not fan_on and s > fan_after:
              L.append(f"M106 S{fan}                        ; {round(fan/255*100)}% once the base has bonded")
              fan_on = True
          e += d * e_per_mm
          L.append(f"G1 {'F%d ' % f_mm_min if not arcs and s < 1 else ''}"
                   f"X{x:.3f} Y{y:.3f} Z{z_base:.4f} E{e:.5f}")
          px, py = x, y

          if s >= next_arc:
              amp = a_lo + (a_hi - a_lo) * (r - r0) / (r_max - r0)
              span = aspect * amp                      # how far it carries at height
              z_top = z_base + amp
              # FLOW LIMITS THE VERTICAL MOVE TOO. The post is extruded at the same cross-section
              # as the base bead, so its volumetric rate is bead_area x Z_SPEED. At the Z axis's
              # 30 mm/s that is 2.4 x 30 = 72 mm3/s — above the 55 cap and into the ~74 where this
              # extruder audibly cracks. The flow ceiling is a property of the hotend and does not
              # care which axis is moving; I had applied it only to XY.
              f_z = round(min(machine.MAX_Z_V,
                              math.sqrt(2 * machine.MAX_Z_A * amp),
                              flow / (line_w * layer_h)) * 60)
              # PETAL — thrown outward and back, not pulled upward.
              # Oleg: "throwing filament in the air does not seem to work well yet. try maxing the
              # speed away from the point in a petal shape and back. 40mm height only".
              #
              # A vertical post hangs from a single foot with nothing to hold it. A petal is a closed
              # loop in a vertical plane: the strand leaves the surface, arcs out and up, comes over
              # the top and lands back near where it started, so it is carried by its own arc.
              #
              # SPEED IS THE MECHANISM, not just a preference. At a fixed flow cap, going fast makes
              # the flying strand THIN: 2.4mm2 at 23 mm/s is a rope with nothing supporting it;
              # 0.14mm2 at 400 mm/s is a thread light enough for its own curve to carry, and with so
              # little mass in it that it freezes almost on contact with air.
              # NEVER GLUE A TIP ONTO AN EARLIER TIP. Oleg: "always land on uniq spot to glue
              # furthest petal point". Interleaving the layers by radius and phase gets most of the
              # way there, but "most" is not "always" — six pairs still landed within 3mm. So check
              # the spot before committing: work out where this petal's tip WOULD land, and if an
              # earlier petal already owns that ground, skip this launch and try again a fifth of a
              # pitch further along the spiral. A foot glued onto a foot is glued to nothing.
              _Lr = reach if reach else amp / 2.0
              _sr = swing * _Lr
              _al = _Lr / _sr
              _ox, _oy = math.sin(_al) * _sr, (1 - math.cos(_al)) * _sr * 0.35
              _ux, _uy = math.cos(th), math.sin(th)
              _tip = (px + _ux * _ox - _uy * _oy, py + _uy * _ox + _ux * _oy)
              if any(math.dist(_tip, t) < tip_gap for t in tips_placed):
                  next_arc = s + pitch * 0.2
                  continue
              tips_placed.append(_tip)
              e += (z_base - anchor) * e_per_mm
              L.append(f"G1 F600 Z{anchor:.4f} E{e:.5f}            ; PRESS in — anchor the petal foot")
              e += weld_dab
              L.append(f"G1 F180 E{e:.5f}                     ; dab a foot")
              L.append(f"G1 F{round(petal_v*60)}")            # restore: F persists in gcode
              # Reach and height are INDEPENDENT. A circle in a vertical plane locks them at 1:2 —
              # throwing 130mm out would have meant a 260mm apex. An ellipse decouples them, so the
              # petal can be a long low throw: far out, barely up, and back. Oleg: "throw it way
              # further, to the edge of the printer", having already fixed the height at 40mm.
              Lr = reach if reach else amp / 2.0
              swing_r = swing * Lr        # swing circle radius, a multiple of the reach
              # KEEP THE FLOW AT THE CAP. Extrusion must be computed for the speed the head can
              # ACTUALLY reach, not the speed commanded. The petal is short segments, so acceleration
              # limits it well below 400 mm/s — computing E for 400 and then moving at 207 delivers
              # only 16 mm3/s instead of 55, i.e. a starved, broken strand. Oleg: "dont slow down the
              # flow of filament".
              # Sample count MUST be a multiple of the lobe count, or the feet are never sampled.
              # With 10 lobes over 48 samples the zeros of sin(lobes*phi) fall at fractional indices
              # (4.8, 9.6, 14.4 ...), so the touchdown test almost never fired and only one foot in
              # ten got a heart — or a weld. The structure was flying between anchors that did not
              # exist. 12 samples per lobe puts a point exactly on every zero.
              # Build the petal as POINTS first, then emit. Charging extrusion inside the point loop
              # meant special-casing the first segment, and the special case was wrong — it billed
              # 1mm of filament for a 17mm move and the flow audit came back at 854 mm3/s. With the
              # points in hand every distance is exact and the flow cap holds by construction.
              ux, uy = math.cos(th), math.sin(th)     # radial: the direction the petal throws
              tx, ty = -uy, ux                        # tangential: the sideways lean
              # TWO LOBES WITH A FOOT IN THE MIDDLE. Oleg: "throw petal in the air, then go down in
              # longest point to glue it and then get back to the air again".
              #
              # phi runs 0..pi, so the head goes OUT and comes BACK: u = Lr*sin(phi) peaks at pi/2.
              # Height is |sin(2*phi)|, which is zero at 0, pi/2 and pi and peaks between — so the
              # strand rises, arcs, TOUCHES DOWN at maximum reach where it is welded, rises again, and
              # lands home. The long span stops being a cantilever hanging off one foot and becomes
              # two arches sharing a middle anchor. That is what lets the throw be long.
              # MANY FEET, NOT ONE. With a single mid-throw touchdown the two lobes are so long they
              # read as straight lines. |sin((touches+1)*phi)| puts `touches` zeros inside the throw,
              # so the strand scallops down and up repeatedly — visibly arched, and no span is longer
              # than reach/(touches+1) unsupported.
              # RISE FIRST, THEN THROW. Oleg: "add more of vertical movement so there is actually a
              # petal to be thrown before you move sidewise".
              #
              # The arc moved outward WHILE it rose, so at no point was there a length of strand
              # standing in the air — it was being laid along a curve, not thrown. A pure vertical
              # climb at each foot draws real material upward first; only then does the head move
              # sideways, and what moves is a strand that already exists. That is the difference
              # between drawing an arc and throwing a petal.
              # A PETAL HAS AREA. Oleg: "now you are in the are of single line mostly".
              # The throw went out and came back along the SAME line, so it could never enclose
              # anything — vertical scallops on a single track. A petal outline needs the outbound and
              # the return to SEPARATE, and meet again at the tip:
              #     radial   u = Lr * sin(phi/2)    0 -> Lr -> 0   over phi 0..2pi
              #     lateral  w = W  * sin(phi)      +W going out, -W coming back
              # which traces a leaf: it opens on the way out, closes on the way home, and the enclosed
              # width is 2W at the widest. Z arches over the whole thing so the leaf lifts off the
              # plate and lands at its own tip.
              lobes_pre = touches + 1
              n_p = lobes_pre * 24
              pts_p = []
              touches_at = set()
              lobes = lobes_pre
              W = petal_wide * Lr
              for k in range(1, n_p + 1):
                  phi = 2 * math.pi * k / n_p
                  u = Lr * math.sin(phi / 2)
                  w = W * math.sin(phi)
                  al = u / swing_r
                  ox = math.sin(al) * swing_r
                  oy = (1 - math.cos(al)) * swing_r * 0.35 + w
                  zc = anchor + (amp + lift_layer) * abs(math.sin(lobes * phi / 2))
                  # SINUSOID BEFORE LANDING. Oleg: "play sinusoid on Z before landing so you travel to
                  # pull the extrusion but do not bind it". Approaching a foot the arc flattens out
                  # and the strand would simply be laid along the plate — bound, and no longer free to
                  # curve. A small Z ripple keeps the nozzle moving vertically through that approach,
                  # so it keeps PULLING material out without pressing it down. Material keeps flowing
                  # at target while nothing is committed to the plate until the foot itself.
                  if land_wave > 0:
                      _ph = abs(math.sin(lobes * phi / 2))
                      if _ph < 0.35:                      # only near the ground, not at the apex
                          zc += land_wave * (0.35 - _ph) / 0.35 * abs(
                              math.sin(lobes * phi * 3.0))
                  pts_p.append((px + ux * ox + tx * oy, py + uy * ox + ty * oy, zc))
                  # ANCHORS ONLY ON THE WAY OUT. Oleg: "remove the ancor point beyond the furtherst
                  # one". phi=pi is the tip — the furthest point. Feet after it were pinning the
                  # RETURN leg down, which is exactly the half that should stay in the air and curve.
                  if abs(math.sin(lobes * phi / 2)) < 0.02 and 1 < k < n_p and phi <= math.pi + 1e-9:
                      touches_at.add(len(pts_p) - 1)
              prev = (px, py, anchor)
              # The flying strand is SET, not derived. Three attempts at deriving it from speed and
              # the flow cap each produced a different wrong answer (0.14 too thin, 2.19 a rope,
              # 872 mm3/s in the audit) because the derivation chains through achievable speed, which
              # depends on segment length, which the lean makes wildly non-uniform.
              # Oleg: "while you fly thru the air, flow need to be managable so it does not split
              # apart". Too thin and it necks and snaps mid-flight; too thick and it is a rope with
              # nothing holding it. So state the strand directly and CHECK the flow it implies.
              # SLOW IN THE AIR, AT MAX FLOW. Oleg: "travel has to be slow in the air with max
              # extrusion flow so it does not get into straight line".
              # A fast head with a thin strand pulls the filament TAUT — it becomes a straight line
              # between two points because it is under tension the whole way. Slow travel while
              # pushing the full flow feeds out more material than the distance needs, so the strand
              # goes SLACK and takes a curve of its own. That slack is the shape.
              # petal_w = 0 derives it: cross-section = flow / speed, which is max flow by definition.
              xsec_petal = (petal_w * petal_h) if petal_w > 0 else (flow / petal_v)
              for k, (hx, hy, zc) in enumerate(pts_p):
                  d3 = math.dist(prev, (hx, hy, zc))
                  if d3 < 1e-9:
                      continue
                  e += d3 * (xsec_petal / area)
                  # ONE SPEED FOR THE WHOLE THROW. Extrusion per mm is fixed, so constant speed IS
                  # constant flow — and varying it was swinging the flow 17x (3 mm3/s at a F600 press
                  # against 55 in flight). Oleg: "speed is not following the extrusion volume, lets aim
                  # for uniformed lines speed wise". The feet still weld, because the dab is a
                  # STATIONARY extrusion: it adds material without laying a line, so it cannot make
                  # the line uneven.
                  L.append(f"G1 F{round(petal_v*60)} X{hx:.3f} Y{hy:.3f} Z{zc:.4f} E{e:.5f}"
                           + (f"   ; petal reach {Lr:.0f}mm apex {amp:.0f}mm" if k == 0 else ""))
                  prev = (hx, hy, zc)
                  if k in touches_at and heart_mm <= 0:
                      # plain foot: press hard, dab, carry on. No decoration.
                      e += (zc - max(heart_z, 0.08)) * e_per_mm
                      L.append(f"G1 F600 Z{max(heart_z,0.08):.4f} E{e:.5f}            ; press the foot")
                      e += weld_dab
                      L.append(f"G1 F180 E{e:.5f}                     ; weld the foot")
                      # RESTORE THE FEEDRATE. F persists in gcode, so the F600 press and the F180 dab
                      # leave every following move crawling until something sets it again — a stretch
                      # of base spiral was running at 10 mm/s and 24 mm3/s instead of 55. Oleg spotted
                      # it as "places where extrusion is paused". Nothing was paused; it was starved.
                      L.append(f"G1 F{round(petal_v*60)}")
                      prev = (hx, hy, max(heart_z, 0.08))
                  elif k in touches_at and heart_mm > 0:
                      # A LITTLE HEART AT EVERY FOOT. Oleg: "when you land to glue it, make a little
                      # pretty heart in there". The foot has to dwell on the plate anyway to weld —
                      # so instead of a blind dab of filament, spend that same material drawing
                      # something. It costs nothing extra and every landing becomes a mark.
                      # The classic heart curve, scaled to `heart_mm` across, traced on the plate:
                      #     x = 16 sin^3 t
                      #     y = 13 cos t - 5 cos 2t - 2 cos 3t - cos 4t
                      hp = []
                      for hk in range(0, 25):
                          t = 2 * math.pi * hk / 24
                          hxx = 16 * math.sin(t) ** 3
                          hyy = (13 * math.cos(t) - 5 * math.cos(2 * t)
                                 - 2 * math.cos(3 * t) - math.cos(4 * t))
                          sc = heart_mm / 32.0
                          hp.append((hx + (ux * hxx + tx * hyy) * sc,
                                     hy + (uy * hxx + ty * hyy) * sc))
                      # PRESSED HARD. The heart is the only part of a throw that must SURVIVE being
                      # pulled on by every arc that leaves it, so it is squashed well below the
                      # anchor height — the flatter and wider it is crushed, the more plate it grips.
                      # Oleg: "hearts need to be much larger diameter and pressed to bed as much as
                      # possible".
                      hz = max(heart_z, 0.08)
                      e += (anchor - hz) * e_per_mm
                      L.append(f"G1 F600 Z{hz:.4f} E{e:.5f}            ; press the heart into the plate")
                      hprev = (hx, hy, hz)
                      for hi, (qx, qy) in enumerate(hp):
                          dh = math.dist(hprev, (qx, qy, anchor))
                          if dh < 1e-9:
                              continue
                          e += dh * (xsec_petal / area)
                          L.append(f"G1 F{round(petal_v*60)} X{qx:.3f} Y{qy:.3f} Z{hz:.4f} "
                                   f"E{e:.5f}" + (f"   ; heart {heart_mm:.0f}mm, pressed to {hz:.2f}"
                                                  if hi == 0 else ""))
                          hprev = (qx, qy, hz)
                      e += weld_dab
                      L.append(f"G1 F180 E{e:.5f}                     ; weld the foot")
                      L.append(f"G1 F{round(petal_v*60)}")            # restore: F persists in gcode
                      prev = (hp[-1][0], hp[-1][1], hz)
              e += weld_dab
              L.append(f"G1 F180 E{e:.5f}                     ; dab the landing foot")
              e += (z_base - anchor) * e_per_mm
              L.append(f"G1 F600 Z{z_base:.4f} E{e:.5f}            ; back to the squished baseline")
              L.append(f"G1 F{f_mm_min}")                     # restore the BASE feedrate
              th2 = th + (span / max(r, 1.0))
              x2, y2 = cx + r * math.cos(th2), cy + r * math.sin(th2)
              th = th2; px, py = x2, y2
              arcs.append((round(amp, 2), round(r)))
              next_arc = s + pitch

    L += ["M107", "SET_PIN PIN=fan1 VALUE=0", "SET_PIN PIN=fan2 VALUE=0",
          "M104 S0", "M140 S0", f"G1 Z{layer_h + 40:.1f} F900",
          f"G0 X10 Y{bed_xy[1] - 10:.0f} F9000"]
    grams = e * area * 1.24 / 1000
    return "\n".join(L) + "\n", dict(arcs=len(arcs), grams=round(grams, 1), speed=round(speed),
                                     mins=round(s / speed / 60, 1), path=round(s / 1000, 1),
                                     sample=arcs[::max(1, len(arcs)//8)] if arcs else [])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--a-lo", type=float, default=10.0)
    ap.add_argument("--a-hi", type=float, default=4.0)
    ap.add_argument("--petal-v", type=float, default=400.0,
                    help="throw speed mm/s — at a fixed flow cap this sets how THIN the\n                          flying strand is, which is what lets its own arc carry it")
    ap.add_argument("--lean", type=float, default=0.35, help="sideways lean: petal, not disc")
    ap.add_argument("--heart-z", type=float, default=0.10,
                    help="absolute Z the heart is crushed to — lower grips more plate")
    ap.add_argument("--heart", type=float, default=0.0,
                    help="heart drawn at each landing foot, mm. 0 = OFF (default).\n                          Tried at 18mm 2026-07-25: it makes a mess — the foot is a\n                          structural anchor being crushed at 0.10mm, and 18mm of extra\n                          crushed line around it smears into the throws leaving and\n                          arriving. A press and a dab is what a foot wants.")
    ap.add_argument("--swing", type=float, default=1.2,
                    help="swing-circle radius as a MULTIPLE of the reach. Bigger = gentler\n                          sweep. This is the arc that throws the strand.")
    ap.add_argument("--prelift", type=float, default=12.0,
                    help="pure vertical climb at each foot BEFORE any sideways move —\n                          this is what makes a petal to throw instead of an arc to lay")
    ap.add_argument("--tip-gap", type=float, default=4.0,
                    help="minimum mm between two petals' far-point glue landings")
    ap.add_argument("--layers", type=int, default=1, help="stacked layers of petals")
    ap.add_argument("--clear", type=float, default=12.0,
                    help="extra apex height per layer so a new arc clears the one below")
    ap.add_argument("--land-wave", type=float, default=3.0,
                    help="Z ripple on the approach to a foot — pulls extrusion without\n                          binding it to the plate")
    ap.add_argument("--wide", type=float, default=0.35,
                    help="petal width as a fraction of reach — this is what gives it AREA")
    ap.add_argument("--touches", type=int, default=3,
                    help="glue-downs inside the throw — more feet, shorter arcs, visibly curved")
    ap.add_argument("--petal-w", type=float, default=0.0,
                    help="flying strand width mm. 0 = derive from flow/speed: hold max flow "
                         "while travelling slowly, so the strand is slack and curved not taut.")
    ap.add_argument("--petal-h", type=float, default=0.4, help="flying strand height mm")
    ap.add_argument("--reach", type=float, default=0.0,
                    help="how far the petal throws, mm. 0 = tie it to height (a circle)")
    ap.add_argument("--anchor", type=float, default=0.10,
                    help="absolute Z (mm) to press to before rising. 0.10 = crushed. See\n                          machine.PRESS_HARD — this is the project's general method.")
    ap.add_argument("--weld-dab", type=float, default=1.2,
                    help="mm of filament dabbed stationary to build a foot")
    ap.add_argument("--squish", type=float, default=0.72,
                    help="baseline Z as a fraction of layer_h — under 1 presses the base in")
    ap.add_argument("--aspect", type=float, default=1.6,
                    help="half-span / height. Hoop scales as ONE variable; the span is\n                          raised where the Z axis needs it at the small end.")
    ap.add_argument("--pitch", type=float, default=25.0, help="mm of path between hoops")
    ap.add_argument("--flow", type=float, default=machine.FLOW)
    ap.add_argument("--line_w", type=float, default=2.0)
    ap.add_argument("--spacing", type=float, default=1.4,
                    help="turn spacing — 1.4 < the 1.53mm landed width, so the base is a\n                          SOLID surface for hoops to launch from and land on")
    ap.add_argument("--layer_h", type=float, default=1.2)
    ap.add_argument("--temp", type=int, default=machine.TEMP)
    ap.add_argument("--bed", type=int, default=95)
    ap.add_argument("--fan", type=int, default=51, help="20%% — off entirely for the first turn")
    ap.add_argument("--r0", type=float, default=25.0)
    ap.add_argument("--margin", type=float, default=75.0)
    ap.add_argument("--bed-size", default="350,350")
    ap.add_argument("--no-home", action="store_true")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    bed_xy = tuple(float(v) for v in a.bed_size.split(","))
    g, st = emit(a.a_lo, a.a_hi, a.aspect, a.pitch, a.flow, a.line_w, a.layer_h, a.temp,
                 a.bed, 1.75, a.r0, a.margin, bed_xy, not a.no_home, a.spacing, a.fan,
                 a.squish, a.anchor, a.weld_dab, a.petal_v, a.lean, a.reach,
                 a.petal_w, a.petal_h, a.touches, a.prelift, a.swing, a.heart, a.heart_z, a.wide,
                 a.land_wave, a.layers, a.clear, a.tip_gap)
    os.makedirs(a.out, exist_ok=True)
    fn = f"{a.out}/hooptest_{a.a_lo:g}-{a.a_hi:g}mm_T{a.temp}.gcode"
    open(fn, "w").write(g)
    print(f"{fn}\n  {st['arcs']} hoops, {a.a_lo}->{a.a_hi}mm tall, span scales with height")
    print(f"  {st['speed']} mm/s, {st['path']} m path, ~{st['mins']} min, {st['grams']} g")
    print(f"  height at radius: {', '.join(f'{h}mm@r{r}' for h,r in st['sample'])}")
