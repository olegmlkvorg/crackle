// viewer_src.mjs — browser viewer source. esbuild-bundled into viewer.html by
// build_viewer.mjs. Renders the chute with three.js and steps THE SAME
// sim_core.mjs the headless QA gate runs — identical engine, dt, constants.
// The STL travels inside the HTML as gzip+base64 (globalThis.STL_GZ_B64).

import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { parseBinarySTL, createSim, ChuteTracker, MM, DEFAULTS } from './sim_core.mjs';

async function loadEmbeddedSTL() {
  const b64 = globalThis.STL_GZ_B64;
  const bin = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
  if (typeof DecompressionStream === 'undefined') {
    throw new Error('This browser lacks DecompressionStream (needs Chrome 80+/Safari 16.4+).');
  }
  const stream = new Blob([bin]).stream().pipeThrough(new DecompressionStream('gzip'));
  return parseBinarySTL(await new Response(stream).arrayBuffer());
}

function hud(id) { return document.getElementById(id); }

async function main() {
  hud('status').textContent = 'loading mesh + physics wasm...';
  const { positions, triCount } = await loadEmbeddedSTL();
  const sim = await createSim(positions);
  const g = sim.geo;
  let tracker = new ChuteTracker(g);
  let done = false;

  // --- three.js scene (world kept z-up to match the STL and the sim) ---
  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  document.getElementById('view').appendChild(renderer.domElement);
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0d0d0f);
  const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 500);
  camera.up.set(0, 0, 1);
  const midZ = ((g.bbox.min[2] + g.bbox.max[2]) / 2) * MM;
  camera.position.set(28, -34, midZ + 14);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.target.set(0, 0, midZ);
  controls.enableDamping = true;

  scene.add(new THREE.HemisphereLight(0xffffff, 0x332211, 1.1));
  const key = new THREE.DirectionalLight(0xffffff, 1.6);
  key.position.set(30, -40, 60);
  scene.add(key);

  const geo = new THREE.BufferGeometry();
  const scaled = new Float32Array(positions.length);
  for (let i = 0; i < positions.length; i++) scaled[i] = positions[i] * MM;
  geo.setAttribute('position', new THREE.BufferAttribute(scaled, 3));
  geo.computeVertexNormals();
  const chute = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({
    color: 0xe8641b, roughness: 0.55, metalness: 0.05,
    side: THREE.DoubleSide, transparent: true, opacity: 0.92,
  }));
  scene.add(chute);

  const marble = new THREE.Mesh(
    new THREE.SphereGeometry(DEFAULTS.marbleRadiusMM * MM, 32, 24),
    new THREE.MeshStandardMaterial({ color: 0xf2f2f2, roughness: 0.15, metalness: 0.3 }),
  );
  scene.add(marble);

  const TRAIL = 4000;
  const trailPos = new Float32Array(TRAIL * 3);
  let trailN = 0;
  const trailGeo = new THREE.BufferGeometry();
  trailGeo.setAttribute('position', new THREE.BufferAttribute(trailPos, 3));
  trailGeo.setDrawRange(0, 0);
  const trail = new THREE.Line(trailGeo, new THREE.LineBasicMaterial({ color: 0x55ccff }));
  trail.frustumCulled = false;
  scene.add(trail);

  function resize() {
    const el = document.getElementById('view');
    renderer.setSize(el.clientWidth, el.clientHeight);
    camera.aspect = el.clientWidth / el.clientHeight;
    camera.updateProjectionMatrix();
  }
  addEventListener('resize', resize); resize();

  hud('mesh').textContent =
    `${triCount.toLocaleString()} tris | crest r ${g.crestR.toFixed(1)}mm | ` +
    `helix z ${g.zone.min.toFixed(0)}..${g.zone.max.toFixed(0)}mm | dt 1/${Math.round(1 / sim.opts.dt)} | ` +
    `friction ${sim.opts.friction} (ASSUMED, not measured)`;

  function dropMarble() {
    sim.drop();
    tracker = new ChuteTracker(g);
    done = false;
    trailN = 0; trailGeo.setDrawRange(0, 0);
    hud('status').textContent = 'rolling...';
    hud('status').className = 'run';
  }
  document.getElementById('drop').onclick = dropMarble;
  dropMarble();

  let last = performance.now(), acc = 0;
  function frame(now) {
    requestAnimationFrame(frame);
    acc += Math.min((now - last) / 1000, 0.05);
    last = now;
    let s = null;
    while (acc >= sim.opts.dt) {
      s = sim.step();
      acc -= sim.opts.dt;
      if (!done && tracker.update(s)) {
        done = true;
        const v = tracker.verdict();
        hud('status').textContent = v.pass
          ? `PASS - ORBIT: ${v.turns.toFixed(2)} turns, rail margin ${v.railMarginMM.toFixed(1)}mm, ` +
            `descent ${v.descentTimeS.toFixed(2)}s`
          : `FAIL - ${v.fails[0]}`;
        hud('status').className = v.pass ? 'pass' : 'fail';
      }
    }
    if (s) {
      marble.position.set(s.posMM[0] * MM, s.posMM[1] * MM, s.posMM[2] * MM);
      if (trailN < TRAIL) {
        trailPos.set([marble.position.x, marble.position.y, marble.position.z], trailN * 3);
        trailN++;
        trailGeo.setDrawRange(0, trailN);
        trailGeo.attributes.position.needsUpdate = true;
      }
      hud('live').textContent =
        `t ${s.t.toFixed(2)}s | z ${s.zMM.toFixed(1)}mm | r ${s.rMM.toFixed(1)}mm | ` +
        `turns ${tracker.turns.toFixed(2)} | v ${Math.hypot(...s.velMM).toFixed(0)}mm/s`;
    }
    controls.update();
    renderer.render(scene, camera);
  }
  requestAnimationFrame(frame);
}

main().catch((e) => {
  const el = document.getElementById('status');
  el.textContent = 'ERROR: ' + e.message;
  el.className = 'fail';
  console.error(e);
});
