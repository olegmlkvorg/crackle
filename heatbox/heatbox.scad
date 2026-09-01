// heatbox — hot-air chamber holding two copper shoes at 110 C while a third is in use.
// Printed in Creality Hyper PC. Vendor claim: "maintains structural integrity above
// 111.2 C" (makerparts3d.com product page, no test load stated) — so 110 C runs the
// material AT its rated limit. Everything below follows from that: no printed feature
// carries load at temperature, the source jet lands on aluminum, and the only proof
// of 110 C is the probe port, never this file.
//
// Render:  openscad -o out/<name>.stl -D 'part="body"' heatbox.scad   (deck, lid, cap)
// Preview: openscad -o out/preview.png --camera=... -D 'part="preview"' heatbox.scad

part = "preview";       // body | deck | lid | cap | preview

// ---- shoes (Q1 — confirm real dims before printing; these are the stated defaults)
shoe_w = 20;            // face width, mm ("2 by 4" read as cm)
shoe_h = 40;            // vertical extent standing
shoe_t = 10;            // thickness — GUESSED, not given
shoe_clear = 5;         // air gap flanking each big face

// ---- heat source (Q2)
inlet_id      = 20;     // given: 2 cm hot-air duct
liner_od      = 22;     // BOM aluminum tube 20 ID x 1 wall; jet must couple to metal
liner         = true;   // false only if source is temperature-limited (see assert)
source_temp   = 160;    // max recommended setpoint, C
chamber_target = 110;   // C

// ---- structure
skin    = 2.4;          // per-skin wall (6 perimeters at 0.4)
gap     = 6;            // double-wall air gap, the insulation
floor_t = 3;
plenum_h = 26;          // under-deck plenum; must clear liner_od (assert A4)
deck_t  = 3;
head    = 12;           // air space above shoe tops
tong_jaw = 8;           // free space at each shoe end for tong jaws (assert A5)
pocket_gap = 8;
jet_off = 5;            // jet row offset outboard of shoe face (clears pocket ribs)
jet_d   = 4;
jets_per_row = 5;       // spacing must exceed jet_d (assert A6) or holes fuse tangent
cap_standoff = 2;       // caps float on nubs; the standoff IS the exhaust (assert A3)
vent_d = 6;
foot_h = 8;

// ---- derived (relationships, not values — crackle house rule)
bay_x = shoe_w + 2*tong_jaw;
int_w = 2*bay_x + 3*pocket_gap;
int_d = shoe_t + 2*(shoe_clear + jet_off);
int_h = plenum_h + deck_t + shoe_h + head;
out_w = int_w + 2*(2*skin + gap);
out_d = int_d + 2*(2*skin + gap);
out_h = floor_t + int_h;                 // lid adds on top
pocket_cx1 = -int_w/2 + pocket_gap + bay_x/2;
pocket_cx2 =  int_w/2 - pocket_gap - bay_x/2;
inlet_area = PI*pow(inlet_id/2,2);
jet_area   = 2*2*jets_per_row*PI*pow(jet_d/2,2) + 2*PI*pow(jet_d/2,2); // rows + 2 end bleeds
slot_w = shoe_w + 2*(tong_jaw-3);        // lid slot passes shoe + tong jaws
slot_d = shoe_t + 8;
cap_w = slot_w + 14; cap_d = slot_d + 14;   // must overhang the lid's pin ring
exit_area  = 2*(2*(slot_w+slot_d))*cap_standoff + 2*PI*pow(vent_d/2,2);

// ---- guards. Each forced red before first render — commands in README.
// A1 material: vendor HDT claim ~111 C; a target above 115 is a different material's part.
assert(chamber_target <= 115,
  str("A1 Hyper PC rated ~111 C; refuse chamber target ", chamber_target));
// A2 source: above 140 C setpoint the jet footprint exceeds PC limits without metal.
assert(liner || source_temp <= 140,
  str("A2 source ", source_temp, " C without aluminum liner lands >140 C air on PC"));
assert(source_temp <= 200,
  str("A2 source ", source_temp, " C exceeds 200 C design cap even with liner"));
// A3 breathe: exhaust below inlet area pressurizes every printed joint.
assert(exit_area >= inlet_area,
  str("A3 exit area ", exit_area, " < inlet area ", inlet_area, " — raise cap_standoff"));
// A4 the liner tube must fit the plenum it enters.
assert(plenum_h >= liner_od + 4,
  str("A4 plenum ", plenum_h, " cannot pass liner OD ", liner_od));
// A5 a pocket the tongs cannot enter holds a shoe nobody can take out.
assert(tong_jaw >= 6, str("A5 tong_jaw ", tong_jaw, " leaves no grip room"));
// A6 jet holes closer than their own diameter touch tangent — non-manifold mesh
// (found the hard way: 6 holes over 20 mm put centers exactly one diameter apart).
assert(shoe_w/(jets_per_row-1) > jet_d,
  str("A6 jet spacing ", shoe_w/(jets_per_row-1), " <= jet_d ", jet_d));

echo(str("interior ", int_w, " x ", int_d, " x ", int_h,
         "  outer ", out_w, " x ", out_d, " x ", out_h + foot_h, " + lid"));
