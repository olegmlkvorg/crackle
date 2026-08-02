// ADVERSARIAL chain probe. Written to FALSIFY sort_head_probe.mjs, not to agree with it.
//
// Two things sort_head_probe.mjs's verdict cannot see, both of which have produced wrong
// conclusions in this project before:
//   1. it calls SHAFT on the FINAL sample (z low + r<6). A marble that rode the spiral all the
//      way out and happened to fall through the exit spigot near the axis scores the same as one
//      that never touched the helix. So this probe tracks MAX radius over the whole descent
//      through the wave zone, which a rider cannot fake.
//   2. it never varies the ASSUMED material constants. So this sweeps friction / restitution /
//      angular damping.
//
// usage: node adv_chain.mjs <chute.stl> <head_seat0.stl> <marbleD> [friction] [restitution] [angDamp]
import { readFileSync } from 'node:fs';
import { parseBinarySTL, createSim, analyzeChute } from '../sim_core.mjs';

const chute = parseBinarySTL(readFileSync(process.argv[2])).positions;
const head = parseBinarySTL(readFileSync(process.argv[3])).positions;
const D = Number(process.argv[4] ?? 10);
const friction = Number(process.argv[5] ?? 0.5);
const restitution = Number(process.argv[6] ?? 0.15);
const angularDamping = Number(process.argv[7] ?? 0.05);

const gc = analyzeChute(chute);
const lift = gc.bbox.max[2] - 16.0;
const merged = new Float32Array(chute.length + head.length);
merged.set(chute, 0);
for (let i = 0; i < head.length; i += 3) {
  merged[chute.length + i] = head[i];
  merged[chute.length + i + 1] = head[i + 1];
  merged[chute.length + i + 2] = head[i + 2] + lift;
}
const g = analyzeChute(merged);
const bowlZ = g.bbox.max[2] - 4;
const zTop = gc.bbox.max[2], zBot = gc.bbox.min[2];
// the chute's own helix zone, measured off the CHUTE mesh alone (the merged bbox is polluted by
// the head, so g.zone is not the chute's wave band)
const waveLo = zBot + 0.25 * gc.H, waveHi = zBot + 0.76 * gc.H;

let nAxis = 0, nTot = 0;
const rows = [];
for (const off of [0, 5, 10, 15, 20, 25, 30, 35, 40]) {
  const sim = await createSim(merged, {
    marbleRadiusMM: D / 2, entrySpeedMM: 0, friction, restitution, angularDamping,
  });
  sim.drop([off, 0, bowlZ], [0, 0, 0]);
  let s, minZ = 1e9, lastMove = 0, maxRwave = 0, maxRbelowSeat = 0, turns = 0, prevU = null;
  for (let i = 0; i < 20 * 480; i++) {
    s = sim.step();
    if (s.zMM < zTop && s.rMM > maxRbelowSeat) maxRbelowSeat = s.rMM;
    if (s.zMM > waveLo && s.zMM < waveHi) {
      if (s.rMM > maxRwave) maxRwave = s.rMM;
      if (prevU !== null && s.rMM > 6) turns += Math.abs(s.unwrappedDeg - prevU);
      prevU = s.unwrappedDeg;
    }
    if (s.zMM < minZ - 0.5) { minZ = s.zMM; lastMove = s.t; }
    if (s.zMM < zBot + 25) break;
    if (s.t - lastMove > 1.5) break;
  }
  // STRICT verdict: it fell the axis only if it NEVER got near the rail while in the wave band.
  const out = s.zMM < zBot + 30;
  const axis = out && maxRwave < 6;
  nTot++; if (axis) nAxis++;
  rows.push(`  off ${String(off).padStart(2)}mm  final z=${s.zMM.toFixed(1)} r=${s.rMM.toFixed(2)} ` +
    `t=${s.t.toFixed(2)}s  maxR-in-wave=${maxRwave.toFixed(2)}mm  maxR-below-seat=${maxRbelowSeat.toFixed(2)}mm ` +
    `gutterDeg=${turns.toFixed(0)}  -> ${axis ? 'AXIS' : out ? 'RODE-OUT' : 'HELD'}`);
}
console.log(`O${D} friction=${friction} restitution=${restitution} angDamp=${angularDamping}  ` +
  `crest r=${gc.crestR.toFixed(2)} wave band z ${waveLo.toFixed(0)}..${waveHi.toFixed(0)}`);
console.log(rows.join('\n'));
console.log(`AXIS ${nAxis}/${nTot}`);
