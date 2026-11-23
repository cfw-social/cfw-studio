#!/usr/bin/env python3
"""Offline tests for r-gfx-image steps 02, 03 and 04 and render.mjs.

  python3 -I -B -m unittest discover -s test -v      (from this recipe's folder; test_qa_gate.py runs b-qa-gate)

No network and no paid APIs. Needs python3, bash and ImageMagick (`convert`), which the
recipe needs too; render.mjs argument tests also need node. Every test runs the step's OWN code block, read from the step file, in a
throwaway step workdir, so an edit that brings a fault back fails here.

- 02 author_html: the self-check accepts #3B82F6 when the brand's palette uses it (a blue
  brand) and still refuses the stock blue for a brand with another accent.
- 03 render: the contact sheet is made under `set -e` on a machine whose ImageMagick has no
  default font (emulated with a `montage` shim, as on an ImageMagick build without one).
- 04 qa_gate: the re-split loop does nothing for one card and crops cards 2..N for N >= 2,
  with a `seq` shim that counts down like macOS seq ("seq 2 1" prints "2 1").
- 02 author_html also refuses script, handlers, embeds, remote content and unescaped text.
- render.mjs refuses bad arguments. Several tests open a real browser; they are skipped unless
  GFX_TEST_PLAYWRIGHT_DIR names a folder with Playwright 1.64.1 and its browser installed.
- Text: no step file or acceptance rubric calls #3b82f6 off-brand without the brand-palette
  exception, and the palette rubric judges against brief.json.brand.palette.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
STEP02 = os.path.join(SKILL_DIR, "steps", "02-author-html.md")
STEP03 = os.path.join(SKILL_DIR, "steps", "03-render.md")
STEP04 = os.path.join(SKILL_DIR, "steps", "04-qa-gate.md")
RENDER = os.path.join(SKILL_DIR, "render.mjs")

STOCK_BLUE = "#3B82F6"
W, H = 120, 90  # a small canvas keeps the ImageMagick runs fast
COLOURS = ["#C0392B", "#27AE60", "#2980B9", "#8E44AD"]


def bash_block(path, heading):
    """The first ```bash block after `heading` in a step file."""
    text = read(path)
    at = text.index(heading)  # ValueError (test error) when the heading is renamed
    m = re.compile(r"```bash\n(.*?)\n```", re.S).search(text, at)
    assert m, "no bash block after %r in %s" % (heading, path)
    return m.group(1)


def shells():
    """bash, plus macOS /bin/bash 3.2 and zsh when present (the bot may run either)."""
    found, seen = [], set()
    for cand in (shutil.which("bash"), "/bin/bash", shutil.which("zsh")):
        if cand and os.path.exists(cand):
            real = os.path.realpath(cand)
            if real not in seen:
                seen.add(real)
                found.append(cand)
    return found


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def make_shims(root):
    """A PATH dir with BSD-style seq, a no-default-font montage and a logging convert."""
    shim = os.path.join(root, "shim")
    os.makedirs(shim)
    real_seq = shutil.which("seq") or "false"
    real_montage = shutil.which("montage") or "false"
    real_convert = shutil.which("convert")
    write(os.path.join(shim, "seq"),
          "#!/bin/sh\n"
          "# macOS seq: counts DOWN when FIRST > LAST ('seq 2 1' prints 2 then 1).\n"
          "if [ \"$#\" -ne 2 ]; then exec '%s' \"$@\"; fi\n"
          "i=$1\n"
          "if [ \"$1\" -le \"$2\" ]; then while [ \"$i\" -le \"$2\" ]; do echo \"$i\"; i=$((i+1)); done\n"
          "else while [ \"$i\" -ge \"$2\" ]; do echo \"$i\"; i=$((i-1)); done; fi\n" % real_seq)
    write(os.path.join(shim, "montage"),
          "#!/bin/sh\n"
          "# ImageMagick with no default font: montage needs a non-empty -font.\n"
          "prev=; ok=\n"
          "for a in \"$@\"; do if [ \"$prev\" = -font ] && [ -n \"$a\" ]; then ok=1; fi; prev=$a; done\n"
          "if [ -z \"$ok\" ]; then echo \"montage: unable to read font \\`' @ error/annotate.c/RenderFreetype/1660.\" >&2; exit 1; fi\n"
          "exec '%s' \"$@\"\n" % real_montage)
    write(os.path.join(shim, "convert"),
          "#!/bin/sh\n"
          "if [ -n \"$CONVERT_LOG\" ]; then printf '%%s\\n' \"$*\" >> \"$CONVERT_LOG\"; fi\n"
          "exec '%s' \"$@\"\n" % real_convert)
    for name in ("seq", "montage", "convert"):
        os.chmod(os.path.join(shim, name), 0o755)
    return shim


