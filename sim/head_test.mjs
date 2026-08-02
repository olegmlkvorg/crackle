import { readFileSync } from 'node:fs';
import { parseBinarySTL, createSim, analyzeChute } from './sim_core.mjs';
// Drop marbles into the sort head's BOWL at random-ish offsets, the way a hand pours them,
// and see where each one ends up. The head must fix the aim the chute cannot tolerate.
const { positions } = parseBinarySTL(readFileSync(process.argv[2]));
const g = analyzeChute(positions);
const top = g.bbox.max[2] - 4, bot = g.bbox.min[2];
for (const d of [12, 16]) {
  for (const off of [0, 15, 30, 40]) {
    const sim = await createSim(positions, { marbleRadiusMM: d / 2, entrySpeedMM: 0 });
    sim.drop([off, 0, top], [0, 0, 0]);
    let s, minZ = 1e9, lastMove = 0;
    for (let i = 0; i < 6 * 480; i++) {
      s = sim.step();
      if (s.zMM < minZ - 0.5) { minZ = s.zMM; lastMove = s.t; }
      if (s.zMM < bot + 3) break;
      if (s.t - lastMove > 1.2) break;
    }
    const through = s.zMM < bot + 8;
    const rOut = Math.hypot(s.posMM[0], s.posMM[1]);
    console.log(`  O${d} poured ${String(off).padStart(2)}mm off centre -> ` +
      (through ? `PASSED THROUGH, exits at r=${rOut.toFixed(1)}mm` : `HELD in the bowl (z=${minZ.toFixed(0)}mm)`));
  }
}
