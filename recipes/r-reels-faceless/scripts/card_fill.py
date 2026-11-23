#!/usr/bin/env python3
"""Fill templates/card.html for one graphics beat of the faceless reel. Standard library only.

  card_fill.py --beats work/beat_list.json --index 2 --palette work/palette.json \\
               --cta work/cta.json --out work/gfx/beat2-demo/index.html \\
               [--display-font NAME] [--body-font NAME]

The scene text is read from the beat list, never from the command line. Every piece of text is
escaped before it enters the page: letters, digits and spaces stay, every other character becomes a
numeric entity (so no value can close a tag, look like an address, a url() or an import, or be
evaluated). The only markup allowed in a headline is `<span class="accent">...</span>` and `<br>`;
anything else is refused. Colours must be six hex digits. All files must resolve inside the current
folder. The output is written to a temporary file in its folder and renamed into place; a target that
is a link is refused.

Scene types: standard, hook, stat, chips, flow, checklist, terminal, cta. A `typing` scene is not
filled here: use b-typing-ui's typing_fill.py. Exit codes: 0 written, 2 bad input or unsafe path.
"""
import argparse
import json
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(os.path.dirname(HERE), "templates", "card.html")
TYPES = ("standard", "hook", "stat", "chips", "flow", "checklist", "terminal", "cta")
PLACEHOLDER_GHOSTS = {"CTA", "TITLE", "HEADER", "HEADLINE", "TEXT", "SUB"}
HEX = re.compile(r"^#?([0-9A-Fa-f]{6})$")
FONT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ]{0,39}$")
TOKEN = re.compile(r'<span class="accent">(.*?)</span>|<br\s*/?>|<[^>]*>|[^<]+', re.S)
LIMITS = {"eyebrow": 40, "ghost": 4, "sub": 160, "headline": 90}


class Bad(Exception):
    pass


# The local-only check in b-hyperframes reads a page again after undoing entities, so it cannot tell a
# sentence from a link. Text that holds an address is refused here, up front, naming the field.
ADDRESS = re.compile(r"(?i)\b(?:https?|wss?|ftp|javascript|vbscript)\s*:|\bdata\s*:\s*[a-z]+/|(?<![\w:])//[\w.-]|"
                     r"url\s*\(|@import|image-set\s*\(|\bsrcdoc\b")


def no_address(value, name):
    if ADDRESS.search(value):
        raise Bad("%s holds a web address or script address; write example.com, not https://example.com" % name)
    return value


def esc(text, strip=True):
    """Text for an HTML element: only letters, digits and spaces stay; all else is a numeric entity."""
    text = re.sub(r"[\r\n\t  \u0085]+", " ", str(text))
    out = []
    for ch in text:
        if ch == " " or ch.isalnum():
            out.append(ch)
        elif ord(ch) < 32 or ord(ch) == 127:
            out.append(" ")
        else:
            out.append("&#%d;" % ord(ch))
    return "".join(out).strip() if strip else "".join(out)


def text_field(scene, key, limit, required=False):
    value = scene.get(key, "")
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise Bad("scene.%s must be text" % key)
    value = no_address(value.strip(), "scene." + key)
    if required and not value:
        raise Bad("scene.%s is required for this card" % key)
    if len(value) > limit:
        raise Bad("scene.%s is longer than %d characters" % (key, limit))
    return value


def text_list(scene, key, lo, hi, limit):
    items = scene.get(key)
    if not isinstance(items, list) or not lo <= len(items) <= hi:
        raise Bad("scene.%s must be a list of %d to %d texts" % (key, lo, hi))
    out = []
    for item in items:
        if not isinstance(item, str) or not item.strip() or len(item.strip()) > limit:
            raise Bad("each scene.%s entry must be text of 1 to %d characters" % (key, limit))
        out.append(no_address(item.strip(), "scene." + key))
    return out


def headline_html(source):
    """Headline markup: text, the accent span and <br>. Everything else is refused."""
    plain = re.sub(r"<[^>]*>", "", source).strip()
    no_address(plain, "the headline")
    if not plain:
        raise Bad("the headline has no text")
    if len(plain) > LIMITS["headline"]:
        raise Bad("the headline is longer than %d characters" % LIMITS["headline"])
    out = []
    for match in TOKEN.finditer(source):
        token = match.group(0)
        if match.group(1) is not None:
            if "<" in match.group(1):
                raise Bad("markup inside the accent span is not allowed")
            out.append('<span class="accent">%s</span>' % esc(match.group(1), strip=False))
        elif re.fullmatch(r"<br\s*/?>", token):
            out.append("<br>")
        elif token.startswith("<"):
            raise Bad("the headline may only use the accent span and <br>")
        else:
            out.append(esc(token, strip=False) if token.strip() else " ")
    return "".join(out), len(plain)