def run_block(shell, wd, prelude, block, shim, log=None):
    env = dict(os.environ, PATH=shim + os.pathsep + os.environ.get("PATH", ""))
    env.pop("CONVERT_LOG", None)
    if log:
        env["CONVERT_LOG"] = log
    script = "set -eu\n" + prelude + "\n" + block + "\n"
    return subprocess.run([shell, "-c", script], cwd=wd, env=env, capture_output=True, text=True)


def rgb(path):
    """Raw 8-bit RGB pixels, for an exact pixel comparison."""
    return subprocess.run(["convert", path, "-depth", "8", "rgb:-"], capture_output=True, check=True).stdout


def dims(path):
    out = subprocess.run(["convert", path, "-format", "%w %h", "info:"], capture_output=True,
                         text=True, check=True).stdout
    return tuple(int(v) for v in out.split())


def tile(path, x, y, out):
    subprocess.run(["convert", path, "-crop", "%dx%d+%d+%d" % (W, H, x, y), "+repage", out],
                   capture_output=True, check=True)
    return rgb(out)


# ------------------------------------------------------------ 02 author_html

CSP = ("<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline' "
       "https://fonts.googleapis.com; font-src https://fonts.gstatic.com data:; img-src data:\">")


def card_html(accent, extra="", body="<h1>Ship it</h1>", head=""):
    return ('<!doctype html><html><head><meta charset="UTF-8">' + CSP +
            '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter&display=swap">' + head + '<style>'
            ':root{--bg:#0B1220;--card:#131C2E;--ink:#F4F6FA;--muted:#9AA6B8;--accent:%s;--line:#22304A}'
            'html,body{margin:0}.card{width:1080px;height:1080px;overflow:hidden;position:relative}%s'
            '</style></head><body><div class="card">%s</div></body></html>' % (accent, extra, body))


class CheckHarness(unittest.TestCase):
    """Runs step 02's own self-check in a throwaway work folder. Has no tests itself."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="gfx02-")
        self.block = bash_block(STEP02, "### 3. Write the save and self-check")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def run_check(self, palette, html, headline="Ship it", items=()):
        wd = tempfile.mkdtemp(dir=self.root)
        brand = {"slug": "test-brand", "name": "Test Brand"}
        if palette is not None:
            brand["palette"] = palette
        write(os.path.join(wd, "brief.json"), json.dumps({"recipe": "r-gfx-image", "intent": "t", "brand": brand}))
        write(os.path.join(wd, "prior", "plan.json"), json.dumps(
            {"count": 1, "format": "square", "cards": [{"n": 1, "layout": "stat", "headline": headline, "items": list(items)}]}))
        write(os.path.join(wd, "work", "card-1.html"), html)
        os.makedirs(os.path.join(wd, "saves"))
        p = subprocess.run(["bash", "-c", "set -eu\nW=1080 H=1080 FMT=square\n" + self.block],
                           cwd=wd, capture_output=True, text=True)
        return p, wd


class AuthorHtmlBrandCheck(CheckHarness):
    """AC1 for r-gfx-image: 02-author-html.md's own brand self-check."""

    def test_blue_brand_accent_passes(self):
        p, wd = self.run_check({"bg": "#0B1220", "accent": STOCK_BLUE}, card_html(STOCK_BLUE))
        self.assertEqual(p.returncode, 0, p.stderr)
        saved = json.loads(read(os.path.join(wd, "saves", "cards_html.json")))
        self.assertIn(STOCK_BLUE, saved["cards"][0]["html"])

    def test_blue_brand_lowercase_palette_passes(self):
        p, _ = self.run_check({"accent": "#3b82f6"}, card_html(STOCK_BLUE))
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_stock_blue_refused_for_other_accent(self):
        html = card_html("#E11D48", ".pill{color:#3b82f6}")
        p, wd = self.run_check({"bg": "#0B1220", "accent": "#E11D48"}, html)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("stock blue", p.stderr)
        self.assertFalse(os.path.exists(os.path.join(wd, "saves", "cards_html.json")))

    def test_stock_blue_refused_without_palette(self):
        p, _ = self.run_check(None, card_html(STOCK_BLUE))
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("stock blue", p.stderr)

    def test_other_accent_clean_html_passes(self):
        p, _ = self.run_check({"accent": "#E11D48"}, card_html("#E11D48"))
        self.assertEqual(p.returncode, 0, p.stderr)


