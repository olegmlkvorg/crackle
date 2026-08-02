#!/usr/bin/env node
// make_bad.mjs — generate KNOWN-BAD chute variants to prove qa_sim can fire.
//   node make_bad.mjs shallow   -> assets/bad_shallow_pitch.stl (z * 0.4:
//     pitch 32 -> 12.8mm/turn, rolling grade ~21deg -> ~8.9deg, V-groove flattened)
// Binary STL in, binary STL out, normals recomputed.

import { readFileSync, writeFileSync } from 'node:fs';
import { parseBinarySTL } from './sim_core.mjs';

const kind = process.argv[2] ?? 'shallow';
if (kind !== 'shallow') { console.error('usage: node make_bad.mjs shallow'); process.exit(2); }

const src = 'assets/spiral_chute_snapshot.stl';
const out = 'assets/bad_shallow_pitch.stl';
const { positions, triCount } = parseBinarySTL(readFileSync(src));

const p = Float32Array.from(positions);
for (let i = 0; i < p.length / 3; i++) p[i * 3 + 2] *= 0.4;

const buf = Buffer.alloc(84 + triCount * 50);
buf.write(`bad_shallow_pitch z*0.4 of snapshot`, 0, 'ascii');
buf.writeUInt32LE(triCount, 80);
for (let i = 0; i < triCount; i++) {
  const o = 84 + i * 50;
  const ax = p[i * 9], ay = p[i * 9 + 1], az = p[i * 9 + 2];
  const ux = p[i * 9 + 3] - ax, uy = p[i * 9 + 4] - ay, uz = p[i * 9 + 5] - az;
  const vx = p[i * 9 + 6] - ax, vy = p[i * 9 + 7] - ay, vz = p[i * 9 + 8] - az;
  let nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
  const len = Math.hypot(nx, ny, nz) || 1;
  buf.writeFloatLE(nx / len, o); buf.writeFloatLE(ny / len, o + 4); buf.writeFloatLE(nz / len, o + 8);
  for (let k = 0; k < 9; k++) buf.writeFloatLE(p[i * 9 + k], o + 12 + k * 4);
}
writeFileSync(out, buf);
console.log(`[make_bad] wrote ${out} (${triCount} tris, z scaled x0.4)`);