def colour(value, name):
    m = HEX.match(value.strip()) if isinstance(value, str) else None
    if not m:
        raise Bad("%s is not a six-digit hex colour" % name)
    return m.group(1).upper()


TICK = ('<svg width="44" height="44" viewBox="0 0 44 44"><path d="M9 23 L19 33 L36 12" fill="none" '
        'stroke="#0B0B0B" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"></path></svg>')
ARROW = ('<svg width="44" height="44" viewBox="0 0 44 44"><path d="M22 6 L22 34 M10 24 L22 36 L34 24" fill="none" '
         'stroke="currentColor" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"></path></svg>')


def hero_for(kind, scene, cta):
    if kind == "chips":
        chips = text_list(scene, "chips", 2, 8, 24)
        return '<div class="chips">%s</div>' % "".join('<div class="chip item">%s</div>' % esc(c) for c in chips)
    if kind == "checklist":
        rows = text_list(scene, "items", 2, 6, 60)
        return '<div class="list">%s</div>' % "".join(
            '<div class="row item"><div class="tick">%s</div><div>%s</div></div>' % (TICK, esc(r)) for r in rows)
    if kind == "flow":
        steps = text_list(scene, "flow", 2, 5, 28)
        parts = []
        for i, s in enumerate(steps):
            if i:
                parts.append('<div class="arrow item">%s</div>' % ARROW)
            parts.append('<div class="step item">%s</div>' % esc(s))
        return '<div class="flow">%s</div>' % "".join(parts)
    if kind == "terminal":
        lines = text_list(scene, "lines", 1, 8, 60)
        body = "".join('<div class="tline"><span class="p">&#62;</span> %s</div>' % esc(l) for l in lines)
        return ('<div class="term item"><div class="dots"><div class="dot"></div><div class="dot"></div>'
                '<div class="dot"></div></div>%s<div class="tline"><span class="cursor" id="cursor"></span></div></div>' % body)
    if kind == "stat":
        stat = text_field(scene, "stat", 10, required=True)
        unit = text_field(scene, "unit", 14)
        return ('<div class="statwrap item"><svg viewBox="0 0 640 640"><circle cx="320" cy="320" r="270" fill="none" '
                'stroke="rgba(128,128,128,0.25)" stroke-width="22"></circle><circle id="ring" cx="320" cy="320" r="270" '
                'fill="none" stroke="var(--accent)" stroke-width="22" stroke-linecap="round" '
                'stroke-dasharray="1700" stroke-dashoffset="0" transform="rotate(-90 320 320)"></circle></svg>'
                '<div><div class="stat">%s</div>%s</div></div>'
                % (esc(stat), '<div class="unit" style="text-align:center">%s</div>' % esc(unit) if unit else ""))
    if kind == "cta":
        handle = cta.get("handle", "") if isinstance(cta, dict) else ""
        if not isinstance(handle, str) or len(handle) > 80:
            raise Bad("cta.handle must be text of at most 80 characters")
        no_address(handle, "cta.handle")
        icon = ('<div class="ctaicon item" id="pulse"><svg viewBox="0 0 260 260"><circle cx="130" cy="130" r="112" '
                'fill="none" stroke="var(--accent)" stroke-width="14"></circle><path d="M130 190 L130 80 M84 124 L130 78 '
                'L176 124" fill="none" stroke="var(--accent)" stroke-width="16" stroke-linecap="round" '
                'stroke-linejoin="round"></path></svg></div>')
        return icon + ('<div class="btn item">%s</div>' % esc(handle.strip()) if handle.strip() else "")
    # standard and hook: rotating rings and nodes
    return ('<div class="orbit item"><svg viewBox="0 0 620 620"><circle cx="310" cy="310" r="120" fill="none" '
            'stroke="var(--accent)" stroke-width="10"></circle><g id="orbit"><circle cx="310" cy="310" r="220" fill="none" '
            'stroke="rgba(128,128,128,0.45)" stroke-width="6" stroke-dasharray="18 22"></circle>'
            '<circle cx="530" cy="310" r="26" fill="var(--accent)"></circle><circle cx="200" cy="500" r="18" '
            'fill="var(--fg)"></circle><circle cx="150" cy="150" r="14" fill="var(--accent)"></circle></g></svg></div>')


def inside_cwd(path):
    root = os.path.realpath(os.getcwd())
    real = os.path.realpath(path)
    return real == root or real.startswith(root + os.sep)


def read_json(path, what):
    if not inside_cwd(path):
        raise Bad("%s must be inside the work folder" % what)
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        raise Bad("%s could not be read as JSON" % what) from None


