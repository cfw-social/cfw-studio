#!/usr/bin/env python3
"""Fill one of this recipe's two page templates from a JSON text file. Standard library only.

  python3 fill_page.py --card motion --out work/gfx_3/index.html --duration 4.5 \
          --text-file work/gfx_3/text.json --accent F97316 [--bg 0F172A] [--fg F1F5F9]
  python3 fill_page.py --card cta    --out work/cta/index.html    --duration 3 \
          --text-file work/cta/text.json --accent F97316 [--fg F1F5F9]

Text files (a JSON object, every value text, unknown keys refused):

  motion  {"title_html": "...", "eyebrow": "", "ghost": ""}   or {"plain": "true"}: no text at all, only the
          background of the card (used for the seconds the end card covers)
          title_html is plain text plus only <span class="accent">..</span> and <br>, at most
          90 characters of text; an entity the author wrote (&amp;) shows as that character. eyebrow at most 40, ghost at most 4.
  cta     {"text": "...", "handle": ""}      text at most 120, handle at most 60 (empty: no line)

Text that holds a web address (https:, //host, url( and the like) is refused, as the local-only
check would refuse the page. Every value is escaped here and is never placed in a page any other way. Braces, backslash,
slash, colon, parentheses and @ become entities, so no text can look like a placeholder, an
address, a url() or an import to the local-only check of b-hyperframes. Colours must be six hex
digits. Placeholders are filled in one pass; a placeholder left over is an error. The result is
a full page; copy gsap.min.js beside it before rendering.

Reads the text file (and the template in ../templates). Writes the page only, inside the current
folder, refusing a link or a path that leaves it. Exit 0 written, 2 bad input, 1 unexpected error.
"""
import argparse
import html
import json
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATES = os.path.join(os.path.dirname(HERE), "templates")
PLACEHOLDER = re.compile(r"\{\{([A-Z_]+)\}\}")
TOKEN = re.compile(r'(<span class="accent">|</span>|<br\s*/?>)')
DEFAULT_BG, DEFAULT_FG = "0F172A", "F1F5F9"


# Text the local-only check of b-hyperframes would refuse once it is on a page: it is a text scan and
# cannot tell an address written as plain text from a real one. Refused here, up front, naming the key.
ADDRESS_RULES = [
    (re.compile(r"(?i)(?<![A-Za-z0-9+.-])(?:https?|wss?|ftp)\s*:"), "a web address (http, https, ws, wss or ftp)"),
    (re.compile(r"[A-Za-z][A-Za-z0-9+.-]*\s*:\s*/\s*/"), "an address with a scheme (name://)"),
    (re.compile(r"(?i)(?:javascript|vbscript)\s*:"), "a script address"),
    (re.compile(r"(?i)(?<![\w$.])data:\s*[a-z0-9.+-]+/[a-z0-9.+-]+"), "a data: address"),
    (re.compile(r"(?<![A-Za-z0-9])//[A-Za-z0-9\[]"), "a protocol-relative address (//host)"),
    (re.compile(r"(?i)(?<![A-Za-z0-9_])url\s*\("), "url("),
    (re.compile(r"(?i)@\s*import|image-set\s*\("), "a CSS import form"),
    (re.compile(r"(?i)XMLHttpRequest|WebSocket|EventSource|sendBeacon|importScripts|serviceWorker|innerHTML|outerHTML"), "a script word"),
]


class FillError(Exception):
    pass


def refuse_addresses(text, name):
    for pattern, what in ADDRESS_RULES:
        if pattern.search(text):
            raise FillError("%s contains %s. The render check refuses any page with an address in it, even as plain "
                            "text: write example.com, not https://example.com" % (name, what))


def esc(text):
    """HTML text for one value; the characters listed in the module note become entities."""
    out = html.escape(text, quote=True)
    for ch, ref in (("{", "&#123;"), ("}", "&#125;"), ("\\", "&#92;"), ("/", "&#47;"),
                    (":", "&#58;"), ("(", "&#40;"), (")", "&#41;"), ("@", "&#64;")):
        out = out.replace(ch, ref)
    return out


def hex6(value, name):
    v = str(value).strip().lstrip("#") if value is not None else ""
    if not re.fullmatch(r"[0-9A-Fa-f]{6}", v):
        raise FillError("%s must be six hex digits (got %r)" % (name, value))
    return v.upper()


def duration_text(value):
    try:
        d = float(value)
    except (TypeError, ValueError):
        raise FillError("duration is not a number")
    if not 0.5 <= d <= 300:
        raise FillError("duration must be 0.5 to 300 seconds")
    return "%g" % round(d, 3)


def line(value, name, limit, required=False):
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise FillError("%s must be text" % name)
    if re.search(r"[\x00-\x08\x0b-\x1f\x7f  ]", value):
        raise FillError("%s holds a control character" % name)
    flat = re.sub(r"\s+", " ", value).strip()
    if required and not flat:
        raise FillError("%s is empty; this recipe never invents copy" % name)
    if len(flat) > limit:
        raise FillError("%s is %d characters; the limit is %d" % (name, len(flat), limit))
    refuse_addresses(flat, name)
    return flat


