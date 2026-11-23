#!/usr/bin/env python3
"""Offline tests for r-carousel step 02's brand self-check.

  python3 -I test/test_brand_check.py -v   (from this recipe's folder)

No network and no paid APIs. Needs Python 3, with no shell. Each test runs the step's OWN
"Native authoring check" block, read from steps/02-author-slides.md, in a throwaway
step workdir, so an edit that brings the fault back fails here.

The check refuses #3b82f6 as the stock template blue. A brand whose own palette uses
#3B82F6 (Test Brand's accent) must pass; a brand with another accent must still be refused
when the stock blue is left in the HTML. A text check keeps SKILL.md, the step files and
acceptance.json saying the same thing.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
STEP02 = os.path.join(SKILL_DIR, "steps", "02-author-slides.md")
STOCK_BLUE = "#3B82F6"
SLIDES = 3


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def python_block(path, heading):
    """The native Python check after `heading` in a step file."""
    text = read(path)
    at = text.index(heading)  # ValueError (test error) when the heading is renamed
    m = re.compile(r"```python\n(.*?)\n```", re.S).search(text, at)
    assert m, "no python block after %r in %s" % (heading, path)
    return m.group(1)


def carousel_html(accent, extra=""):
    sections = "".join('<section class="slide" id="s%d"><h1>H%d</h1><p>B.</p></section>' % (n, n)
                       for n in range(1, SLIDES + 1))
    return ('<!doctype html><html><head><meta charset="UTF-8"><style>'
            ':root{--accent:%s;--ink:#1A1A1A;--bg:#0F172A;--card:#FFFFFF;--line:#E5E7EB;--muted:#64748B}%s'
            '</style></head><body>%s</body></html>' % (accent, extra, sections))


class CheckHarness(unittest.TestCase):
    """Runs the step's own authoring check in a throwaway work folder. Has no tests itself."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="car02-")
        self.block = python_block(STEP02, "## Native authoring check")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def run_check(self, palette, html, slides=None):
        wd = tempfile.mkdtemp(dir=self.root)
        brand = {"slug": "test-brand", "name": "Test Brand"}
        if palette is not None:
            brand["palette"] = palette
        write(os.path.join(wd, "brief.json"), json.dumps({"recipe": "r-carousel", "intent": "t", "brand": brand}))
        write(os.path.join(wd, "prior", "outline.json"), json.dumps(
            {"num_slides": SLIDES, "slides": [{"n": n, "role": "content", "headline": "H%d" % n}
                                              for n in range(1, SLIDES + 1)]}))
        slides = slides or [{"n": n, "role": "content", "headline": "H%d" % n,
                             "body": "B.", "visual": "step list"} for n in range(1, SLIDES + 1)]
        write(os.path.join(wd, "work", "slide_copy.json"), json.dumps(
            {"aspect_ratio": "4:5", "slides": slides}))
        write(os.path.join(wd, "work", "carousel.html"), html)
        os.makedirs(os.path.join(wd, "saves"))
        p = subprocess.run([sys.executable, "-c", self.block], cwd=wd, capture_output=True, text=True)
        return p, wd


class AuthorSlidesBrandCheck(CheckHarness):
    """AC1 for r-carousel: brand_vars_set as the step's self-check enforces it."""

    def test_blue_brand_accent_passes(self):
        p, wd = self.run_check({"bg": "#0F172A", "accent": STOCK_BLUE}, carousel_html(STOCK_BLUE))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(os.path.exists(os.path.join(wd, "saves", "slide_copy.json")))
        self.assertIn(STOCK_BLUE, read(os.path.join(wd, "saves", "carousel_html.md")))

    def test_blue_brand_lowercase_palette_passes(self):
        p, _ = self.run_check({"accent": "#3b82f6"}, carousel_html(STOCK_BLUE))
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_stock_blue_refused_for_other_accent(self):
        html = carousel_html("#E11D48", ".pill{color:#3b82f6}")
        p, wd = self.run_check({"bg": "#0F172A", "accent": "#E11D48"}, html)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("stock blue left in template", p.stderr)
        self.assertFalse(os.path.exists(os.path.join(wd, "saves", "slide_copy.json")))

    def test_stock_blue_refused_without_palette(self):
        p, _ = self.run_check(None, carousel_html(STOCK_BLUE))
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("stock blue left in template", p.stderr)

    def test_other_accent_clean_html_passes(self):
        p, _ = self.run_check({"accent": "#E11D48"}, carousel_html("#E11D48"))
        self.assertEqual(p.returncode, 0, p.stderr)


