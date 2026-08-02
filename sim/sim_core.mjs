// sim_core.mjs — marble-chute physics core. SAME file runs headless under node
// (qa_sim.mjs) and inside the browser bundle (viewer.html). That is the point:
// the QA gate and the interactive page step identical code on identical geometry.
//
// Engine: @dimforge/rapier3d-compat — deterministic fixed-step rigid-body engine
// with trimesh colliders; the -compat build inlines the wasm as base64 so one
// bundle runs in node and in a file:// page with no network.
//
// Units: 1 world unit = 1 cm (mm * 0.1). Rapier's solver tolerances are tuned
// for ~1-unit bodies; a 0.8-unit marble in a 6x24 world sits in that range,
// where raw mm (8 vs 235) would not. Gravity 981 cm/s^2.
//
// Material constants (provenance: ASSUMED, typical glass-on-PLA ranges — not
// measured; the QA verdict must hold across a friction sweep before it is
// treated as a physical prediction):
//   friction 0.5, restitution 0.15 (marble) / 0.1 (chute),
//   angularDamping 0.05 as a rolling-resistance surrogate (rapier has none).

import RAPIER from '@dimforge/rapier3d-compat';

export const MM = 0.1; // mm -> world units (cm)

let rapierReady = null;
export function initEngine() {
  if (!rapierReady) {
    // rapier3d-compat 0.19.3 internally trips wasm-bindgen's "deprecated
    // parameters" console.warn (upstream cosmetic issue); keep QA output clean.
    const warn = console.warn;
    console.warn = (...a) => {
      if (!String(a[0]).includes('deprecated parameters')) warn(...a);
    };
    rapierReady = RAPIER.init().finally(() => { console.warn = warn; });
  }
  return rapierReady.then(() => RAPIER);
}

// ---------------------------------------------------------------- STL parsing

// Binary STL -> vertex soup in mm. Accepts ArrayBuffer or Uint8Array.
export function parseBinarySTL(buf) {
  const u8 = buf instanceof Uint8Array ? buf : new Uint8Array(buf);
  const dv = new DataView(u8.buffer, u8.byteOffset, u8.byteLength);
  const triCount = dv.getUint32(80, true);
  const expect = 84 + triCount * 50;
  if (u8.byteLength < expect) {
    throw new Error(`STL truncated: need ${expect} bytes, have ${u8.byteLength}`);
  }
  const positions = new Float32Array(triCount * 9);
  for (let i = 0; i < triCount; i++) {
    const off = 84 + i * 50 + 12; // skip normal
    for (let k = 0; k < 9; k++) {
      positions[i * 9 + k] = dv.getFloat32(off + k * 4, true);
    }
  }
  return { positions, triCount };
}

// ------------------------------------------------------- geometry measurement

