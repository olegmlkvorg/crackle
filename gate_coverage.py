#!/usr/bin/env python3
"""Emit JSON coverage for validate.py's standing rules R1-R8.

Coverage is deliberately independent of validate.check(): it records which emitted motion each
rule selected.  A PASS with zero selected moves is converted to REFUSE.
"""
import argparse
import concurrent.futures
import glob
import json
import math
import os
import re
import subprocess
import sys
import tempfile

import machine

AREA = math.pi * (1.75 / 2) ** 2


PROVENANCE = {
    "R1": "machine.PRESS_HARD; Oleg 2026-07-27: nozzle 0.1mm to board",
    "R2": "; LAYER_H= emitted by generator; maximum one declared layer step",
    "R3": "machine.MAX_SPEED plus one-speed-per-print rule; Oleg 2026-07-27",
    "R4": ("machine.R4_FLOW_MIN_RATIO..machine.R4_FLOW_MAX_RATIO; Oleg 2026-07-27 "
           "'flow must be constant'; the 20% tolerance has no recorded empirical provenance"),
    "R5": "validate.py R5; dry travel/extrusion <= 1.0, Oleg 2026-07-27",
    "R6": "machine.SUSTAINED_FLOW_BY_MATERIAL; measured per-material figures",
    "R7": "validate.py R7; probe within 5C of the file's emitted print temperature",
    "R8": "machine.flow_cap(material, printer); declared flow >=80% or FLOW_DERATE",
}


def stamp(text, name):
    m = re.search(rf"^; {re.escape(name)}=([^\n]+)", text, re.M)
    return m.group(1).strip() if m else None


class FieldParseError(ValueError):
    pass


def stamped_float(text, name):
    value = stamp(text, name)
    if value is None:
        return None
    token = value.split(";", 1)[0].strip()
    try:
        return float(token)
    except ValueError as exc:
        raise FieldParseError(f"field {name} has unparseable numeric value {value!r}") from exc


def moves(text):
    """Return actual G0/G1 motion with sticky XYZ/E/F and comments kept separately."""
    out = []
    x = y = z = None
    e, feed, absolute = 0.0, None, True
    body = False
    for line_no, raw in enumerate(text.splitlines(), 1):
        if "BODY_START" in raw:
            body = True
        code = raw.split(";", 1)[0].strip()
        if code.startswith("M82"):
            absolute = True
            continue
        if code.startswith("M83"):
            absolute = False
            continue
        if code.startswith("G92"):
            me = re.search(r"\bE(-?[\d.]+)", code)
            if me:
                e = float(me.group(1))
            continue
        if not re.match(r"^G[01](?:\s|$)", code):
            continue
        vals = {k: float(v) for k, v in re.findall(r"\b([XYZEF])(-?[\d.]+)", code)}
        nx, ny, nz = vals.get("X", x), vals.get("Y", y), vals.get("Z", z)
        if "F" in vals:
            feed = vals["F"] / 60.0
        de = None
        if "E" in vals:
            de = vals["E"] - e if absolute else vals["E"]
            e = vals["E"] if absolute else e + vals["E"]
        distance = (math.dist((x, y, z or 0.0), (nx, ny, nz or 0.0))
                    if None not in (x, y, nx, ny) else 0.0)
        out.append(dict(line=line_no, raw=raw, code=code, body=body, x0=x, y0=y, z0=z,
                        x=nx, y=ny, z=nz, de=de, distance=distance, feed=feed))
        x, y, z = nx, ny, nz
    return out


def result(rule, applicable, why, selected, passed, detail, threshold):
    count = len(selected)
    if not applicable:
        verdict = "NOT_APPLICABLE"
    elif count == 0:
        verdict = "REFUSE"
        passed = False
        detail = f"zero real moves examined; {detail}"
    else:
        verdict = "PASS" if passed else "FAIL"
    return {"rule": rule, "applicable": applicable, "applicability_reason": why,
            "moves_examined": count, "verdict": verdict, "detail": detail,
            "threshold": threshold, "threshold_provenance": PROVENANCE[rule]}