def build(beat, palette, cta, display_font="", body_font="", template=None):
    if not isinstance(beat, dict) or beat.get("kind") != "graphics" or not isinstance(beat.get("scene"), dict):
        raise Bad("the beat is not a graphics beat")
    scene = beat["scene"]
    start, end = beat.get("start"), beat.get("end")
    if not all(type(v) in (int, float) for v in (start, end)) or not 0.5 <= end - start <= 300:
        raise Bad("the beat span must be 0.5 to 300 seconds")
    kind = str(scene.get("type") or "standard").lower()
    if kind == "typing":
        raise Bad("typing cards are filled by b-typing-ui's typing_fill.py, not here")
    if kind not in TYPES:
        raise Bad("unknown scene type '%s' (known: %s)" % (kind[:30], ", ".join(TYPES)))
    head, plain_len = headline_html(text_field(scene, "title_html", 400, required=True))
    eyebrow = text_field(scene, "eyebrow", LIMITS["eyebrow"])
    ghost = text_field(scene, "ghost", LIMITS["ghost"])
    if ghost.upper() in PLACEHOLDER_GHOSTS:
        raise Bad("the ghost glyph '%s' is a placeholder word; use a number or a letter" % ghost)
    sub = text_field(scene, "sub", LIMITS["sub"])
    palette = palette if isinstance(palette, dict) else {}
    colours = {k: colour(palette.get(k, ""), "palette." + k) for k in ("BG", "FG", "ACCENT", "BAND")}
    faces = ["Oswald", "Inter", "JetBrains Mono"]
    stacks = {}
    for key, name, generic in (("DISPLAY", display_font, '"Oswald", sans-serif'), ("BODY", body_font, '"Inter", sans-serif')):
        name = (name or "").strip()
        if name:
            if not FONT.match(name):
                raise Bad("a font name may use letters, digits and spaces only (1 to 40 characters)")
            if name not in faces:
                faces.append(name)
            stacks[key] = '"%s", %s' % (name, generic)
        else:
            stacks[key] = generic
    size = 132 if plain_len <= 24 else 112 if plain_len <= 48 else 96 if plain_len <= 72 else 84
    values = {
        "DURATION": "%g" % round(end - start, 3),
        "BG": colours["BG"], "FG": colours["FG"], "ACCENT": colours["ACCENT"], "BAND": colours["BAND"],
        "FONT_FACES": " ".join('@font-face { font-family: "%s"; src: local("%s"); }' % (f, f) for f in faces),
        "DISPLAY": stacks["DISPLAY"], "BODY": stacks["BODY"], "TYPE": kind, "HEAD_SIZE": str(size),
        "GHOST": esc(ghost), "HEADLINE": head,
        "EYEBROW_BLOCK": '<div class="eyebrow" id="eyebrow">%s</div>' % esc(eyebrow) if eyebrow else "",
        "SUB_BLOCK": '<div class="sub" id="sub">%s</div>' % esc(sub) if sub else "",
        "HERO": hero_for(kind, scene, cta),
    }
    if template is None:
        with open(TEMPLATE, encoding="utf-8") as fh:
            template = fh.read()
    # One pass over a fixed list. Text that looks like a placeholder is never filled again.
    page = re.sub(r"\{\{([A-Z_]+)\}\}", lambda m: values[m.group(1)] if m.group(1) in values else m.group(0), template)
    left = sorted(set(re.findall(r"\{\{[A-Z_]+\}\}", page)))
    if left:
        raise Bad("unfilled placeholders: " + ", ".join(left))
    return page


def write_safely(path, page):
    if os.path.islink(path):
        raise Bad("the output is a symbolic link")
    parent = os.path.dirname(os.path.abspath(path)) or "."
    if not inside_cwd(parent) or not inside_cwd(path):
        raise Bad("the output must be inside the work folder")
    os.makedirs(parent, exist_ok=True)
    if not inside_cwd(parent):
        raise Bad("the output must be inside the work folder")
    fd, tmp = tempfile.mkstemp(dir=parent, prefix=".card-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(page)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def main(argv=None):
    p = argparse.ArgumentParser(description="Fill the faceless card template for one graphics beat.")
    p.add_argument("--beats", required=True)
    p.add_argument("--index", required=True, type=int)
    p.add_argument("--palette", required=True)
    p.add_argument("--cta", default="")
    p.add_argument("--out", required=True)
    p.add_argument("--display-font", default="")
    p.add_argument("--body-font", default="")
    a = p.parse_args(argv)
    try:
        beats = read_json(a.beats, "the beat list")
        palette = read_json(a.palette, "the palette")
        cta = read_json(a.cta, "the CTA file") if a.cta else {}
        items = beats.get("beats") if isinstance(beats, dict) else None
        if not isinstance(items, list) or not 0 <= a.index < len(items):
            raise Bad("no beat with that index")
        page = build(items[a.index], palette, cta, a.display_font, a.body_font)
        write_safely(a.out, page)
    except Bad as e:
        sys.stderr.write("card_fill.py: FAILED - %s\n" % e)
        return 2
    except OSError:
        sys.stderr.write("card_fill.py: FAILED - a file could not be read or written\n")
        return 2
    print("card written: %s" % a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
