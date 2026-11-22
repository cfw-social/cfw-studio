#!/usr/bin/env python3
"""Local-only check for a HyperFrames composition folder.

    python3 check_local.py --comp work/comp [--work work]

Reads every HTML, CSS, script and SVG file in the composition folder, plus the text
files they reference, and fails if the page could load anything from the network or
could build such a request at run time. Local files must resolve inside the work
folder. This is a text scan, not a sandbox: see README.md for what it cannot catch.

Exit codes: 0 passed, 1 problems found (listed on stderr), 2 bad usage.
"""
import argparse
import hashlib
import html as htmllib
import os
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hfcommon import FAIL, OK, Stop, has_symlink_below, inside_work, is_inside, load_pins, run_main, work_folder  # noqa: E402

TEXT_EXT = {".html", ".htm", ".css", ".js", ".mjs", ".cjs", ".svg", ".xml"}
MARKUP_EXT = {".html", ".htm", ".svg", ".xml"}
SCRIPT_EXT = {".html", ".htm", ".js", ".mjs", ".cjs", ".svg"}
MAX_FILE = 4 * 1024 * 1024

REF_ATTRS = {"src", "href", "poster", "data-src", "data-composition-src", "xlink:href",
             "action", "formaction", "background", "manifest", "ping", "data", "archive", "cite",
             "codebase", "icon", "longdesc", "usemap", "lowsrc", "dynsrc", "profile"}
SRCSET_ATTRS = {"srcset", "imagesrcset"}
REFUSED_ATTRS = {"srcdoc"}
GENERIC_FONTS = {"sans-serif", "serif", "monospace", "cursive", "fantasy", "system-ui", "ui-sans-serif",
                 "ui-serif", "ui-monospace", "ui-rounded", "emoji", "math", "fangsong", "-apple-system",
                 "blinkmacsystemfont", "inherit", "initial", "unset", "revert", "revert-layer"}
NAMESPACES = re.compile(r"http://www\.w3\.org/(?:2000/svg|1999/xlink|1999/xhtml)")
DATA_OK = re.compile(r"^data:(?:image/(?:png|jpe?g|gif|webp|avif)|font/(?:woff2?|ttf|otf));base64,", re.I)

