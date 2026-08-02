import { readFileSync } from 'node:fs';
import { parseBinarySTL, createSim, analyzeChute } from './sim_core.mjs';
const { positions } = parseBinarySTL(readFileSync(process.argv[2]));
const g = analyzeChute(positions);
const floor = g.bbox.min[2], zTop = g.zone.max + 0.10 * g.H, c = g.centerAt(zTop);
console.log('How far off-centre can a small marble be dropped and still fall clear?');
console.log('(at rest, no sideways speed: the question is aim, not throw)\n');
for (const off of [0, 2, 4, 6, 8, 10, 14]) {
  const sim = await createSim(positions, { marbleRadiusMM: 6, entrySpeedMM: 0 });
  sim.drop([c[0] + off, c[1], zTop], [0, 0, 0]);
  let s, maxR = 0, minZ = 1e9, lastMove = 0;
  for (let i = 0; i < 8 * 480; i++) {
    s = sim.step(); maxR = Math.max(maxR, s.rMM);
    if (s.zMM < minZ - 0.5) { minZ = s.zMM; lastMove = s.t; }
    if (s.zMM < floor + 22) break;
    if (s.t - lastMove > 1.5) break;
  }
  const clear = s.zMM < floor + 25 && maxR < 6;
  console.log(`  dropped ${String(off).padStart(2)}mm off centre -> maxR=${maxR.toFixed(1)}mm ` +
    `t=${s.t.toFixed(2)}s  ${clear ? 'FELL CLEAR' : 'caught by the rail, rode down'}`);
}
