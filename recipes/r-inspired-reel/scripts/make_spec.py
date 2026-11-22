#!/usr/bin/env python3
"""Write a version of acceptance.json for this order, with the duration window set from format.json.

  python3 make_spec.py --format format.json --spec ../recipe/acceptance.json --out work/acceptance.order.json [--tolerance 0.15]

The new reel should run about as long as the reference. The window is the reference length plus
or minus the tolerance, kept inside the recipe's own hard window. Nothing else in the spec changes.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from format_schema import validate_format  # noqa: E402
from rs_common import Stop, main, number, read_bytes, read_json, resolve, work_root, write_json  # noqa: E402


def run(argv):
    ap = argparse.ArgumentParser(prog="make_spec.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--format", required=True)
    ap.add_argument("--spec", required=True, help="the recipe's acceptance.json (read only)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--tolerance", default="0.15")
    ap.add_argument("--workdir")
    a = ap.parse_args(argv)
    tol = number(a.tolerance, "--tolerance", 0.02, 0.5)
    root = work_root(a.workdir)
    fmt = validate_format(read_json(root, a.format))
    spec_path = os.path.abspath(a.spec)
    if os.path.islink(spec_path) or not spec_path.lower().endswith(".json") or not os.path.isfile(spec_path):
        raise Stop("--spec must be a regular .json file")
    try:
        spec = json.loads(read_bytes(spec_path, 1_000_000).decode("utf-8"))
        win = next(c for c in spec["checks"] if c.get("type") == "duration_window")
        hard_lo, hard_hi = float(win["min_s"]), float(win["max_s"])
    except (ValueError, KeyError, StopIteration, TypeError):
        raise Stop("the spec has no duration_window check with min_s and max_s")
    dur = fmt["duration_s"]
    lo, hi = max(hard_lo, round(dur * (1 - tol), 1)), min(hard_hi, round(dur * (1 + tol), 1))
    if lo >= hi:
        raise Stop("the reference length (%.1f s) leaves no window inside %g to %g s" % (dur, hard_lo, hard_hi), 1)
    win["min_s"], win["max_s"] = lo, hi
    resolve(root, a.out)
    write_json(root, a.out, spec)
    print("SPEC: duration window %.1f to %.1f s -> %s" % (lo, hi, a.out))
    return 0


if __name__ == "__main__":
    main(run)