class AuthorHtmlInertCheck(CheckHarness):
    """Step 02's self-check refuses active content and unescaped text."""

    def refused(self, html, message, **kw):
        p, wd = self.run_check({"accent": "#E11D48"}, html, **kw)
        self.assertNotEqual(p.returncode, 0, html)
        self.assertIn(message, p.stderr)
        self.assertFalse(os.path.exists(os.path.join(wd, "saves", "cards_html.json")))

    def with_body(self, snippet):
        return card_html("#E11D48", body="<h1>Ship it</h1>" + snippet)

    def test_script_and_handlers_refused(self):
        self.refused(self.with_body("<script>fetch('x')</script>"), "script tag")
        self.refused(self.with_body("<SCRIPT src=//evil.example/x.js></SCRIPT>"), "script tag")
        self.refused(self.with_body('<p onclick="x()">hi</p>'), "event-handler")
        self.refused(self.with_body("<img src=data:image/png;base64,AA== onerror=x()>"), "event-handler")
        self.refused(self.with_body('<a href="javascript:x()">t</a>'), "javascript:")

    def test_embeds_refused(self):
        for tag in ("<iframe src=a></iframe>", "<object data=a></object>", "<embed src=a>", "<base href=x>", "<form></form>"):
            self.refused(self.with_body(tag), "tag")

    def test_remote_content_refused(self):
        self.refused(card_html("#E11D48", head='<link rel="stylesheet" href="https://evil.example/a.css">'), "not a font host")
        self.refused(self.with_body('<img src="https://evil.example/a.png">'), "remote or file image")
        self.refused(self.with_body('<img src="file:///etc/hosts">'), "remote or file image")
        self.refused(card_html("#E11D48", extra=".a{background:url(https://evil.example/a.png)}"), "url()")
        self.refused(card_html("#E11D48", head="<style>@import 'https://evil.example/a.css';</style>"), "@import")

    def test_policy_line_required(self):
        self.refused(card_html("#E11D48").replace(CSP, ""), "content-security-policy")

    def test_font_hosts_and_data_uris_allowed(self):
        html = card_html("#E11D48", body='<h1>Ship it</h1><img src="data:image/png;base64,AA==">'
                         '<p style="background:url(data:image/png;base64,AA==)">one = 1 and on=x</p>')
        p, _ = self.run_check({"accent": "#E11D48"}, html)
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_text_must_be_escaped(self):
        raw = "<b>Q&A</b>"
        self.refused(card_html("#E11D48", body="<h1>%s</h1>" % raw), "not escaped", headline=raw)
        ok = card_html("#E11D48", body="<h1>&lt;b&gt;Q&amp;A&lt;/b&gt;</h1>")
        p, _ = self.run_check({"accent": "#E11D48"}, ok, headline=raw)
        self.assertEqual(p.returncode, 0, p.stderr)
        # raw text present next to the escaped copy is still refused
        self.refused(card_html("#E11D48", body="<h1>&lt;b&gt;Q&amp;A&lt;/b&gt;</h1>" + raw), "raw", headline=raw)

    def test_shipped_template_passes_its_own_check(self):
        tpl = read(os.path.join(SKILL_DIR, "template.html"))
        p, _ = self.run_check({"accent": "#22C55E"}, tpl, headline="HEADLINE", items=["ITEM ONE", "ITEM TWO"])
        self.assertEqual(p.returncode, 0, p.stderr)


