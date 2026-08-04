// SORT HEAD -- MANY MARBLES, ONE AFTER ANOTHER. The defect this exists to catch cannot be seen
// with one marble: the head sorted 9/9 single pours while a rejected marble parked ON the sieve
// mouth, so the SECOND marble is the first one that fails. Every other harness here drops one
// marble into an empty head and removes it before the next.
//
// So this one keeps every marble in the world. Marbles collide with each other as well as with
// the mesh, they are poured on a clock, and each is tracked to where it stops.
//
// usage: node sort_head_multi.mjs <chute.stl> <head_seat0.stl> [seq] [friction] [restitution] [seed]
//   seq   comma list of marble diameters in pour order, default 16,10,16,10,10,16,10
// prints one line per marble: final r, z, and what it did.
import { readFileSync } from 'node:fs';
import { parseBinarySTL, analyzeChute, initEngine, MM } from './sim_core.mjs';

const chute = parseBinarySTL(readFileSync(process.argv[2])).positions;
const head = parseBinarySTL(readFileSync(process.argv[3])).positions;
const seq = (process.argv[4] ?? '16,10,16,10,10,16,10').split(',').map(Number);
const friction = Number(process.argv[5] ?? 0.5);
const restitution = Number(process.argv[6] ?? 0.15);
let seed = Number(process.argv[7] ?? 12345);
const rnd = () => ((seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff);

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
const topZ = g.bbox.max[2], zBot = gc.bbox.min[2], chuteTop = gc.bbox.max[2];

const R = await initEngine();
const world = new R.World({ x: 0, y: 0, z: -981 });
const dt = 1 / 480;
world.integrationParameters.dt = dt;
const verts = new Float32Array(merged.length);
for (let i = 0; i < merged.length; i++) verts[i] = merged[i] * MM;
const idx = new Uint32Array(merged.length / 3);
for (let i = 0; i < idx.length; i++) idx[i] = i;
const fixed = world.createRigidBody(R.RigidBodyDesc.fixed());
world.createCollider(
  R.ColliderDesc.trimesh(verts, idx).setFriction(friction).setRestitution(0.1), fixed);

// pour ring: marbles are dropped from just under the bowl rim, at a random offset and angle, the
// same envelope the single-marble probes sweep (0..40mm off centre)
const pourZ = topZ - 4;
const balls = [];
function pour(d) {
  const rad = (d / 2) * MM;
  const off = 5 + rnd() * 35, th = rnd() * 2 * Math.PI;
  const body = world.createRigidBody(R.RigidBodyDesc.dynamic().setCcdEnabled(true)
    .setAngularDamping(0.05)
    .setTranslation(off * Math.cos(th) * MM, off * Math.sin(th) * MM, pourZ * MM));
  const density = 6 / ((4 / 3) * Math.PI * rad ** 3);
  world.createCollider(R.ColliderDesc.ball(rad).setFriction(friction)
    .setRestitution(restitution).setDensity(density), body);
  balls.push({ d, body, t0: 0, off, done: null });
}

const GAP = 1.2;              // s between pours: long enough for the previous one to settle
const TOTAL = GAP * seq.length + 6;
let t = 0, next = 0, k = 0;
while (t < TOTAL) {
  if (k < seq.length && t >= next) { pour(seq[k]); balls[k].t0 = t; k++; next += GAP; }
  world.step();
  t += dt;
}

const st = (b) => {
  const p = b.body.translation();
  return { r: Math.hypot(p.x, p.y) / MM, z: p.z / MM };
};
console.log(`pour z=${pourZ.toFixed(1)}  chute top=${chuteTop.toFixed(1)}  chute bottom=${zBot.toFixed(1)}` +
  `  friction=${friction} restitution=${restitution} seed=${process.argv[7] ?? 12345}`);
let sorted = 0, want = 0, jam = null;
for (let i = 0; i < balls.length; i++) {
  const b = balls[i], s = st(b);
  const out = s.z < zBot + 40;
  const inHead = s.z > chuteTop - 5;
  let tag;
  if (out) tag = 'THROUGH  (down the chute)';
  else if (inHead) tag = `IN HEAD  r=${s.r.toFixed(2)}`;
  else tag = 'IN CHUTE (stuck part way)';
  if (b.d < 12) { want++; if (out) sorted++; else if (!jam) jam = i; }
  console.log(`  #${i} O${b.d}  poured ${b.off.toFixed(0)}mm off  ->  z=${s.z.toFixed(1)} ` +
    `r=${s.r.toFixed(2)}  ${tag}`);
}
console.log(`SORTED ${sorted}/${want} of the small ones` +
  (jam === null ? '' : `   FIRST JAM at marble #${jam}`));