def analyze_text(text):
    ms = moves(text)
    body = [m for m in ms if m["body"] and m["distance"] > 1e-9]
    ext = [m for m in body if m["de"] is not None and m["de"] > 1e-9]
    lh_s, flow_s, mat, printer = stamp(text, "LAYER_H"), stamp(text, "FLOW"), stamp(text, "MATERIAL"), stamp(text, "PRINTER")
    lh = stamped_float(text, "LAYER_H")
    flow_stamp = stamp(text, "FLOW")
    variable_flow = bool(flow_stamp and re.fullmatch(r"VARIABLE:[\d.]+\.\.[\d.]+", flow_stamp))
    declared_flow = None if variable_flow else stamped_float(text, "FLOW")
    out = []

    first = ext[:1]
    r1bad = bool(first) and (first[0]["z"] is None or abs(first[0]["z"] - machine.PRESS_HARD) > 1e-6)
    out.append(result("R1", True, "every printable body needs a pressed first bead", first,
                      not r1bad, "first body bead missing or not pressed" if r1bad else "first body bead pressed",
                      {"pressed_z_mm": machine.PRESS_HARD}))

    # R2 intentionally samples only standalone Z commands whose next deposition uses that Z.
    # Continuous-Z paths have no discrete ladder, so R2 is explicitly not applicable to them.
    layer_moves = []
    pending = None
    for m in ms:
        if re.match(r"^G1 (?:F\d+(?:\.\d+)? )?Z\d+\.\d+$", m["code"]):
            pending = m
        elif pending is not None and m["de"] is not None and m["de"] > 0 and "X" in m["code"]:
            if not layer_moves or pending["z"] != layer_moves[-1]["z"]:
                layer_moves.append(pending)
            pending = None
    steps = [layer_moves[i]["z"] - layer_moves[i-1]["z"] for i in range(1, len(layer_moves))]
    r2app = len(layer_moves) >= 2
    r2bad = not lh or any(s > lh + 1e-6 for s in steps)
    out.append(result("R2", r2app, "two or more deposited Z levels" if r2app else "single deposited Z level",
                      layer_moves[1:] if r2app else [], not r2bad,
                      "layer step exceeds declaration or LAYER_H is absent" if r2bad else "all deposited layer steps fit declaration",
                      {"max_step_mm": lh}))

    pv = stamp(text, "PRESSED_LAYER1")
    pz = stamped_float(text, "PRESSED_LAYER1")
    eligible = [m for m in ext if pz is None or m["z"] is None or abs(m["z"] - pz) > 1e-6]
    speeds = [round(m["feed"], 1) for m in eligible if m["feed"]]
    r3bad = not speeds or max(speeds) > machine.MAX_SPEED + .6 or len(set(speeds)) > 1
    out.append(result("R3", bool(ext), "body contains extruding moves", [m for m in eligible if m["feed"]],
                      not r3bad, "speed varies/exceeds cap" if r3bad else "one body speed within cap",
                      {"max_mm_s": machine.MAX_SPEED, "constancy_tolerance_mm_s": .6}))

    flows = []
    flow_moves = []
    bridge_declared = stamp(text, "BRIDGE_MM2") is not None
    for m in eligible:
        upper = m["raw"].upper()
        declared_regime = ("LINK" in upper or "THIN CROSS" in upper
                           or ("BRIDGE" in upper and bridge_declared))
        if m["feed"] and m["distance"] > .05 and m["de"] and not declared_regime and "PRIME" not in upper:
            flows.append(m["de"] * AREA * m["feed"] / m["distance"]); flow_moves.append(m)
    r4bad = not declared_flow or not flows or any(
        v < machine.R4_FLOW_MIN_RATIO * declared_flow
        or v > machine.R4_FLOW_MAX_RATIO * declared_flow for v in flows)
    out.append(result("R4", bool(ext) and not variable_flow,
                      "explicit variable-flow calibration" if variable_flow else "body contains deposited path",
                      [] if variable_flow else flow_moves, not r4bad,
                      "flow absent or outside declared band" if r4bad else "move flow within declared band",
                      {"declared_mm3_s": declared_flow,
                       "min_fraction": machine.R4_FLOW_MIN_RATIO,
                       "max_fraction": machine.R4_FLOW_MAX_RATIO}))

    travel = [m for m in body if m["de"] is None]
    travel_mm, ext_mm = sum(m["distance"] for m in travel), sum(m["distance"] for m in ext)
    ratio = travel_mm / ext_mm if ext_mm else float("inf")
    out.append(result("R5", bool(body), "body motion exists", body, ratio <= 1.0,
                      f"dry travel ratio {ratio:.6g}", {"max_travel_to_extrusion": 1.0}))

    mat_ok = mat in machine.SUSTAINED_FLOW_BY_MATERIAL if mat else False
    out.append(result("R6", True, "every deposited path requires a known material", ext, mat_ok,
                      f"material {mat!r} {'known' if mat_ok else 'has no maintained flow figure'}",
                      {"known_materials": sorted(machine.SUSTAINED_FLOW_BY_MATERIAL)}))

    code_lines = [l.split(";", 1)[0].strip() for l in text.splitlines()]
    homes = [i for i, l in enumerate(code_lines) if l == "G28" or l.startswith("G28 ")]
    probe_moves = [m for m in ms if homes and m["line"] > homes[0] and not m["body"]][:1]
    temps = []
    for i in homes:
        for l in code_lines[:i]:
            mt = re.match(r"M10[49].*\bS([\d.]+)", l)
            if mt: temps.append(float(mt.group(1)))
    print_s = stamp(text, "PRINT_TEMP")
    print_temp = stamped_float(text, "PRINT_TEMP")
    if print_temp is None and homes:
        after = []
        for l in code_lines[homes[0]:]:
            mt = re.match(r"M109.*\bS([\d.]+)", l)
            if mt: after.append(float(mt.group(1)))
        print_temp = max(after) if after else None
    probe_ok = bool(temps) and print_temp is not None and temps[-1] >= print_temp - 5
    out.append(result("R7", bool(homes), "file homes before printing" if homes else "NO HOME file",
                      probe_moves, probe_ok, f"probe {temps[-1] if temps else None}C; print {print_temp}C",
                      {"print_temperature_c": print_temp, "maximum_colder_by_c": 5}))

    cap = machine.flow_cap(mat, printer) if mat else None
    derated = declared_flow is not None and cap and declared_flow < .8*cap
    r8ok = declared_flow is not None and cap is not None and (not derated or stamp(text, "FLOW_DERATE"))
    out.append(result("R8", bool(ext) and not variable_flow,
                      "variable-flow calibration has no single operating flow" if variable_flow else "deposited path declares an operating flow",
                      [] if variable_flow else flow_moves,
                      bool(r8ok), "flow floor declared with reason" if r8ok else "flow floor missing or silently derated",
                      {"material_printer_cap_mm3_s": cap, "min_fraction": .8}))
    return out