echo(str("inlet ", inlet_area, " mm2, deck jets ", jet_area,
         " mm2, exit ", exit_area, " mm2"));

$fn = 48;
e = 0.01;

// ================================================================ body
module shell(w, d, h, t) {
  difference() { cube([w, d, h], center=false);
    translate([t, t, t]) cube([w-2*t, d-2*t, h+e]); }
}

module body() {
  difference() {
    union() {
      // outer skin + floor
      translate([-out_w/2, -out_d/2, 0]) shell(out_w, out_d, out_h, skin);
      translate([-out_w/2, -out_d/2, 0]) cube([out_w, out_d, floor_t]);
      // inner skin
      translate([-int_w/2 - skin, -int_d/2 - skin, floor_t - e])
        shell(int_w + 2*skin, int_d + 2*skin, int_h + skin + e, skin);
      // rim closing the gap at the top
      translate([-out_w/2, -out_d/2, out_h]) difference() {
        cube([out_w, out_d, skin]);
        translate([2*skin + gap, 2*skin + gap, -e])
          cube([out_w - 2*(2*skin+gap), out_d - 2*(2*skin+gap), skin + 2*e]); }
      // sparse ribs tying the skins (4 verticals per long side)
      for (sx=[-1.5:1:1.5], sy=[-1,1])
        translate([sx*int_w/4 - 1, sy*(int_d/2 + skin + gap/2) - gap/2 - 1, floor_t])
          cube([2, gap + 2, int_h - 10]);
      // inlet socket boss, left end wall, axis at plenum mid-height
      translate([-out_w/2 - 8, 0, floor_t + plenum_h/2]) rotate([0, 90, 0])
        cylinder(d=liner_od + 0.4 + 2*3, h=8 + 2*skin + gap + e);
      // 45-degree gusset carrying the boss's protruding underside, which is otherwise
      // an unsupported horizontal-cylinder overhang
      hull() {
        translate([-out_w/2 - 8, -6, floor_t + plenum_h/2]) cube([e, 12, e]);
        translate([-out_w/2 - e, -6, floor_t + plenum_h/2 - 8]) cube([e, 12, e]);
        translate([-out_w/2 - e, -6, floor_t + plenum_h/2]) cube([e, 12, e]);
      }
      // deck ledges: chamfered stubs at plenum height (2 per long wall, 1 per end)
      for (p=[[pocket_cx1,-1],[pocket_cx1,1],[pocket_cx2,-1],[pocket_cx2,1]])
        translate([p[0]-3, p[1]*int_d/2 - (p[1]>0 ? 3 : 0), 0]) ledge();
      for (sx=[-1,1])
        translate([sx*int_w/2 - (sx>0 ? 3 : 0), -3, 0]) rotate([0,0,0]) ledge_end(sx);
      // plinth: a perimeter skirt, NOT feet. Cone feet put four 10 mm circles on the
      // bed and left the whole floor bridging 8 mm of air — unprintable without a
      // support raft under the largest part. A closed skirt rises from the bed and
      // the floor bridges it, same trick as the lid skirt; one centre rib halves the
      // span. Air gap under the box is unchanged.
      translate([-out_w/2, -out_d/2, -foot_h]) difference() {
        cube([out_w, out_d, foot_h + e]);
        translate([skin, skin, -e]) cube([out_w - 2*skin, out_d - 2*skin, foot_h + 3*e]);
      }
      translate([-skin/2, -out_d/2, -foot_h]) cube([skin, out_d, foot_h + e]);
    }
    // inlet bore: minimal-contact — 3 ribs inside a loose bore guide the tube,
    // so the aluminum (running near source temp end to end) barely touches PC.
    // No rib at top: the printed tunnel's top bridge sags a little, and sag must
    // land on open clearance, never on the surface that locates the liner.
    translate([-out_w/2 - 8 - e, 0, floor_t + plenum_h/2]) rotate([0, 90, 0]) {
      difference() {
        cylinder(d=liner_od + 1.4, h=8 + 2*skin + gap + 3*e);
        for (a=[30, 150, 270]) rotate([0, 0, a])
          translate([liner_od/2 + 0.2, -1, -e]) cube([1.2, 2, 8 + 2*skin + gap + 5*e]);
      }
    }
    // probe port, right end wall, mid-height above deck: 6.5 mm for a K-type bead
    translate([out_w/2 - 2*skin - gap - skin - e, 0, floor_t + plenum_h + deck_t + 20])
      rotate([0, 90, 0]) cylinder(d=6.5, h=2*skin + gap + 4*e);
    // deflector grooves in plenum floor near far end (BOM aluminum L-sheet slides in)
    translate([int_w/2 - 25, -int_d/2, floor_t - e]) cube([1.6, int_d, 2 + e]);
  }
}
module ledge() { // 6x3x3 stub, 45-degree underside so it prints without support
  translate([0, 0, floor_t + plenum_h - 3])
    hull() { translate([0,0,3]) cube([6, 3, e]); translate([2,0,0]) cube([2, 3, e]); }
}
module ledge_end(sx) {
  translate([0, 0, floor_t + plenum_h - 3])
    hull() { translate([0,0,3]) cube([3, 6, e]); translate([sx>0 ? 0 : 1, 2, 0]) cube([2, 2, e]); }
}

