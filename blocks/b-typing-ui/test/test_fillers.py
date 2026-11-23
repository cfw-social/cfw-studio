#!/usr/bin/env python3
"""Tests for b-typing-ui. Standard library only. No account, no private file, no network.

  python3 -m unittest discover -s blocks/b-typing-ui/test -v

The JS checks use node (22 or newer). If node is missing, those tests are reported as skipped.
"""
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.abspath(__file__))
BLOCK = os.path.dirname(HERE)
SCRIPTS = os.path.join(BLOCK, "scripts")
TYPING = os.path.join(SCRIPTS, "typing_fill.py")
HOOK = os.path.join(SCRIPTS, "hook_fill.py")
NODE = shutil.which("node")
sys.path.insert(0, SCRIPTS)
import fill_common as fc  # noqa: E402
import hook_fill  # noqa: E402
import typing_fill  # noqa: E402

# Hostile markup with no address in it: escaped, and the page still passes the render check.
HOSTILE = [
    "</script><script>alert(1)</script>",
    "<img src=x onerror=alert(1)>",
    '" onmouseover="alert(1)" x="',
    "' onfocus='alert(1)",
    "<svg/onload=alert(1)>",
    "{{ACCENT}} {{PROMPT}} {{DURATION}}",
    "back\\slash \\u0041 \\n \\\"",
    "line\r\nbreak\rcr   sep   para",
    "`${alert(1)}` ${x}",
    "</template><script>x</script>",
    "-->\n<!-- <script>",
]


# Addresses are refused up front: the render check refuses any page that holds one, even as plain text.
ADDRESSES = [
    '<a href="https://evil.example/x">go</a>', "javascript:alert(1)", "<style>@import 'https://e.x'</style>",
    "<style>*{background:url(//e)}</style>", "see https://example.com now", "HTTP://EXAMPLE.COM", "http://x", "ws://x", "wss://x",
    "ftp://x", "gopher://x", "git+ssh://host/x", "//example.com/x", "x //example.com", "vbscript:x", "JavaScript :x",
    "data:text/html,x", "Data: image/png", "url(x.png)", "URL (x)", "@import 'x'", "@ import x", "image-set(a 1x)",
    "http:", "https :", "\\68ttp://x", "\\6a avascript:x",
]

# Awkward but harmless: accepted by the fillers, and the filled page passes the real check.
HARMLESS = [
    'He said "hi" & left', "<b>bold</b> & 5 < 6 > 4", "emoji \U0001F600 and \u00e9", "a/b", "1:2", "50% off (today)",
    "me@example.com", "example.com/path", "C:\\folder", "it's {braces} and \\ backslash", "Time: 10:30", "Note: read this",
    "WebSocket and innerHTML and XMLHttpRequest are just words", "font-family: serif", "window.open and document.write", "location = home",
    "self [0] and top [1]", "x.src = y", "5 == 5", "import numpy", "fetch (it)", "-->", "<!-- not a comment -->",
]


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def template(name):
    return read(os.path.join(BLOCK, "templates", name))