MUTATIONS = {
    "R1": ("raise first bead away from plate", lambda s: s.replace("G1 Z0.100", "G1 Z0.500", 1)),
    "R2": ("raise layer 2 by more than one layer", lambda s: s.replace("G1 Z0.300", "G1 Z0.700", 1)),
    "R3": ("accelerate one body bead above the head-speed ceiling", lambda s: s.replace("G1 X30", "G1 F6000 X30", 1)),
    "R4": ("starve one body bead to 40% material", lambda s: s.replace("X30 Y10 E8.000", "X30 Y10 E5.600", 1)),
    "R5": ("insert dry travel longer than deposited path", lambda s: s.replace("; END", "G0 X200 Y200 F6000\n; END", 1)),
    "R6": ("load an uncharacterised material", lambda s: s.replace("MATERIAL=pla", "MATERIAL=unknown", 1)),
    "R7": ("probe cold so thermal growth collapses the first-layer gap", lambda s: s.replace("M109 S210\nG28", "M109 S150\nG28", 1)),
    "R8": ("silently derate requested flow below 80%", lambda s: s.replace("FLOW=55", "FLOW=20", 1)),
}


def fixture():
    # E values give ~48 mm3/s at 50mm/s. Three layers make R2 genuinely applicable.
    return """; PRINTER=k2plus
; MATERIAL=pla
; LAYER_H=0.2
; FLOW=55
; PRESSED_LAYER1=0.1
; PRINT_TEMP=210
M109 S210
G28
G0 X10 Y10 Z0.100
; BODY_START
G1 Z0.100
G1 F3000 X20 Y10 E4.000
G1 Z0.300
G1 X30 Y10 E8.000
G1 Z0.500
G1 X40 Y10 E12.000
; END
"""