// All QA thresholds are MEASURED off the mesh being tested, never hardcoded to
// the snapshot, so the same gate runs on variants (and fails the bad ones for
// the geometry they actually have).
export function analyzeChute(positions) {
  let minX = 1e30, minY = 1e30, minZ = 1e30, maxX = -1e30, maxY = -1e30, maxZ = -1e30;
  const n = positions.length / 3;
  for (let i = 0; i < n; i++) {
    const x = positions[i * 3], y = positions[i * 3 + 1], z = positions[i * 3 + 2];
    if (x < minX) minX = x; if (x > maxX) maxX = x;
    if (y < minY) minY = y; if (y > maxY) maxY = y;
    if (z < minZ) minZ = z; if (z > maxZ) maxZ = z;
  }
  const cx = (minX + maxX) / 2, cy = (minY + maxY) / 2;
  const H = maxZ - minZ;
  // Helix zone: middle band, clear of the entry funnel above and outrun below.
  const zone = { min: minZ + 0.25 * H, max: minZ + 0.76 * H };
  // Rail crest radius = outermost surface inside the helix zone.
  let crestR = 0;
  for (let i = 0; i < n; i++) {
    const z = positions[i * 3 + 2];
    if (z > zone.min && z < zone.max) {
      const r = Math.hypot(positions[i * 3] - cx, positions[i * 3 + 1] - cy);
      if (r > crestR) crestR = r;
    }
  }
  // Handedness: does crest z rise or fall with theta? Bin crest verts by theta
  // over roughly one turn near the zone bottom, median adjacent-bin z step.
  const NB = 24;
  const binZ = new Array(NB).fill(Infinity);
  for (let i = 0; i < n; i++) {
    const z = positions[i * 3 + 2];
    if (z < zone.min || z > zone.min + 0.35 * H) continue;
    const x = positions[i * 3] - cx, y = positions[i * 3 + 1] - cy;
    const r = Math.hypot(x, y);
    if (r < 0.97 * crestR) continue;
    const b = Math.floor(((Math.atan2(y, x) + Math.PI) / (2 * Math.PI)) * NB) % NB;
    if (z < binZ[b]) binZ[b] = z;
  }
  const diffs = [];
  for (let b = 0; b < NB; b++) {
    const a = binZ[b], c = binZ[(b + 1) % NB];
    if (isFinite(a) && isFinite(c)) diffs.push(c - a);
  }
  diffs.sort((a, b) => a - b);
  const medianStep = diffs.length ? diffs[Math.floor(diffs.length / 2)] : 0;
  // z rises with theta => marble descends in the -theta direction.
  const descentDir = medianStep > 0 ? -1 : 1;
  // Entry: angle where the funnel bottom reaches its smallest radius (the
  // hand-off from funnel into gutter), just above the helix zone.
  const eb0 = zone.max + 0.02 * H, eb1 = zone.max + 0.12 * H;
  const NE = 24;
  const entryMinR = new Array(NE).fill(Infinity);
  for (let i = 0; i < n; i++) {
    const z = positions[i * 3 + 2];
    if (z < eb0 || z > eb1) continue;
    const x = positions[i * 3] - cx, y = positions[i * 3 + 1] - cy;
    const b = Math.floor(((Math.atan2(y, x) + Math.PI) / (2 * Math.PI)) * NE) % NE;
    const r = Math.hypot(x, y);
    if (r < entryMinR[b]) entryMinR[b] = r;
  }
  let entryBin = 0, best = Infinity;
  for (let b = 0; b < NE; b++) if (entryMinR[b] < best) { best = entryMinR[b]; entryBin = b; }
  const entryTheta = ((entryBin + 0.5) / NE) * 2 * Math.PI - Math.PI;
  const entryR = Math.min(best + 4, crestR - 6); // ride the surface, clear of crest
  const entry = {
    posMM: [cx + entryR * Math.cos(entryTheta), cy + entryR * Math.sin(entryTheta), eb1 + 6],
    // small tangential shove in the descent direction (configurable upstream)
    dirTangent: [descentDir * -Math.sin(entryTheta), descentDir * Math.cos(entryTheta), 0],
  };
  return {
    bbox: { min: [minX, minY, minZ], max: [maxX, maxY, maxZ] },
    center: [cx, cy], H, zone, crestR, descentDir, entry,
    exitZ: minZ + 0.15 * H,
  };
}

// ----------------------------------------------------------------- simulation

export const DEFAULTS = {
  dt: 1 / 480,           // fixed step; CCD on the marble handles the ~1.5mm ribbon
  marbleRadiusMM: 8,     // O16 marble
  marbleMassG: 6,
  friction: 0.5,         // ASSUMED glass-on-PLA
  restitution: 0.15,     // ASSUMED
  angularDamping: 0.05,  // ASSUMED rolling-resistance surrogate
  entrySpeedMM: 100,     // initial tangential speed, mm/s
};

