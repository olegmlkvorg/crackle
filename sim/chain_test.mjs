import { readFileSync } from 'node:fs';
import { parseBinarySTL, createSim, analyzeChute } from './sim_core.mjs';
// END TO END. The head aims, then the marble falls through the head's own coupling bulge where
// nothing guides it, then into the chute. Whether the sort SURVIVES that chain is the only
// question that matters, and it cannot be answered by testing the parts separately.
const chute = parseBinarySTL(readFileSync(process.argv[2])).positions;
const head = parseBinarySTL(readFileSync(process.argv[3])).positions;
const gc = analyzeChute(chute);
const lift = gc.bbox.max[2] - 16.0;                 // head spigot seats in the chute socket
const merged = new Float32Array(chute.length + head.length);
merged.set(chute, 0);
for (let i = 0; i < head.length; i += 3) {
  merged[chute.length + i] = head[i];
  merged[chute.length + i + 1] = head[i + 1];
  merged[chute.length + i + 2] = head[i + 2] + lift;
}
const g = analyzeChute(merged);
const bowlZ = g.bbox.max[2] - 4, floor = gc.bbox.min[2];
console.log(`chain: chute ${gc.bbox.max[2].toFixed(0)}mm + head seated at ${lift.toFixed(0)}mm ` +
  `= ${g.bbox.max[2].toFixed(0)}mm total\n`);
for (const d of [12, 16]) {
  for (const off of [0, 20, 35]) {
    const sim = await createSim(merged, { marbleRadiusMM: d / 2, entrySpeedMM: 0 });
    sim.drop([off, 0, bowlZ], [0, 0, 0]);
    let s, minZ = 1e9, lastMove = 0, maxRlow = 0;
    for (let i = 0; i < 14 * 480; i++) {
      s = sim.step();
      if (s.zMM < minZ - 0.5) { minZ = s.zMM; lastMove = s.t; }
      if (s.zMM < gc.bbox.max[2] - 60) maxRlow = Math.max(maxRlow, s.rMM);
      if (s.zMM < floor + 25) break;
      if (s.t - lastMove > 1.5) break;
    }
    const out = s.zMM < floor + 30;
    const shaft = out && maxRlow < 6;
    console.log(`  O${d} poured ${String(off).padStart(2)}mm off centre -> ` +
      (shaft ? `SORTED: fell the shaft, t=${s.t.toFixed(2)}s`
        : out ? `rode the spiral out, maxR=${maxRlow.toFixed(1)}mm t=${s.t.toFixed(2)}s`
          : `held/stopped at z=${minZ.toFixed(0)}mm`));
  }
}
