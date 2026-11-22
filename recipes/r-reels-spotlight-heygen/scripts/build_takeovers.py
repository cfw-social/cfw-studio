#!/usr/bin/env python3
"""usage: python3 scripts/build_takeovers.py WORK_DIR RECIPE_DIR BLOCKS_DIR GSAP_JS

Run from the step work folder. WORK_DIR, GSAP_JS and every path written must be inside it.

Fill the takeover templates from WORK_DIR/plan.json and write the HyperFrames project
WORK_DIR/comp (index.html, compositions/tk<N>.html, base.mp4, gsap.min.js).

* The recipe's own templates (tk-stat, tk-keyword, tk-list, tk-quote) are filled here. Text from
  the plan is escaped to HTML entities before it enters a page: < > & quotes, braces, backslash,
  slash, colon, parentheses and @ all become entities, so no value can look like markup, an
  address or a placeholder. Text that holds a web address or a script address is refused (b-hyperframes'
  check reads a page after undoing entities, so it could not tell it from a real one). The only markup allowed is one <span class="accent">WORD</span> in
  TITLE and QUOTE. Placeholders are filled in a single pass, so a value never fills another one.
* A tk-typing-ui takeover is filled by the b-typing-ui block's own filler
  (scripts/typing_fill.py --wrap template --slot tk<N>, with the brand colours; the block checks contrast). This script writes the text file for it
  and starts it with an argument list, never through a shell.
"""
import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import page_text  # noqa: E402

TOP_KEYS = ("TITLE", "QUOTE")
# The five takeover templates and the fill keys each one reads. Nothing else is accepted: a template name is
# never used in a path unless it is one of these, and a fill key can never be ID, BG, DURATION or any other
# value this script sets itself.
TEMPLATES = {
    "tk-stat": ("EYEBROW", "STAT", "LABEL"),
    "tk-keyword": ("WORD", "SUPPORT"),
    "tk-list": ("TITLE", "ITEM1", "ITEM2", "ITEM3"),
    "tk-quote": ("QUOTE", "ATTR"),
    "tk-typing-ui": ("PROMPT", "LABEL", "CARD_LABEL", "BOTTOM_TAG", "TYPING_SPEED"),
}
PLACEHOLDER = page_text.PLACEHOLDER
HEX6 = re.compile(r"#[0-9A-Fa-f]{6}")
esc, accent_html, fill = page_text.esc, page_text.accent_html, page_text.fill


def number(value, what, lo, hi):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value or not lo <= value <= hi:
        sys.exit("FATAL: %s must be a number from %g to %g (got %r)" % (what, lo, hi, value))
    return float(value)


def inside(path, root):
    rp = os.path.realpath(path)
    return rp == root or rp.startswith(root + os.sep)


