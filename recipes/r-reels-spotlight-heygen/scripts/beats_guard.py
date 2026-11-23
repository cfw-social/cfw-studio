#!/usr/bin/env python3
"""usage: python3 scripts/beats_guard.py BEAT_LIST.json EDIT_PLAN.json BED_DURATION_SECONDS

The mechanical guard for beat_list.json (the b-roll plan). Exits non-zero with the reason. Every check is an
explicit test (never an `assert`), so `python -O` cannot switch it off.
  - at least one beat has kind "broll";
  - each b-roll clip is a file inside inputs/broll/ and 0 <= in < out <= clip duration;
  - each beat index is a whole number (it becomes part of a file name later);
  - each window lies inside [2, bed - 2];
  - no b-roll beat overlaps a graphics takeover of the edit plan.
"""
import json
import math
import os
import subprocess
import sys


def need(ok, why):
    if not ok:
        sys.exit("beats_guard: " + why)


def is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def main(argv):
    need(len(argv) == 4, "usage: beats_guard.py BEAT_LIST.json EDIT_PLAN.json BED_DURATION_SECONDS")
    with open(argv[1], encoding="utf-8") as fh:
        bl = json.load(fh)
    with open(argv[2], encoding="utf-8") as fh:
        plan = json.load(fh)
    try:
        bed = float(argv[3])
    except ValueError:
        sys.exit("beats_guard: the bed duration must be a number")
    need(math.isfinite(bed) and bed > 0, "the bed duration must be above 0")
    root = os.path.realpath("inputs/broll") + os.sep
    beats = bl.get("beats") if isinstance(bl, dict) else None
    need(isinstance(beats, list), "beat_list.json has no beats list")
    broll = [b for b in beats if isinstance(b, dict) and b.get("kind") == "broll"]
    need(broll, "beats has no broll beat")
    takeovers = plan.get("takeovers", []) if isinstance(plan, dict) else []
    for b in broll:
        idx = b.get("index")
        need(isinstance(idx, int) and not isinstance(idx, bool) and 0 <= idx <= 100000, "a beat index must be a whole number (got %r)" % (idx,))
        br = b.get("broll")
        need(isinstance(br, dict) and isinstance(br.get("clip"), str), "beat %d has no broll clip" % idx)
        clip = br["clip"]
        need(os.path.realpath(clip).startswith(root) and os.path.isfile(clip), "beat %d: clip is not a file in inputs/broll" % idx)
        out = subprocess.run(["ffprobe", "-v", "error", "-protocol_whitelist", "file", "-show_entries", "format=duration", "-of", "csv=p=0", clip],
                             capture_output=True, text=True)
        try:
            dur = float(out.stdout.strip())
        except ValueError:
            sys.exit("beats_guard: beat %d: the clip has no readable duration" % idx)
        need(is_num(br.get("in")) and is_num(br.get("out")), "beat %d: in and out must be numbers" % idx)
        t_in, t_out = float(br["in"]), float(br["out"])
        need(0 <= t_in < t_out <= dur + 0.05, "beat %d: in/out outside the clip" % idx)
        need(is_num(b.get("start")) and is_num(b.get("end")), "beat %d: start and end must be numbers" % idx)
        s, e = float(b["start"]), float(b["end"])
        need(s >= 2 - 1e-6 and e <= bed - 2 + 1e-6, "beat %d: window %s-%s is outside [2, %.2f]" % (idx, s, e, bed - 2))
        for tk in takeovers:
            need(e <= tk["start"] or s >= tk["end"], "broll beat %d overlaps graphics takeover %s-%s" % (idx, tk["start"], tk["end"]))
    print("beats OK: %d b-roll windows, %.1f%% coverage" % (len(broll), bl.get("achieved_broll_pct", 0)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