class AuthoringCheckEscaping(CheckHarness):
    """Order text must be in the page escaped, and never raw."""

    def slides(self, headline, body="B."):
        return [{"n": n, "role": "content", "headline": headline if n == 1 else "H%d" % n,
                 "body": body, "visual": "step list"} for n in range(1, SLIDES + 1)]

    def page(self, first):
        html = carousel_html("#E11D48").replace("<h1>H1</h1>", first, 1)
        return html

    def test_escaped_text_passes(self):
        html = self.page("<h1>Fish &amp; &lt;chips&gt; &quot;now&quot;</h1>")
        p, _ = self.run_check({"accent": "#E11D48"}, html, self.slides('Fish & <chips> "now"'))
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_the_accent_span_the_template_shows_is_accepted(self):
        """Regression: template.html shows <span class="hl">word</span> in a headline, and the check refused it."""
        html = self.page('<h1>The big <span class="hl">promise</span> headline</h1>')
        p, wd = self.run_check({"accent": "#E11D48"}, html, self.slides("The big promise headline"))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(os.path.exists(os.path.join(wd, "saves", "carousel_html.md")))
        template = read(os.path.join(SKILL_DIR, "template.html"))
        self.assertIn('<span class="hl">', template)
        self.assertIn('<span class="hl">', read(STEP02))

    def test_any_other_span_or_tag_still_splits_the_copy_and_fails(self):
        for first in ('<h1>The big <span class="x">promise</span> headline</h1>',
                      '<h1>The big <b>promise</b> headline</h1>',
                      '<h1>The big <span class="hl" onclick="x()">promise</span> headline</h1>'):
            html = self.page(first)
            p, _ = self.run_check({"accent": "#E11D48"}, html, self.slides("The big promise headline"))
            self.assertNotEqual(p.returncode, 0, first)

    def test_a_span_written_in_the_copy_is_still_raw_markup(self):
        raw = 'The <span class="hl">big</span> one'
        html = self.page("<h1>%s</h1>" % raw)
        p, _ = self.run_check({"accent": "#E11D48"}, html, self.slides(raw))
        self.assertNotEqual(p.returncode, 0)

    def test_raw_tag_in_copy_fails(self):
        html = self.page("<h1><h1>Big</h1></h1>")
        p, wd = self.run_check({"accent": "#E11D48"}, html, self.slides("<h1>Big</h1>"))
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("not escaped", p.stderr)
        self.assertFalse(os.path.exists(os.path.join(wd, "saves", "carousel_html.md")))

    def test_raw_anchor_in_copy_fails(self):
        raw = '<a href="https://evil.example/x">go</a>'
        html = self.page("<h1>%s</h1>" % raw)
        p, _ = self.run_check({"accent": "#E11D48"}, html, self.slides(raw))
        self.assertNotEqual(p.returncode, 0)

    def test_escaped_form_present_but_raw_also_present_fails(self):
        raw = "<b>x</b>"
        html = self.page("<h1>&lt;b&gt;x&lt;/b&gt;</h1><div>%s</div>" % raw)
        p, _ = self.run_check({"accent": "#E11D48"}, html, self.slides(raw))
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("raw (unescaped)", p.stderr)

    def test_missing_copy_fails(self):
        p, _ = self.run_check({"accent": "#E11D48"}, carousel_html("#E11D48"), self.slides("Not in the page"))
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("missing or not escaped", p.stderr)