ANY_FILE_RULES = [
    (re.compile(r"(?i)(?<![A-Za-z0-9+.-])(?:https?|wss?|ftp)\s*:"), "a network address (http, https, ws, wss or ftp)"),
    (re.compile(r"(?i)(?:javascript|vbscript)\s*:"), "a script address"),
    (re.compile(r"""["'`]//[A-Za-z0-9\[]"""), "a protocol-relative address"),
    (re.compile(r"(?i)(?<![\w$.])data:\s*[a-z0-9.+-]+/[a-z0-9.+-]+"), "a data: address that is not a small image or font"),
]
MARKUP_RULES = [
    (re.compile(r"(?i)<\s*(?:iframe|object|embed|base|frame|frameset|applet|portal)\b"), "an embedding or base element"),
    (re.compile(r"(?i)<\s*meta\b[^>]*http-equiv"), "a meta http-equiv element"),
    (re.compile(r"(?i)<\s*link\b[^>]*rel\s*=\s*[\"']?(?:preconnect|dns-prefetch|prefetch|prerender)"), "a connection hint link"),
]
SCRIPT_RULES = [
    (re.compile(r"\bfetch\s*\("), "fetch("),
    (re.compile(r"\bXMLHttpRequest\b"), "XMLHttpRequest"),
    (re.compile(r"\bWebSocket\b"), "WebSocket"),
    (re.compile(r"\bEventSource\b"), "EventSource"),
    (re.compile(r"\bsendBeacon\b"), "sendBeacon"),
    (re.compile(r"\bimport\s*\("), "dynamic import("),
    (re.compile(r"(?m)^\s*import\s+[\w*{\"']"), "a module import"),
    (re.compile(r"\bimportScripts\b"), "importScripts"),
    (re.compile(r"\b(?:Shared)?Worker\s*\("), "a Worker"),
    (re.compile(r"\bserviceWorker\b"), "serviceWorker"),
    (re.compile(r"\beval\s*\("), "eval("),
    (re.compile(r"\bnew\s+Function\b|(?<![\w$.])Function\s*\("), "the Function constructor"),
    (re.compile(r"\b(?:window|self|globalThis|top|parent|frames)\s*\["), "computed access on the global object"),
    (re.compile(r"\binnerHTML\b(?!\s*=\s*(?:\"\"|'')\s*[;\n}])|\b(?:outerHTML|insertAdjacentHTML|createContextualFragment|DOMParser)\b|document\s*\.\s*write"),
     "markup built from a string at run time"),
    (re.compile(r"\bsetAttribute\s*\(\s*[\"'](?:src|href|srcset|data|poster|action|formaction|xlink:href)[\"']"),
     "a link attribute set at run time"),
    (re.compile(r"\.\s*(?:src|href|srcset|poster)\s*=[^=]"), "a link property set at run time"),
    (re.compile(r"\bnew\s+(?:Image|Audio)\s*\("), "new Image or new Audio"),
    (re.compile(r"\bcreateElement(?:NS)?\s*\([^)]*(?:script|iframe|link|img|video|audio|source|object|embed)"),
     "a loadable element created at run time"),
    (re.compile(r"\blocation\s*(?:\.\s*(?:href|assign|replace)\b|=[^=])|\bwindow\s*\.\s*open\b"), "navigation or window.open"),
]
CSS_ESCAPE = re.compile(r"\\([0-9a-fA-F]{1,6})[ \t\n]?|\\(.)", re.S)
ESCAPE_IN_URL = re.compile(r"(?i)(?:url\([^)]*|@import[^;]*|src\s*:[^;}]*)\\[0-9a-fA-F\\]")
IMAGE_SET = re.compile(r"(?i)image-set\s*\(")
URL_FN = re.compile(r"""url\(\s*(['"]?)(.*?)\1\s*\)""", re.I | re.S)
IMPORT = re.compile(r"""@import\s+(?:url\(\s*)?["']?([^"')\s;]+)""", re.I)
FONT_FACE = re.compile(r"@font-face\s*\{[^}]*?font-family\s*:\s*([^;}]+)[;}]", re.I)
FONT_FAMILY = re.compile(r"(?<![\w-])font-family\s*(?::|=)\s*([^;}\"{]+|\"[^\"]*\"|'[^']*')", re.I)
FONT_SHORT = re.compile(r"(?<![\w-])font\s*:\s*[^;}{]*?\d(?:px|pt|em|rem|%|vw|vh)(?:\s*/\s*[\d.]+\w*)?\s+([^;}{]+)", re.I)
CUSTOM_PROP = re.compile(r"(--[\w-]+)\s*:\s*([^;}]+)")


def decode_escapes(text):
    """Undo HTML entities and CSS escapes so that a disguised address shows up."""
    text = htmllib.unescape(text)

    def css(m):
        if m.group(1):
            n = int(m.group(1), 16)
            return chr(n) if 0 < n <= 0x10FFFF else ""
        return m.group(2)
    return CSS_ESCAPE.sub(css, text)


def line_of(text, pos):
    return text.count("\n", 0, pos) + 1


def split_families(raw):
    out = []
    for part in raw.split(","):
        name = part.strip().strip("'\"").strip()
        if name and "!important" in name.lower():
            name = name.lower().replace("!important", "").strip()
        if name:
            out.append(name)
    return out