def title_html(value):
    """Plain text with only the accent span and <br> kept as markup; every text part is escaped."""
    if not isinstance(value, str):
        raise FillError("title_html must be text")
    parts = TOKEN.split(value)
    depth, out, plain = 0, [], []
    for i, part in enumerate(parts):
        if i % 2 == 0:
            if "<" in part or ">" in part:
                raise FillError("title_html holds markup other than the accent span and <br>")
            part = html.unescape(part)   # an entity the author wrote shows as that character
            plain.append(part)
            out.append(esc(part))
            continue
        if part == '<span class="accent">':
            depth += 1
            if depth > 1:
                raise FillError("title_html nests accent spans")
            out.append('<span class="accent">')
        elif part == "</span>":
            depth -= 1
            if depth < 0:
                raise FillError("title_html closes an accent span that is not open")
            out.append("</span>")
        else:
            out.append("<br>")
    if depth:
        raise FillError("title_html leaves an accent span open")
    text = line("".join(plain), "title_html text", 90, required=True)
    return "".join(out), text


def load_text(path, allowed, required):
    real = os.path.realpath(path)
    root = os.path.realpath(os.getcwd())
    if os.path.commonpath([root, real]) != root:
        raise FillError("--text-file %r is outside the work folder" % path)
    try:
        with open(real, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        raise FillError("--text-file %r is not readable JSON" % path)
    if not isinstance(data, dict):
        raise FillError("--text-file must hold a JSON object")
    unknown = sorted(set(data) - set(allowed))
    if unknown:
        raise FillError("unknown text key(s): %s" % ", ".join(unknown))
    for key in required:
        if key not in data:
            raise FillError("--text-file has no %r" % key)
    return data


def values(card, text, duration, accent, bg, fg):
    base = {"DURATION": duration_text(duration), "ACCENT": hex6(accent, "accent"), "FG": hex6(fg, "fg")}
    if card == "motion" and text.get("plain") == "true":
        base.update({"BG": hex6(bg, "bg"), "TITLE_HTML": "", "EYEBROW": "", "GHOST": ""})
    elif card == "motion":
        title, _ = title_html(text["title_html"])
        base.update({"BG": hex6(bg, "bg"), "TITLE_HTML": title,
                     "EYEBROW": esc(line(text.get("eyebrow"), "eyebrow", 40)),
                     "GHOST": esc(line(text.get("ghost"), "ghost", 4))})
    else:
        handle = line(text.get("handle"), "handle", 60)
        base.update({"CTA_TEXT": esc(line(text["text"], "text", 120, required=True)),
                     "HANDLE_BLOCK": '<p id="cta-handle">%s</p>' % esc(handle) if handle else ""})
    return base


def one_pass(template, vals):
    def put(m):
        if m.group(1) not in vals:
            raise FillError("the template has an unknown placeholder {{%s}}" % m.group(1))
        return vals[m.group(1)]
    out = PLACEHOLDER.sub(put, template)
    return out


def write_page(path, page):
    root = os.path.realpath(os.getcwd())
    target = os.path.abspath(path)
    if os.path.islink(target):
        raise FillError("--out %r is a link; refused" % path)
    parent = os.path.realpath(os.path.dirname(target))
    if os.path.commonpath([root, parent]) != root or not os.path.isdir(parent):
        raise FillError("--out %r is outside the work folder or its folder is missing" % path)
    fd, tmp = tempfile.mkstemp(dir=parent, prefix=".fill-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(page)
        os.replace(tmp, os.path.join(parent, os.path.basename(target)))
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--card", required=True, choices=("motion", "cta"))
    p.add_argument("--out", required=True)
    p.add_argument("--duration", required=True)
    p.add_argument("--text-file", required=True)
    p.add_argument("--accent", required=True)
    p.add_argument("--bg", default=DEFAULT_BG)
    p.add_argument("--fg", default=DEFAULT_FG)
    a = p.parse_args(argv)
    try:
        keys, req = (("title_html", "eyebrow", "ghost", "plain"), ()) if a.card == "motion" else (("text", "handle"), ("text",))
        text = load_text(a.text_file, keys, req)
        if a.card == "motion" and text.get("plain") != "true" and "title_html" not in text:
            raise FillError("--text-file has no 'title_html'")
        if a.card == "motion" and "plain" in text and text["plain"] != "true":
            raise FillError("plain must be the text \"true\"")
        name = "motion-card.html" if a.card == "motion" else "cta-card.html"
        with open(os.path.join(TEMPLATES, name), encoding="utf-8") as fh:
            template = fh.read()
        page = one_pass(template, values(a.card, text, a.duration, a.accent, a.bg, a.fg))
        left = sorted(set(PLACEHOLDER.findall(page)))
        if left:
            raise FillError("placeholder left unfilled: %s" % ", ".join(left))
        write_page(a.out, page)
    except FillError as e:
        sys.stderr.write("fill_page.py: FAILED - %s\n" % e)
        return 2
    print("filled %s card: %s" % (a.card, a.out))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException:
        sys.stderr.write("fill_page.py: FAILED - unexpected error; nothing was written\n")
        sys.exit(1)
