import { readFileSync } from 'node:fs';
import { parseBinarySTL, createSim, analyzeChute } from './sim_core.mjs';
const stl = process.argv[2];
const { positions } = parseBinarySTL(readFileSync(stl));
const g0 = analyzeChute(positions);
const zTop = g0.zone.max + 0.10 * g0.H;
const fit = g0.centerAt(zTop);
console.log(`fitted axis at z=${zTop.toFixed(0)}: [${fit[0].toFixed(2)}, ${fit[1].toFixed(2)}]  ` +
  `(offset ${Math.hypot(fit[0], fit[1]).toFixed(2)}mm from the true geometric axis 0,0)`);
for (const [label, c] of [['FITTED axis', fit], ['TRUE axis (0,0)', [0, 0]]]) {
  const sim = await createSim(positions, { marbleRadiusMM: 6, entrySpeedMM: 0 });
  sim.drop([c[0], c[1], zTop], [0, 0, 0]);
  let s, minZ = 1e9, lastMove = 0;
  for (let i = 0; i < 8 * 480; i++) {
    s = sim.step();
    if (s.zMM < minZ - 0.5) { minZ = s.zMM; lastMove = s.t; }
    if (s.zMM < g0.bbox.min[2] + 20) break;
    if (s.t - lastMove > 1.5) break;
  }
  const fell = s.zMM < g0.bbox.min[2] + 25;
  console.log(`  drop on ${label.padEnd(16)} -> lowestZ=${minZ.toFixed(0)}mm t=${s.t.toFixed(2)}s  ` +
    (fell ? 'FELL CLEAR THROUGH THE SHAFT' : 'STALLED'));
}