class Refs(HTMLParser):
    """Collects every attribute that can name a file or an address."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.refs = []  # (line, value)

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if value is None:
                continue
            name = name.lower()
            if name in REF_ATTRS:
                self.refs.append((self.getpos()[0], value))
            elif name in REFUSED_ATTRS:
                self.refs.append((self.getpos()[0], "srcdoc:" + value[:20]))
            elif name in SRCSET_ATTRS:
                for item in value.split(","):
                    if item.strip():
                        self.refs.append((self.getpos()[0], item.strip().split()[0]))

    handle_startendtag = handle_starttag


class Checker:
    def __init__(self, comp, work, gsap_sha):
        self.comp, self.work, self.gsap_sha = comp, work, gsap_sha
        self.problems, self.seen, self.queue, self.scanned = [], set(), [], 0
        self.fonts_used, self.fonts_declared, self.custom = {}, set(), {}

    def problem(self, path, line, msg):
        try:
            name = str(Path(path).relative_to(self.work))
        except ValueError:
            name = str(path)
        item = f"{name}:{line}: {msg}"
        if item not in self.problems:
            self.problems.append(item)

    def add_file(self, path):
        key = os.path.realpath(path)
        if key not in self.seen:
            self.seen.add(key)
            self.queue.append(Path(path))

    def check_ref(self, src, line, value, allow_fragment=True):
        raw = value.strip()
        if not raw or (allow_fragment and raw.startswith("#")):
            return
        if DATA_OK.match(raw):
            return
        if re.search(r"[\\\x00-\x1f]", raw):
            self.problem(src, line, f"reference with a backslash or control character: {raw[:60]!r}")
            return
        if re.match(r"(?i)^[a-z][a-z0-9+.-]*:", raw) or raw.startswith("//"):
            self.problem(src, line, f"reference to an address outside the work folder: {raw[:80]}")
            return
        if "{{" in raw or "${" in raw or "var(" in raw.lower():
            self.problem(src, line, f"reference that cannot be checked (placeholder or variable): {raw[:60]}")
            return
        rel = unquote(re.split(r"[?#]", raw, maxsplit=1)[0])
        if re.match(r"(?i)^[a-z][a-z0-9+.-]*:", rel) or rel.startswith(("/", "//")) or "\\" in rel:
            self.problem(src, line, f"reference that is not a relative local path: {raw[:80]}")
            return
        target = Path(os.path.normpath(Path(src).parent / rel))
        if not is_inside(target, self.work) or has_symlink_below(self.work, target):
            self.problem(src, line, f"reference leaves the work folder or uses a symbolic link: {raw[:80]}")
            return
        if not target.exists():
            self.problem(src, line, f"referenced file does not exist: {raw[:80]}")
            return
        if target.is_file() and target.suffix.lower() in TEXT_EXT:
            self.add_file(target)

    def scan_file(self, path):
        suffix = path.suffix.lower()
        try:
            if path.stat().st_size > MAX_FILE:
                self.problem(path, 1, "file is larger than 4 MB; text files are not scanned above that size")
                return
            data = path.read_bytes()
        except OSError as exc:
            self.problem(path, 1, f"cannot read file: {exc}")
            return
        if self.gsap_sha and hashlib.sha256(data).hexdigest() == self.gsap_sha:
            return  # the pinned GSAP build, verified by checksum
        self.scanned += 1
        text = data.decode("utf-8", errors="replace")
        plain = NAMESPACES.sub("", text)
        decoded = NAMESPACES.sub("", decode_escapes(text))
        for second, (body, note) in enumerate(((plain, ""), (decoded, " (after undoing escapes)"))):
            if second and decoded == plain:
                continue
            for rx, what in ANY_FILE_RULES:
                for m in rx.finditer(body):
                    if what.startswith("a data:") and DATA_OK.match(body[m.start():m.start() + 80].replace(" ", "")):
                        continue
                    self.problem(path, line_of(body, m.start()), f"refused: {what}{note}")
            for m in URL_FN.finditer(body):
                if second:
                    self.check_ref(path, line_of(body, m.start()), m.group(2))
        for m in IMAGE_SET.finditer(decoded):
            self.problem(path, line_of(decoded, m.start()), "refused: image-set(, which can name many addresses")
        for m in ESCAPE_IN_URL.finditer(text):
            self.problem(path, line_of(text, m.start()), "refused: a CSS escape inside url(), @import or src")
        if suffix in MARKUP_EXT:
            for rx, what in MARKUP_RULES:
                for m in rx.finditer(text):
                    self.problem(path, line_of(text, m.start()), f"refused: {what}")
            parser = Refs()
            parser.feed(text)
            for line, value in parser.refs:
                self.check_ref(path, line, value)
        if suffix in SCRIPT_EXT:
            for rx, what in SCRIPT_RULES:
                for m in rx.finditer(text):
                    self.problem(path, line_of(text, m.start()), f"refused: {what}")
        for m in URL_FN.finditer(text):
            self.check_ref(path, line_of(text, m.start()), m.group(2))
        for m in IMPORT.finditer(text):
            self.check_ref(path, line_of(text, m.start()), m.group(1), allow_fragment=False)
        if suffix in {".html", ".htm", ".css", ".svg"}:
            for m in FONT_FACE.finditer(text):
                self.fonts_declared.update(f.lower() for f in split_families(m.group(1)))
            for name, value in CUSTOM_PROP.findall(text):
                self.custom.setdefault(name, []).extend(split_families(value))
            for rx in (FONT_FAMILY, FONT_SHORT):
                for m in rx.finditer(text):
                    for fam in split_families(m.group(1)):
                        self.fonts_used.setdefault(fam, (path, line_of(text, m.start())))

    def check_fonts(self):
        """The renderer asks a font service for every named family that the page does not declare."""
        names = {}
        for fam, where in self.fonts_used.items():
            low = fam.lower()
            if low.startswith("var("):
                var = re.match(r"var\(\s*(--[\w-]+)", low)
                values = self.custom.get(var.group(1)) if var else None
                if not values:
                    self.problem(where[0], where[1], f"font-family uses {fam}, which cannot be resolved")
                    continue
                for v in values:
                    names[v.lower()] = where
            else:
                names[low] = where
        for low, where in sorted(names.items()):
            if low in GENERIC_FONTS or low.startswith("var(") or low in self.fonts_declared:
                continue
            self.problem(where[0], where[1],
                         f"font family '{low}' has no @font-face in the composition; the renderer would "
                         "ask a font service on the network. Declare it with src: local('...') or a local file")

    def run(self):
        for root, dirs, files in os.walk(self.comp):
            for name in dirs + files:
                p = Path(root) / name
                if p.is_symlink():
                    self.problem(p, 1, "symbolic link inside the composition folder")
            for name in files:
                p = Path(root) / name
                if p.suffix.lower() in TEXT_EXT and not p.is_symlink():
                    self.add_file(p)
        if not (self.comp / "index.html").is_file():
            self.problem(self.comp / "index.html", 1, "composition has no index.html")
        while self.queue:
            self.scan_file(self.queue.pop())
        self.check_fonts()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--comp", required=True, help="composition folder, inside the work folder")
    ap.add_argument("--work", help="work folder (default: current folder)")
    ap.add_argument("--pins", help="test use only: another pins file")
    args = ap.parse_args()
    work = work_folder(args.work)
    comp = inside_work(args.comp, work, "--comp")
    if not comp.is_dir():
        raise Stop(2, f"composition folder not found: {args.comp}")
    gsap_sha = load_pins(args.pins).get("gsap", {}).get("file_sha256")
    chk = Checker(comp, work, gsap_sha)
    chk.run()
    if chk.problems:
        for item in chk.problems:
            print(item, file=sys.stderr)
        print(f"LOCAL_ONLY: FAIL ({len(chk.problems)} problems)")
        return FAIL
    print(f"LOCAL_ONLY: PASS ({chk.scanned} files scanned)")
    return OK


if __name__ == "__main__":
    run_main(main)
