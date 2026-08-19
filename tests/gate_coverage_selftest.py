#!/usr/bin/env python3
"""Self-test for the machine-readable validator coverage gate."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gate_coverage

raise SystemExit(gate_coverage.main(["--selftest"]))
