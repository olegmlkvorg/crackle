#!/usr/bin/env python3
"""Gate the explicit namespace contract shared by solid.finish callers."""
import ast
from contextlib import redirect_stdout
import io
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile

from shapely.geometry import box

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import machine
import solid


REQUIRED = {
    "aux", "bead_w", "bed", "brim", "fan", "first_w", "flow", "height", "layer_h",
    "material", "no_home", "out", "press", "printer", "stick", "temp", "wall",
}
STAVE_CALLERS = ("stave_test.py", "stave_hub.py", "stave_shelf.py")


def assigned_namespace_attributes(path):
    tree = ast.parse(path.read_text(), filename=str(path))
    found = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            leaves = target.elts if isinstance(target, (ast.Tuple, ast.List)) else [target]
            for leaf in leaves:
                if (isinstance(leaf, ast.Attribute) and isinstance(leaf.value, ast.Name)
                        and leaf.value.id == "a"):
                    found.add(leaf.attr)
    return found


def main():
    missing = {}
    for name in STAVE_CALLERS:
        absent = sorted(REQUIRED - assigned_namespace_attributes(ROOT / name))
        if absent:
            missing[name] = absent
    if missing:
        details = "; ".join(f"{name}: {', '.join(attrs)}" for name, attrs in missing.items())
        raise AssertionError("solid.finish namespace contract incomplete: " + details)

    with tempfile.TemporaryDirectory(prefix="crackle-finish-contract-") as tmp:
        args = SimpleNamespace(
            aux=0.2, bead_w=1.2, bed=90, brim=0, fan=51, first_w=7.2, flow=36.0,
            height=0.5, layer_h=0.4, material="pla", no_home=False, out=tmp,
            press=machine.PRESS_HARD, printer="k1c", stick=6.35, temp=210, wall=3.6)
        output = io.StringIO()
        with redirect_stdout(output):
            solid.finish(box(20, 20, 32, 32), args, "contract", str(Path(tmp) / "part.gcode"))
        lines = output.getvalue().splitlines()
        if len(lines) < 2 or "(no brim)" not in lines[-2] or "mm/s at flow" not in lines[-1]:
            raise AssertionError("solid.finish did not print its complete two-line summary")
        print("PASS finish summary: " + lines[-1].strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