def main(argv):
    if len(argv) != 5:
        sys.exit(__doc__)
    work, recipe, blocks, gsap = argv[1:5]
    root = os.path.realpath(".")
    for what, p in (("WORK_DIR", work), ("GSAP_JS", gsap)):
        if not inside(p, root):
            sys.exit("FATAL: %s %s is outside the work folder" % (what, p))
    if not os.path.isfile(gsap):
        sys.exit("FATAL: gsap.min.js not found: run b-hyperframes/scripts/fetch_gsap.py first. Never load a CDN copy.")
    with open(os.path.join(work, "plan.json"), encoding="utf-8") as fh:
        plan = json.load(fh)
    if not isinstance(plan, dict) or not isinstance(plan.get("brand"), dict):
        sys.exit("FATAL: plan.json needs duration and brand")
    dur, brand = round(number(plan.get("duration"), "duration", 1, 600), 2), plan["brand"]
    if not isinstance(plan.get("takeovers", []), list):
        sys.exit("FATAL: takeovers must be a list")
    for k in ("bg", "accent", "fg"):
        if not isinstance(brand.get(k), str) or not HEX6.fullmatch(brand[k]):
            sys.exit("FATAL: brand.%s must be a 6-digit hex with one #" % k)
    proj = os.path.join(work, "comp")
    os.makedirs(os.path.join(proj, "compositions"), exist_ok=True)
    shutil.copy(os.path.join(work, "base.mp4"), os.path.join(proj, "base.mp4"))
    shutil.copy(gsap, os.path.join(proj, "gsap.min.js"))
    shutil.copy(gsap, os.path.join(proj, "compositions", "gsap.min.js"))
    typing_fill = os.path.join(blocks, "b-typing-ui", "scripts", "typing_fill.py")

    tkdivs = []
    for i, tk in enumerate(plan.get("takeovers", [])):
        if not isinstance(tk, dict):
            sys.exit("FATAL: takeover %d is not an object" % i)
        template = tk.get("template")
        if not isinstance(template, str) or template not in TEMPLATES:
            sys.exit("FATAL: takeover %d template %r is not one of %s" % (i, template, ", ".join(sorted(TEMPLATES))))
        start, end = number(tk.get("start"), "takeover %d start" % i, 0, 600), number(tk.get("end"), "takeover %d end" % i, 0, 600)
        if not start < end <= dur + 0.05:
            sys.exit("FATAL: takeover %d needs start < end <= the reel length" % i)
        d = round(end - start, 2)
        fills = tk.get("fill")
        if not isinstance(fills, dict):
            sys.exit("FATAL: takeover %d has no fill object" % i)
        unknown = sorted(set(fills) - set(TEMPLATES[template]))
        missing = ["PROMPT"] if template == "tk-typing-ui" and "PROMPT" not in fills else []
        if unknown or missing:
            sys.exit("FATAL: takeover %d (%s) fill keys: unknown %s, missing %s; allowed: %s" % (i, template, unknown, missing, ", ".join(TEMPLATES[template])))
        for k, v in fills.items():
            if not isinstance(v, (str, int, float)) or isinstance(v, bool):
                sys.exit("FATAL: takeover %d %s must be text or a number" % (i, k))
        out_path = os.path.join(proj, "compositions", "tk%d.html" % i)
        if tk["template"] == "tk-typing-ui":
            text = {"prompt": str(fills.get("PROMPT", ""))}
            for key, name in (("LABEL", "label"), ("CARD_LABEL", "card_label"), ("BOTTOM_TAG", "bottom_tag")):
                if key in fills:
                    text[name] = str(fills[key])
            text_file = os.path.join(work, "takeover-text", "tk%d.json" % i)
            os.makedirs(os.path.dirname(text_file), exist_ok=True)
            with open(text_file, "w", encoding="utf-8") as fh:
                json.dump(text, fh)
            cmd = [sys.executable, typing_fill, "--out", out_path, "--duration", "%g" % d, "--text-file", text_file,
                   "--accent", brand["accent"].lstrip("#"), "--bg", brand["bg"].lstrip("#"), "--fg", brand["fg"].lstrip("#"),
                   "--wrap", "template", "--slot", "tk%d" % i,
                   "--speed", str(fills.get("TYPING_SPEED", "1.0"))]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0:
                sys.exit("FATAL: b-typing-ui typing_fill.py refused takeover %d (exit %d): %s"
                         % (i, res.returncode, (res.stderr or res.stdout).strip()))
        else:
            values = {"ID": "tk%d" % i, "DURATION": d, "BG": brand["bg"], "ACCENT": brand["accent"], "FG": brand["fg"]}
            for k, v in fills.items():
                try:
                    page_text.refuse_addresses(v, "takeover %d %s" % (i, k))
                except ValueError as exc:
                    sys.exit("FATAL: %s" % exc)
                values[k] = accent_html(v) if k in TOP_KEYS else esc(v)
            tpl = os.path.join(recipe, "templates", "%s.html" % tk["template"])
            with open(tpl, encoding="utf-8") as fh:
                page = fill(fh.read(), values)
            left = PLACEHOLDER.findall(page)
            if left:
                sys.exit("FATAL: takeover %d (%s) has unfilled placeholders: %s" % (i, tk["template"], ", ".join(sorted(set(left)))))
            with open(out_path, "w", encoding="utf-8") as fh:
                fh.write(page)
        tkdivs.append('<div id="tk%d-slot" class="takeover-slot" data-composition-id="tk%d" '
                      'data-composition-src="compositions/tk%d.html" data-start="%s" '
                      'data-duration="%s" data-width="1080" data-height="1920" data-track-index="%d"></div>'
                      % (i, i, i, start, d, i + 1))
    with open(os.path.join(recipe, "templates", "root-shell.html"), encoding="utf-8") as fh:
        root_page = fill(fh.read(), {"DURATION": dur, "VIDEO_SRC": "base.mp4", "BG": brand["bg"],
                                     "TAKEOVER_DIVS": "\n  ".join(tkdivs), "CAPTION_DIV": ""})   # captions come later, from b-reel-premium
    with open(os.path.join(proj, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(root_page)
    print("assembled: %d graphics takeovers, %ss" % (len(tkdivs), dur))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
