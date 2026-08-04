#!/usr/bin/env node
// build_viewer.mjs: bundle viewer_src.mjs (three + rapier wasm + sim_core)
// into ONE self-contained viewer.html: no network, double-clickable file://.
//   node build_viewer.mjs [stl] [out]

import { build } from 'esbuild';
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { gzipSync } from 'node:zlib';

// Paths resolve against THIS file, not the cwd, so the build runs from anywhere.
const here = dirname(fileURLToPath(import.meta.url));
const stlPath = resolve(here, process.argv[2] ?? 'assets/spiral_chute_snapshot.stl');
const outPath = resolve(process.argv[3] ?? `${here}/viewer.html`);

const result = await build({
  entryPoints: [resolve(here, 'viewer_src.mjs')],
  bundle: true,
  minify: true,
  write: false,
  format: 'iife',
  target: 'es2022',
  logLevel: 'warning',
});
// A literal </script> inside the bundle would terminate the inline tag.
const js = result.outputFiles[0].text.replaceAll('</script>', '<\\/script>');

const stlB64 = gzipSync(readFileSync(stlPath), { level: 9 }).toString('base64');

const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>marble chute sim - local proof</title>
<style>
  * { margin: 0; box-sizing: border-box; }
  html, body { height: 100%; }
  body { display: flex; flex-direction: column; background: #0d0d0f; color: #ddd;
         font: 14px/1.45 -apple-system, system-ui, sans-serif; }
  header { padding: 10px 14px; display: flex; gap: 12px; align-items: center; flex-wrap: wrap;
           border-bottom: 1px solid #2a2a2e; }
  header h1 { font-size: 15px; font-weight: 600; color: #e8641b; }
  button { background: #e8641b; color: #111; border: 0; border-radius: 6px;
           padding: 7px 14px; font-weight: 600; cursor: pointer; }
  button:hover { background: #ff7a2e; }
  #status.run { color: #55ccff; } #status.pass { color: #6fdc6f; } #status.fail { color: #ff5c5c; }
  #view { flex: 1; min-height: 0; }
  #view canvas { display: block; }
  footer { padding: 6px 14px; color: #888; font-size: 12px; border-top: 1px solid #2a2a2e; }
</style>
</head>
<body>
<header>
  <h1>marble chute - physics sim</h1>
  <button id="drop">Drop marble</button>
  <span id="status">booting...</span>
  <span id="live"></span>
</header>
<div id="view"></div>
<footer>
  <span id="mesh">...</span><br>
  Same sim_core.mjs as the headless QA gate (qa_sim.mjs) - one engine, two surfaces.
  Sim material constants are ASSUMED (typical glass-on-PLA), not measured; treat timings as
  indicative, captivity verdict held across a friction/entry-speed sweep.
</footer>
<script>globalThis.STL_GZ_B64 = "${stlB64}";</script>
<script>${js}</script>
</body>
</html>
`;
writeFileSync(outPath, html);
console.log(`[build_viewer] ${outPath} written: bundle ${(js.length / 1e6).toFixed(2)}MB js + ` +
  `${(stlB64.length / 1e6).toFixed(2)}MB stl(gz,b64), total ${(html.length / 1e6).toFixed(2)}MB`);
