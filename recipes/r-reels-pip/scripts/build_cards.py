#!/usr/bin/env python3
"""Write one page per graphics beat, ready to render with b-hyperframes. Renders nothing.

  python3 build_cards.py --beats prior/beat_list.json --brand work/brand.json \
          [--gsap vendor/gsap.min.js] [--list work/cards.json]

For beat N it makes work/gfx_N/ with index.html, text.json and gsap.min.js. The page comes from:
  scene type "typing-ui"  b-typing-ui typing_fill.py, variant pip-safe. Needs scene.prompt;
                          optional scene.label, scene.card_label, scene.bottom_tag.
  scene type "hook"       b-typing-ui hook_fill.py. Lines: scene.lines (a list of at most 3), else
                          the headline split at <br> with its markup removed. scene.eyebrow, scene.sub.
  scene type "plain"      the motion card's background with no text (the seconds the end card covers).
  any other type          this recipe's motion card, fill_page.py. scene.title_html, eyebrow, ghost.
All text is escaped by those fillers; nothing from the beat list is placed in a command line except
as one argument of a started program (no shell). Colours come from the brand: accent (or
palette.accent), palette.bg, palette.fg, each six hex digits; defaults 0F172A / F1F5F9 / F97316.
Writes work/cards.json: [{"index", "dir", "kind", "duration", "out"}]; render each dir to "out".
Exit 0 done, 1 a beat or input is unusable (named), 3 a block is missing.
"""
import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BLOCKS = os.path.realpath(os.path.join(HERE, "..", "..", "..", "blocks"))
TAGS = re.compile(r"<[^>]*>")


class Bad(Exception):
    pass


ROOT = os.path.realpath(os.getcwd())


def number(v, name):
    if type(v) not in (int, float) or v != v or v in (float("inf"), float("-inf")):
        raise Bad("%s is not a number" % name)
    return float(v)


def beat_index(beat):
    """The beat's index, checked before it becomes any part of a path: a plain whole number 0 to 999."""
    i = beat.get("index") if isinstance(beat, dict) else None
    if type(i) is not int or not 0 <= i < 1000:
        raise Bad("a beat has an index that is not a whole number from 0 to 999 (%r); the beat list is not from b-broll-sync" % (i,))
    return i


def inside(path):
    """The real path of `path` is inside the work folder tree (the current folder)."""
    real = os.path.realpath(path)
    return os.path.commonpath([ROOT, real]) == ROOT


def safe_folder(path):
    """Create a folder under the work folder, after checking its real path and that it is no link."""
    if os.path.islink(path) or not inside(path):
        raise Bad("%s is a link or leaves the work folder; refused" % path)
    parent = os.path.dirname(path) or "."
    if not inside(parent):
        raise Bad("%s leaves the work folder; refused" % parent)
    os.makedirs(path, exist_ok=True)


def safe_write(path, data=None, copy_from=None):
    """Write or copy a file inside the work folder: not a link, real path inside, never through a planted link."""
    if os.path.islink(path) or not inside(os.path.dirname(path) or ".") or not inside(path):
        raise Bad("%s is a link or leaves the work folder; refused" % path)
    if copy_from is not None:
        if not inside(copy_from):
            raise Bad("%s leaves the work folder; refused" % copy_from)
        shutil.copyfile(copy_from, path)
    else:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)


def brand_colours(brand):
    pal = brand.get("palette") if isinstance(brand.get("palette"), dict) else {}
    return (str(brand.get("accent") or pal.get("accent") or "F97316").lstrip("#"),
            str(pal.get("bg") or brand.get("bg") or "0F172A").lstrip("#"),
            str(pal.get("fg") or brand.get("fg") or "F1F5F9").lstrip("#"))


def hook_lines(scene):
    if isinstance(scene.get("lines"), list):
        lines = [str(x) for x in scene["lines"]][:3]
    else:
        raw = re.split(r"<br\s*/?>", str(scene.get("title_html") or ""))
        lines = [html.unescape(TAGS.sub("", part)).strip() for part in raw if TAGS.sub("", part).strip()][:3]
    if not lines:
        raise Bad("a hook scene has no lines")
    keys = {"line1": lines[0], "line2": lines[1] if len(lines) > 1 else "", "line3": lines[2] if len(lines) > 2 else ""}
    return keys


def run(cmd, what):
    done = subprocess.run(cmd, capture_output=True, text=True)
    if done.returncode != 0:
        raise Bad("%s failed: %s" % (what, (done.stderr or done.stdout).strip()[-400:]))


def write_json(path, obj):
    safe_write(path, data=obj)


