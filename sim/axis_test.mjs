import { readFileSync } from 'node:fs';
import { parseBinarySTL, createSim, ChuteTracker } from './sim_core.mjs';
const stl = process.argv[2];
const { positions } = parseBinarySTL(readFileSync(stl));
for (const d of [14, 16]) {
  const sim = await createSim(positions, { marbleRadiusMM: d / 2, entrySpeedMM: 0 });
  const g = sim.geo;
  // drop it ON THE AXIS from above the helix, at rest: what a funnel actually delivers
  const zTop = g.zone.max + 0.10 * g.H;
  const c = g.centerAt(zTop);
  sim.drop([c[0], c[1], zTop], [0, 0, 0]);
  const t = new ChuteTracker(g, { minTurns: 1, maxTime: 12 });
  let s, lastR = 0, maxR = 0;
  for (let i = 0; i < 12 * 480; i++) { s = sim.step(); maxR = Math.max(maxR, s.rMM); if (t.update(s)) break; }
  const m = t.measurements();
  const exited = t.exitT !== null;
  const straight = exited && maxR < 6 && m.turns < 0.5;
  console.log(`O${d} dropped ON THE AXIS at rest: ` +
    `maxR=${maxR.toFixed(1)}mm turns=${m.turns.toFixed(2)} lowestZ=${m.lowestZMM.toFixed(0)}mm ` +
    `exit=${exited ? m.exitTimeS.toFixed(2) + 's' : 'never'}  -> ` +
    (straight ? 'FELL STRAIGHT THROUGH THE SHAFT' : exited ? 'CAUGHT BY THE RAIL, then rode down' : 'STUCK'));
}