class Inventory(HTMLParser):
    """Records every tag with its attribute names, and every inline script body."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags, self.scripts, self.attr_values, self._in_script = [], [], [], False

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, tuple(sorted(n for n, _ in attrs))))
        self.attr_values.extend((n, v) for n, v in attrs)
        if tag == "script":
            self._in_script = True
            self.scripts.append("")

    def handle_endtag(self, tag):
        if tag == "script":
            self._in_script = False

    def handle_data(self, data):
        if self._in_script:
            self.scripts[-1] += data


def inventory(page):
    p = Inventory()
    p.feed(page)
    p.close()
    return p


def prompt_literal(page):
    m = re.search(r'var PROMPT_TEXT\s*=\s*"((?:[^"\\]|\\.)*)";', page)
    assert m, "no PROMPT_TEXT literal in the page"
    return m.group(1)


class Work:
    """A temporary work folder to run the scripts in."""

    def __init__(self, test):
        self.dir = os.path.realpath(tempfile.mkdtemp(prefix="typing-ui-"))
        self.other = os.path.realpath(tempfile.mkdtemp(prefix="typing-ui-other-"))
        test.addCleanup(shutil.rmtree, self.dir, True)
        test.addCleanup(shutil.rmtree, self.other, True)

    def json(self, name, obj):
        with open(os.path.join(self.dir, name), "w", encoding="utf-8") as fh:
            json.dump(obj, fh)
        return name

    def run(self, script, *args):
        r = subprocess.run([sys.executable, "-I", script, *args], cwd=self.dir, capture_output=True, text=True)
        return r

    def path(self, name):
        return os.path.join(self.dir, name)


def parse_check(test, code):
    d = tempfile.mkdtemp()
    try:
        p = os.path.join(d, "s.js")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(code)
        r = subprocess.run([NODE, "--check", p], capture_output=True, text=True)
        test.assertEqual(r.returncode, 0, r.stderr)
    finally:
        shutil.rmtree(d)


class TypingEscaping(unittest.TestCase):
    def fill(self, text, **kw):
        kw.setdefault("duration", 6.0)
        kw.setdefault("accent", "F97316")
        return typing_fill.fill(template("typing-scene.html"), text=text, **kw)

    def test_hostile_text_adds_no_element_attribute_or_script_code(self):
        benign = inventory(self.fill({"prompt": "hello", "label": "chat", "card_label": "Card", "bottom_tag": "tag"}))
        for bad in HOSTILE:
            with self.subTest(bad=bad):
                page = self.fill({"prompt": bad, "label": bad, "card_label": bad, "bottom_tag": bad})
                inv = inventory(page)
                self.assertEqual(inv.tags, benign.tags)
                self.assertEqual([v for n, v in inv.attr_values if n.startswith("on")], [])
                if set(bad) & set("<>\"'&{}"):
                    self.assertFalse(bad in page.replace(prompt_literal(page), ""), "raw text must not appear outside the escaped literal")
                self.assertEqual(len(inv.scripts), len(benign.scripts))
                # Script bodies are identical except for the one prompt literal.
                swap = lambda s, lit: s.replace(lit, "X")
                for a, b in zip(inv.scripts, benign.scripts):
                    self.assertEqual(swap(a, prompt_literal(page)), swap(b, prompt_literal(self.fill({"prompt": "hello"}))))

    @unittest.skipUnless(NODE, "node is needed for the JS checks")
    def test_prompt_types_exactly_and_scripts_parse(self):
        for bad in HOSTILE + ["plain", "multi\nline\n\nbreaks", "\"quoted\" 'single' and ünïcode ✓"]:
            with self.subTest(bad=bad):
                page = self.fill({"prompt": bad})
                lit = prompt_literal(page)
                r = subprocess.run([NODE, "-e", 'process.stdout.write(JSON.stringify("%s"))' % lit], capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stderr)
                want = re.sub(r"\r\n|\r| | |\x85", "\n", bad)
                self.assertEqual(json.loads(r.stdout), want)
                for code in inventory(page).scripts:
                    parse_check(self, code)

    def test_text_fields_are_one_line_and_escaped(self):
        page = self.fill({"prompt": "p", "label": "a\nb\r\nc", "bottom_tag": 'x"y'})
        self.assertIn(">a b c<", page)
        self.assertIn("x&quot;y", page)

    def test_no_double_fill(self):
        page = self.fill({"prompt": "p", "label": "{{ACCENT}}"}, accent="123ABC")
        self.assertIn("&#123;&#123;ACCENT&#125;&#125;", page)
        self.assertNotIn("123ABC}}", page)

    def test_defaults_are_neutral(self):
        page = self.fill({"prompt": "p"})
        self.assertIn(">AI chat<", page)
        self.assertIn(">The prompt<", page)
        self.assertIn("display:none", page)  # no bottom tag by default
        for name in ("typing-scene.html", "hook-scene.html"):
            text = template(name).lower()
            for brand in ("claude", "anthropic", "openai", "chatgpt", "gemini", "copilot"):
                self.assertNotIn(brand, text, "%s names %s" % (name, brand))

    def test_template_shape_the_recipes_rely_on(self):
        t = template("typing-scene.html")
        self.assertEqual(t.count('<template id="typing-scene-template">'), 1)
        self.assertIn('var PROMPT_TEXT  = "{{PROMPT}}";', t)
        self.assertIn("{{CARD_LABEL}}", t)

    def test_problems_are_refused(self):
        bad_cases = [
            dict(text={"prompt": ""}),
            dict(text={"prompt": "   "}),
            dict(text={"prompt": "x" * 4001}),
            dict(text={"prompt": "x", "label": "y" * 61}),
            dict(text={"prompt": "x", "bogus": "1"}),
            dict(text={"prompt": "bell\x07"}),
            dict(text={"prompt": "nul\x00"}),
            dict(text={"prompt": "x"}, variant="wide"),
            dict(text={"prompt": "x"}, wrap="page"),
            dict(text={"prompt": "x"}, duration=0),
            dict(text={"prompt": "x"}, duration=float("nan")),
            dict(text={"prompt": "x"}, duration=1e9),
            dict(text={"prompt": "x"}, speed=0),
            dict(text={"prompt": "x"}, slot="Bad Slot"),
            dict(text={"prompt": "x"}, slot='a"><script>'),
        ]
        for case in bad_cases:
            with self.subTest(case=case):
                with self.assertRaises(fc.FillError):
                    self.fill(**case)

    def test_slot_renames_every_scene_id_and_prefix(self):
        page = self.fill({"prompt": "p"}, slot="tk3", variant="pip-safe")
        self.assertNotIn("typing-scene", page)
        self.assertIsNone(re.search(r'(?<=[.#"])ts-', page))
        self.assertIn('data-composition-id="tk3"', page)
        self.assertIn('"tk3-ts-pip-safe"', page)
        self.assertIn('window.__timelines["tk3"]', page)

    def test_wrap_template_keeps_the_wrapper_and_standalone_drops_it(self):
        self.assertTrue(self.fill({"prompt": "p"}, wrap="template").startswith('<template id="typing-scene-template">'))
        page = self.fill({"prompt": "p"})
        self.assertTrue(page.startswith("<!DOCTYPE html>"))
        self.assertNotIn("<template", page)


class HookEscaping(unittest.TestCase):
    def fill(self, text, **kw):
        kw.setdefault("duration", 3.0)
        kw.setdefault("accent", "F97316")
        return hook_fill.fill(template("hook-scene.html"), text=text, **kw)

    def test_hostile_text_adds_no_element_attribute_or_script_code(self):
        keys = ("eyebrow", "line1", "line2", "line3", "subhead")
        benign_page = self.fill({k: "ok" for k in keys})
        benign = inventory(benign_page)
        for bad in HOSTILE:
            with self.subTest(bad=bad):
                page = self.fill({k: bad for k in keys})
                inv = inventory(page)
                self.assertEqual(inv.tags, benign.tags)
                self.assertEqual([v for n, v in inv.attr_values if n.startswith("on")], [])
                self.assertEqual(inv.scripts, benign.scripts, "no text may reach a script")
                if set(bad) & set("<>\"'&{}"):
                    self.assertFalse(bad in page, "raw text must not appear in the page")

    @unittest.skipUnless(NODE, "node is needed for the JS checks")
    def test_scripts_parse(self):
        for code in inventory(self.fill({"line1": 'A "B" \\ </script>'})).scripts:
            parse_check(self, code)

    def test_optional_lines_may_be_empty_but_line1_may_not(self):
        page = self.fill({"line1": "ONE"})
        self.assertIn('id="hs-line2"></span>', page)
        for text in ({}, {"line1": ""}, {"line1": "  "}, {"line1": "x", "line9": "y"}, {"line1": "x" * 41}, {"line1": "x", "subhead": "y" * 121}):
            with self.subTest(text=text):
                with self.assertRaises(fc.FillError):
                    self.fill(text)

    def test_slot_and_wrap(self):
        page = self.fill({"line1": "A"}, slot="hk1", wrap="template")
        self.assertTrue(page.startswith("<template id=\"hk1-template\">"))
        self.assertNotIn("hook-scene", page)
        self.assertIsNone(re.search(r'(?<=[.#"])hs-', page))


class Colours(unittest.TestCase):
    def test_hex_accepts_six_digits_only(self):
        self.assertEqual(fc.hex6("f97316", "c"), "F97316")
        self.assertEqual(fc.hex6("#0f172a", "c"), "0F172A")
        for bad in ("", "red", "12345", "1234567", "#12345678", "GGGGGG", "f97316;}</style>", " F97316", "F97316\n", "#", None, 123456):
            with self.subTest(bad=bad):
                with self.assertRaises(fc.FillError):
                    fc.hex6(bad, "c")

    def test_bad_accent_or_bg_in_both_fillers(self):
        for bad in ("red", "12345", "#GGGGGG", "F97316;}</style><script>"):
            with self.subTest(bad=bad):
                with self.assertRaises(fc.FillError):
                    typing_fill.fill(template("typing-scene.html"), 5, {"prompt": "x"}, bad)
                with self.assertRaises(fc.FillError):
                    typing_fill.fill(template("typing-scene.html"), 5, {"prompt": "x"}, "F97316", bg=bad)
                with self.assertRaises(fc.FillError):
                    hook_fill.fill(template("hook-scene.html"), 3, {"line1": "x"}, bad)


class CommandLine(unittest.TestCase):
    def setUp(self):
        self.w = Work(self)

    def test_writes_inside_the_work_folder(self):
        t = self.w.json("t.json", {"prompt": "hello"})
        r = self.w.run(TYPING, "--out", "x.html", "--duration", "5", "--text-file", t, "--accent", "F97316")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.isfile(self.w.path("x.html")))
        h = self.w.json("h.json", {"line1": "HOOK"})
        r = self.w.run(HOOK, "--out", "h.html", "--duration", "3", "--text-file", h, "--accent", "#F97316")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.isfile(self.w.path("h.html")))

    def test_bad_colour_writes_nothing(self):
        t = self.w.json("t.json", {"prompt": "hello"})
        for script, text in ((TYPING, t), (HOOK, self.w.json("h.json", {"line1": "x"}))):
            r = self.w.run(script, "--out", "x.html", "--duration", "5", "--text-file", text, "--accent", "orange")
            self.assertEqual(r.returncode, 2, r.stderr)
            self.assertIn("hex", r.stderr)
        self.assertFalse(os.path.exists(self.w.path("x.html")))

    def test_output_outside_the_work_folder_is_refused(self):
        t = self.w.json("t.json", {"prompt": "hello"})
        os.symlink(self.w.other, self.w.path("outlink"))
        os.symlink(os.path.join(self.w.other, "target.html"), self.w.path("dangling.html"))
        outs = [os.path.join(self.w.other, "x.html"), "../escape.html", "outlink/x.html", "dangling.html", "missing-folder/x.html"]
        for out in outs:
            with self.subTest(out=out):
                r = self.w.run(TYPING, "--out", out, "--duration", "5", "--text-file", t, "--accent", "F97316")
                self.assertEqual(r.returncode, 2, r.stderr)
        self.assertEqual(os.listdir(self.w.other), [])
        self.assertFalse(os.path.exists(os.path.join(os.path.dirname(self.w.dir), "escape.html")))

    def test_planted_links_and_same_file_outputs_are_refused(self):
        t = self.w.json("t.json", {"prompt": "hello"})
        victim = os.path.join(self.w.other, "victim.html")
        with open(victim, "w") as fh:
            fh.write("keep me")
        os.symlink(victim, self.w.path("planted.html"))                 # link to a file outside
        os.symlink(self.w.path("t.json"), self.w.path("inside-link.html"))  # link that stays inside
        os.symlink(self.w.other, self.w.path("dirlink"))                # parent folder pointing outside
        for script, text in ((TYPING, t), (HOOK, self.w.json("h.json", {"line1": "x"}))):
            own = os.path.basename(script) == "hook_fill.py" and "h.json" or "t.json"
            for out in ("planted.html", "inside-link.html", "dirlink/victim.html", own, "./" + own):
                with self.subTest(script=os.path.basename(script), out=out):
                    r = self.w.run(script, "--out", out, "--duration", "5", "--text-file", text, "--accent", "F97316")
                    self.assertEqual(r.returncode, 2, r.stderr)
                    self.assertNotIn("Traceback", r.stderr)
        self.assertEqual(read(victim), "keep me")
        self.assertEqual(json.loads(read(self.w.path("t.json"))), {"prompt": "hello"})
        self.assertEqual(json.loads(read(self.w.path("h.json"))), {"line1": "x"})
        self.assertEqual(sorted(os.listdir(self.w.other)), ["victim.html"])
        self.assertEqual([n for n in os.listdir(self.w.dir) if n.startswith(".fill-")], [])

    def test_no_temporary_file_is_left_and_output_is_replaced_whole(self):
        t = self.w.json("t.json", {"prompt": "hello"})
        for _ in range(2):
            r = self.w.run(TYPING, "--out", "x.html", "--duration", "5", "--text-file", t, "--accent", "F97316")
            self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(sorted(os.listdir(self.w.dir)), ["t.json", "x.html"])

    def test_unexpected_error_prints_one_fixed_line_and_no_stack_trace(self):
        def boom():
            raise RuntimeError("secret detail /private/path")
        import io
        err = io.StringIO()
        old, sys.stderr = sys.stderr, err
        try:
            code = fc.run_main(boom)
        finally:
            sys.stderr = old
        self.assertEqual(code, 1)
        self.assertEqual(len(err.getvalue().strip().splitlines()), 1)
        self.assertNotIn("secret", err.getvalue())
        self.assertNotIn("Traceback", err.getvalue())

    def test_text_file_outside_the_work_folder_is_refused(self):
        with open(os.path.join(self.w.other, "t.json"), "w") as fh:
            json.dump({"prompt": "x"}, fh)
        os.symlink(os.path.join(self.w.other, "t.json"), self.w.path("link.json"))
        for path in (os.path.join(self.w.other, "t.json"), "link.json", "missing.json"):
            r = self.w.run(TYPING, "--out", "x.html", "--duration", "5", "--text-file", path, "--accent", "F97316")
            self.assertEqual(r.returncode, 2, path)
        self.assertFalse(os.path.exists(self.w.path("x.html")))

    def test_bad_text_files_and_options(self):
        for name, body in (("a.json", "{not json"), ("b.json", "[]"), ("c.json", '{"prompt": 5}'), ("d.json", '{"prompt": "x", "extra": "y"}')):
            with open(self.w.path(name), "w") as fh:
                fh.write(body)
            r = self.w.run(TYPING, "--out", "x.html", "--duration", "5", "--text-file", name, "--accent", "F97316")
            self.assertEqual(r.returncode, 2, name)
        t = self.w.json("t.json", {"prompt": "x"})
        base = ["--out", "x.html", "--duration", "5", "--text-file", t, "--accent", "F97316"]
        self.assertEqual(self.w.run(TYPING, *base, "--template", "evil.html").returncode, 2)
        self.assertEqual(self.w.run(TYPING, "--out", "x.html").returncode, 2)
        self.assertEqual(self.w.run(TYPING, *base, "--variant", "huge").returncode, 2)
        self.assertEqual(self.w.run(TYPING, *base, "--duration", "abc").returncode, 2)
        self.assertFalse(os.path.exists(self.w.path("x.html")))

    def test_damaged_block_exits_3(self):
        copy = os.path.join(self.w.other, "block")
        shutil.copytree(os.path.join(BLOCK, "scripts"), os.path.join(copy, "scripts"))   # no templates folder
        t = self.w.json("t.json", {"prompt": "x"})
        r = self.w.run(os.path.join(copy, "scripts", "typing_fill.py"), "--out", "x.html", "--duration", "5", "--text-file", t, "--accent", "F97316")
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertFalse(os.path.exists(self.w.path("x.html")))


CHECK_LOCAL = os.path.join(os.path.dirname(BLOCK), "b-hyperframes", "scripts", "check_local.py")
STAND_IN_GSAP = b"/* stand-in for the pinned animation library; the real file is not in this repository */\n"


class PassesTheLocalOnlyCheck(unittest.TestCase):
    """Every filled page, in every variant and wrap mode, must pass b-hyperframes/scripts/check_local.py.

    The check skips the animation library only when its SHA-256 equals the pin, so these tests
    use the check's own test option (--pins) with a stand-in file. Nothing is fetched.
    """

    def check(self, page):
        self.assertTrue(os.path.isfile(CHECK_LOCAL), "b-hyperframes is not beside this block: " + CHECK_LOCAL)
        work = os.path.realpath(tempfile.mkdtemp(prefix="typing-ui-check-"))
        self.addCleanup(shutil.rmtree, work, True)
        comp = os.path.join(work, "comp")
        os.mkdir(comp)
        with open(os.path.join(comp, "index.html"), "w", encoding="utf-8") as fh:
            fh.write(page)
        with open(os.path.join(comp, "gsap.min.js"), "wb") as fh:
            fh.write(STAND_IN_GSAP)
        import hashlib
        with open(os.path.join(work, "pins.json"), "w") as fh:
            json.dump({"gsap": {"file_sha256": hashlib.sha256(STAND_IN_GSAP).hexdigest()}}, fh)
        r = subprocess.run([sys.executable, "-I", CHECK_LOCAL, "--comp", "comp", "--pins", "pins.json"],
                           cwd=work, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertIn("LOCAL_ONLY: PASS", r.stdout)

    def test_typing_card_every_variant_and_wrap(self):
        texts = [{"prompt": "Write a short email.\nKeep it friendly."}, {"prompt": "x", "label": "Chat", "card_label": "Try this", "bottom_tag": "save it"},
                 {"prompt": HOSTILE[0], "label": HOSTILE[1][:60], "card_label": HOSTILE[2], "bottom_tag": HOSTILE[3]}]
        texts += [{"prompt": bad} for bad in HOSTILE]
        for text in texts:
            for variant in ("full", "pip-safe"):
                for wrap in ("standalone", "template"):
                    for slot in (None, "tk1"):
                        with self.subTest(text=text["prompt"][:20], variant=variant, wrap=wrap, slot=slot):
                            page = typing_fill.fill(template("typing-scene.html"), 6, text, "F97316", variant=variant, wrap=wrap, slot=slot)
                            if wrap == "template":
                                # A sub-composition is checked inside a page that carries it.
                                page = "<!DOCTYPE html><html><body>" + page + "</body></html>"
                            self.check(page)

    def test_hook_card_every_wrap(self):
        texts = [{"line1": "ONE"}, {"eyebrow": "Day 3", "line1": "PROMPT 3.", "line2": "COLD EMAIL", "line3": "OPENER.", "subhead": "Try it today"}]
        texts += [{"eyebrow": bad[:80], "line1": bad[:40], "line2": bad[:40], "line3": bad[:40], "subhead": bad} for bad in HOSTILE]
        for text in texts:
            for wrap in ("standalone", "template"):
                for slot in (None, "hk1"):
                    with self.subTest(line1=text["line1"][:20], wrap=wrap, slot=slot):
                        page = hook_fill.fill(template("hook-scene.html"), 3, text, "F97316", wrap=wrap, slot=slot)
                        if wrap == "template":
                            page = "<!DOCTYPE html><html><body>" + page + "</body></html>"
                        self.check(page)

    def test_every_named_font_has_a_local_font_face(self):
        for name, fams in (("typing-scene.html", ("Inter", "JetBrains Mono")), ("hook-scene.html", ("Oswald", "JetBrains Mono", "Inter"))):
            for fam in fams:
                self.assertIn('@font-face { font-family: "%s"; src: local("%s"); }' % (fam, fam), template(name))


class ReviewFixes(unittest.TestCase):
    def typing(self, **text):
        return typing_fill.fill(template("typing-scene.html"), 5, text, "F97316")

    def test_broken_and_control_characters_are_bad_input_naming_the_key(self):
        bad = {"lone high surrogate": "a\ud800b", "lone low surrogate": "a\udc00", "null byte": "a\x00b", "bell": "a\x07",
               "escape": "a\x1b[0m", "delete": "a\x7f", "c1 control": "a\x9bb"}
        for name, value in bad.items():
            for key in ("prompt", "label", "card_label", "bottom_tag"):
                with self.subTest(case=name, key=key):
                    text = {"prompt": "ok"}
                    text[key] = value
                    with self.assertRaises(fc.FillError) as cm:
                        self.typing(**text)
                    self.assertIn(key, str(cm.exception))
            with self.subTest(case=name, key="hook"):
                with self.assertRaises(fc.FillError) as cm:
                    hook_fill.fill(template("hook-scene.html"), 3, {"line1": "x", "subhead": value}, "F97316")
                self.assertIn("subhead", str(cm.exception))

    def test_cli_exit_2_not_the_generic_error_for_a_lone_surrogate(self):
        w = Work(self)
        with open(w.path("t.json"), "w") as fh:
            fh.write('{"prompt": "bad \\ud800 text"}')
        r = w.run(TYPING, "--out", "x.html", "--duration", "5", "--text-file", "t.json", "--accent", "F97316")
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("prompt", r.stderr)
        self.assertNotIn("unexpected", r.stderr)
        self.assertFalse(os.path.exists(w.path("x.html")))

    def test_tab_and_line_breaks_are_allowed_only_where_stated(self):
        page = self.typing(prompt="a\tb\nc\r\nd", label="x\ty\nz")
        self.assertIn(">x y z<", page)           # one-line keys turn them into one space
        self.assertIn("\\u0009", prompt_literal(page))   # the prompt keeps the tab
        self.assertIn("\\u000a", prompt_literal(page))

    def test_direction_override_characters_are_refused(self):
        for cp in [0x200E, 0x200F] + list(range(0x202A, 0x202F)) + list(range(0x2066, 0x206A)):
            ch = chr(cp)
            for key in ("prompt", "label", "card_label", "bottom_tag"):
                with self.subTest(cp=hex(cp), key=key):
                    text = {"prompt": "ok"}
                    text[key] = "abc%sdef" % ch
                    with self.assertRaises(fc.FillError) as cm:
                        self.typing(**text)
                    self.assertIn(key, str(cm.exception))
                    self.assertIn("direction", str(cm.exception))
            with self.subTest(cp=hex(cp), key="hook"):
                with self.assertRaises(fc.FillError):
                    hook_fill.fill(template("hook-scene.html"), 3, {"line1": "a%sb" % ch}, "F97316")
        self.typing(prompt="Arabic \u0627\u0644\u0639\u0631\u0628\u064a\u0629 and emoji \U0001F600 are fine")

    def test_slot_rename_never_touches_the_persons_text(self):
        tricky = '.ts-card #ts-bubble "ts-label" typing-scene .hs-glow'
        page = typing_fill.fill(template("typing-scene.html"), 5,
                                {"prompt": tricky, "label": tricky, "card_label": tricky, "bottom_tag": tricky}, "F97316", slot="tk9")
        self.assertEqual(page.count(".ts-card #ts-bubble &quot;ts-label&quot; typing-scene .hs-glow"), 3)   # label, card_label, bottom_tag
        # Everything outside the text positions is identical to a fill with harmless text.
        harmless = typing_fill.fill(template("typing-scene.html"), 5, {"prompt": "p", "label": "L", "card_label": "C", "bottom_tag": "T"}, "F97316", slot="tk9")
        swapped = page.replace(".ts-card #ts-bubble &quot;ts-label&quot; typing-scene .hs-glow", "X")
        base = harmless.replace(">L<", ">X<").replace(">C<", ">X<").replace(">T<", ">X<")
        self.assertEqual(re.sub(r'var PROMPT_TEXT  = "[^"]*";', "", swapped), re.sub(r'var PROMPT_TEXT  = "[^"]*";', "", base))
        hook = hook_fill.fill(template("hook-scene.html"), 3, {"line1": ".hs-glow #hs-line1 hook-scene", "line2": ".ts-card"}, "F97316", slot="hk2")
        self.assertIn(".hs-glow #hs-line1 hook-scene", hook)
        self.assertIn(">.ts-card<", hook)
        self.assertEqual(hook.count("hk2-hs-glow"), hook.replace(".hs-glow #hs-line1 hook-scene", "").count("hk2-hs-glow"))


class TextLimits(unittest.TestCase):
    """The fillers and the render check must agree: refused text writes nothing, accepted text passes the check."""

    check = PassesTheLocalOnlyCheck.check

    def test_refused_texts_name_the_key_and_say_what_to_write(self):
        for bad in ADDRESSES:
            for key in ("prompt", "label", "card_label", "bottom_tag"):
                with self.subTest(text=bad, key=key):
                    text = {"prompt": "ok"}
                    text[key] = bad
                    with self.assertRaises(fc.FillError) as cm:
                        typing_fill.fill(template("typing-scene.html"), 5, text, "F97316")
                    self.assertIn(key, str(cm.exception))
                    self.assertIn("Fix:", str(cm.exception))
            for key in ("eyebrow", "line1", "line2", "line3", "subhead"):
                with self.subTest(text=bad, key=key):
                    text = {"line1": "ok"}
                    text[key] = bad
                    with self.assertRaises(fc.FillError) as cm:
                        hook_fill.fill(template("hook-scene.html"), 3, text, "F97316")
                    self.assertIn(key, str(cm.exception))
        with self.assertRaises(fc.FillError) as cm:
            typing_fill.fill(template("typing-scene.html"), 5, {"prompt": "go to https://example.com"}, "F97316")
        self.assertIn("write example.com, not https://example.com", str(cm.exception))

    def test_refused_texts_exit_2_and_write_nothing(self):
        for bad in ADDRESSES[:12]:
            w = Work(self)
            t = w.json("t.json", {"prompt": bad})
            h = w.json("h.json", {"line1": "ok", "subhead": bad})
            for script, text in ((TYPING, t), (HOOK, h)):
                r = w.run(script, "--out", "x.html", "--duration", "5", "--text-file", text, "--accent", "F97316")
                self.assertEqual(r.returncode, 2, "%s: %s" % (bad, r.stderr))
                self.assertNotIn("unexpected", r.stderr)
            self.assertEqual(sorted(os.listdir(w.dir)), ["h.json", "t.json"])

    def test_harmless_texts_are_accepted_and_pass_the_real_check(self):
        for text in HARMLESS:
            for wrap in ("standalone", "template"):
                with self.subTest(text=text, wrap=wrap, card="typing"):
                    page = typing_fill.fill(template("typing-scene.html"), 6,
                                            {"prompt": text + "\nsecond line", "label": text[:60], "card_label": text[:60], "bottom_tag": text[:80]},
                                            "F97316", wrap=wrap)
                    self.check(page if wrap == "standalone" else "<!DOCTYPE html><html><body>" + page + "</body></html>")
                with self.subTest(text=text, wrap=wrap, card="hook"):
                    page = hook_fill.fill(template("hook-scene.html"), 3,
                                          {"eyebrow": text[:80], "line1": text[:40], "line2": text[:40], "line3": text[:40], "subhead": text[:120]},
                                          "F97316", wrap=wrap)
                    self.check(page if wrap == "standalone" else "<!DOCTYPE html><html><body>" + page + "</body></html>")

    def test_script_words_keep_their_text(self):
        page = typing_fill.fill(template("typing-scene.html"), 5, {"prompt": "use WebSocket", "label": "innerHTML"}, "F97316")
        self.assertIn(">&#105;nnerHTML<", page)          # shown as innerHTML, but the word is not in the file
        self.assertNotIn("WebSocket", page)
        lit = prompt_literal(page)
        self.assertNotIn("WebSocket", lit)
        if NODE:
            r = subprocess.run([NODE, "-e", 'process.stdout.write("%s")' % lit], capture_output=True, text=True)
            self.assertEqual(r.stdout, "use WebSocket")


class SizeAndColours(unittest.TestCase):
    check = PassesTheLocalOnlyCheck.check

    def typing(self, **kw):
        kw.setdefault("accent", "F97316")
        return typing_fill.fill(template("typing-scene.html"), 6, {"prompt": "Write a short email."}, **kw)

    def hook(self, **kw):
        kw.setdefault("accent", "F97316")
        return hook_fill.fill(template("hook-scene.html"), 3, {"line1": "ONE", "subhead": "two"}, **kw)

    def test_default_prompt_size_is_readable_and_per_variant(self):
        self.assertIn("font-size: 44px;\n      color: var(--text-white);", self.typing())
        self.assertIn("font-size: 38px;\n      color: var(--text-white);", self.typing(variant="pip-safe"))
        self.assertIn("max-height: 1300px", self.typing())
        self.assertIn("max-height: 640px", self.typing(variant="pip-safe"))
        self.assertIn("overflow: hidden", self.typing())

    def test_prompt_size_is_bounded(self):
        for bad in (23.9, 73, 0, -5, 1e9, float("nan"), "big"):
            with self.subTest(bad=bad):
                with self.assertRaises(fc.FillError):
                    self.typing(prompt_size=bad)
        for good in (24, 52, 72, "60"):
            for variant in ("full", "pip-safe"):
                with self.subTest(good=good, variant=variant):
                    page = self.typing(prompt_size=good, variant=variant)
                    self.assertIn("font-size: %gpx;\n      color: var(--text-white);" % float(good), page)

    def test_size_option_on_the_command_line(self):
        w = Work(self)
        t = w.json("t.json", {"prompt": "hello"})
        base = ["--out", "x.html", "--duration", "5", "--text-file", t, "--accent", "F97316"]
        self.assertEqual(w.run(TYPING, *base, "--prompt-size", "60").returncode, 0)
        self.assertIn("font-size: 60px", read(w.path("x.html")))
        for bad in ("10", "100", "abc", "1e2"):
            r = w.run(TYPING, *base, "--prompt-size", bad)
            self.assertEqual(r.returncode, 2, bad)
        r = w.run(TYPING, *base, "--prompt-size", "72", "--out", "y.html")
        self.assertEqual(r.returncode, 0)

    def test_a_very_long_prompt_is_reported_as_cut_off(self):
        w = Work(self)
        t = w.json("t.json", {"prompt": "word " * 700})
        r = w.run(TYPING, "--out", "x.html", "--duration", "140", "--text-file", t, "--accent", "F97316")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("will be cut off", r.stderr)
        t = w.json("short.json", {"prompt": "short prompt"})
        self.assertNotIn("cut off", w.run(TYPING, "--out", "y.html", "--duration", "5", "--text-file", t, "--accent", "F97316").stderr)

    def test_the_timing_rule_matches_the_templates_own_script(self):
        text = read(os.path.join(os.path.dirname(SCRIPTS), "templates", "typing-scene.html"))
        for needle in ("var TYPING_HOLD = 0.6;", "Math.min(0.5, latest / 2)", "duration * 0.88 / speed", "start + 0.5", "Math.min(end, latest)"):
            self.assertIn(needle, text)
        self.assertEqual((typing_fill.TYPING_START, typing_fill.TYPING_HOLD, typing_fill.WINDOW_FRACTION, typing_fill.MIN_WINDOW), (0.5, 0.6, 0.88, 0.5))
        self.assertAlmostEqual(typing_fill.typing_window(9.0, 1.0)[1], 9.0 * 0.88)
        self.assertEqual(typing_fill.typing_window(5.0, 4.0), (0.5, 1.1))

    def test_a_prompt_that_cannot_finish_typing_is_refused_with_the_fix(self):
        w = Work(self)
        t = w.json("t.json", {"prompt": "x" * 300})        # 300 characters need 10 s of typing at 30 a second
        r = w.run(TYPING, "--out", "x.html", "--duration", "6", "--text-file", t, "--accent", "F97316")
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("cannot finish typing", r.stderr)
        self.assertIn("shorter prompt", r.stderr)
        self.assertIn("minimum --duration", r.stderr)
        self.assertFalse(os.path.exists(w.path("x.html")))
        m = re.search(r"minimum --duration for this prompt at --speed 1 is ([\d.]+) s", r.stderr)
        self.assertTrue(m, r.stderr)
        need = float(m.group(1))
        self.assertEqual(w.run(TYPING, "--out", "y.html", "--duration", "%.1f" % need, "--text-file", t, "--accent", "F97316").returncode, 0)
        self.assertEqual(w.run(TYPING, "--out", "z.html", "--duration", "%.1f" % (need - 0.1), "--text-file", t, "--accent", "F97316").returncode, 2)

    def test_a_prompt_that_fits_is_written_and_the_boundary_is_exact(self):
        w = Work(self)
        t = w.json("t.json", {"prompt": "x" * 90})         # 90 characters: 3.0 s at the limit
        self.assertEqual(w.run(TYPING, "--out", "a.html", "--duration", "9", "--text-file", t, "--accent", "F97316").returncode, 0)
        # the hold keeps the window from ending later than D - 0.6, so D - 0.6 - 0.5 must be at least 3.0 s: D = 4.1 s
        for dur, code in (("4.1", 0), ("4.09", 2)):
            r = w.run(TYPING, "--out", "b.html", "--duration", dur, "--text-file", t, "--accent", "F97316")
            self.assertEqual(r.returncode, code, (dur, r.stderr))
        # the hold at the end can also be the limit: a lower speed cannot help once the clip is too short
        r = w.run(TYPING, "--out", "c.html", "--duration", "3.5", "--speed", "0.25", "--text-file", t, "--accent", "F97316")
        self.assertEqual(r.returncode, 2)
        self.assertIn("no --speed can help", r.stderr)

    def test_a_lower_speed_is_named_as_a_fix_when_it_helps(self):
        w = Work(self)
        t = w.json("t.json", {"prompt": "x" * 90})
        r = w.run(TYPING, "--out", "a.html", "--duration", "8", "--speed", "3", "--text-file", t, "--accent", "F97316")
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("lower --speed", r.stderr)
        self.assertEqual(w.run(TYPING, "--out", "b.html", "--duration", "8", "--speed", "1", "--text-file", t, "--accent", "F97316").returncode, 0)

    def test_contrast_maths(self):
        self.assertAlmostEqual(fc.contrast("000000", "FFFFFF"), 21.0, places=2)
        self.assertAlmostEqual(fc.contrast("FFFFFF", "FFFFFF"), 1.0, places=2)
        self.assertEqual(fc.mix("FFFFFF", "000000", 50), "808080")
        self.assertGreater(fc.contrast("F8FAFC", "0F172A"), 15)

    def test_colours_are_applied_on_both_cards(self):
        t = self.typing(bg="112233", fg="EEDDCC")
        self.assertIn("--bg-navy:       #112233;", t)
        self.assertIn("--text-white:    #EEDDCC;", t)
        self.assertIn("background:#112233;", t)
        h = self.hook(bg="224466", fg="FFEEDD")
        self.assertIn("--bg-navy:    #224466;", h)
        self.assertIn("--text-white: #FFEEDD;", h)
        self.assertIn("background:#224466;", h)
        self.assertIn("--bg-navy:    #224466;", self.hook(bg="#224466", wrap="template"))   # applies in template mode too
        self.assertIn("--bg-navy:       #0F172A;", self.typing())                           # defaults unchanged
        self.assertIn("--text-white: #F8FAFC;", self.hook())

    def test_poor_contrast_is_refused_with_a_clear_message(self):
        cases = [dict(bg="0F172A", fg="1E293B"), dict(bg="FFFFFF", fg="F0F0F0"), dict(bg="808080", fg="888888")]
        for kw in cases:
            for make in (self.typing, self.hook):
                with self.subTest(kw=kw, card=make.__name__):
                    with self.assertRaises(fc.FillError) as cm:
                        make(**kw)
                    self.assertIn("contrast ratio", str(cm.exception))
                    self.assertIn("below 3.0", str(cm.exception))
        with self.assertRaises(fc.FillError) as cm:                           # the accent is text on the hook card
            self.hook(bg="F97316", fg="000000", accent="F97317")
        self.assertIn("accent on bg", str(cm.exception))
        for bad in ("red", "12345", "#GGGGGG", ""):
            with self.assertRaises(fc.FillError):
                self.typing(fg=bad)
            with self.assertRaises(fc.FillError):
                self.hook(fg=bad)

    def test_contrast_refusal_on_the_command_line_writes_nothing(self):
        w = Work(self)
        t = w.json("t.json", {"prompt": "hello"})
        h = w.json("h.json", {"line1": "x"})
        for script, text in ((TYPING, t), (HOOK, h)):
            r = w.run(script, "--out", "x.html", "--duration", "5", "--text-file", text, "--accent", "F97316", "--bg", "FFFFFF", "--fg", "F0F0F0")
            self.assertEqual(r.returncode, 2, r.stderr)
            self.assertIn("contrast", r.stderr)
        self.assertFalse(os.path.exists(w.path("x.html")))
        r = w.run(HOOK, "--out", "x.html", "--duration", "5", "--text-file", h, "--accent", "F97316", "--bg", "FFFFFF", "--fg", "111111")
        self.assertEqual(r.returncode, 2)                                      # orange accent on white is below 3.0
        r = w.run(HOOK, "--out", "x.html", "--duration", "5", "--text-file", h, "--accent", "B45309", "--bg", "FFFFFF", "--fg", "111111")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_custom_sizes_and_colours_still_pass_the_render_check(self):
        for variant in ("full", "pip-safe"):
            for wrap in ("standalone", "template"):
                for size in (24, 44, 72):
                    with self.subTest(card="typing", variant=variant, wrap=wrap, size=size):
                        page = self.typing(variant=variant, wrap=wrap, prompt_size=size, bg="FFFFFF", fg="111111", slot="s1")
                        self.check(page if wrap == "standalone" else "<!DOCTYPE html><html><body>" + page + "</body></html>")
        for wrap in ("standalone", "template"):
            with self.subTest(card="hook", wrap=wrap):
                page = self.hook(bg="FFFFFF", fg="111111", accent="B45309", wrap=wrap, slot="h1")
                self.check(page if wrap == "standalone" else "<!DOCTYPE html><html><body>" + page + "</body></html>")

    def test_selectors_use_an_id_not_the_composition_attribute(self):
        for name in ("typing-scene.html", "hook-scene.html"):
            styles = "".join(re.findall(r"<style>(.*?)</style>", template(name), re.S))
            self.assertNotIn("[data-composition-id", styles, name)
            self.assertIn("-root", styles)


CHECK_MODULE = None


def check_module():
    """The real check_local.py, loaded from the b-hyperframes block, to read the patterns it refuses."""
    global CHECK_MODULE
    if CHECK_MODULE is None:
        import importlib.util
        spec = importlib.util.spec_from_file_location("check_local_under_test", CHECK_LOCAL)
        CHECK_MODULE = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(CHECK_MODULE)
    return CHECK_MODULE


class TextNodes(HTMLParser):
    """The visible text of a page: text nodes outside script and style, decoded."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.nodes, self._skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.nodes.append(data)