class RenderArguments(unittest.TestCase):
    """render.mjs refuses bad arguments before it touches a browser."""

    @classmethod
    def setUpClass(cls):
        if not shutil.which("node"):
            raise unittest.SkipTest("node is not installed")

    def run_render(self, *args):
        wd = tempfile.mkdtemp(prefix="gfxr-")
        self.addCleanup(shutil.rmtree, wd, True)
        write(os.path.join(wd, "work", "card-1.html"), "<html></html>")
        return subprocess.run(["node", RENDER, *args], cwd=wd, capture_output=True, text=True)

    def test_refuses_bad_canvas_files_and_pin(self):
        good = ["--width", "1080", "--height", "1080", "--playwright-version", "1.64.1", "work/card-1.html"]
        cases = {
            "canvas": ["--width", "1000", "--height", "1000", "--playwright-version", "1.64.1", "work/card-1.html"],
            "no files": ["--width", "1080", "--height", "1080", "--playwright-version", "1.64.1"],
            "bad name": good[:-1] + ["work/other.html"],
            "outside": good[:-1] + ["../card-1.html"],
            "out-dir outside": good + ["--out-dir", ".."],
            "no pin": ["--width", "1080", "--height", "1080", "work/card-1.html"],
            "loose pin": ["--width", "1080", "--height", "1080", "--playwright-version", "1", "work/card-1.html"],
        }
        for name, args in cases.items():
            with self.subTest(name):
                p = self.run_render(*args)
                self.assertNotEqual(p.returncode, 0)
                self.assertIn("render.mjs:", p.stderr)

    def test_refuses_wrong_installed_version(self):
        p = self.run_render("--width", "1080", "--height", "1080", "--playwright-version", "1.64.1", "work/card-1.html")
        self.assertNotEqual(p.returncode, 0)  # no Playwright in the throwaway folder


PLAYWRIGHT_DIR = os.environ.get("GFX_TEST_PLAYWRIGHT_DIR")


@unittest.skipUnless(PLAYWRIGHT_DIR and os.path.isdir(os.path.join(PLAYWRIGHT_DIR, "node_modules", "playwright"))
                     and shutil.which("ffprobe"),
                     "set GFX_TEST_PLAYWRIGHT_DIR to a folder with Playwright 1.64.1 and its browser (and ffprobe on PATH)")
