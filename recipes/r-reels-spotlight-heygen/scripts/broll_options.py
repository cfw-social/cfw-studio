#!/usr/bin/env python3
"""usage (from the step work folder): python3 scripts/broll_options.py [BRIEF.json]

Read the six b-roll options from brief.json `options`, check them, and print one line:

  COVERAGE CLIP_SECS MIN_SECS MAX_SECS ORDER REUSE

for the plan.js call in step 04. Defaults: 30 4 2 6 as-given false. ORDER is `as-given` or `even`;
anything else is refused. To put a clip on certain words, pin it in the scene plan. Exit 1 on any bad value.
"""
import json
import math
import sys

DEFAULTS = {"broll_coverage_pct": 30, "broll_clip_seconds": 4, "broll_min_seconds": 2, "broll_max_seconds": 6}


def num(name, value, lo, hi):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not lo <= value <= hi:
        sys.exit("broll_options: %s must be a number from %g to %g (got %r)" % (name, lo, hi, value))
    return "%g" % value


def main(argv):
    path = argv[1] if len(argv) > 1 else "brief.json"
    with open(path, encoding="utf-8") as fh:
        brief = json.load(fh)
    opts = brief.get("options") if isinstance(brief, dict) else None
    opts = opts if isinstance(opts, dict) else {}
    cov = num("broll_coverage_pct", opts.get("broll_coverage_pct", DEFAULTS["broll_coverage_pct"]), 0, 100)
    clip = num("broll_clip_seconds", opts.get("broll_clip_seconds", DEFAULTS["broll_clip_seconds"]), 0.5, 30)
    lo = num("broll_min_seconds", opts.get("broll_min_seconds", DEFAULTS["broll_min_seconds"]), 0.5, 30)
    hi = num("broll_max_seconds", opts.get("broll_max_seconds", DEFAULTS["broll_max_seconds"]), 0.5, 30)
    if float(lo) > float(hi):
        sys.exit("broll_options: broll_min_seconds is larger than broll_max_seconds")
    order = opts.get("broll_order", "as-given")
    if order not in ("as-given", "even"):
        sys.exit("broll_options: broll_order must be as-given or even (got %r); to put a clip on certain words, pin it in work/scene_plan.json" % (order,))
    reuse = opts.get("broll_reuse", False)
    if reuse not in (True, False, "true", "false"):
        sys.exit("broll_options: broll_reuse must be true or false")
    print(cov, clip, lo, hi, order, "true" if reuse in (True, "true") else "false")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