# For every pattern check_local.py refuses: ordinary-looking text that contains it, and what the fillers must do.
#   "refuse": exit 2 up front, naming the key (addresses and CSS address forms)
#   "accept": the page is built, passes the real check, and the visible text is unchanged (words)
# Samples are at most 38 characters so they fit every key. A new pattern in the check fails the coverage test below.
RULE_SAMPLES = {
    "a network address (http, https, ws, wss or ftp)": [("refuse", "see https://example.com"), ("refuse", "ftp://files.example"), ("refuse", "ws: socket")],
    "a script address": [("refuse", "run javascript:void(0)"), ("refuse", "vbscript:msgbox")],
    "a protocol-relative address": [("refuse", 'go to "//cdn.example/x'), ("refuse", "it's '//a.example")],
    "a data: address that is not a small image or font": [("refuse", "data:text/html,hi"), ("refuse", "data: image/png;base64,AAAA")],
    "an embedding or base element": [("accept", "<iframe src=a></iframe>"), ("accept", "<object data=a>"), ("accept", "<embed src=a>"), ("accept", "<base href=a>"),
                                      ("accept", "<frame src=a>"), ("accept", "<frameset>"), ("accept", "<applet>"), ("accept", "<portal src=a>")],
    "a meta http-equiv element": [("accept", '<meta http-equiv="refresh">')],
    "a connection hint link": [("accept", '<link rel="preconnect" x>'), ("accept", "<link rel=dns-prefetch>"), ("accept", "<link rel=prerender>")],
    "fetch(": [("accept", "fetch(x) is a word"), ("accept", "fetch (x)")],
    "XMLHttpRequest": [("accept", "XMLHttpRequest")],
    "WebSocket": [("accept", "a WebSocket link")],
    "EventSource": [("accept", "EventSource")],
    "sendBeacon": [("accept", "navigator.sendBeacon(x)")],
    "dynamic import(": [("accept", "import(x)"), ("accept", "import (x)")],
    "a module import": [("accept", "intro\nimport os\nrest"), ("accept", "import {a} from b"), ("accept", "import * as x")],
    "importScripts": [("accept", "importScripts(x)")],
    "a Worker": [("accept", "new Worker(x)"), ("accept", "new SharedWorker(x)"), ("accept", "Worker (x)")],
    "serviceWorker": [("accept", "navigator.serviceWorker")],
    "eval(": [("accept", "eval(x)"), ("accept", "eval (x)")],
    "the Function constructor": [("accept", "new Function"), ("accept", "new   Function(x)"), ("accept", "Function(x)"), ("accept", "x = Function (y)")],
    "computed access on the global object": [("accept", "window[x]"), ("accept", "self [x]"), ("accept", "globalThis[0]"), ("accept", "top[0] and parent[1]"), ("accept", "frames[0]")],
    "markup built from a string at run time": [("accept", "el.innerHTML = x"), ("accept", "innerHTML"), ("accept", "outerHTML"), ("accept", "insertAdjacentHTML(x)"),
                                               ("accept", "createContextualFragment"), ("accept", "DOMParser"), ("accept", "document.write(x)"), ("accept", "document . write")],
    "a link attribute set at run time": [("accept", 'setAttribute("src", x)'), ("accept", "setAttribute('href', y)"), ("accept", 'setAttribute ( "poster" , z )')],
    "a link property set at run time": [("accept", "a.src = b"), ("accept", "x.href=y"), ("accept", "x .srcset = z"), ("accept", "v.poster = q")],
    "new Image or new Audio": [("accept", "new Image()"), ("accept", "new Audio(x)")],
    "a loadable element created at run time": [("accept", 'createElement("script")'), ("accept", "document.createElementNS(a, 'img')"), ("accept", "createElement('iframe')")],
    "navigation or window.open": [("accept", "location.href"), ("accept", "location = x"), ("accept", "location.assign"), ("accept", "location.replace"), ("accept", "window.open(x)")],
    "ESCAPE_IN_URL": [("refuse", "url(\\31)"), ("refuse", "@import \\31"), ("accept", "src: \\31 x")],
    "IMAGE_SET": [("refuse", "image-set(a 1x)"), ("refuse", "IMAGE-SET (a 1x)")],
    "URL_FN": [("refuse", "url(x.png)"), ("refuse", "url( 'a' )"), ("refuse", "URL(//a)")],
    "IMPORT": [("refuse", "@import 'a.css'"), ("refuse", "@import url(a)"), ("refuse", "@IMPORT x")],
    "FONT_FACE": [("accept", "@font-face { font-family: X }")],
    "FONT_FAMILY": [("accept", "font-family: Papyrus"), ("accept", "font-family=Papyrus")],
    "FONT_SHORT": [("accept", "font: 12px Papyrus"), ("accept", "font : 2em/1.5 Papyrus")],
    "CUSTOM_PROP": [("accept", "--x: Papyrus"), ("accept", "set --brand-font: Papyrus")],
}


