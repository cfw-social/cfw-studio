#!/usr/bin/env python3
"""Resolve the faceless card palette ONCE from brief.json. Standard library only.

Orders carry palettes in more than one shape: {bg, fg, accent} or Social's
{primary, secondary, accent}. Left to guesswork, a step could paint every card in the
brand's near-black ink (#111111): the frames then sit under the gate's luma floor and the
captions vanish into the card. This picks the same colours every time:

  ACCENT  palette.accent, else #F97316
  BG      the card canvas: palette.bg/background/canvas/surface, else the lightest other palette
          colour when it is light (luma >= 160), else the darkest one, else #0F172A.
          A canvas darker than luma 20 is lifted to luma 24 (frames must clear the floor of 16
          after the grade).
  FG      ink on the canvas: palette.fg/text/foreground/ink, else the other palette colour with the
          most contrast to BG; when that contrast is under 100 luma: #111111 on light, #F1F5F9 on dark.
  BAND    the caption band every card paints at y 1392-1920: BG when BG is dark, else FG when FG
          is dark (luma <= 60), else #111111.
  CAP_FG  caption text over BAND: the lightest of BG/FG, at least luma 200 (else #F1F5F9).

  brand_palette.py --brief brief.json [--out work/palette.json]   -> prints the palette as JSON
  (also importable: brand_palette.resolve(palette_dict) returns the same dict)
"""
import argparse
import json
import os
import re
import sys

HEX = re.compile(r"^#?([0-9A-Fa-f]{6})$")
DEFAULT_BG, DEFAULT_FG, DEFAULT_ACCENT = "#0F172A", "#F1F5F9", "#F97316"
LIGHT_INK, DARK_INK = "#111111", "#F1F5F9"


def norm(v):
    if not isinstance(v, str):
        return None
    m = HEX.match(v.strip().replace("##", "#"))
    return "#" + m.group(1).upper() if m else None


def luma(h):
    r, g, b = int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)
    return 0.299 * r + 0.587 * g + 0.114 * b


def lift(h, target=24.0):
    """Mix toward white until luma >= target (keeps the hue of a near-black brand colour)."""
    r, g, b = int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)
    for k in range(0, 101):
        f = k / 100.0
        c = tuple(int(round(x + (255 - x) * f)) for x in (r, g, b))
        if 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2] >= target:
            return "#%02X%02X%02X" % c
    return "#FFFFFF"


def first(p, keys):
    for k in keys:
        v = norm(p.get(k))
        if v:
            return v
    return None


def resolve(palette):
    p = palette if isinstance(palette, dict) else {}
    notes = []
    accent = first(p, ("accent", "highlight")) or DEFAULT_ACCENT
    bg = first(p, ("bg", "background", "canvas", "surface"))
    fg = first(p, ("fg", "text", "foreground", "ink"))
    others = []
    for k, v in p.items():
        h = norm(v)
        if h and h not in (accent, bg, fg) and h not in others:
            others.append(h)
    if not bg:
        light = [h for h in others if luma(h) >= 160]
        if light:
            bg = max(light, key=luma)
            notes.append("canvas = lightest palette colour %s" % bg)
        elif others:
            bg = min(others, key=luma)
            notes.append("canvas = darkest palette colour %s" % bg)
        else:
            bg = DEFAULT_BG
            notes.append("canvas = default %s" % bg)
    if luma(bg) < 20:
        lifted = lift(bg)
        notes.append("canvas %s (luma %.0f) lifted to %s so frames clear the luma floor" % (bg, luma(bg), lifted))
        bg = lifted
    if not fg:
        cands = [h for h in others if h != bg]
        fg = max(cands, key=lambda h: abs(luma(h) - luma(bg))) if cands else None
        if not fg or abs(luma(fg) - luma(bg)) < 100:
            fg = LIGHT_INK if luma(bg) >= 128 else DARK_INK
    if luma(bg) <= 60:
        band = bg
    elif luma(fg) <= 60:
        band = fg
    else:
        band = LIGHT_INK
    cap = max((bg, fg), key=luma)
    if luma(cap) < 200:
        cap = DARK_INK
    return {"BG": bg, "FG": fg, "ACCENT": accent, "BAND": band, "CAP_FG": cap, "notes": notes}


def main(argv=None):
    a = argparse.ArgumentParser(description="Resolve the faceless card palette from brief.json.")
    a.add_argument("--brief", default="brief.json")
    a.add_argument("--out", default="")
    args = a.parse_args(argv)
    try:
        if not os.path.isfile(args.brief):
            sys.stderr.write("brand_palette.py: FAILED - brief %s not found (not guessing a palette)\n" % args.brief)
            return 2
        with open(args.brief, encoding="utf-8") as fh:
            b = json.load(fh)
    except ValueError as e:
        sys.stderr.write("brand_palette.py: FAILED - brief %s is not valid JSON: %s\n" % (args.brief, e))
        return 2
    brand = b.get("brand") if isinstance(b, dict) and isinstance(b.get("brand"), dict) else {}
    d = resolve(brand.get("palette"))
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(d, fh, indent=1)
    for n in d["notes"]:
        sys.stderr.write("[palette] %s\n" % n)
    print(json.dumps({k: d[k] for k in ("BG", "FG", "ACCENT", "BAND", "CAP_FG")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
