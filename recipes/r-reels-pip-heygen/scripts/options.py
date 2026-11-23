#!/usr/bin/env python3
"""Check the order's options and write them, with defaults filled in, to work/options.json.

  python3 options.py [--brief brief.json] [--out work/options.json]

Option values come from the order, and some end up in ffmpeg filters or page text, so each is
checked here and nothing else reads brief.json's options. A bad value stops with one plain line
(exit 1). An option this recipe does not know is named on stderr and left out (never silently).
Standard library only; reads the brief, writes the one file.

  captions on|off              sfx on|off                 cta_card on|off
  grade warm-amber|clean-bright|off
  cta_duration 0.5..8 (3)      pip_ring 0..30 (8)         pip_shadow 0..60 (22)
  broll_coverage_pct 0..100 (30)   broll_clip_seconds 1..30 (4)
  broll_min_seconds 1..30 (2)      broll_max_seconds 1..30 (6)
  broll_order as-given|even (as-given)   broll_reuse true|false (false)
"""
import argparse
import json
import os
import re
import sys

ONOFF = ("on", "off")
CHOICES = {"captions": (ONOFF, "on"), "sfx": (ONOFF, "on"), "cta_card": (ONOFF, "on"),
           "grade": (("warm-amber", "clean-bright", "off"), "clean-bright"),
           "broll_order": (("as-given", "even"), "as-given"),
           "broll_reuse": (("true", "false"), "false")}
NUMBERS = {"cta_duration": (0.5, 8, 3), "pip_ring": (0, 30, 8), "pip_shadow": (0, 60, 22),
           "broll_coverage_pct": (0, 100, 30), "broll_clip_seconds": (1, 30, 4),
           "broll_min_seconds": (1, 30, 2), "broll_max_seconds": (1, 30, 6)}
WHOLE = {"pip_ring", "pip_shadow"}
TEXT = ()


def clean(options):
    out, ignored = {}, []
    for key in options:
        if key not in CHOICES and key not in NUMBERS and key not in TEXT:
            ignored.append(key)
    for key, (allowed, default) in CHOICES.items():
        v = options.get(key, default)
        v = str(v).lower() if isinstance(v, bool) else v
        if v not in allowed:
            raise ValueError("option %s must be one of: %s" % (key, ", ".join(allowed)))
        out[key] = v
    for key, (low, high, default) in NUMBERS.items():
        v = options.get(key, default)
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            if isinstance(v, str) and re.fullmatch(r"[0-9]+(\.[0-9]+)?", v):
                v = float(v)
            else:
                raise ValueError("option %s must be a number" % key)
        if not low <= v <= high or (key in WHOLE and v != int(v)):
            raise ValueError("option %s must be %s%d to %d" % (key, "a whole number, " if key in WHOLE else "", low, high))
        out[key] = int(v) if v == int(v) else v
    for key in TEXT:
        v = options.get(key)
        if v is None:
            continue
        if not isinstance(v, str) or not v.strip() or v.startswith("-") or re.search(r"[\x00-\x1f\x7f]", v):
            raise ValueError("option %s must be plain text that does not start with a dash" % key)
        out[key] = v.strip()
    if out["broll_min_seconds"] > out["broll_max_seconds"]:
        raise ValueError("broll_min_seconds is larger than broll_max_seconds")
    return out, sorted(ignored)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--brief", default="brief.json")
    p.add_argument("--out", default="work/options.json")
    a = p.parse_args(argv)
    try:
        with open(a.brief, encoding="utf-8") as fh:
            brief = json.load(fh)
        options = brief.get("options") if isinstance(brief, dict) else None
        if options is None:
            options = {}
        if not isinstance(options, dict):
            raise ValueError("brief.json options is not an object")
        out, ignored = clean(options)
    except (OSError, ValueError) as e:
        sys.stderr.write("options.py: FAILED - %s\n" % e)
        return 1
    if ignored:
        sys.stderr.write("options.py: ignored (not part of this recipe): %s\n" % ", ".join(ignored))
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    print("options OK: %s" % a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