class AuthoringCheckRejectsActiveContent(CheckHarness):
    """The authoring check refuses script, handlers, embeds and remote content."""

    def refused(self, snippet, message):
        html = carousel_html("#E11D48").replace("</body>", snippet + "</body>")
        p, wd = self.run_check({"accent": "#E11D48"}, html)
        self.assertNotEqual(p.returncode, 0, snippet)
        self.assertIn(message, p.stderr)
        self.assertFalse(os.path.exists(os.path.join(wd, "saves", "carousel_html.md")))

    def test_script_tag_rejected(self):
        self.refused("<script>fetch('x')</script>", "script tag")
        self.refused("<SCRIPT src=//evil.example/x.js></SCRIPT>", "script tag")

    def test_event_handler_rejected(self):
        self.refused('<p onclick="x()">hi</p>', "event-handler")
        self.refused("<img src=data:image/png;base64,AA== onerror=x()>", "event-handler")

    def test_embeds_rejected(self):
        for tag in ("<iframe src=a></iframe>", "<object data=a></object>", "<embed src=a>"):
            self.refused(tag, "iframe, object, embed")

    def test_remote_content_rejected(self):
        self.refused('<link rel="stylesheet" href="https://evil.example/a.css">', "not a font host")
        self.refused('<img src="https://evil.example/a.png">', "remote or file image")
        self.refused("<style>@import 'https://evil.example/a.css';</style>", "@import")
        self.refused("<style>.a{background:url(https://evil.example/a.png)}</style>", "url()")
        self.refused('<a href="javascript:x()">t</a>', "javascript:")

    def test_more_remote_and_hidden_forms_rejected(self):
        self.refused('<img srcset="https://evil.example/a.png 2x" src="data:image/png;base64,AA==">', "srcset")
        self.refused('<video poster="https://evil.example/a.png"></video>', "poster")
        self.refused('<form action="https://evil.example/x"><input></form>', "form")
        self.refused('<a href="&#106;avascript&#58;x()">t</a>', "javascript:")
        self.refused('<a href="java&#x09;script:x()">t</a>', "javascript:")
        self.refused('<p style="background:&#117;rl(https://evil.example/a.png)">t</p>', "url()")
        self.refused("<style>.a{background:\\75rl(https://evil.example/a.png)}</style>", "backslash")
        self.refused("<style>.a{background:u\\72l(https://evil.example/a.png)}</style>", "backslash")
        self.refused('<p style="background:image-set(\'https://evil.example/a.png\' 1x)">t</p>', "image-set")

    def test_font_hosts_and_data_uris_allowed(self):
        html = carousel_html("#E11D48").replace("<style>",
            '<link href="https://fonts.googleapis.com/css2?family=Poppins" rel="stylesheet">'
            '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><style>', 1)
        html = html.replace("</body>", '<img src="data:image/png;base64,AA==">'
                            "<p style=\"background:url(data:image/png;base64,AA==)\">one = 1 and on=x</p></body>")
        p, _ = self.run_check({"accent": "#E11D48"}, html)
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_shipped_template_passes_its_own_check(self):
        # The template ships sections s1, s2 and s5 as samples; renumber to s1..s3.
        tpl = read(os.path.join(SKILL_DIR, "template.html")).replace('id="s5"', 'id="s3"')
        slides = [{"n": 1, "headline": "headline goes here",
                   "body": "One supporting sentence that earns the swipe. Keep it short and specific."},
                  {"n": 2, "headline": "A clear insight, one per slide", "body": ""},
                  {"n": 3, "headline": "follow", "body": "A one-line offer or next step."}]
        p, _ = self.run_check({"accent": "#F97316"}, tpl, slides)
        self.assertEqual(p.returncode, 0, p.stderr)


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
