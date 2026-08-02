#!/usr/bin/env node
// qa_sim.mjs — headless dynamic QA gate for printed-chute meshes.
//   node qa_sim.mjs <stl> --scenario chute [--speed mm/s] [--maxtime s] [--turns n]
// Exit 0 = ORBIT (captive, descends, exits). Exit 1 = FAIL with measurements.
// Steps the SAME sim_core the browser viewer runs.

import { readFileSync } from 'node:fs';
import { parseBinarySTL, createSim, ChuteTracker, DEFAULTS } from './sim_core.mjs';

function arg(name, dflt) {
  const i = process.argv.indexOf(`--${name}`);
  return i >= 0 ? process.argv[i + 1] : dflt;
}

const stlPath = process.argv[2];
if (!stlPath || stlPath.startsWith('--')) {
  console.error('usage: node qa_sim.mjs <stl> --scenario chute [--speed mm/s] [--maxtime s] [--turns n]');
  process.exit(2);
}
const scenario = arg('scenario', 'chute');
if (scenario !== 'chute') {
  console.error(`unknown scenario: ${scenario}`);
  process.exit(2);
}

const { positions, triCount } = parseBinarySTL(readFileSync(stlPath));
const sim = await createSim(positions, {
  entrySpeedMM: Number(arg('speed', DEFAULTS.entrySpeedMM)),
  friction: Number(arg('friction', DEFAULTS.friction)),
  restitution: Number(arg('restitution', DEFAULTS.restitution)),
});
const maxTime = Number(arg('maxtime', 30));
const tracker = new ChuteTracker(sim.geo, {
  maxTime,
  minTurns: Number(arg('turns', 3)),
});

const g = sim.geo;
console.log(`[qa_sim] ${stlPath}`);
console.log(`[qa_sim] tris=${triCount}  bbox z ${g.bbox.min[2].toFixed(1)}..${g.bbox.max[2].toFixed(1)}mm  ` +
  `crestR=${g.crestR.toFixed(1)}mm  helix zone z ${g.zone.min.toFixed(1)}..${g.zone.max.toFixed(1)}mm  ` +
  `exitZ<${g.exitZ.toFixed(1)}mm  descentDir=${g.descentDir > 0 ? '+theta' : '-theta'}`);
console.log(`[qa_sim] drop at [${g.entry.posMM.map((v) => v.toFixed(1)).join(', ')}]mm  ` +
  `speed=${sim.opts.entrySpeedMM}mm/s  dt=1/${Math.round(1 / sim.opts.dt)}  scenario=${scenario}`);

const maxSteps = Math.ceil((maxTime + 2) / sim.opts.dt);
for (let i = 0; i < maxSteps; i++) {
  const s = sim.step();
  if (tracker.update(s)) break;
}

const v = tracker.verdict();
const fmt = (x, d = 2) => (x === null ? 'n/a' : x.toFixed(d));
console.log(`[qa_sim] turns=${fmt(v.turns)}  maxR(zone)=${fmt(v.maxRInZoneMM, 1)}mm vs crest ${fmt(v.crestRMM, 1)}mm ` +
  `(margin ${fmt(v.railMarginMM, 1)}mm)  descent=${fmt(v.descentTimeS)}s  exit@${fmt(v.exitTimeS)}s  ` +
  `stall=${fmt(v.stallTimeS, 1)}s  lowestZ=${fmt(v.lowestZMM, 1)}mm`);

if (v.pass) {
  console.log('[qa_sim] PASS — ORBIT: marble stays captive, descends, exits.');
  process.exit(0);
} else {
  for (const f of v.fails) console.log(`[qa_sim] FAIL — ${f}`);
  process.exit(1);
}