def build(beat, brand, gsap, work="work"):
    i = beat_index(beat)
    scene = beat.get("scene") if isinstance(beat.get("scene"), dict) else {}
    kind = str(scene.get("type") or "standard").strip().lower()
    folder = os.path.join(work, "gfx_%d" % i)
    safe_folder(folder)
    page, text = os.path.join(folder, "index.html"), os.path.join(folder, "text.json")
    dur = "%g" % round(number(beat.get("end"), "a beat's end") - number(beat.get("start"), "a beat's start"), 3)
    accent, bg, fg = brand_colours(brand)
    py = sys.executable
    if kind == "typing-ui":
        data = {"prompt": scene.get("prompt")}
        if not isinstance(data["prompt"], str) or not data["prompt"].strip():
            raise Bad("beat %s: a typing-ui scene needs scene.prompt (this recipe never invents copy)" % i)
        for k in ("label", "card_label", "bottom_tag"):
            if isinstance(scene.get(k), str):
                data[k] = scene[k]
        write_json(text, data)
        run([py, os.path.join(BLOCKS, "b-typing-ui", "scripts", "typing_fill.py"), "--out", page, "--duration", dur,
             "--text-file", text, "--accent", accent, "--bg", bg, "--fg", fg, "--variant", "pip-safe"], "beat %s typing card" % i)
        label = "typing"
    elif kind == "hook":
        data = hook_lines(scene)
        data["eyebrow"] = str(scene.get("eyebrow") or "")
        data["subhead"] = str(scene.get("sub") or "")
        write_json(text, data)
        run([py, os.path.join(BLOCKS, "b-typing-ui", "scripts", "hook_fill.py"), "--out", page, "--duration", dur,
             "--text-file", text, "--accent", accent, "--bg", bg, "--fg", fg], "beat %s hook card" % i)
        label = "hook"
    elif kind == "plain":
        write_json(text, {"plain": "true"})
        run([py, os.path.join(HERE, "fill_page.py"), "--card", "motion", "--out", page, "--duration", dur,
             "--text-file", text, "--accent", accent, "--bg", bg, "--fg", fg], "beat %s plain card" % i)
        label = "plain"
    else:
        write_json(text, {"title_html": str(scene.get("title_html") or ""), "eyebrow": str(scene.get("eyebrow") or ""),
                          "ghost": str(scene.get("ghost") or "")})
        run([py, os.path.join(HERE, "fill_page.py"), "--card", "motion", "--out", page, "--duration", dur,
             "--text-file", text, "--accent", accent, "--bg", bg, "--fg", fg], "beat %s motion card" % i)
        label = "motion"
    safe_write(os.path.join(folder, "gsap.min.js"), copy_from=gsap)
    return {"index": i, "dir": folder.replace(os.sep, "/"), "kind": label, "duration": float(dur),
            "out": "work/bg_beats/bg_beat%d.mp4" % i}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--beats", required=True)
    p.add_argument("--brand", required=True)
    p.add_argument("--gsap", default="vendor/gsap.min.js")
    p.add_argument("--list", default="work/cards.json")
    a = p.parse_args(argv)
    for block in ("b-typing-ui", "b-hyperframes"):
        if not os.path.isdir(os.path.join(BLOCKS, block)):
            sys.stderr.write("build_cards.py: FAILED - block %s is missing beside this recipe\n" % block)
            return 3
    try:
        with open(a.beats, encoding="utf-8") as fh:
            beats = json.load(fh)["beats"]
        with open(a.brand, encoding="utf-8") as fh:
            brand = json.load(fh)
        if not isinstance(brand, dict):
            brand = {}
        if not os.path.isfile(a.gsap):
            raise Bad("%s is missing; run b-hyperframes fetch_gsap.py --outdir vendor first" % a.gsap)
        cards = []
        if not isinstance(beats, list):
            raise Bad("the beat list has no beats")
        for beat in beats:          # every index is checked before anything is written
            beat_index(beat)
        for beat in sorted(beats, key=lambda b: number(b.get("start"), "a beat's start")):
            if beat.get("kind") == "graphics":
                cards.append(build(beat, brand, a.gsap))
            elif beat.get("kind") != "broll":
                raise Bad("beat %s is kind %r; this recipe builds only graphics and broll beats" % (beat.get("index"), beat.get("kind")))
        safe_folder(os.path.join("work", "bg_beats"))
        write_json(a.list, cards)
    except (OSError, ValueError, KeyError, TypeError) as e:
        sys.stderr.write("build_cards.py: FAILED - cannot read the beat list or brand (%s)\n" % e.__class__.__name__)
        return 1
    except Bad as e:
        sys.stderr.write("build_cards.py: FAILED - %s\n" % e)
        return 1
    for c in cards:
        print("beat %d: %s card, %.1f s -> %s" % (c["index"], c["kind"], c["duration"], c["dir"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
