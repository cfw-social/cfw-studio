"""Shared safety helpers for the two filler scripts of b-typing-ui.

Python standard library only. No network. Never starts another program.

What these helpers guarantee:
  - text from a JSON file is checked for type and length, then HTML-escaped before it
    enters a page; the one JS string (the typed prompt) is JSON-encoded instead, with no HTML step;
  - colours are exactly six hex digits, numbers are finite and in range;
  - placeholders are filled in one pass from a fixed list, and a leftover one is an error;
  - the template is refused if it contains any remote address;
  - files are read and written only when their real path (links followed) is inside the
    work folder, which is the current folder, or is the block's own template folder.
"""
import html
import json
import os
import re
import sys
import tempfile

BLOCK_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_DIR = os.path.join(BLOCK_DIR, "templates")

HEX6 = re.compile(r"[0-9A-Fa-f]{6}")
SLOT = re.compile(r"[a-z][a-z0-9-]{0,23}")
PLACEHOLDER = re.compile(r"\{\{([A-Z0-9_]+)\}\}")

# Exit codes shared by both fillers.
EXIT_BAD_INPUT = 2
EXIT_MISSING = 3


class FillError(Exception):
    """A problem with the input. The message says what to fix."""

    code = EXIT_BAD_INPUT


class MissingError(FillError):
    """A required file of the block itself is missing or was changed."""

    code = EXIT_MISSING


# ---- paths ------------------------------------------------------------------

def _inside(root, target):
    rel = os.path.relpath(target, root)
    return rel == "." or not (rel == ".." or rel.startswith(".." + os.sep) or os.path.isabs(rel))


def work_root():
    return os.path.realpath(os.getcwd())


def read_in_work(path, what):
    """Read a UTF-8 file whose real path is inside the work folder."""
    real = os.path.realpath(path)
    if not _inside(work_root(), real):
        raise FillError("%s %r is outside the work folder; refused" % (what, path))
    try:
        with open(real, encoding="utf-8") as fh:
            return fh.read()
    except (OSError, UnicodeDecodeError) as e:
        raise FillError("%s %r cannot be read (%s)" % (what, path, e.__class__.__name__))