class RenderInBrowser(unittest.TestCase):
    """Opens a real browser: the card runs no script and loads no remote resource, and the PNG has the exact size."""

    def test_no_script_no_remote_and_exact_size(self):
        wd = tempfile.mkdtemp(prefix="gfxb-")
        self.addCleanup(shutil.rmtree, wd, True)
        os.symlink(os.path.join(PLAYWRIGHT_DIR, "node_modules"), os.path.join(wd, "node_modules"))
        write(os.path.join(wd, "package.json"), "{}")
        # The page tries to run a script and to fetch two remote images; the context blocks all of it.
        html = ('<!doctype html><html><head><meta charset="UTF-8"></head><body style="margin:0;background:#fff">'
                '<div style="width:1080px;height:1080px;background:#fff" id="c">x</div>'
                '<img src="https://example.invalid/a.png"><script>document.getElementById("c").style.background="#000"</script>'
                '</body></html>')
        write(os.path.join(wd, "work", "card-1.html"), html)
        p = subprocess.run(["node", RENDER, "--width", "1080", "--height", "1080", "--playwright-version", "1.64.1",
                            "work/card-1.html"], cwd=wd, capture_output=True, text=True, timeout=120)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("blocked request: https://example.invalid", p.stderr)
        self.assertEqual(dims(os.path.join(wd, "work", "img-1.png")), (1080, 1080))
        self.assertEqual(rgb(os.path.join(wd, "work", "img-1.png"))[:3], b"\xff\xff\xff", "the script ran")

    def test_escaped_order_text_stays_text(self):
        """Hostile order text, escaped as step 02 does it, shows as text: no tag, no request, no script."""
        import html as html_lib
        wd = tempfile.mkdtemp(prefix="gfxe-")
        self.addCleanup(shutil.rmtree, wd, True)
        os.symlink(os.path.join(PLAYWRIGHT_DIR, "node_modules"), os.path.join(wd, "node_modules"))
        write(os.path.join(wd, "package.json"), "{}")
        hostile = '<img src="https://example.invalid/x.png"><script>document.body.style.background="#000"</script>'
        html = ('<!doctype html><html><head><meta charset="UTF-8"></head><body style="margin:0;background:#fff">'
                '<div style="width:1080px;height:1080px;background:#fff;color:#fff;font-size:10px">%s</div>'
                '</body></html>' % html_lib.escape(hostile))
        write(os.path.join(wd, "work", "card-1.html"), html)
        p = subprocess.run(["node", RENDER, "--width", "1080", "--height", "1080", "--playwright-version", "1.64.1",
                            "work/card-1.html"], cwd=wd, capture_output=True, text=True, timeout=120)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertNotIn("blocked request", p.stderr, "escaped text still caused a request")
        self.assertEqual(rgb(os.path.join(wd, "work", "img-1.png"))[:3], b"\xff\xff\xff")

    def render_in(self, wd, *extra):
        write(os.path.join(wd, "work", "card-1.html"),
              '<!doctype html><html><body style="margin:0;background:#fff"><div style="width:1080px;height:1080px"></div></body></html>')
        return subprocess.run(["node", RENDER, "--width", "1080", "--height", "1080", "--playwright-version", "1.64.1",
                               *extra, "work/card-1.html"], cwd=wd, capture_output=True, text=True, timeout=120)

    def fresh(self):
        wd = tempfile.mkdtemp(prefix="gfxs-")
        outside = tempfile.mkdtemp(prefix="gfxo-")
        self.addCleanup(shutil.rmtree, wd, True)
        self.addCleanup(shutil.rmtree, outside, True)
        os.symlink(os.path.join(PLAYWRIGHT_DIR, "node_modules"), os.path.join(wd, "node_modules"))
        write(os.path.join(wd, "package.json"), "{}")
        return wd, outside

    def test_refuses_a_linked_output_folder(self):
        wd, outside = self.fresh()
        os.makedirs(os.path.join(wd, "work"))
        os.rmdir(os.path.join(wd, "work"))
        os.symlink(outside, os.path.join(wd, "work"))
        write(os.path.join(outside, "card-1.html"), "<html></html>")
        p = subprocess.run(["node", RENDER, "--width", "1080", "--height", "1080", "--playwright-version", "1.64.1",
                            "work/card-1.html"], cwd=wd, capture_output=True, text=True, timeout=120)
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual([f for f in os.listdir(outside) if f.endswith(".png")], [], "a PNG was written outside")

    def test_refuses_a_linked_parent_of_the_output_folder(self):
        wd, outside = self.fresh()
        os.symlink(outside, os.path.join(wd, "link"))
        p = self.render_in(wd, "--out-dir", "link/sub")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("link or not a folder", p.stderr)
        self.assertEqual(os.listdir(outside), [], "something was created outside")

    def test_refuses_a_linked_output_file(self):
        wd, outside = self.fresh()
        os.makedirs(os.path.join(wd, "work"))
        target = os.path.join(outside, "victim.png")
        write(target, "keep")
        os.symlink(target, os.path.join(wd, "work", "img-1.png"))
        p = self.render_in(wd)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("link or not a file", p.stderr)
        self.assertEqual(read(target), "keep")

    def test_writes_by_rename_and_leaves_no_temporary_file(self):
        wd, _ = self.fresh()
        p = self.render_in(wd)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(sorted(os.listdir(os.path.join(wd, "work"))), ["card-1.html", "img-1.png"])


def png_chunks(path):
    with open(path, "rb") as fh:
        data = fh.read()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", path
    i, names = 8, []
    while i < len(data):
        n = int.from_bytes(data[i:i + 4], "big")
        names.append(data[i + 4:i + 8].decode("latin-1"))
        i += 12 + n
    return names


class ExampleImages(unittest.TestCase):
    def test_no_text_or_time_chunks(self):
        pngs = [os.path.join(SKILL_DIR, "examples", f) for f in sorted(os.listdir(os.path.join(SKILL_DIR, "examples")))
                if f.endswith(".png")]
        self.assertTrue(pngs)
        for path in pngs:
            bad = [c for c in png_chunks(path) if c in ("tEXt", "zTXt", "iTXt", "tIME", "eXIf", "iCCP")]
            self.assertEqual(bad, [], os.path.basename(path))


