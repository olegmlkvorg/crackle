#!/usr/bin/env node
// qa_sim.mjs : headless dynamic QA gate for printed-chute meshes.
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
if (scenario !== 'chute' && scenario !== 'sorter') {
  console.error(`unknown scenario: ${scenario} (chute | sorter)`);
  process.exit(2);
}
// SORTER: the chute's rail crest is a sieve, so the SAME geometry must give DIFFERENT outcomes
// for different marbles. --expect says which one this run is asserting.
const expect = arg('expect', 'ride');
if (scenario === 'sorter' && expect !== 'ride' && expect !== 'shaft') {
  console.error(`--expect must be ride or shaft`);
  process.exit(2);
}
const marbleD = Number(arg('marble', 16));
// FEED MATTERS MORE THAN SIZE. A marble already in the gutter rides whatever its diameter; the
// crest only sorts what arrives down the middle, which is what a funnel on top actually delivers.
// Default the sorter to axis feed, because testing a sorter on gutter feed answers nothing.
const feed = arg('feed', scenario === 'sorter' ? 'axis' : 'gutter');

const { positions, triCount } = parseBinarySTL(readFileSync(stlPath));
const sim = await createSim(positions, {
  marbleRadiusMM: marbleD / 2,
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
  `speed=${sim.opts.entrySpeedMM}mm/s  dt=1/${Math.round(1 / sim.opts.dt)}  marble=O${marbleD}  ` +
  `scenario=${scenario}${scenario === 'sorter' ? ' expect=' + expect : ''}  feed=${feed}`);

if (feed === 'axis') {
  const zTop = sim.geo.zone.max + 0.10 * sim.geo.H;
  const c = sim.geo.centerAt(zTop);
  sim.drop([c[0], c[1], zTop], [0, 0, 0]);   // at rest, down the middle
}
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

if (scenario === 'sorter') {
  // In a sorter a centre drop is the CORRECT answer for an undersized marble, so the chute
  // gate's verdict is not the question. What happened is: did it go down the shaft, or ride?
  // CENTER-DROP ends the run by design, so this flag is the RIGHT thing to read here, but any
  // depth or time read after it is where the watcher stopped, not the marble. Reading lowestZ
  // after this flag once produced a "stalls partway down" result that was pure watcher artifact.
  const wentShaft = tracker.escaped?.kind === 'CENTER-DROP';
  const rode = !wentShaft && v.turns >= 1.0;
  const got = wentShaft ? 'SHAFT' : rode ? 'RIDE' : 'NEITHER';
  console.log(`[qa_sim] outcome=${got} (expected ${expect.toUpperCase()})`);
  if (got === expect.toUpperCase()) {
    console.log(`[qa_sim] PASS: SORT: a O${marbleD} marble ${wentShaft ?
      'falls through the crest into the shaft' : 'rides the spiral past the crest'}.`);
    process.exit(0);
  }
  console.log(`[qa_sim] FAIL: SORT: a O${marbleD} marble came out ${got}, wanted ` +
    `${expect.toUpperCase()}. The crest does not sort these two sizes at this entry speed.`);
  process.exit(1);
}
if (v.pass) {
  console.log('[qa_sim] PASS: ORBIT: marble stays captive, descends, exits.');
  process.exit(0);
} else {
  for (const f of v.fails) console.log(`[qa_sim] FAIL: ${f}`);
  process.exit(1);
}