def write_in_work(path, text, inputs=()):
    """
    Write a file inside the work folder, safely. Returns the path written.
    Refuses: a target that is a link (even one pointing inside), a parent folder whose real
    path is outside the work folder, and a target that is the same file as any of `inputs`.
    The text goes to a fresh temporary file made exclusively in the target folder, which is then
    renamed into place; the final real path is checked, and the temporary file is removed on failure.
    """
    root = work_root()
    absolute = os.path.abspath(path)
    parent = os.path.dirname(absolute)
    if os.path.islink(absolute):
        raise FillError("--out %r is a link; refused" % path)
    if not os.path.isdir(parent):
        raise FillError("--out folder %r does not exist" % os.path.relpath(parent, root))
    real_parent = os.path.realpath(parent)
    if not _inside(root, real_parent):
        raise FillError("--out %r is outside the work folder; refused" % path)
    full = os.path.join(real_parent, os.path.basename(absolute))
    if os.path.lexists(full) and os.path.isdir(full):
        raise FillError("--out %r is a folder" % path)
    for other in inputs:
        if os.path.exists(other) and os.path.exists(full) and os.path.samefile(other, full):
            raise FillError("--out %r is the same file as an input; refused" % path)
        if os.path.realpath(other) == full:
            raise FillError("--out %r is the same file as an input; refused" % path)
    fd, tmp = tempfile.mkstemp(dir=real_parent, prefix=".fill-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.chmod(tmp, 0o644)
        os.replace(tmp, full)
    except OSError as e:
        _remove(tmp)
        raise FillError("--out %r cannot be written (%s)" % (path, e.__class__.__name__))
    except BaseException:
        _remove(tmp)
        raise
    if not _inside(root, os.path.realpath(full)):
        _remove(full)
        raise FillError("--out %r ended up outside the work folder; removed" % path)
    return full


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


def run_main(main):
    """Run a filler's main(). An unexpected error prints one fixed line and exits 1, never a stack trace."""
    try:
        return main()
    except SystemExit:
        raise
    except BaseException:  # noqa: B902 (last resort)
        sys.stderr.write("FAILED - unexpected error; nothing was written. Check the arguments and the files, then try again.\n")
        return 1


def read_template(name):
    """The block's own template. Never a path from the command line."""
    path = os.path.join(TEMPLATE_DIR, name)
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        raise MissingError("template %s is missing from the block" % name)
    problems = local_only_problems(text)
    if problems:
        raise MissingError("template %s is not local-only: %s" % (name, "; ".join(problems)))
    return text


# ---- values -----------------------------------------------------------------

def hex6(value, name):
    """A colour: six hex digits, with or without a leading #. Returns it upper-case, no #."""
    if not isinstance(value, str):
        raise FillError("%s must be text like F97316" % name)
    v = value[1:] if value.startswith("#") else value
    if not HEX6.fullmatch(v):
        raise FillError("%s %r is not a six-digit hex colour" % (name, value))
    return v.upper()


def number(value, name, low, high):
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise FillError("%s must be a number" % name)
    if v != v or v in (float("inf"), float("-inf")) or v < low or v > high:
        raise FillError("%s must be between %g and %g" % (name, low, high))
    return v


# ---- colour contrast (WCAG 2.x) ----------------------------------------------------

MIN_CONTRAST = 3.0


def _rgb(hexcode):
    return tuple(int(hexcode[i:i + 2], 16) for i in (0, 2, 4))


def mix(a, b, pct_a):
    """CSS color-mix(in srgb, a pct_a%, b) on six-digit hex strings; returns six-digit hex."""
    ra, rb = _rgb(a), _rgb(b)
    return "".join("%02X" % round(x * pct_a / 100.0 + y * (100 - pct_a) / 100.0) for x, y in zip(ra, rb))


def luminance(hexcode):
    def lin(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(c) for c in _rgb(hexcode))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def require_contrast(pairs):
    """pairs: [(label, text_hex, background_hex)]. Refuse any pair below 3.0, naming it."""
    for label, fg, bg in pairs:
        ratio = contrast(fg, bg)
        if ratio < MIN_CONTRAST:
            raise FillError("%s: contrast ratio %.2f is below %.1f (colour %s on %s). Choose a lighter or darker colour"
                            % (label, ratio, MIN_CONTRAST, fg, bg))


def slot_name(value):
    if value is None:
        return None
    if not SLOT.fullmatch(value):
        raise FillError("--slot %r must be lower-case letters, digits and hyphens, starting with a letter (24 characters at most)" % value)
    return value


def load_text_json(path, allowed, required):
    """Read the JSON text file: an object whose keys are all in `allowed`, values all strings."""
    raw = read_in_work(path, "--text-file")
    try:
        data = json.loads(raw)
    except ValueError as e:
        raise FillError("--text-file is not valid JSON: %s" % e)
    if not isinstance(data, dict):
        raise FillError("--text-file must hold a JSON object")
    unknown = sorted(set(data) - set(allowed))
    if unknown:
        raise FillError("--text-file has unknown key(s): %s (allowed: %s)" % (", ".join(unknown), ", ".join(sorted(allowed))))
    for key, value in data.items():
        if not isinstance(value, str):
            raise FillError("--text-file key %r must be text" % key)
    missing = [k for k in required if not data.get(k, "").strip()]
    if missing:
        raise FillError("--text-file needs non-empty: %s" % ", ".join(missing))
    return data


_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_LINE_BREAKS = re.compile(r"\r\n|\r| | |\x85")


_SURROGATE = re.compile(r"[\ud800-\udfff]")
_BIDI = re.compile(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069]")
_C1 = re.compile(r"[\x80-\x84\x86-\x9f]")


def _no_controls(text, name):
    """Refuse characters that do not belong in a label or a prompt. `name` is the JSON key."""
    if _SURROGATE.search(text):
        raise FillError("%s holds a broken character (a lone surrogate); fix the text" % name)
    if _CONTROL.search(text) or _C1.search(text):
        raise FillError("%s holds a control character; remove it (only tab and line breaks may appear, and only in prompt)" % name)
    if _BIDI.search(text):
        raise FillError("%s holds a text-direction control character (U+200E, U+200F, U+202A to U+202E, U+2066 to U+2069); remove it" % name)


# Text that the render check (b-hyperframes/scripts/check_local.py) would refuse once it is on the page.
# The check is a text scan: it cannot tell an address written as plain text from a real one, and it
# also reads text after undoing HTML entities and CSS escapes. So these are refused here, up front.
_ADDRESS_RULES = [
    (re.compile(r"(?i)(?<![A-Za-z0-9+.-])(?:https?|wss?|ftp)\s*:"), "a web address (http, https, ws, wss or ftp)",
     "write example.com, not https://example.com"),
    (re.compile(r"[A-Za-z][A-Za-z0-9+.-]*\s*:\s*/\s*/"), "an address with a scheme (name://)", "write the name without the scheme"),
    (re.compile(r"(?i)(?:javascript|vbscript)\s*:"), "a script address (javascript: or vbscript:)", "leave out the colon, or rephrase"),
    (re.compile(r"(?i)(?<![\w$.])data:\s*[a-z0-9.+-]+/[a-z0-9.+-]+"), "a data: address", "write the content in words"),
    (re.compile(r"(?<![A-Za-z0-9])//[A-Za-z0-9\[]"), "a protocol-relative address (//host)", "write example.com, not //example.com"),
    (re.compile(r"(?i)(?<![A-Za-z0-9_])url\s*\("), "url(", "leave out the brackets, or rephrase"),
    (re.compile(r"(?i)@\s*import"), "@import", "rephrase"),
    (re.compile(r"(?i)image-set\s*\("), "image-set(", "rephrase"),
]
_CSS_ESCAPE = re.compile(r"\\([0-9a-fA-F]{1,6})[ \t\n]?|\\(.)", re.S)


def _css_decode(text):
    """The way the check undoes CSS escapes, so that a disguised address shows up."""
    def one(m):
        if m.group(1):
            n = int(m.group(1), 16)
            return chr(n) if 0 < n <= 0x10FFFF else ""
        return m.group(2)
    return _CSS_ESCAPE.sub(one, text)


def refuse_addresses(text, name):
    """Refuse a web address, script address or CSS address form in a text value. Exit 2, naming the key."""
    for form in (text, _css_decode(text)):
        for pattern, what, hint in _ADDRESS_RULES:
            if pattern.search(form):
                raise FillError("%s contains %s. The render check refuses any page with an address in it, even as plain text. Fix: %s" % (name, what, hint))


# Script words that the check refuses wherever they appear in a page, even in plain text. They are not
# addresses, so they are accepted, and one letter of each is written as an escape so the page shows the
# same text without the word being in the file.
_SCRIPT_WORDS = re.compile(
    r"(?i)XMLHttpRequest|WebSocket|EventSource|sendBeacon|importScripts|serviceWorker|innerHTML|outerHTML|"
    r"insertAdjacentHTML|createContextualFragment|DOMParser|(?:document|window)\s*\.\s*(?:write|open)|"
    r"location\s*\.\s*(?:href|assign|replace)|new\s+Function")


def _hidden_positions(text):
    return {m.start() for m in _SCRIPT_WORDS.finditer(text)}


def _limit(text, name, limit):
    if len(text) > limit:
        raise FillError("%s is %d characters (at most %d)" % (name, len(text), limit))


def one_line(text, name, limit):
    """Text for one HTML line. Line breaks and runs of spaces become one space."""
    _no_controls(text, name)
    flat = re.sub(r"\s+", " ", _LINE_BREAKS.sub(" ", text)).strip()
    _limit(flat, name, limit)
    refuse_addresses(flat, name)
    return html_text(flat)


_HTML_ENTITY_CHARS = frozenset("{}\\/:()@=[]")


def html_text(text):
    """
    HTML-escape. < > & and quotes become entities. So do braces, backslash, slash, colon, parentheses, @,
    = and brackets, so no value can look like a placeholder, a url(), an import or a font rule. They display
    the same. One letter of each script word (see _SCRIPT_WORDS) is also written as an entity.
    """
    hide = _hidden_positions(text)
    out = []
    for i, ch in enumerate(text):
        if i in hide or ch in _HTML_ENTITY_CHARS:
            out.append("&#%d;" % ord(ch))
        else:
            out.append(html.escape(ch, quote=True))
    return "".join(out)


def multi_line(text, name, limit):
    """Text with line breaks, normalised to LF, for the typed prompt."""
    _no_controls(text, name)
    norm = _LINE_BREAKS.sub("\n", text)
    _limit(norm, name, limit)
    refuse_addresses(norm, name)
    return norm


_JS_PLAIN = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .,;!?-_")


def js_string_body(text):
    """
    The body of a JS "..." literal whose value is exactly `text`.
    Letters, digits, spaces and . , ; ! ? - _ stay as they are. Every other character is written
    as a \\uXXXX escape (a UTF-16 pair above U+FFFF). So no quote, backslash, line break, </script>,
    {{KEY}}, entity or address can appear in the script text, and the page needs no decoding step.
    """
    out = []
    hide = _hidden_positions(text)
    for i, ch in enumerate(text):
        if ch in _JS_PLAIN and i not in hide:
            out.append(ch)
            continue
        cp = ord(ch)
        if cp > 0xFFFF:
            cp -= 0x10000
            out.append("\\u%04x\\u%04x" % (0xD800 + (cp >> 10), 0xDC00 + (cp & 0x3FF)))
        else:
            out.append("\\u%04x" % cp)
    return "".join(out)


# ---- local-only check ------------------------------------------------------------

_REMOTE = [
    (re.compile(r"(?i)\b(?:https?|wss?|ftp|file)\s*:"), "a remote or file address"),
    (re.compile(r"//"), "a // (a protocol-relative address or comment)"),
    (re.compile(r"(?i)@import"), "@import"),
    (re.compile(r"(?i)\bdata\s*:(?!image/)"), "a data: address that is not an image"),
    (re.compile(r"(?i)javascript\s*:"), "a javascript: address"),
    (re.compile(r"(?i)<\s*(?:iframe|object|embed|base|link)\b"), "an iframe, object, embed, base or link tag"),
    (re.compile(r"(?i)<\s*meta\b[^>]*http-equiv"), "a meta http-equiv tag"),
    (re.compile(r"(?i)\b(?:fetch|import)\s*\("), "fetch( or import("),
    (re.compile(r"(?i)XMLHttpRequest|WebSocket|EventSource|sendBeacon"), "a network API"),
]
_SCRIPT_SRC = re.compile(r"(?i)<script\b[^>]*\bsrc\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)")


def local_only_problems(page):
    """Everything in `page` that could reach the network or leave the folder. Empty list = clean."""
    problems = []
    for pattern, label in _REMOTE:
        if pattern.search(page):
            problems.append(label)
    for m in _SCRIPT_SRC.finditer(page):
        if m.group(1).strip("\"'") != "gsap.min.js":
            problems.append("a script src other than gsap.min.js: %s" % m.group(1))
    for m in re.finditer(r"(?i)\b(?:src|href|poster|action|srcset)\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", page):
        target = m.group(1).strip("\"'")
        if target and target != "gsap.min.js" and not target.startswith("data:image/") and not target.startswith("#"):
            problems.append("an attribute points at %r" % target)
    return problems


# ---- filling ----------------------------------------------------------------

def one_pass(src, values):
    """Fill {{KEY}} once. A value that itself contains {{KEY}} is never filled again."""
    out = PLACEHOLDER.sub(lambda m: values[m.group(1)] if m.group(1) in values else m.group(0), src)
    left = sorted(set(PLACEHOLDER.findall(out)))
    if left:
        raise FillError("unfilled placeholders: %s" % ", ".join(left))
    return out


def cut_template(src, anchor):
    """Drop the usage comment before the anchor; return the <template>...</template> block."""
    if src.count(anchor) != 1:
        raise MissingError("template changed shape: no single %s" % anchor)
    block = src[src.index(anchor):].rstrip()
    if not block.endswith("</template>"):
        raise MissingError("template changed shape: it does not end with </template>")
    return block


def unwrap(block):
    inner = re.sub(r"^<template[^>]*>\s*", "", block, count=1)
    return re.sub(r"\s*</template>$", "", inner)


def rename_slot(src, scene, prefix, slot):
    """Give a scene its own id and prefix its element ids and classes, so several can share a page."""
    src = src.replace(scene, slot)
    return re.sub(r"(?<=[.#\"])%s-" % re.escape(prefix), "%s-%s-" % (slot, prefix), src)


def standalone(inner, bg):
    return ("<!DOCTYPE html>\n<html><head><meta charset=\"utf-8\">"
            "<style>html,body{margin:0;padding:0;width:1080px;height:1920px;overflow:hidden;background:#%s;}</style>"
            "</head><body>\n%s\n</body></html>\n" % (bg, inner))


def note(message):
    sys.stderr.write(message + "\n")
