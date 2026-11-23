#!/usr/bin/env python3
"""Refuse a scene plan that would put a text card under the end card. Standard library only.

  python3 check_scene_plan.py --plan work/scene_plan.json --bed-dur 30.5 --brief brief.json \
          [--cta-dir inputs/cta] [--options work/options.json]

The end card (step 5) is a translucent scrim with copy, laid over the last `cta_duration` seconds. A text
card under it prints through the scrim and the two tangle. So when an end card will be drawn (the option
cta_card is on, there is CTA copy in inputs/cta/ or the brand, and the plan has no planned `cta` scene),
every scene that reaches into that window must be a b-roll scene, a `plain` card (the card background, no
text), or the planned `cta` card. A graphic scene with another type there is refused, naming it.
Scenes timed by phrases (start_phrase) have no numbers to check; the last scene is always checked, and a
phrase-timed scene earlier is reported as a warning. Nothing is written. Exit 0 fine, 1 refused, 2 bad input.
"""
import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cta_copy  # noqa: E402


class Bad(ValueError):
    pass


def time_value(value, name):
    """A real, finite number of seconds, 0 or more. NaN, Infinity, true/false, text and negatives are refused."""
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise Bad("%s must be a finite number of seconds, 0 or more (got %r)" % (name, value))
    return float(value)


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def has_copy(brief, cta_dir):
    try:
        got, _ = cta_copy.read_cta_dir(cta_dir)
    except cta_copy.Bad:
        got = None
    brand = brief.get("brand") if isinstance(brief, dict) and isinstance(brief.get("brand"), dict) else {}
    return bool((got or {}).get("text") or str(brand.get("cta") or "").strip())


def check(plan, bed, seconds):
    scenes = plan.get("scenes") if isinstance(plan, dict) else None
    if not isinstance(scenes, list) or not scenes:
        raise ValueError("the plan has no scenes")
    if any(isinstance(s, dict) and s.get("kind") == "graphic" and str(s.get("type") or "").lower() == "cta" for s in scenes):
        return [], ["the plan has its own cta card: no end card is drawn, so nothing is checked"]
    bed, seconds = time_value(bed, "--bed-dur"), time_value(seconds, "cta_duration")
    window, problems, warnings = bed - seconds, [], []
    for i, s in enumerate(scenes):
        if not isinstance(s, dict) or s.get("kind") != "graphic":
            continue
        kind = str(s.get("type") or "standard").lower()
        end = s.get("end")
        if end is not None:
            end = time_value(end, "scene %r end" % s.get("id", i))
        last = i == len(scenes) - 1
        if end is not None:
            reaches = end > window + 0.05
        elif last:
            reaches = True
        else:
            warnings.append("scene %r is timed by phrases: not checked against the end-card window" % s.get("id", i))
            continue
        if reaches and kind != "plain":
            problems.append("scene %r (type %s) reaches into the last %g s, where the end card is drawn: make the last scene a "
                            "`plain` card (or a b-roll clip), or end the text card before %.1f s" % (s.get("id", i), kind, seconds, window))
    return problems, warnings


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--plan", required=True)
    p.add_argument("--bed-dur", required=True, type=float)
    p.add_argument("--brief", default="brief.json")
    p.add_argument("--cta-dir", default="inputs/cta")
    p.add_argument("--options", default="work/options.json")
    a = p.parse_args(argv)
    try:
        plan, brief, opts = load(a.plan), load(a.brief), load(a.options)
        if opts.get("cta_card") != "on" or not has_copy(brief, a.cta_dir):
            print("scene plan OK: no end card will be drawn (cta_card off or no CTA copy)")
            return 0
        problems, warnings = check(plan, a.bed_dur, opts["cta_duration"])
    except Bad as e:
        sys.stderr.write("check_scene_plan.py: FAILED - %s\n" % e)
        return 2
    except (OSError, ValueError, KeyError, TypeError) as e:
        sys.stderr.write("check_scene_plan.py: FAILED - cannot read the plan, brief or options (%s)\n" % e.__class__.__name__)
        return 2
    for w in warnings:
        print("warning: " + w)
    if problems:
        for x in problems:
            print("REFUSED: " + x)
        return 1
    print("scene plan OK: nothing but a plain card or b-roll under the end card")
    return 0


if __name__ == "__main__":
    sys.exit(main())