// ================================================================ deck (drop-in)
module deck() {
  difference() {
    union() {
      cube([int_w - 0.6, int_d - 0.6, deck_t], center=true);
      // pocket corner L-ribs, 12 tall — locate the shoe, touch it on edges only.
      // One (+,+) L built with its arms overlapping in a 2x2 corner block, mirrored
      // to the other corners, so every union is solid rather than edge-tangent.
      for (cx=[pocket_cx1, pocket_cx2], sx=[-1,1], sy=[-1,1])
        translate([cx + sx*(shoe_w/2 + 0.8), sy*(shoe_t/2 + 0.8), deck_t/2 - e])
          scale([sx, sy, 1]) {
            translate([-8, 0, 0]) cube([10, 2, 12]);   // along the big face
            translate([0, -8, 0]) cube([2, 10, 12]);   // along the shoe end
          }
      // 3 dome bumps per pocket: the shoe stands on points, not on a plane
      for (cx=[pocket_cx1, pocket_cx2], p=[[-6,0],[6,-2],[6,2]])
        translate([cx + p[0], p[1], deck_t/2 - 0.4]) sphere(d=3);
    }
    // jet rows flanking each big face (advisor: never under the shoe — ribs block it)
    for (cx=[pocket_cx1, pocket_cx2], sy=[-1,1], i=[0:jets_per_row-1])
      translate([cx - shoe_w/2 + i*shoe_w/(jets_per_row-1),
                 sy*(shoe_t/2 + jet_off), 0])
        cylinder(d=jet_d, h=deck_t + 2, center=true);
    // end bleeds so the plenum's far corners are not dead
    for (sx=[-1,1]) translate([sx*(int_w/2 - 8), 0, 0])
      cylinder(d=jet_d, h=deck_t + 2, center=true);
  }
}

// ================================================================ lid + cap
module lid() {
  difference() {
    union() {
      cube([out_w, out_d, 3], center=true);
      translate([0, 0, -3]) difference() {   // skirt registering inside inner skin
        cube([int_w - 0.8, int_d - 0.8, 3], center=true);
        cube([int_w - 0.8 - 2*skin, int_d - 0.8 - 2*skin, 3 + e], center=true); }
      for (sx=[-1,1]) translate([sx*(out_w/2 - 6), 0, 3]) // grip bars
        cube([6, out_d - 20, 3], center=true);
      // standoff bumps live HERE, on the lid's top face, not under the cap: nubs on
      // the cap's underside would land four points on the bed and leave its plate
      // bridging air. The cap drops onto these, pins locate it, and every surface
      // that sets the exhaust gap (A3) prints as a vertical feature.
      for (cx=[pocket_cx1, pocket_cx2], sx=[-1,1], sy=[-1,1])
        translate([cx + sx*(slot_w/2 + 3), sy*(slot_d/2 + 3), 1.5]) {
          cylinder(d=5, h=cap_standoff);
          cylinder(d=2.6, h=cap_standoff + 4);
        }
    }
    for (cx=[pocket_cx1, pocket_cx2])       // shoe slots
      translate([cx, 0, 0]) cube([slot_w, slot_d, 10], center=true);
    for (sy=[-1,1])                          // exhaust vents, far (right) end
      translate([int_w/2 - 10, sy*(int_d/2 - 6), 0])
        cylinder(d=vent_d, h=10, center=true);
  }
}
module cap() {
  difference() {
    union() {
      cube([cap_w, cap_d, 2], center=true);
      translate([0, 0, 1]) hull() {          // grip fin, grabbed bare-handed when warm
        cube([24, 3, e], center=true);
        translate([0, 0, 14]) cube([14, 3, e], center=true); }
    }
    // sockets over the lid's locating pins — holes, so the cap prints flat, plate down
    for (sx=[-1,1], sy=[-1,1])
      translate([sx*(slot_w/2 + 3), sy*(slot_d/2 + 3), 0])
        cylinder(d=3.2, h=4, center=true);
    // notch a shank could pass if Q1 says the shoes carry handles
    translate([cap_w/2 - 2, 0, 0]) cube([8.1, 8, 6], center=true);
  }
}

// ================================================================ emit
if (part == "body") body();
if (part == "deck") deck();
if (part == "lid")  lid();
if (part == "cap")  cap();
if (part == "preview") {
  difference() { body(); translate([0, -60, -20]) cube([200, 60, 150]); } // cutaway
  translate([0, 0, floor_t + plenum_h + deck_t/2]) deck();
  translate([0, 0, out_h + 1.5 + 3]) lid();
  for (cx=[pocket_cx1, pocket_cx2]) {
    translate([cx, 0, out_h + 6 + cap_standoff]) cap();
    color("chocolate") translate([cx, 0, floor_t + plenum_h + deck_t + shoe_h/2 + 1.5])
      cube([shoe_w, shoe_t, shoe_h], center=true);   // the copper shoes, for scale
  }
}
