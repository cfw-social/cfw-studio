#!/usr/bin/env python3
"""usage (from the step work folder):
  python3 scripts/premium_plan.py --edit-plan prior/edit_plan.json --brief brief.json --out work/premium/plan.json

Carve the plan that b-reel-premium reads out of the edit plan: grade, the two brand colours the
captions use, the caption groups, the sound-effect cues and, when the brief names one, a music file.
Prints `CAPTIONS SFX GRADE` (the first two `on` or `off` from the brief's options, then the plan's grade) for the later calls. Writes
nothing else. b-reel-premium's check_plan.py then checks the result; the music path and the sound
names are checked there, not here.
"""
import argparse
import json
import os
import sys


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--edit-plan", required=True)
    ap.add_argument("--brief", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv[1:])
    with open(a.edit_plan, encoding="utf-8") as fh:
        edit = json.load(fh)
    with open(a.brief, encoding="utf-8") as fh:
        brief = json.load(fh)
    opts = brief.get("options") if isinstance(brief, dict) and isinstance(brief.get("options"), dict) else {}
    flags = {}
    for key in ("captions", "sfx"):
        value = opts.get(key, "on")
        if value not in ("on", "off"):
            sys.exit("premium_plan: options.%s must be on or off (got %r)" % (key, value))
        flags[key] = value
    if edit.get("grade", "clean-bright") not in ("warm-amber", "clean-bright", "off"):
        sys.exit("premium_plan: grade must be warm-amber, clean-bright or off (got %r)" % (edit.get("grade"),))
    brand = edit.get("brand") or {}
    plan = {
        "grade": edit.get("grade", "clean-bright"),
        "brand": {"accent": brand.get("accent"), "fg": brand.get("fg")},
        "caption_groups": edit.get("caption_groups") or [],
        "sfx": (edit.get("sfx") or []) if flags["sfx"] == "on" else [],
    }
    music = opts.get("music")
    if music:
        plan["music"] = {"file": music}
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(plan, fh, indent=1)
    print(flags["captions"], flags["sfx"], plan["grade"])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