# ------------------------------------------------------------ recipe text

EXCEPTION = "brief.json.brand.palette"


def prose_units(text):
    """The bullets and paragraphs of a Markdown file, with code fences dropped."""
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    units, cur = [], []
    for line in text.splitlines():
        s = re.sub(r"^[>\s]*", "", line)
        if not s or re.match(r"([-*]|\d+\.)\s|#", s):
            if cur:
                units.append(" ".join(cur))
                cur = []
        if s:
            cur.append(s)
    if cur:
        units.append(" ".join(cur))
    return units


def recipe_text_units():
    """(file, text) for each Markdown bullet/paragraph and acceptance desc in this recipe."""
    for dirpath, dirs, files in os.walk(SKILL_DIR):
        dirs[:] = sorted(d for d in dirs if d != "test")
        for name in sorted(files):
            path = os.path.join(dirpath, name)
            if name.endswith(".md"):
                for unit in prose_units(read(path)):
                    yield path, unit
            elif name.startswith("acceptance") and name.endswith(".json"):
                for check in json.loads(read(path)).get("checks", []):
                    if "desc" in check:
                        yield path, check["desc"]


class BlueBrandText(unittest.TestCase):
    """The recipe's words say what the check does: #3b82f6 is off-brand only outside the brand palette."""

    def test_no_stock_blue_rule_without_the_brand_palette_exception(self):
        bad = ["%s: %s" % (os.path.relpath(p, SKILL_DIR), u[:140]) for p, u in recipe_text_units()
               if "3b82f6" in u.lower() and EXCEPTION not in u]
        self.assertEqual(bad, [], "these call #3b82f6 off-brand with no %s exception" % EXCEPTION)

    def test_palette_rubric_judges_against_the_brand_palette(self):
        acc = json.loads(read(os.path.join(SKILL_DIR, "acceptance.json")))
        desc = next(c["desc"] for c in acc["checks"] if c["id"] == "on_brand_palette")
        self.assertIn(EXCEPTION, desc)


# ------------------------------------------------- 03 render + 04 qa_gate

def make_cards(wd, n):
    """work/img-1..n.png: one solid colour per card at the test canvas."""
    os.makedirs(os.path.join(wd, "work"), exist_ok=True)
    for i in range(1, n + 1):
        subprocess.run(["convert", "-size", "%dx%d" % (W, H), "xc:" + COLOURS[i - 1],
                        os.path.join(wd, "work", "img-%d.png" % i)], capture_output=True, check=True)


class ImageStepCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert shutil.which("convert"), "ImageMagick `convert` is required (the recipe needs it too)"

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="gfx34-")
        self.shim = make_shims(self.root)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def for_each(self, check):
        for shell in shells():
            for n in (1, 2, 3, 4):
                with self.subTest(shell=shell, n=n):
                    check(shell, n)


