#!/usr/bin/env python3
"""usage: python3 scripts/gate_spec.py --spec acceptance.json --bed-duration SECONDS --out work/acceptance.run.json [--no-broll]

Write the copy of acceptance.json that b-qa-gate reads for this run. The gate needs the measured
length of the voice bed for two kinds (`json_words_nonempty`, `luma_floor_windows`): this script
writes it as `expected_duration_s` on every check of those kinds, at the top level and in every
step. It changes nothing else, so no threshold is ever loosened here.

--no-broll  the order has no b-roll: drop the look about b-roll beats and the `beat_list.broll`
            window source (there is no beat_list.json to read).
"""
import argparse
import json
import math
import sys

NEEDS_BED = ("json_words_nonempty", "luma_floor_windows")


def checks_of(spec):
    yield spec.get("checks") or []
    for step in (spec.get("steps") or {}).values():
        yield step.get("checks") or []


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--bed-duration", required=True, type=float)
    ap.add_argument("--out", required=True)
    ap.add_argument("--no-broll", action="store_true")
    a = ap.parse_args(argv[1:])
    if not math.isfinite(a.bed_duration) or not 0 < a.bed_duration <= 600:
        sys.exit("gate_spec: --bed-duration must be a number above 0 and at most 600")
    with open(a.spec, encoding="utf-8") as fh:
        spec = json.load(fh)
    for checks in checks_of(spec):
        for c in checks:
            if c.get("type") in NEEDS_BED:
                c["expected_duration_s"] = round(a.bed_duration, 3)
            if a.no_broll and isinstance(c.get("windows_from"), list):
                c["windows_from"] = [w for w in c["windows_from"] if not str(w).startswith("beat_list.")]
    if a.no_broll:
        spec["checks"] = [c for c in spec.get("checks") or [] if c.get("id") != "broll_beats_correct"]
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(spec, fh, indent=2)
    print("gate spec written: %s (bed %.3fs%s)" % (a.out, a.bed_duration, ", no b-roll" if a.no_broll else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
