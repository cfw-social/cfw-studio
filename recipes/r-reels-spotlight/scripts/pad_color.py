#!/usr/bin/env python3
"""usage (from the step work folder): python3 scripts/pad_color.py [BRIEF.json]

Print the padding colour for the `letterbox` layout as `0xRRGGBB`, for ffmpeg's `pad=...:color=`. It is the
brand background in brief.json (`brand.palette.bg`, else `brand.bg`) when that is exactly six hex digits
(one optional leading `#`); with none given in a readable brief, the default navy `0F172A`. A brief that is missing, is not JSON or is not an
object is an error (exit 1), never a silent default. Anything else is an error (exit 1) too:
a colour from an order is never put into a filter string unless it passed this check.
"""
import json
import re
import sys

DEFAULT = "0F172A"


def main(argv):
    path = argv[1] if len(argv) > 1 else "brief.json"
    try:
        with open(path, encoding="utf-8") as fh:
            brief = json.load(fh)
    except (OSError, ValueError):
        sys.exit("pad_color: %s cannot be read as JSON; the padding colour is not guessed" % path)
    if not isinstance(brief, dict):
        sys.exit("pad_color: %s must hold a JSON object" % path)
    brand = brief.get("brand") if isinstance(brief.get("brand"), dict) else {}
    palette = brand.get("palette") if isinstance(brand.get("palette"), dict) else {}
    value = palette.get("bg", brand.get("bg"))
    if value is None or value == "":
        value = DEFAULT
    if not isinstance(value, str) or not re.fullmatch(r"#?[0-9A-Fa-f]{6}", value):
        sys.exit("pad_color: the brand background must be exactly six hex digits (got %r)" % (value,))
    print("0x" + value.lstrip("#").upper())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
