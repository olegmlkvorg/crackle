#!/usr/bin/env python3
"""BRIDGE-TPU-1 result sheet: one tap per item, for judging the printed plate by hand.

Writes out/bridge_tpu1_results.html, a self-contained page (no network, opens from file://).
Spans, rows, post footprints and bead heights are IMPORTED from bridge_tpu.py, never retyped,
so a change to the coupon changes the sheet.

Per row (R1, R2) and span, three questions, each pass / fail / unclear, default unclear:
  sag   mid-span drop under one layer height (the row's lh, printed in the question)
  hold  the strand stays on both posts under a hand pull
  clean the bridge level above is clean
plus one per row, because the verdict's second falsifier needs it:
  posts all ten posts stood to 20 mm (no wobble, fall, or split)

The answers export as JSON (copy, or download bridge_tpu1_results.json) in the shape
bridge_tpu_verdict.py reads. The plate map is drawn from bridge_tpu.layout(), posts labelled.

Usage: python3 bridge_tpu_results.py [--out DIR]
"""
import argparse, html, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bridge_tpu as bt

QUESTIONS = (
    ("sag", "Sag under one layer ({lh:g} mm)?"),
    ("hold", "Holds when pulled?"),
    ("clean", "Bridge above clean?"),
)
POST_Q = ("posts", "All ten posts stood to 20 mm?")
CHOICES = ("pass", "fail", "unclear")


def span_key(g):
    return f"{g:g}"


def model():
    """Everything the page and the verdict need, derived from bridge_tpu."""
    rows = {}
    for row, (w, lh) in bt.ROWS.items():
        rows[row] = {"bead_w": w, "lh": lh,
                     "pairs": [{"span": g, "A": list(A), "B": list(B)} for A, B, g in bt.layout(row)]}
    return {"coupon": "BRIDGE-TPU-1", "spans": [span_key(g) for g in bt.SPANS], "rows": rows}


def plate_svg(m):
    """Top view, one panel per row, drawn from the post footprints. X right, Y up (bed front at the
    bottom). Each panel is cropped to its own row so the posts stay legible at phone width; the
    row's real X range is printed under it."""
    panels = []
    for row, r in m["rows"].items():
        xs = [v for p in r["pairs"] for v in (p["A"][0], p["B"][2])]
        ys = [v for p in r["pairs"] for v in (p["A"][1], p["A"][3])]
        x0, x1 = min(xs) - 3, max(xs) + 10
        y0, y1 = min(ys) - 3, max(ys) + 9
        W, H = x1 - x0, y1 - y0
        fy = lambda y: y1 - y
        o = [f'<svg viewBox="0 0 {W:.1f} {H:.1f}" role="img" aria-label="{row} plate map">',
             f'<text class="rl" x="{W/2:.1f}" y="4.5" text-anchor="middle">{row}</text>']
        for p in r["pairs"]:
            for n in ("A", "B"):
                a = p[n]
                o.append(f'<rect class="post" x="{a[0]-x0:.2f}" y="{fy(a[3]):.2f}" '
                         f'width="{a[2]-a[0]:.2f}" height="{a[3]-a[1]:.2f}"/>')
            A, B = p["A"], p["B"]
            ym = fy((A[1] + A[3]) / 2)
            o.append(f'<line class="br" x1="{A[2]-x0:.2f}" y1="{ym:.2f}" x2="{B[0]-x0:.2f}" y2="{ym:.2f}"/>')
            o.append(f'<text class="sl" x="{B[2]-x0+1:.2f}" y="{ym+1.2:.2f}">{p["span"]:g}</text>')
        o.append("</svg>")
        panels.append(f'<figure>{"".join(o)}<figcaption>{row}: X {min(xs):.0f}–{max(xs):.0f} mm, '
                      f'{"left" if row == "R1" else "right"} row</figcaption></figure>')
    return ('<div class="map">' + "".join(panels) + '</div><p class="cap">Seen from above, bed front '
            '(Y=0) at the bottom. Numbers are the clear span in mm; the gaps grow toward the back.</p>')


def seg(name, label):
    btns = "".join(
        f'<label class="c {c}"><input type="radio" name="{name}" value="{c}"{" checked" if c == "unclear" else ""}>'
        f"<span>{c}</span></label>" for c in CHOICES)
    return f'<div class="q"><div class="ql">{html.escape(label)}</div><div class="seg">{btns}</div></div>'


def page(m):
    cards = []
    for row, r in m["rows"].items():
        items = [f'<h2>{row} <small>bead {r["bead_w"]:g} × {r["lh"]:g} mm</small></h2>',
                 '<section class="card">' + seg(f"{row}|posts", POST_Q[1]) + "</section>"]
        for p in r["pairs"]:
            s = span_key(p["span"])
            qs = "".join(seg(f"{row}|{s}|{k}", t.format(lh=r["lh"])) for k, t in QUESTIONS)
            items.append(f'<section class="card"><h3>{s} mm span</h3>{qs}</section>')
        cards.append("\n".join(items))
    data = json.dumps(m)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bridge Span Results</title>
