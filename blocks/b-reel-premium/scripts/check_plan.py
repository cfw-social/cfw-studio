#!/usr/bin/env python3
"""Check a premium plan (captions, colours, sound effects, grade, music) before anything renders.

  python3 check_plan.py --plan work/premium/plan.json --duration 42.3
  python3 check_plan.py --plan work/premium/plan.json --reel work/assembled.mp4 [--workdir work]

Prints one line on stdout and exits 0 when the plan is sound. Otherwise prints every problem,
one per line, on stderr. Reads only the plan, the music file it names (existence only), and the
reel's duration (ffprobe). Writes nothing.

Exit codes: 0 sound, 1 the plan has problems, 2 bad arguments or unreadable plan, 3 ffprobe missing.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import plan_lib as pl  # noqa: E402


def build_parser():
    ap = argparse.ArgumentParser(prog="check_plan.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--plan", required=True, help="plan JSON file, inside the work folder")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--duration", type=float, help="reel length in seconds")
    group.add_argument("--reel", help="reel file; its length is read with ffprobe")
    ap.add_argument("--workdir", default=".", help="the work folder (default: current folder)")
    ap.add_argument("--captions", choices=("on", "off"), default="on", help="off skips the caption checks")
    ap.add_argument("--sfx", choices=("on", "off"), default="on", help="off skips the sound-effect checks")
    ap.add_argument("--cover-tolerance", type=float, default=3.0,
                    help="how far from the end of the reel the last caption may end, in seconds (default 3.0)")
    ap.add_argument("--any-script", action="store_true", help="allow caption words that are not Latin script")
    return ap


def main(argv):
    args = build_parser().parse_args(argv)
    try:
        root = pl.workdir_root(args.workdir)
        plan_path = pl.check_in_workdir(args.plan, root, "--plan", must_exist=True)
        if args.reel:
            reel = pl.check_in_workdir(args.reel, root, "--reel", must_exist=True)
            duration = pl.probe_duration(reel)
        else:
            duration = pl.check_duration(args.duration)
        pl.check_tolerance(args.cover_tolerance)
        try:
            plan = pl.load_json(plan_path)
        except (OSError, ValueError) as e:
            sys.stderr.write("check_plan.py: cannot read the plan: %s\n" % e)
            return 2
        probs = pl.plan_problems(plan, duration, root, captions=args.captions == "on", sfx=args.sfx == "on",
                                 cover_tolerance=args.cover_tolerance, any_script=args.any_script)
        if probs:
            raise pl.PlanError(probs)
    except FileNotFoundError as e:
        sys.stderr.write("check_plan.py: a required tool is missing: %s\n" % e)
        return 3
    n_groups = len(plan.get("caption_groups") or []) if args.captions == "on" else 0
    n_sfx = len(plan.get("sfx") or []) if args.sfx == "on" else 0
    print("premium plan OK: %d caption groups, %d sfx, grade %s" % (n_groups, n_sfx, plan["grade"]))
    return 0


if __name__ == "__main__":
    sys.exit(pl.run_main(main, "check_plan.py", sys.argv[1:]))
