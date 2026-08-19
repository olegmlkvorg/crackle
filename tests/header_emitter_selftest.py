#!/usr/bin/env python3
"""Prove the mandatory G-code header boundary fires, passes, and covers emitters."""
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import machine


def sample(flow="12.5"):
    return ("; MATERIAL=pla\n; LAYER_H=0.4\n; FLOW=" + flow
            + "\n; BODY_START\nG1 X1 Y1 Z0.4 E0.1 F3000\n")


with tempfile.TemporaryDirectory() as directory:
    good = os.path.join(directory, "fresh.gcode")
    machine.emit_gcode(good, sample())
    emitted = open(good).read()
    for field in ("MATERIAL", "LAYER_H", "FLOW"):
        assert len(re.findall(rf"^; {field}=", emitted, re.M)) == 1, field

    variable = os.path.join(directory, "calibration.gcode")
    machine.emit_gcode(variable, sample("VARIABLE:10..30"))
    assert "; FLOW=VARIABLE:10..30" in open(variable).read()

    refused = os.path.join(directory, "missing-flow.gcode")
    try:
        machine.emit_gcode(refused, sample().replace("; FLOW=12.5\n", ""))
        raise AssertionError("unstamped emission was accepted")
    except ValueError as exc:
        assert "REFUSING TO EMIT" in str(exc) and "; FLOW=" in str(exc), exc
    assert not os.path.exists(refused)

# Structural gate: a source that emits a body/header must route its final write through the shared
# boundary. Adding a generator with a raw writer makes this test fail before it can ship.
emitters = []
for base, dirs, files in os.walk(ROOT):
    dirs[:] = [d for d in dirs if d not in (".git", "tests", "tools", "fixtures")]
    for name in files:
        if not name.endswith(".py"):
            continue
        path = os.path.join(base, name)
        text = open(path).read()
        emits_marker = re.search(
            r"(?:\bw\(|\.append\()f?['\"]; (?:BODY_START|HEADER_BLOCK_START)", text)
        if emits_marker:
            if re.search(r"open\([^\n]+['\"]w['\"]\)\.write", text):
                raise AssertionError(f"raw G-code writer bypasses machine.emit_gcode: {path}")
            if "machine.emit_gcode(" in text:
                emitters.append(os.path.relpath(path, ROOT))

assert emitters, "no routed emitters found"
print(f"PASS mandatory header emitter: {len(emitters)} directly-writing emit paths routed")
