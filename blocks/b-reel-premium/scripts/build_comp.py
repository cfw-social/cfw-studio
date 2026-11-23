#!/usr/bin/env python3
"""Fill the caption overlay page and the root page from a checked premium plan.

  python3 build_comp.py --plan work/premium/plan.json --reel work/assembled.mp4 --cap-top 1180 \
      --outdir work/premium/comp

Writes inside --outdir only:
  index.html                       the root page (transparent, holds only the caption slot)
  compositions/caption-overlay.html
  gsap.min.js (also in compositions/) a copy of the animation library file (default vendor/gsap.min.js)
  fonts/caption-font.<ext> (also in compositions/) only when the plan names brand.font_file

The reel is read only for its length (and to confirm it holds video); it is NOT copied into the
composition. Render the composition to a transparent video with
`hf_render.py --comp DIR --out captions.mov --format mov`, then mux.py lays it over the graded reel.

The plan is checked first with the same rules as check_plan.py. Caption words are written into the
page as script-safe JSON in which every character except ASCII letters, digits and spaces is a
\\uXXXX escape, and are shown with textContent. The colours, the top edge and the length are checked
numbers or hex colours. The result is scanned for remote addresses and scripts before the script
exits 0. It never fetches the animation library: pass the file b-hyperframes fetched.

Exit codes: 0 done, 1 plan or input problem (nothing written), 2 bad arguments, 3 ffprobe missing.
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import plan_lib as pl  # noqa: E402

# Anything that could reach the network or load other code from a finished page.
REMOTE = re.compile(
    r"(?i)\b(?:https?|wss?|ftp):|(?<![\w*])//|\bfetch\s*\(|XMLHttpRequest|WebSocket|EventSource|sendBeacon"
    r"|@import|\bimport\s*\(|<iframe|<object|<embed|<base\b|http-equiv|javascript:|data:(?!image/)"
)
SCRIPT_SRC = re.compile(r"(?i)<script\b[^>]*\bsrc\s*=\s*[\"']?([^\"'\s>]+)")


def remote_problems(name, text):
    probs = []
    for m in REMOTE.finditer(text):
        probs.append("%s holds %r, which could reach the network" % (name, m.group(0)))
    for m in SCRIPT_SRC.finditer(text):
        if m.group(1) != "gsap.min.js":
            probs.append("%s loads the script %r; only gsap.min.js beside the page is allowed" % (name, m.group(1)))
    return probs


def build_parser():
    ap = argparse.ArgumentParser(prog="build_comp.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--plan", required=True)
    ap.add_argument("--reel", required=True, help="the assembled reel; read for its length only, not copied")
    ap.add_argument("--cap-top", required=True, type=int, help="top edge of the caption band, 0 to 1920")
    ap.add_argument("--gsap", default="vendor/gsap.min.js",
                    help="the animation library file b-hyperframes fetched (default: vendor/gsap.min.js)")
    ap.add_argument("--outdir", required=True, help="folder to write, inside the work folder")
    ap.add_argument("--duration", type=float, help="reel length in seconds (default: read with ffprobe)")
    ap.add_argument("--workdir", default=".")
    ap.add_argument("--any-script", action="store_true", help="allow caption words that are not Latin script")
    ap.add_argument("--cover-tolerance", type=float, default=3.0)
    return ap


def main(argv):
    args = build_parser().parse_args(argv)
    try:
        root = pl.workdir_root(args.workdir)
        plan_path = pl.check_in_workdir(args.plan, root, "--plan", must_exist=True)
        reel = pl.check_in_workdir(args.reel, root, "--reel", must_exist=True)
        gsap = pl.check_in_workdir(args.gsap, root, "--gsap", must_exist=True)
        pl.refuse_inner_symlinks(args.outdir, root, "--outdir")
        outdir = pl.check_in_workdir(args.outdir, root, "--outdir", must_exist=False)
        if outdir == root:
            raise pl.PlanError(["--outdir must be a folder below the work folder, not the work folder itself"])
        if os.path.exists(outdir) and not os.path.isdir(outdir):
            raise pl.PlanError(["--outdir exists and is not a folder"])
        if not 0 <= args.cap_top <= 1920:
            raise pl.PlanError(["--cap-top must be a whole number from 0 to 1920"])
        pl.check_tolerance(args.cover_tolerance)
        if os.path.getsize(gsap) == 0:
            raise pl.PlanError(["--gsap file is empty"])
        if args.duration is None:
            pl.require_video(reel, "--reel")
        duration = pl.check_duration(args.duration) if args.duration is not None else pl.probe_duration(reel)
        duration = round(duration, 2)
        try:
            plan = pl.load_json(plan_path)
        except (OSError, ValueError) as e:
            sys.stderr.write("build_comp.py: cannot read the plan: %s\n" % e)
            return 2
        pl.require_sound_plan(plan, duration, root, captions=True, sfx=False,
                              cover_tolerance=args.cover_tolerance, any_script=args.any_script)

        groups = pl.clean_groups(plan["caption_groups"])
        accent = pl.norm_color(plan["brand"]["accent"])
        fg = pl.norm_color(plan["brand"]["fg"])
        values = {
            "DURATION": pl.num_text(duration), "CAP_TOP": str(int(args.cap_top)),
            "ACCENT": accent, "FG": fg, "GROUPS_JSON": pl.script_json(groups),
            "TIMELINE_JS": pl.timeline_js(groups),
        }
        font = None
        if plan["brand"].get("font_file") is not None:
            font = pl.check_font_path(plan["brand"]["font_file"], root)
            values["FONT_FACE"] = ('@font-face { font-family: "%s"; src: url("fonts/caption-font%s"); font-weight: 700; }'
                                   % (pl.FONT_FAMILY_NAME, font[1]))
            values["FONT_STACK"] = '"%s", sans-serif' % pl.FONT_FAMILY_NAME
            values["FONT_NAME"] = pl.FONT_FAMILY_NAME
        else:
            values["FONT_FACE"] = ""
            values["FONT_STACK"] = "sans-serif"
            values["FONT_NAME"] = "sans-serif"
        caption_page = pl.fill_template(pl.read_template("caption-overlay.html"), values)
        root_page = pl.fill_template(pl.read_template("root-shell-polish.html"), values)
        probs = remote_problems("caption-overlay.html", caption_page) + remote_problems("index.html", root_page)
        if probs:
            raise pl.PlanError(probs)
    except FileNotFoundError as e:
        sys.stderr.write("build_comp.py: a required tool is missing: %s\n" % e)
        return 3

    comp_dir = os.path.join(outdir, "compositions")
    jobs = [(os.path.join(comp_dir, "caption-overlay.html"), {"data": caption_page.encode("utf-8")}),
            (os.path.join(outdir, "index.html"), {"data": root_page.encode("utf-8")}),
            (os.path.join(outdir, "gsap.min.js"), {"copy_from": gsap}),
            # The caption page is a sub-composition: its own relative links resolve from compositions/, and
            # the renderer may inline it into the root, so the library and font sit in both places.
            (os.path.join(comp_dir, "gsap.min.js"), {"copy_from": gsap})]
    if font:
        for base in (outdir, comp_dir):
            jobs.append((os.path.join(base, "fonts", "caption-font" + font[1]), {"copy_from": font[0]}))
    inputs = {os.path.realpath(x) for x in (plan_path, reel, gsap) + ((font[0],) if font else ())}
    for target, _ in jobs:
        if os.path.realpath(target) in inputs:
            raise pl.PlanError(["%s is also an input file" % os.path.relpath(target, root)])
    for target, _ in jobs:
        pl.preflight_target(target, root, "--outdir")
    pl.ensure_dir(outdir, root, "--outdir")
    for target, kw in jobs:
        pl.write_file(target, root, what="--outdir", **kw)
    print("comp written: %s (%d groups, %.2f s, cap_top=%d)" % (os.path.relpath(outdir, root), len(groups), duration, args.cap_top))
    return 0


if __name__ == "__main__":
    sys.exit(pl.run_main(main, "build_comp.py", sys.argv[1:]))