export async function createSim(positions, opts = {}) {
  const R = await initEngine();
  const o = { ...DEFAULTS, ...opts };
  const geo = analyzeChute(positions);

  const world = new R.World({ x: 0, y: 0, z: -981 });
  world.integrationParameters.dt = o.dt;

  const verts = new Float32Array(positions.length);
  for (let i = 0; i < positions.length; i++) verts[i] = positions[i] * MM;
  const indices = new Uint32Array(positions.length / 3);
  for (let i = 0; i < indices.length; i++) indices[i] = i;
  const chuteBody = world.createRigidBody(R.RigidBodyDesc.fixed());
  world.createCollider(
    R.ColliderDesc.trimesh(verts, indices).setFriction(o.friction).setRestitution(0.1),
    chuteBody,
  );

  const rad = o.marbleRadiusMM * MM;
  const density = o.marbleMassG / ((4 / 3) * Math.PI * rad ** 3);
  const marbleBody = world.createRigidBody(
    R.RigidBodyDesc.dynamic().setCcdEnabled(true).setAngularDamping(o.angularDamping),
  );
  world.createCollider(
    R.ColliderDesc.ball(rad).setFriction(o.friction).setRestitution(o.restitution).setDensity(density),
    marbleBody,
  );

  let t = 0;
  let prevTheta = null, unwrapped = 0;

  function drop(posMM, velMM) {
    const p = posMM ?? geo.entry.posMM;
    const v = velMM ?? geo.entry.dirTangent.map((c) => c * o.entrySpeedMM);
    marbleBody.setTranslation({ x: p[0] * MM, y: p[1] * MM, z: p[2] * MM }, true);
    marbleBody.setLinvel({ x: v[0] * MM, y: v[1] * MM, z: v[2] * MM }, true);
    marbleBody.setAngvel({ x: 0, y: 0, z: 0 }, true);
    t = 0; prevTheta = null; unwrapped = 0;
  }

  function state() {
    const p = marbleBody.translation(), v = marbleBody.linvel();
    const x = p.x / MM - geo.center[0], y = p.y / MM - geo.center[1];
    const theta = Math.atan2(y, x);
    if (prevTheta !== null) {
      let d = theta - prevTheta;
      if (d > Math.PI) d -= 2 * Math.PI;
      if (d < -Math.PI) d += 2 * Math.PI;
      unwrapped += d;
    }
    prevTheta = theta;
    return {
      t,
      posMM: [p.x / MM, p.y / MM, p.z / MM],
      velMM: [v.x / MM, v.y / MM, v.z / MM],
      rMM: Math.hypot(x, y),
      zMM: p.z / MM,
      unwrappedDeg: (unwrapped * 180) / Math.PI,
    };
  }

  function step() {
    world.step();
    t += o.dt;
    return state();
  }

  drop();
  return { world, marbleBody, geo, opts: o, drop, step, state, RAPIER: R };
}

// ------------------------------------------------------------------ QA gates

