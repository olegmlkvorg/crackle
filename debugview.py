#!/usr/bin/env python3
"""Low-level live printer debug view. Serves a page + proxies Moonraker (dodges CORS entirely).

Fluidd (http://<printer>:4408) already does temps/console/files — don't rebuild that. THIS shows
what Fluidd doesn't, and what toolpath-native work needs: the actual PATH being drawn, live, with
TRAVELS distinguished from extrusions. For crackle, the travels ARE the product, so watching them
appear is the whole point. Plus the exact source line executing.

Usage: python3 debugview.py [--ip 192.168.3.140] [--port 8899]  -> open http://localhost:8899
"""
import argparse, http.server, json, socketserver, urllib.parse, urllib.request

ap = argparse.ArgumentParser(); ap.add_argument("--ip", default="192.168.3.140")
ap.add_argument("--port", type=int, default=8899); A = ap.parse_args()
MOON = f"http://{A.ip}:7125"

PAGE = r"""<!doctype html><meta charset=utf-8><title>printer · low level</title>
<meta name=viewport content="width=device-width,initial-scale=1">
<style>
:root{--bg:#0a0a0b;--pan:#121214;--ln:#26262a;--ink:#eee;--mut:#8a8a8a;--ext:#ff6a1a;--trav:#3aa0ff;--ok:#3fb968}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:13px/1.5 ui-monospace,Menlo,monospace}
.wrap{display:grid;grid-template-columns:1fr 420px;gap:10px;padding:10px;height:100vh}
@media(max-width:900px){.wrap{grid-template-columns:1fr;height:auto}}
.card{background:var(--pan);border:1px solid var(--ln);border-radius:10px;padding:10px;overflow:auto}
h2{margin:0 0 8px;font-size:11px;letter-spacing:.18em;text-transform:uppercase;color:var(--mut);font-weight:600}
#cv{width:100%;height:auto;background:#08080a;border-radius:8px;display:block}
.kv{display:flex;justify-content:space-between;border-bottom:1px solid var(--ln);padding:3px 0}
.kv b{color:var(--mut);font-weight:500}
.bar{height:6px;background:#1c1c1f;border-radius:99px;overflow:hidden;margin:6px 0 10px}
.bar>i{display:block;height:100%;background:var(--ext);width:0}
pre{margin:0;font-size:12px;line-height:1.45;white-space:pre-wrap;word-break:break-all}
.cur{background:#2a1a08;color:#ffb37a;display:block;border-left:2px solid var(--ext);padding-left:6px}
.dim{color:#6a6a6a}
.legend span{margin-right:12px}.legend i{display:inline-block;width:10px;height:2px;vertical-align:middle;margin-right:4px}
</style>
<div class=wrap>
 <div class=card>
   <h2>toolpath — drawn so far</h2>
   <div class=legend><span><i style="background:var(--ext)"></i>extrude</span>
     <span><i style="background:var(--trav)"></i>travel (the web)</span>
     <span class=dim id=counts></span></div>
   <canvas id=cv width=900 height=900></canvas>
 </div>
 <div>
  <div class=card style="margin-bottom:10px">
   <h2>state</h2>
   <div class=bar><i id=pbar></i></div>
   <div class=kv><b>file</b><span id=f>—</span></div>
   <div class=kv><b>state</b><span id=st>—</span></div>
   <div class=kv><b>line</b><span id=ln>—</span></div>
   <div class=kv><b>section</b><span id=sec>—</span></div>
   <div class=kv><b>pos</b><span id=pos>—</span></div>
   <div class=kv><b>nozzle</b><span id=t0>—</span></div>
   <div class=kv><b>bed</b><span id=tb>—</span></div>
   <div class=kv><b>feed / flow</b><span id=ff>—</span></div>
  </div>
  <div class=card style="max-height:46vh"><h2>executing</h2><pre id=src>—</pre></div>
 </div>
</div>
<script>
const $=i=>document.getElementById(i); let LINES=null,FILE=null,SEG=null,BB=null;
const api=async q=>(await fetch('/api/'+q)).json();
async function loadFile(name){
  const txt=await (await fetch('/gcode/'+encodeURIComponent(name))).text();
  LINES=txt.split('\n'); FILE=name; SEG=[]; let x=0,y=0,minx=1e9,miny=1e9,maxx=-1e9,maxy=-1e9,off=0;
  for(const l of LINES){
    const s=l.split(';')[0].trim(), st=off; off+=l.length+1;
    if(!/^G[01]\b/.test(s)) continue;
    const mx=/X(-?[\d.]+)/.exec(s), my=/Y(-?[\d.]+)/.exec(s), me=/E(-?[\d.]+)/.exec(s);
    const nx=mx?+mx[1]:x, ny=my?+my[1]:y;
    if(mx||my){SEG.push({x0:x,y0:y,x1:nx,y1:ny,e:!!me,b:st});
      minx=Math.min(minx,x,nx);maxx=Math.max(maxx,x,nx);miny=Math.min(miny,y,ny);maxy=Math.max(maxy,y,ny);}
    x=nx;y=ny;
  }
  BB={minx,miny,maxx,maxy};
}
function draw(pos){
  const c=$('cv'),g=c.getContext('2d');g.clearRect(0,0,c.width,c.height);
  if(!SEG||!BB)return; const pad=30,w=BB.maxx-BB.minx||1,h=BB.maxy-BB.miny||1;
  const k=Math.min((c.width-2*pad)/w,(c.height-2*pad)/h);
  const X=v=>pad+(v-BB.minx)*k, Y=v=>c.height-pad-(v-BB.miny)*k;   // flip Y: printer origin is bottom-left
  let ne=0,nt=0;
  for(const s of SEG){ if(s.b>pos) break;
    g.strokeStyle=s.e?'#ff6a1a':'rgba(58,160,255,.55)'; g.lineWidth=s.e?1.6:0.7;
    g.beginPath();g.moveTo(X(s.x0),Y(s.y0));g.lineTo(X(s.x1),Y(s.y1));g.stroke();
    s.e?ne++:nt++; }
  $('counts').textContent=`${ne} extrusions · ${nt} travels`;
}
async function tick(){
 try{
  const q=await api('printer/objects/query?virtual_sdcard&print_stats&gcode_move&extruder&heater_bed');
  const s=q.result.status, vs=s.virtual_sdcard||{}, ps=s.print_stats||{}, gm=s.gcode_move||{},
        e=s.extruder||{}, b=s.heater_bed||{};
  const name=(ps.filename||'').split('/').pop();
  $('f').textContent=name||'—'; $('st').textContent=ps.state||'—';
  const pos=vs.file_position||0, size=vs.file_size||1;
  $('pbar').style.width=(pos/size*100)+'%';
  const p=gm.gcode_position||[0,0,0];
  $('pos').textContent=`X${p[0].toFixed(1)} Y${p[1].toFixed(1)} Z${p[2].toFixed(2)}`;
  $('t0').textContent=`${(e.temperature||0).toFixed(0)} → ${(e.target||0).toFixed(0)}°C`;
  $('tb').textContent=`${(b.temperature||0).toFixed(0)} → ${(b.target||0).toFixed(0)}°C`;
  $('ff').textContent=`${((gm.speed||0)/60).toFixed(0)} mm/s · ${((gm.extrude_factor||1)*100).toFixed(0)}%`;
  if(name && name!==FILE) await loadFile(name);
  if(LINES){
    let line=1,acc=0; for(let i=0;i<LINES.length;i++){acc+=LINES[i].length+1; if(acc>pos){line=i+1;break;}}
    $('ln').textContent=`${line} / ${LINES.length}`;
    let out=''; for(let i=Math.max(0,line-6);i<Math.min(LINES.length,line+6);i++)
      out+=(i===line-1?`<span class="cur">${esc(LINES[i])}</span>`:`<span class="dim">${esc(LINES[i])}</span>`)+'\n';
    $('src').innerHTML=out;
    for(let i=line-1;i>=0;i--) if(/^; .*(layer|band|base)/.test(LINES[i])){$('sec').textContent=LINES[i].slice(2);break;}
    draw(pos);
  }
 }catch(err){ $('st').textContent='offline: '+err.message; }
 setTimeout(tick,600);
}
const esc=s=>s.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
tick();
</script>"""

class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        try:
            if self.path == "/" or self.path.startswith("/index"):
                body = PAGE.encode(); ct = "text/html; charset=utf-8"
            elif self.path.startswith("/api/"):
                body = urllib.request.urlopen(f"{MOON}/{self.path[5:]}", timeout=10).read()
                ct = "application/json"
            elif self.path.startswith("/gcode/"):
                n = urllib.parse.unquote(self.path[7:])
                body = urllib.request.urlopen(
                    f"{MOON}/server/files/gcodes/{urllib.parse.quote(n)}", timeout=30).read()
                ct = "text/plain; charset=utf-8"
            else:
                self.send_error(404); return
            self.send_response(200); self.send_header("Content-Type", ct)
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        except Exception as ex:
            self.send_error(502, str(ex))

socketserver.TCPServer.allow_reuse_address = True
with socketserver.TCPServer(("", A.port), H) as s:
    print(f"printer debug view -> http://localhost:{A.port}   (proxying {MOON})")
    s.serve_forever()