class RenderContactSheet(ImageStepCase):
    """AC2: step 03's save block makes the sheet under `set -e` with no default font."""

    def test_step_text_has_no_empty_font(self):
        self.assertNotRegex(read(STEP03), r"-font\s+(''|\"\")", "an empty -font is the fault itself")

    def test_shims_reproduce_the_faults(self):
        """Guard the guard: the shims really behave like the tools they stand in for."""
        env = dict(os.environ, PATH=self.shim + os.pathsep + os.environ.get("PATH", ""))
        out = subprocess.run(["sh", "-c", "seq 2 1"], env=env, capture_output=True, text=True).stdout.split()
        self.assertEqual(out, ["2", "1"])
        p = subprocess.run(["sh", "-c", "montage -tile 1x x.png y.png"], env=env, capture_output=True, text=True)
        self.assertEqual(p.returncode, 1)
        self.assertIn("unable to read font", p.stderr)

    def test_sheet_for_one_to_four_cards(self):
        self.for_each(self.check_sheet)

    def check_sheet(self, shell, n):
        wd = tempfile.mkdtemp(dir=self.root)
        make_cards(wd, n)
        os.makedirs(os.path.join(wd, "saves"))
        write(os.path.join(wd, "prior", "cards_html.json"), json.dumps(
            {"width": W, "height": H, "format": "square",
             "cards": [{"n": i, "html": "<html></html>"} for i in range(1, n + 1)]}))
        p = run_block(shell, wd, "W=%d H=%d N=%d" % (W, H, n), bash_block(STEP03, "### 3. Write the saves"), self.shim)
        self.assertEqual(p.returncode, 0, "03 render failed:\n" + p.stderr)
        saves = os.path.join(wd, "saves")
        meta = json.loads(read(os.path.join(saves, "images.json")))
        cols = meta["cols"]
        self.assertEqual((meta["count"], cols), (n, 1 if n == 1 else 2))
        rows = -(-n // cols)
        sheet = os.path.join(saves, "contact_sheet.png")
        self.assertEqual(dims(sheet), (cols * W, rows * H))  # the image_dims check
        for k in range(rows * cols):
            got = tile(sheet, (k % cols) * W, (k // cols) * H, os.path.join(self.root, "t.png"))
            if k < n:
                want = rgb(os.path.join(wd, "work", "img-%d.png" % (k + 1)))
                self.assertEqual(got, want, "sheet tile %d is not card %d" % (k + 1, k + 1))
            else:
                self.assertEqual(set(got), {0}, "padding tile %d is not black" % (k + 1))
        self.assertEqual(rgb(os.path.join(saves, "image_1.png")), rgb(os.path.join(wd, "work", "img-1.png")))


class QaGateResplit(ImageStepCase):
    """AC3: step 04's re-split loop does nothing for one card and crops 2..N for N >= 2."""

    def test_resplit_for_one_to_four_cards(self):
        self.for_each(self.check_resplit)

    def check_resplit(self, shell, n):
        # prior/ as step 03 leaves it, built here without step 03 so this test stands alone.
        src = tempfile.mkdtemp(dir=self.root)
        make_cards(src, n)
        cols = 1 if n == 1 else 2
        prior = os.path.join(src, "prior")
        os.makedirs(prior)
        sheet = ["convert"]
        for r in range(-(-n // cols)):
            sheet.append("(")
            for c in range(1, cols + 1):
                i = r * cols + c
                sheet += ([os.path.join(src, "work", "img-%d.png" % i)] if i <= n
                          else ["-size", "%dx%d" % (W, H), "xc:black"])
            sheet += ["+append", ")"]
        subprocess.run(sheet + ["-append", os.path.join(prior, "contact_sheet.png")], capture_output=True, check=True)
        shutil.copy(os.path.join(src, "work", "img-1.png"), os.path.join(prior, "image_1.png"))
        with open(os.path.join(prior, "image_1.png"), "rb") as fh:
            sha1 = hashlib.sha256(fh.read()).hexdigest()
        write(os.path.join(prior, "images.json"), json.dumps(
            {"width": W, "height": H, "count": n, "cols": cols, "images": [{"n": 1, "sha256": sha1}]}))

        wd = tempfile.mkdtemp(dir=self.root)
        os.makedirs(os.path.join(wd, "work"))
        shutil.copytree(prior, os.path.join(wd, "prior"))
        log = os.path.join(self.root, "convert-%s.log" % os.path.basename(wd))
        prelude = "W=%d H=%d N=%d COLS=%d" % (W, H, n, cols)
        p = run_block(shell, wd, prelude, bash_block(STEP04, "### 1. Re-split the set from the contact sheet"),
                      self.shim, log)
        self.assertEqual(p.returncode, 0, "04 re-split failed:\n" + p.stderr)
        calls = read(log).splitlines() if os.path.exists(log) else []
        self.assertEqual(len(calls), n - 1, "crops for cards 2..N only: %r" % calls)
        for i, call in enumerate(calls, start=2):
            self.assertTrue(call.endswith("work/img-%d.png" % i), call)
        made = sorted(f for f in os.listdir(os.path.join(wd, "work")) if f.startswith("img-"))
        self.assertEqual(made, ["img-%d.png" % i for i in range(1, n + 1)])
        for i in range(1, n + 1):
            self.assertEqual(rgb(os.path.join(wd, "work", "img-%d.png" % i)),
                             rgb(os.path.join(src, "work", "img-%d.png" % i)), "card %d changed in transit" % i)


if __name__ == "__main__":
    unittest.main(verbosity=2)
