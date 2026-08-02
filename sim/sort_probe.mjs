import { readFileSync } from 'node:fs';
import { parseBinarySTL, createSim, analyzeChute } from './sim_core.mjs';
// Deliberately NOT using ChuteTracker as the stop condition. Its CENTER-DROP flag ENDS the run,
// and reading lowestZ after that reports where the WATCHER stopped, not where the marble stopped.
// That inverted a conclusion once already.
const stl = process.argv[2];
const { positions } = parseBinarySTL(readFileSync(stl));
const g = analyzeChute(positions);
const floor = g.bbox.min[2];
async function run(d, mode) {
  const sim = await createSim(positions, { marbleRadiusMM: d / 2, entrySpeedMM: mode === 'axis' ? 0 : 100 });
  if (mode === 'axis') {
    const zTop = g.zone.max + 0.10 * g.H, c = g.centerAt(zTop);
    sim.drop([c[0], c[1], zTop], [0, 0, 0]);
  } else sim.drop();
  let s, minZ = 1e9, lastMove = 0, maxR = 0, turns0 = 0;
  for (let i = 0; i < 10 * 480; i++) {
    s = sim.step();
    maxR = Math.max(maxR, s.rMM);
    if (s.zMM < minZ - 0.5) { minZ = s.zMM; lastMove = s.t; }
    if (s.zMM < floor + 22) break;
    if (s.t - lastMove > 2.0) break;
  }
  const out = s.zMM < floor + 25;
  const spun = Math.abs(s.unwrappedDeg) / 360;
  return `O${d} ${mode.padEnd(6)} -> lowestZ=${minZ.toFixed(0)}mm maxR=${maxR.toFixed(1)}mm ` +
    `turns=${spun.toFixed(2)} t=${s.t.toFixed(2)}s  ${out ? (maxR < 6 ? 'FELL CLEAR DOWN THE SHAFT' : 'RODE THE SPIRAL OUT') : 'DID NOT EXIT'}`;
}
for (const [d, m] of [[12,'axis'],[16,'axis'],[12,'gutter'],[16,'gutter']]) console.log('  ' + await run(d, m));