def _rule_regexes(mod):
    """(label, regex) for every pattern in the check that refuses something."""
    out = []
    for lst in (mod.ANY_FILE_RULES, mod.MARKUP_RULES, mod.SCRIPT_RULES):
        out.extend((what, rx) for rx, what in lst)
    for name in ("ESCAPE_IN_URL", "IMAGE_SET", "URL_FN", "IMPORT", "FONT_FACE", "FONT_FAMILY", "FONT_SHORT", "CUSTOM_PROP"):
        out.append((name, getattr(mod, name)))
    return out


class EveryPatternTheCheckRefuses(unittest.TestCase):
    """Either the filler refuses the text up front, or the page passes the real check and the text is unchanged."""

    check = PassesTheLocalOnlyCheck.check

    def test_every_pattern_in_the_check_has_samples(self):
        mod = check_module()
        labels = {label for label, _ in _rule_regexes(mod)}
        self.assertEqual(sorted(labels - set(RULE_SAMPLES)), [], "the check has patterns this test does not cover; add samples")
        self.assertEqual(sorted(set(RULE_SAMPLES) - labels), [], "samples for patterns the check no longer has")

    def test_every_sample_really_triggers_its_pattern(self):
        mod = check_module()
        regexes = {}
        for label, rx in _rule_regexes(mod):
            regexes.setdefault(label, []).append(rx)
        for label, samples in RULE_SAMPLES.items():
            for _, text in samples:
                raw = text.replace("\\n", "\n")
                forms = (raw, mod.decode_escapes(raw))
                with self.subTest(label=label, text=text):
                    self.assertTrue(any(rx.search(f) for rx in regexes[label] for f in forms), "sample does not match its pattern")
        # every alternative of the multi-word patterns is covered by at least one sample
        for word in ("XMLHttpRequest", "outerHTML", "insertAdjacentHTML", "createContextualFragment", "DOMParser", "innerHTML", "document"):
            self.assertTrue(any(word in t for _, t in RULE_SAMPLES["markup built from a string at run time"] + RULE_SAMPLES["XMLHttpRequest"]), word)

    def keys_for(self, card):
        return ("prompt", "label", "card_label", "bottom_tag") if card == "typing" else ("eyebrow", "line1", "line2", "line3", "subhead")

    def fill(self, card, text, **kw):
        if card == "typing":
            return typing_fill.fill(template("typing-scene.html"), 6, text, "F97316", **kw)
        return hook_fill.fill(template("hook-scene.html"), 3, text, "F97316", **kw)

    def test_refused_samples_are_refused_in_every_key(self):
        for label, samples in RULE_SAMPLES.items():
            for verdict, sample in samples:
                if verdict != "refuse":
                    continue
                text = sample.replace("\\n", "\n")
                for card in ("typing", "hook"):
                    for key in self.keys_for(card):
                        with self.subTest(label=label, sample=sample, card=card, key=key):
                            base = {"prompt": "ok"} if card == "typing" else {"line1": "ok"}
                            base[key] = text
                            with self.assertRaises(fc.FillError) as cm:
                                self.fill(card, base)
                            self.assertIn(key, str(cm.exception))

    def test_accepted_samples_build_pass_the_check_and_keep_their_text(self):
        for label, samples in RULE_SAMPLES.items():
            for verdict, sample in samples:
                if verdict != "accept":
                    continue
                text = sample.replace("\\n", "\n")
                one_line = re.sub(r"\s+", " ", text).strip()
                for card in ("typing", "hook"):
                    with self.subTest(label=label, sample=sample, card=card):
                        keys = self.keys_for(card)
                        data = {k: (text if k == "prompt" else one_line) for k in keys}
                        if card == "hook":
                            data["line1"] = one_line
                        page = self.fill(card, data)
                        self.check(page)
                        nodes = TextNodes()
                        nodes.feed(page)
                        nodes.close()
                        shown = [n.strip() for n in nodes.nodes]
                        for key in keys:
                            if key == "prompt":
                                got = json.loads('"%s"' % prompt_literal(page))
                                self.assertEqual(got, re.sub(r"\r\n|\r", "\n", text))
                            else:
                                self.assertIn(one_line, shown, "%s: the visible text changed" % key)