// ChuteTracker consumes the per-step state stream and renders the verdict.
// qa_sim.mjs (headless gate) and viewer.html (live HUD) share THIS logic.
//
// Turn counting is gated on r > minRideR: near the axis atan2 is noise and a
// marble plunging down the open center shaft racked up 3.65 fake "turns" —
// caught when the known-bad variant PASSED the first gate version. Same event
// added the CENTER-DROP gate: sustained r < centerR while in the helix zone
// means the marble is falling inside the shaft, not riding the gutter.
export class ChuteTracker {
  constructor(geo, o = {}) {
    this.geo = geo;
    this.minTurns = o.minTurns ?? 3;
    this.maxTime = o.maxTime ?? 30;      // s of sim time to reach the exit
    this.stallLimit = o.stallLimit ?? 5; // s without >1mm of new descent
    this.minRideR = o.minRideR ?? 6;     // mm: below this, angle deltas are not gutter travel
    this.centerR = o.centerR ?? 5;       // mm: sustained center-shaft occupancy = drop-through
    this.centerHold = o.centerHold ?? 0.05; // s
    this.maxRInZone = 0; this.maxRAt = null;
    this.zoneEntered = false; this.zoneEnterT = null;
    this.gutterAngle = 0; this.prevUnwrapped = null; this.turns = 0;
    this.centerT0 = null;
    this.minZ = Infinity; this.minZAt = 0; this.stallTime = 0;
    this.exitT = null;
    this.escaped = null;
  }
  update(s) {
    const { zone, crestR, exitZ } = this.geo;
    const inZone = s.zMM > zone.min && s.zMM < zone.max;
    const d = this.prevUnwrapped === null ? 0 : s.unwrappedDeg - this.prevUnwrapped;
    this.prevUnwrapped = s.unwrappedDeg;
    if (inZone) {
      if (!this.zoneEntered) { this.zoneEntered = true; this.zoneEnterT = s.t; }
      if (s.rMM > this.minRideR) this.gutterAngle += d;
      this.turns = Math.abs(this.gutterAngle) / 360;
      if (s.rMM > this.maxRInZone) {
        this.maxRInZone = s.rMM;
        this.maxRAt = { t: s.t, zMM: s.zMM };
      }
      if (s.rMM > crestR && !this.escaped) {
        this.escaped = { kind: 'HOP', t: s.t, rMM: s.rMM, zMM: s.zMM };
      }
      if (s.rMM < this.centerR) {
        if (this.centerT0 === null) this.centerT0 = s.t;
        if (s.t - this.centerT0 > this.centerHold && !this.escaped) {
          this.escaped = { kind: 'CENTER-DROP', t: s.t, rMM: s.rMM, zMM: s.zMM };
        }
      } else {
        this.centerT0 = null;
      }
    }
    if (s.zMM < this.minZ - 1) { this.minZ = s.zMM; this.minZAt = s.t; }
    this.stallTime = Math.max(this.stallTime, s.t - this.minZAt);
    if (this.exitT === null && this.zoneEntered && s.zMM < exitZ) this.exitT = s.t;
    return this.exitT !== null || this.escaped !== null || s.t > this.maxTime + 1;
  }
  verdict() {
    const fails = [];
    const m = this.measurements();
    if (this.escaped?.kind === 'HOP') {
      fails.push(`HOP: marble crossed the rail — r=${this.escaped.rMM.toFixed(1)}mm > crest ` +
        `${this.geo.crestR.toFixed(1)}mm at z=${this.escaped.zMM.toFixed(1)}mm, t=${this.escaped.t.toFixed(2)}s`);
    }
    if (this.escaped?.kind === 'CENTER-DROP') {
      fails.push(`CENTER-DROP: marble fell inside the center shaft, not the gutter — ` +
        `r=${this.escaped.rMM.toFixed(1)}mm < ${this.centerR}mm sustained at z=${this.escaped.zMM.toFixed(1)}mm, ` +
        `t=${this.escaped.t.toFixed(2)}s, gutter turns=${this.turns.toFixed(2)}`);
    }
    if (this.exitT !== null && this.turns < this.minTurns) {
      fails.push(`SHORT: only ${this.turns.toFixed(2)} gutter turns (r>${this.minRideR}mm) in the helix zone ` +
        `(need >= ${this.minTurns})`);
    }
    if (this.stallTime > this.stallLimit && !this.escaped) {
      fails.push(`STALL: ${this.stallTime.toFixed(1)}s without new descent (limit ${this.stallLimit}s), ` +
        `stuck near z=${this.minZ.toFixed(1)}mm after ${this.turns.toFixed(2)} turns`);
    }
    if (this.exitT === null && !this.escaped) {
      fails.push(`NO-EXIT: never reached exit z<${this.geo.exitZ.toFixed(1)}mm within ` +
        `${this.maxTime}s (lowest z=${this.minZ.toFixed(1)}mm, ${this.turns.toFixed(2)} turns)`);
    }
    return { pass: fails.length === 0, fails, ...m };
  }
  measurements() {
    return {
      turns: this.turns,
      maxRInZoneMM: this.maxRInZone,
      crestRMM: this.geo.crestR,
      railMarginMM: this.geo.crestR - this.maxRInZone,
      descentTimeS: this.exitT !== null && this.zoneEnterT !== null ? this.exitT - this.zoneEnterT : null,
      exitTimeS: this.exitT,
      stallTimeS: this.stallTime,
      lowestZMM: this.minZ,
    };
  }
}
