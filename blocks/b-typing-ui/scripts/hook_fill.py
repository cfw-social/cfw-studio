#!/usr/bin/env python3
"""Fill the hook card template (templates/hook-scene.html) from a JSON text file.

  python3 hook_fill.py --out work/hook.html --duration 2.5 --text-file work/hook.json \
          --accent F97316 [--bg 0F172A] [--fg F8FAFC] [--wrap standalone|template] [--slot ID]

The text file is a JSON object. `line1` is required; the rest are optional (empty = hidden):

  {"eyebrow": "Day 13", "line1": "PROMPT 13.", "line2": "COLD EMAIL", "line3": "OPENER.", "subhead": ""}

All text is escaped here and goes into the page as HTML text only; it never sits in a script
string. Exit 0 written, 2 bad input or unsafe path (nothing written), 1 an unexpected error (one fixed line, no stack trace), 3 the block's own
template is missing or was changed. Python standard library only. No network. Starts no other program.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fill_common as fc  # noqa: E402

ANCHOR = '<template id="hook-scene-template">'
KEYS = ("eyebrow", "line1", "line2", "line3", "subhead")
LIMITS = {"eyebrow": 80, "line1": 40, "line2": 40, "line3": 40, "subhead": 120}


def fill(template, duration, text, accent, bg="0F172A", wrap="standalone", slot=None, fg="F8FAFC"):
    """Return the filled page. `text` is the parsed JSON object."""
    unknown = sorted(set(text) - set(KEYS))
    if unknown:
        raise fc.FillError("unknown text key(s): %s" % ", ".join(unknown))
    if not isinstance(text.get("line1"), str) or not text["line1"].strip():
        raise fc.FillError("line1 is empty; the hook needs a first line")
    if wrap not in ("standalone", "template"):
        raise fc.FillError("wrap must be standalone or template")
    accent = fc.hex6(accent, "accent")
    bg = fc.hex6(bg, "bg")
    fg = fc.hex6(fg, "fg")
    fc.require_contrast([("fg on bg", fg, bg), ("accent on bg", accent, bg)])
    slot = fc.slot_name(slot)
    vals = {"DURATION": "%g" % fc.number(duration, "duration", 0.5, 300), "ACCENT": accent, "BG": bg, "FG": fg}
    for key in KEYS:
        vals[key.upper()] = fc.one_line(text.get(key, ""), key, LIMITS[key])
    block = fc.cut_template(template, ANCHOR)
    if slot:
        # Rename on the bare template, before any text goes in, so text is never rewritten.
        block = fc.rename_slot(block, "hook-scene", "hs", slot)
    page = fc.one_pass(block, vals)
    return fc.standalone(fc.unwrap(page), bg) if wrap == "standalone" else page + "\n"


def main(argv=None):
    p = argparse.ArgumentParser(description="Fill the hook card template from a JSON text file.")
    p.add_argument("--out", required=True, help="page to write; must be inside the work folder")
    p.add_argument("--duration", required=True, help="clip length in seconds")
    p.add_argument("--text-file", required=True, help="JSON file with eyebrow, line1, line2, line3, subhead")
    p.add_argument("--accent", required=True, help="six-digit hex colour")
    p.add_argument("--bg", default="0F172A", help="background colour, six hex digits")
    p.add_argument("--fg", default="F8FAFC", help="text colour, six hex digits; must have contrast 3.0 or more against the background")
    p.add_argument("--wrap", default="standalone", choices=("standalone", "template"))
    p.add_argument("--slot", default=None, help="give the scene its own id so several can share one page")
    a = p.parse_args(argv)
    try:
        text = fc.load_text_json(a.text_file, KEYS, ("line1",))
        page = fill(fc.read_template("hook-scene.html"), a.duration, text, a.accent, a.bg, a.wrap, a.slot, a.fg)
        fc.write_in_work(a.out, page, inputs=(a.text_file,))
    except fc.FillError as e:
        sys.stderr.write("hook_fill.py: FAILED - %s\n" % e)
        return e.code
    print("hook card written: %s" % a.out)
    if not os.path.exists(os.path.join(os.path.dirname(os.path.abspath(a.out)), "gsap.min.js")):
        fc.note("hook_fill.py: note - gsap.min.js is not beside the page yet; put the pinned copy from b-hyperframes there before rendering")
    return 0


if __name__ == "__main__":
    sys.exit(fc.run_main(main))
