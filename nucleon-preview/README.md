# Nucleon made-to-measure preview

Stage: three generated previews. Nothing here has been printed. Print readiness is withheld until
the sharp-angle validator repair settles. Physical fit and desirability require Oleg after the
print lane resumes.

The three sizes change the structure: 40 mm uses 6 broad ellipses, 50 mm uses 8, and 64 mm uses
12 narrower ellipses. This increases junction density and shortens the members between junctions
instead of scaling one lattice.

Corrected 2026-08-19: the first preview joined ellipse tips with extruding chords across the inner
void. The renderer showed them faithfully. The generator now walks a sampled outer-boundary arc
between ellipses, and the independent parser refuses any extruding segment that enters the declared
inner void. The old 40 mm chord was 36.404 mm with E advancing 200.62527 to 211.52257 at line 466;
the old 64 mm chord was 62.480 mm with E advancing 572.54450 to 591.24730 at line 928.

Run `python3 nucleon-preview/build.py`. It emits each G-code file through `nucleon.emit`, then
passes that exact file to `render.py --body-only`. The renderer embeds the G-code SHA-256 in the
SVG metadata. `verify.py` recomputes the digest and independently parses the committed G-code for
requested dimensions, uninterrupted body extrusion, and machine bounds.
It also proves zero extruding moves cross the inner void.
