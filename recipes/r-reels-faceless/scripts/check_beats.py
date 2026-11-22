#!/usr/bin/env python3
"""The recipe's `beats_cover_bed` check, on b-broll-sync's beat_list.json. Standard library only.

  check_beats.py --beats saves/beat_list.json --bed-duration 41.2 [--inputs-dir inputs]

Beats must be ordered, contiguous, positive and span the voice bed; graphics beats need a safe unique slug
and a headline; the last beat is a graphics call-to-action; every b-roll beat's clip is a real file inside
--inputs-dir with a finite window that covers the beat. Prints the achieved b-roll share. Files must be inside
the current folder. Exit 0 passed, 1 failed, 2 bad usage.
"""
import argparse
import json
import math
import os
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import contracts  # noqa: E402


def inside(path, root):
    real, base = os.path.realpath(path), os.path.realpath(root)
    return real == base or real.startswith(base + os.sep)


def main(argv=None):
    p = argparse.ArgumentParser(description="Check the beat list covers the voice bed.")
    p.add_argument("--beats", required=True)
    p.add_argument("--bed-duration", required=True, type=float)
    p.add_argument("--inputs-dir", default="inputs")
    a = p.parse_args(argv)
    cwd = os.getcwd()
    if not inside(a.beats, cwd) or not math.isfinite(a.bed_duration) or a.bed_duration <= 0:
        sys.stderr.write("check_beats.py: bad path or --bed-duration\n")
        return 2
    try:
        with open(a.beats, encoding="utf-8") as fh:
            plan = json.load(fh)
    except (OSError, ValueError):
        sys.stderr.write("check_beats.py: the beat list is missing or not JSON\n")
        return 2
    try:
        contracts.validate_beats(plan, a.bed_duration)
        broll_secs = 0.0
        for beat in plan["beats"]:
            if beat["kind"] != "broll":
                continue
            b = beat.get("broll") or {}
            clip = b.get("clip")
            if not isinstance(clip, str) or not os.path.isfile(clip) or not inside(clip, os.path.join(cwd, a.inputs_dir)):
                raise ValueError("beat %d: the clip is not a file inside %s" % (beat["index"], a.inputs_dir))
            t_in, t_out = contracts.number(b.get("in")), contracts.number(b.get("out"))
            span = contracts.number(beat["end"]) - contracts.number(beat["start"])
            if t_in < 0 or t_out - t_in < span - 0.1:
                raise ValueError("beat %d: the clip window does not cover the beat" % beat["index"])
            broll_secs += span
    except (ValueError, KeyError, TypeError, AttributeError) as e:
        print("FAIL beats_cover_bed: %s" % e)
        return 1
    print("PASS beats_cover_bed: %d beats, b-roll %.0f%% of the bed" % (len(plan["beats"]), 100 * broll_secs / a.bed_duration))
    return 0


if __name__ == "__main__":
    sys.exit(main())
