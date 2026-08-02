import { readFileSync } from 'node:fs';
import { parseBinarySTL, createSim, analyzeChute } from './sim_core.mjs';
// RAW probe: no tracker, no early flags. Log the marble's radius and lateral speed as it
// crosses two planes we care about: the tube exit and the top of the chute wave zone.
const chute = parseBinarySTL(readFileSync(process.argv[2])).positions;
const head  = parseBinarySTL(readFileSync(process.argv[3])).positions;
const gc = analyzeChute(chute);
const lift = gc.bbox.max[2] - 16.0;
const merged = new Float32Array(chute.length + head.length);
merged.set(chute, 0);
for (let i = 0; i < head.length; i += 3) {
  merged[chute.length + i] = head[i];
  merged[chute.length + i+1] = head[i+1];
  merged[chute.length + i+2] = head[i+2] + lift;
}
const g = analyzeChute(merged);
const bowlZ = g.bbox.max[2] - 4;
const zTubeExit = Number(process.argv[4]);      // in MERGED coords
const zWaveTop  = Number(process.argv[5]);
console.log(`probe planes: tube exit z=${zTubeExit}  wave top z=${zWaveTop}  pour z=${bowlZ.toFixed(1)}`);
// Nine pours, not three. The outcome is decided by one chaotic impact, so a 3-sample gate cannot
// tell a design change from noise -- measured 2026-08-03, three geometries that differ by nothing
// physical came out 1/3, 2/3 and 1/3.
let nSort = 0, nTot = 0;
for (const off of [0, 5, 10, 15, 20, 25, 30, 35, 40]) {
  const sim = await createSim(merged, { marbleRadiusMM: Number(process.argv[6] ?? 12) / 2,
                                        entrySpeedMM: 0 });
  sim.drop([off, 0, bowlZ], [0, 0, 0]);
  let s, prev = null, atExit = null, atWave = null, minZ = 1e9, lastMove = 0;
  for (let i = 0; i < 14 * 480; i++) {
    s = sim.step();
    if (prev && prev.zMM > zTubeExit && s.zMM <= zTubeExit) atExit = s;
    if (prev && prev.zMM > zWaveTop  && s.zMM <= zWaveTop)  atWave = s;
    prev = s;
    if (s.zMM < minZ - 0.5) { minZ = s.zMM; lastMove = s.t; }
    if (s.zMM < gc.bbox.min[2] + 25) break;
    if (s.t - lastMove > 1.5) break;
  }
  const f = (x) => x.toFixed(2).padStart(7);
  const line = (tag, q) => q ? `${tag} r=${f(q.rMM)}mm  vlat=${f(Math.hypot(q.velMM[0], q.velMM[1]))}mm/s  vz=${f(q.velMM[2])}  t=${q.t.toFixed(3)}` : `${tag} never crossed`;
  console.log(`\n pour ${off}mm off centre`);
  console.log('   ' + line('tube exit ', atExit));
  console.log('   ' + line('wave top  ', atWave));
  const shaft = s.zMM < gc.bbox.min[2] + 30 && s.rMM < 6;
  nTot++; if (shaft) nSort++;
  console.log(`   final z=${s.zMM.toFixed(1)} r=${s.rMM.toFixed(1)} t=${s.t.toFixed(2)}  ` +
    (shaft ? 'SHAFT' : 'RODE/HELD'));
}
console.log(`\nSHAFT ${nSort}/${nTot}`);
