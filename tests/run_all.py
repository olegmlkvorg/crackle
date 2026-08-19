#!/usr/bin/env python3
"""Discover and run every standalone Python test in tests/.

Exit 0 means every discovered program ran and passed. Exit 1 means at least one ran and failed,
exit 2 means inputs prevented at least one program from running, and exit 3 means both occurred.
Artifact dependencies are literal REQUIRED_ARTIFACTS assignments in the test programs, parsed
without importing them. A malformed declaration is NOT RUN, never silently ignored.
"""
import argparse
import ast
import concurrent.futures
import os
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parent.parent
TESTS = Path(__file__).resolve().parent
SELF = Path(__file__).resolve()


def requirements(path):
    """Read a test's declared corpus inputs without executing the test."""
    try:
        tree = ast.parse(path.read_text(), filename=str(path))
    except (OSError, SyntaxError) as exc:
        raise ValueError(f"cannot classify Python program: {exc}") from exc
    found = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "REQUIRED_ARTIFACTS"
                for target in node.targets):
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, SyntaxError) as exc:
                raise ValueError("REQUIRED_ARTIFACTS must be a literal list or tuple") from exc
            if not isinstance(value, (list, tuple)) or not all(
                    isinstance(item, str) and item for item in value):
                raise ValueError("REQUIRED_ARTIFACTS must contain non-empty filenames")
            found.extend(value)
    return tuple(found)


def discover():
    """Classify every file below tests/: Python programs run, G-code is fixture data."""
    programs, unclassified = [], []
    for path in sorted(TESTS.rglob("*")):
        if not path.is_file() or path.resolve() == SELF or "__pycache__" in path.parts:
            continue
        if path.suffix == ".py":
            programs.append(path)
        elif path.suffix not in (".gcode", ".pyc") and not path.name.startswith("."):
            unclassified.append(path)
    return programs, unclassified


def run_one(path, artifacts, timeout):
    started = time.monotonic()
    try:
        needed = requirements(path)
    except ValueError as exc:
        return path, "NOT RUN", time.monotonic() - started, str(exc), ""
    missing = [str(artifacts / name) for name in needed if not (artifacts / name).is_file()]
    if missing:
        return (path, "NOT RUN", time.monotonic() - started,
                "required artifact absent: " + ", ".join(missing), "")
    env = os.environ.copy()
    env["CRACKLE_ARTIFACTS"] = str(artifacts)
    try:
        result = subprocess.run(
            [sys.executable, str(path)], cwd=ROOT, env=env, text=True,
            capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or "") + (exc.stderr or "")
        return path, "FAIL", time.monotonic() - started, f"exceeded {timeout:g}s timeout", output
    output = result.stdout + result.stderr
    status = "PASS" if result.returncode == 0 else "FAIL"
    reason = f"exit {result.returncode}" if result.returncode else ""
    return path, status, time.monotonic() - started, reason, output


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", type=Path,
                        default=Path(os.environ.get("CRACKLE_ARTIFACTS", ROOT / "out")))
    parser.add_argument("--jobs", type=int, default=min(4, os.cpu_count() or 1))
    parser.add_argument("--timeout", type=float, default=300.0,
                        help="per-program timeout in seconds")
    args = parser.parse_args(argv)
    programs, unclassified = discover()
    if not programs and not unclassified:
        print("SUITE NOT RUN: discovered 0 test programs")
        return 2

    started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        results = list(pool.map(
            lambda path: run_one(path, args.artifacts.resolve(), args.timeout), programs))
    results.extend((path, "NOT RUN", 0.0,
                    "unclassified file in tests/; use .py for a program or .gcode for a fixture",
                    "") for path in unclassified)
    results.sort(key=lambda row: str(row[0]))

    for path, status, duration, reason, output in results:
        label = path.relative_to(ROOT)
        print(f"{status:7s} {label} ({duration:.1f}s){': ' + reason if reason else ''}")
        if status == "FAIL" and output.strip():
            print("\n".join("    " + line for line in output.rstrip().splitlines()[-40:]))

    counts = {status: sum(row[1] == status for row in results)
              for status in ("PASS", "FAIL", "NOT RUN")}
    failures = [str(row[0].relative_to(ROOT)) for row in results if row[1] == "FAIL"]
    not_run = [str(row[0].relative_to(ROOT)) for row in results if row[1] == "NOT RUN"]
    total = len(results)
    print(f"SUITE total={total} ran={total-counts['NOT RUN']} "
          f"passed={counts['PASS']} failed={counts['FAIL']} not_run={counts['NOT RUN']} "
          f"wall={time.monotonic()-started:.1f}s")
    if failures:
        print("FAILURES: " + ", ".join(failures))
    if not_run:
        print("NOT RUN: " + ", ".join(not_run))
    return (1 if failures else 0) + (2 if not_run else 0)


if __name__ == "__main__":
    raise SystemExit(main())