class LocalOnly(unittest.TestCase):
    def test_templates_have_no_remote_address(self):
        for name in ("typing-scene.html", "hook-scene.html"):
            self.assertEqual(fc.local_only_problems(template(name)), [], name)

    def test_filled_pages_have_no_remote_address(self):
        for page in (typing_fill.fill(template("typing-scene.html"), 6, {"prompt": "a b", "label": "x"}, "F97316"),
                     typing_fill.fill(template("typing-scene.html"), 6, {"prompt": "a b"}, "F97316", wrap="template", slot="s1"),
                     hook_fill.fill(template("hook-scene.html"), 3, {"line1": "A", "line2": "B", "subhead": "C"}, "F97316")):
            self.assertEqual(fc.local_only_problems(page), [])
            self.assertIsNone(re.search(r"(?i)https?:|wss?:|//|@import|url\(", page))
            inv = inventory(page)
            self.assertEqual([t for t, _ in inv.tags if t in ("img", "link", "iframe", "object", "embed", "base")], [])
            self.assertEqual([v for n, v in inv.attr_values if n in ("src", "href")], ["gsap.min.js"])

    def test_the_check_catches_what_it_should(self):
        for bad in ('<img src="https://x.example/a.png">', '<script src="//cdn.example/x.js"></script>', '<script src="other.js"></script>',
                    "@import url(x.css)", "fetch('x')", "new WebSocket(u)", '<iframe src="a.html"></iframe>', '<meta http-equiv="refresh">',
                    '<a href="data:text/html,x">', "javascript:void(0)", "// comment", '<link rel="stylesheet" href="a.css">'):
            with self.subTest(bad=bad):
                self.assertTrue(fc.local_only_problems(bad), bad)
        self.assertEqual(fc.local_only_problems('<script src="gsap.min.js"></script><img src="data:image/png;base64,AAAA">'), [])

    def test_scripts_do_not_reach_out(self):
        needles = [("sub", "process"), ("import ", "socket"), ("url", "lib"), ("http", ".client"), ("import ", "http"), ("os.", "system"), ("os.", "environ"),
                   ("getenv",), ("popen",), ("eval", "("), ("exec", "("), ("__import__",), ("api", "_key")]
        for name in ("fill_common.py", "typing_fill.py", "hook_fill.py"):
            text = read(os.path.join(SCRIPTS, name)).lower()
            for n in needles:
                self.assertFalse("".join(n) in text, "%s contains %s" % (name, "".join(n)))


if __name__ == "__main__":
    unittest.main()