<style>
:root{{--bg:#fff;--fg:#1a1a1a;--mut:#5c5c66;--line:#d4d4dc;--card:#f7f7f9;--acc:#5a3dc8;
--pass:#1f7a3a;--fail:#c0262d;--unc:#6b6b76}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#121216;--fg:#ececf1;--mut:#a3a3ad;
--line:#33333d;--card:#1c1c22;--acc:#a18cf0;--pass:#4cc073;--fail:#f06a6f;--unc:#9a9aa5}}}}
:root[data-theme="dark"]{{--bg:#121216;--fg:#ececf1;--mut:#a3a3ad;--line:#33333d;--card:#1c1c22;--acc:#a18cf0;
--pass:#4cc073;--fail:#f06a6f;--unc:#9a9aa5}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--fg);font:16px/1.4 "Inter",system-ui,sans-serif}}
main{{max-width:640px;margin:0 auto;padding:16px}}
h1{{font-size:20px;margin:0 0 4px}} h2{{font-size:18px;margin:24px 0 8px}} h2 small{{color:var(--mut);font-weight:400;font-size:14px}}
h3{{font-size:15px;margin:0 0 8px}}
p{{margin:4px 0 12px;color:var(--mut);font-size:14px}}
.stage{{display:inline-block;border:1px solid var(--line);border-radius:4px;padding:2px 8px;font-size:13px;color:var(--mut)}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px;margin:8px 0}}
.q{{margin:8px 0}} .ql{{font-size:14px;margin-bottom:4px}}
.seg>*{{min-width:0}} .seg{{display:grid;grid-template-columns:repeat(3,1fr);gap:4px}}
.c input{{position:absolute;opacity:0;pointer-events:none}}
.c span{{display:block;text-align:center;padding:10px 0;border:1px solid var(--line);border-radius:4px;cursor:pointer;font-size:14px}}
.c.pass input:checked+span{{background:var(--pass);border-color:var(--pass);color:#fff}}
.c.fail input:checked+span{{background:var(--fail);border-color:var(--fail);color:#fff}}
.c.unclear input:checked+span{{background:var(--unc);border-color:var(--unc);color:#fff}}
.c input:focus-visible+span{{outline:2px solid var(--acc);outline-offset:2px}}
svg{{width:100%;height:auto;display:block}}
.post{{fill:var(--acc)}} .br{{stroke:var(--fg);stroke-width:.5;stroke-dasharray:1 1}}
.rl{{font-size:3.6px;fill:var(--fg);font-weight:600}} .sl{{font-size:3px;fill:var(--fg)}}
.map{{display:grid;grid-template-columns:1fr 1fr;gap:12px}} figure{{margin:0}} figcaption,.cap{{font-size:12px;color:var(--mut);margin:4px 0 0}}
.bar{{display:flex;gap:8px;margin:16px 0}}
button{{flex:1;padding:12px;font:inherit;font-size:15px;border-radius:4px;border:1px solid var(--acc);background:var(--acc);color:#fff;cursor:pointer}}
button.alt{{background:transparent;color:var(--acc)}}
textarea{{width:100%;height:140px;font:12px/1.3 ui-monospace,monospace;background:var(--card);color:var(--fg);border:1px solid var(--line);border-radius:4px;padding:8px}}
#msg{{min-height:1.2em;font-size:13px;color:var(--mut)}}
</style></head><body><main>
<h1>BRIDGE-TPU-1 results</h1>
<span class="stage">Not printed yet: fill this in after the print</span>
<p>Tap one answer per line. Everything starts at <b>unclear</b>, so skip anything you cannot tell. Sag is measured with calipers at mid-span against the post top.</p>
<section class="card">{plate_svg(m)}</section>
{''.join(cards)}
<h2>Export</h2>
<div class="bar"><button id="copy">Copy JSON</button><button id="dl" class="alt">Download file</button></div>
<div id="msg"></div>
<textarea id="out" readonly aria-label="Results JSON"></textarea>
</main>
<script>
const M={data};
function collect(){{
  const v=n=>(document.querySelector('input[name="'+n+'"]:checked')||{{}}).value||"unclear";
  const rows={{}};
  for(const r of Object.keys(M.rows)){{
    const spans={{}};
    for(const s of M.spans)spans[s]={{sag:v(r+"|"+s+"|sag"),hold:v(r+"|"+s+"|hold"),clean:v(r+"|"+s+"|clean")}};
    rows[r]={{posts:v(r+"|posts"),spans}};
  }}
  return {{coupon:M.coupon,rows}};
}}
const out=document.getElementById("out"),msg=document.getElementById("msg");
function refresh(){{out.value=JSON.stringify(collect(),null,1);}}
document.addEventListener("change",refresh);refresh();
document.getElementById("copy").onclick=async()=>{{refresh();
  try{{await navigator.clipboard.writeText(out.value);msg.textContent="Copied.";}}
  catch(e){{out.select();msg.textContent="Selected: press copy.";}}}};
document.getElementById("dl").onclick=()=>{{refresh();
  const a=document.createElement("a");a.href=URL.createObjectURL(new Blob([out.value],{{type:"application/json"}}));
  a.download="bridge_tpu1_results.json";a.click();msg.textContent="Downloaded bridge_tpu1_results.json";}};
</script></body></html>
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "out"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    path = os.path.join(a.out, "bridge_tpu1_results.html")
    open(path, "w").write(page(model()))
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