def known_bad_results():
    base = fixture()
    report = {}
    for rule, (physical_reason, mutate) in MUTATIONS.items():
        row = next(r for r in analyze_text(mutate(base)) if r["rule"] == rule)
        report[rule] = {"physical_mutation": physical_reason, "verdict": row["verdict"],
                        "moves_examined": row["moves_examined"], "demonstrated": row["verdict"] in ("FAIL", "REFUSE")}
    return report


def is_multipart(text):
    return bool(re.search(r"^; SEQUENTIAL=", text, re.M) or len(re.findall(r"^; ---- part", text, re.M)) >= 2)


def file_coverage_status(rows):
    """Coverage asks whether applicable rules inspected moves, not whether the file is valid."""
    if any(row["applicable"] and row["moves_examined"] == 0 for row in rows):
        return "REFUSE"
    return "PASS"


def validator_result(path, timeout_s=90):
    """Return validate.py's own verdict and findings without allowing it to abort the report."""
    command = [sys.executable, os.path.join(os.path.dirname(__file__), "validate.py"), path]
    try:
        run = subprocess.run(command, text=True, capture_output=True, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        return {"verdict": "REFUSE", "findings": [],
                "reason": f"validate.py exceeded {timeout_s}s timeout"}
    output = "\n".join(part for part in (run.stdout, run.stderr) if part).strip()
    findings = [line.strip() for line in output.splitlines()
                if line.lstrip().startswith(("FAIL", "REFUSE"))]
    if run.returncode == 0:
        return {"verdict": "PASS", "findings": findings, "reason": "validate.py exited 0"}
    if findings:
        return {"verdict": "FAIL", "findings": findings,
                "reason": f"validate.py exited {run.returncode}"}
    return {"verdict": "REFUSE", "findings": [],
            "reason": f"validate.py exited {run.returncode} without a parseable finding: {output[-500:]}"}


def refused_record(path, reason):
    return {"path": os.path.abspath(path), "analysis_status": "REFUSED", "reason": reason,
            "multipart": False, "coverage_rules": [], "coverage_status": "REFUSE",
            "validator_verdict": "NOT_RUN", "validator_findings": [], "verdict": "REFUSE"}


def build_report(paths, include_all, bad, validate_file=validator_result, validator_timeout=90,
                 validator_workers=4, selection="explicit paths"):
    files = []
    pending_validation = []
    for path in sorted(paths):
        try:
            with open(path) as source:
                text = source.read()
        except (OSError, UnicodeError) as exc:
            files.append(refused_record(path, f"unreadable: {exc}"))
            continue
        multipart = is_multipart(text)
        if not include_all and not multipart:
            if selection == "explicit paths":
                files.append(refused_record(path, "named file is not recognised as multi-part; use --all to analyse it"))
            continue
        if not re.search(r"^G[01](?:\s|$)", text, re.M):
            files.append(refused_record(path, "not recognised as emitted motion G-code: no G0/G1 command"))
            continue
        try:
            rows = analyze_text(text)
        except (FieldParseError, ValueError) as exc:
            files.append(refused_record(path, f"coverage parser refused {os.path.basename(path)}: {exc}"))
            continue
        for row in rows:
            row["known_bad"] = bad[row["rule"]]
        coverage = file_coverage_status(rows)
        record = {"path": os.path.abspath(path), "analysis_status": "ANALYSED",
                  "multipart": multipart, "coverage_rules": rows, "coverage_status": coverage,
                  "validator_verdict": "PENDING", "validator_findings": [], "verdict": "PENDING"}
        files.append(record)
        pending_validation.append(record)

    def run_validator(record):
        return record, validate_file(record["path"], validator_timeout)

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, validator_workers)) as pool:
        for record, validated in pool.map(run_validator, pending_validation):
            record["validator_verdict"] = validated["verdict"]
            record["validator_findings"] = validated.get("findings", [])
            record["validator_reason"] = validated.get("reason")
            record["verdict"] = validated["verdict"]

    summary = {"files": len(files)}
    for verdict in ("PASS", "FAIL", "REFUSE"):
        summary[verdict.lower()] = sum(f["verdict"] == verdict for f in files)
    summary["coverage"] = {verdict.lower(): sum(f["coverage_status"] == verdict for f in files)
                           for verdict in ("PASS", "FAIL", "REFUSE")}
    return {"schema": "crackle.gate-coverage.v2",
            "corpus": {"selection": selection, "requested_paths": len(paths),
                       "rule": "all supplied G-code" if include_all else "multi-part: SEQUENTIAL stamp or at least two part markers"},
            "verdict_definition": "verdict is validate.py's result",
            "coverage_status_definition": "PASS means every applicable coverage rule examined at least one real move; REFUSE means one did not. Per-rule physical verdicts do not change coverage_status.",
            "files": files, "summary": summary}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--all", action="store_true", help="include all supplied files, not only multi-part")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--validator-timeout", type=int, default=90)
    ap.add_argument("--validator-workers", type=int, default=4)
    ns = ap.parse_args(argv)
    bad = known_bad_results()
    if ns.selftest:
        baseline = analyze_text(fixture())
        assert all(r["verdict"] == "PASS" for r in baseline), baseline
        assert all(v["demonstrated"] for v in bad.values()), bad
        zero = fixture().replace("; BODY_START\n", "; BODY_START\n; all body motion removed\n").replace("G1 F3000", "; G1 F3000").replace("G1 X30", "; G1 X30").replace("G1 X40", "; G1 X40")
        zrow = next(r for r in analyze_text(zero) if r["rule"] == "R1")
        assert zrow["verdict"] == "REFUSE" and zrow["moves_examined"] == 0, zrow
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "fixture.gcode")
            with open(path, "w") as output:
                output.write(fixture())
            fake = lambda _path, _timeout: {"verdict": "FAIL", "findings": ["FAIL physical validator finding"], "reason": "test"}
            checked = build_report([path], True, bad, validate_file=fake)
            assert checked["files"][0]["coverage_status"] == "PASS", checked
            assert checked["files"][0]["verdict"] == "FAIL", checked
            assert checked["files"][0]["validator_findings"], checked
            physically_bad = os.path.join(directory, "raised-first-bead.gcode")
            with open(physically_bad, "w") as output:
                output.write(MUTATIONS["R1"][1](fixture()))
            rejected = build_report([physically_bad], True, bad, validate_file=fake)["files"][0]
            assert rejected["coverage_status"] == "PASS", rejected
            assert rejected["verdict"] == "FAIL", rejected
            assert next(r for r in rejected["coverage_rules"] if r["rule"] == "R1")["verdict"] == "FAIL", rejected
            malformed = os.path.join(directory, "malformed.gcode")
            with open(malformed, "w") as output:
                output.write(fixture().replace("PRESSED_LAYER1=0.1", "PRESSED_LAYER1=oops"))
            refused = build_report([malformed], True, bad, validate_file=fake)["files"][0]
            assert refused["verdict"] == "REFUSE" and refused["coverage_rules"] == [], refused
        print(json.dumps({"selftest": "PASS", "known_bad": bad, "zero_move": zrow}, indent=2, sort_keys=True))
        return 0
    paths = ns.paths or glob.glob(os.path.join(os.path.dirname(__file__), "out", "*.gcode"))
    selection = "explicit paths" if ns.paths else "repository out/*.gcode snapshot"
    document = build_report(paths, ns.all, bad, validator_timeout=ns.validator_timeout,
                            validator_workers=ns.validator_workers, selection=selection)
    print(json.dumps(document, indent=2, sort_keys=True, allow_nan=False))
    return 1 if document["summary"]["fail"] or document["summary"]["refuse"] else 0


if __name__ == "__main__":
    sys.exit(main())
