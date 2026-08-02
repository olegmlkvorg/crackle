import { readFileSync } from 'node:fs';
import { parseBinarySTL, createSim, analyzeChute } from './sim_core.mjs';
// WHY the tube lets the marble out sideways. Split the lateral velocity into RADIAL (across the
// bore, which a wall bounce can damp) and AZIMUTHAL (around the bore, which nothing in a round
// tube opposes). No tracker, no flags: raw state, logged inside the tube.
//   node sort_head_trace.mjs <chute> <head> <zTubeBottom> <zTubeTop> [marbleD]
const chute = parseBinarySTL(readFileSync(process.argv[2])).positions;
const head = parseBinarySTL(readFileSync(process.argv[3])).positions;
const zBot = Number(process.argv[4]), zTop = Number(process.argv[5]);
const D = Number(process.argv[6] ?? 12);
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
console.log(`tube z ${zBot}..${zTop}  pour z=${bowlZ.toFixed(1)}  marble O${D}`);
for (const off of [10, 20, 35]) {
  const sim = await createSim(merged, { marbleRadiusMM: D / 2, entrySpeedMM: 0 });
  sim.drop([off, 0, bowlZ], [0, 0, 0]);
  console.log(`\n pour ${off}mm off centre        r     vr      vth      vz`);
  let s, minZ = 1e9, lastMove = 0, next = zTop, printed = 0;
  for (let i = 0; i < 14 * 480; i++) {
    s = sim.step();
    if (s.zMM <= next && s.zMM >= zBot - 12) {
      const [x, y] = [s.posMM[0], s.posMM[1]];
      const r = Math.hypot(x, y) || 1e-9;
      const ur = [x / r, y / r], ut = [-y / r, x / r];
      const vr = s.velMM[0] * ur[0] + s.velMM[1] * ur[1];
      const vt = s.velMM[0] * ut[0] + s.velMM[1] * ut[1];
      const f = (q) => q.toFixed(2).padStart(8);
      console.log(`   z=${s.zMM.toFixed(1).padStart(6)} ${f(r)}${f(vr)}${f(vt)}${f(s.velMM[2])}`);
      next = s.zMM - (zTop - zBot) / 8;
      printed++;
    }
    if (s.zMM < minZ - 0.5) { minZ = s.zMM; lastMove = s.t; }
    if (s.zMM < zBot - 12) break;
    if (s.t - lastMove > 1.5) break;
  }
  if (!printed) console.log('   never entered the tube');
}
