#!/usr/bin/env python3
"""End-card copy tests: resolve, the silent tail, and the card script.

  python3 -I recipes/r-reels-spotlight/test/test_cta.py -v

1. The hero line is the order's own copy (inputs/cta/cta.json, else the typed inputs/cta/cta.md,
   else brief brand.cta). With none there is no card and no tail; generic copy is never written.
2. An unreadable cta.json or brief.json stops the step; it does not become a skipped card.
3. The card script escapes text, refuses bad colours, and omits the handle line with no handle.
"""
import json
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _common import NEEDS_FFMPEG, RECIPE_DIR, SCRIPTS, Tmp, duration, load_json, make_video, py, read, write_json, write_text


class ResolveTest(Tmp):
    def resolve(self, brief=None, cta=None, cta_raw=None, brief_raw=None, typed=None):
        wd = self.path("wd%d" % len(os.listdir(self.tmp)))
        os.makedirs(wd)
        if brief_raw is not None:
            write_text(os.path.join(wd, "brief.json"), brief_raw)
        elif brief is not None:
            write_json(os.path.join(wd, "brief.json"), brief)
        if cta is not None:
            write_json(os.path.join(wd, "inputs", "cta", "cta.json"), cta)
        if cta_raw is not None:
            os.makedirs(os.path.join(wd, "inputs", "cta"), exist_ok=True)
            write_text(os.path.join(wd, "inputs", "cta", "cta.json"), cta_raw)
        if typed is not None:
            os.makedirs(os.path.join(wd, "inputs", "cta"), exist_ok=True)
            write_text(os.path.join(wd, "inputs", "cta", "cta.md"), typed)
        r = py("cta_copy.py", "resolve", "--inputs", "inputs/cta", "--brief", "brief.json", cwd=wd)
        return r, (json.loads(r.stdout) if r.returncode == 0 else None)

    def test_brand_cta_is_the_hero_line(self):
        r, d = self.resolve(brief={"brand": {"name": "Acme", "cta": "COMMENT GUIDE", "handle": "@acme"}})
        self.assertEqual((d["text"], d["brandName"], d["handle"]), ("COMMENT GUIDE", "Acme", "@acme"))

    def test_cta_json_wins(self):
        r, d = self.resolve(brief={"brand": {"name": "Acme", "cta": "FROM BRAND"}},
                            cta={"text": "FROM ORDER", "brandName": "Other", "handle": "@other"})
        self.assertEqual((d["text"], d["brandName"], d["handle"]), ("FROM ORDER", "Other", "@other"))

    def test_no_copy_means_no_text(self):
        for brief in ({"brand": {"name": "Studio"}}, {"brand": {"name": ""}}, {"brand": None}, {},
                      {"brand": {"name": "Acme", "cta": "   "}}):
            with self.subTest(brief=brief):
                r, d = self.resolve(brief=brief)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(d["text"], "")
                self.assertNotIn("ollow", r.stdout)

    def test_typed_md_alone_and_precedence(self):
        r, d = self.resolve(brief={"brand": {"name": "Acme"}}, typed="COMMENT GUIDE\n@acme\n")
        self.assertEqual((d["text"], d["handle"]), ("COMMENT GUIDE", "@acme"))
        r, d = self.resolve(brief={"brand": {"name": "Acme", "cta": "FROM BRAND", "handle": "@brand"}}, typed="TYPED")
        self.assertEqual((d["text"], d["handle"]), ("TYPED", "@brand"))
        r, d = self.resolve(brief={"brand": {"name": "Acme"}}, cta={"text": "FROM JSON"}, typed="TYPED")
        self.assertEqual(d["text"], "FROM JSON")
        r, d = self.resolve(brief={"brand": {"name": "Acme"}}, typed="  \n")
        self.assertEqual(d["text"], "")

    def test_a_bare_code_name_is_not_a_handle(self):
        r, d = self.resolve(brief={"brand": {}}, typed="Built with Node.js, join now\n")
        self.assertEqual(d["handle"], "")

    def test_unreadable_inputs_stop(self):
        self.assertNotEqual(self.resolve(brief={"brand": {}}, cta_raw="{broken")[0].returncode, 0)
        self.assertNotEqual(self.resolve(brief_raw="{broken")[0].returncode, 0)
        self.assertNotEqual(self.resolve()[0].returncode, 0)

    def test_shell_metacharacters_stay_data(self):
        nasty = 'x"; touch PWNED; $(touch PWNED2) `touch PWNED3`'
        r, d = self.resolve(brief={"brand": {}}, cta={"text": nasty})
        self.assertEqual(d["text"], nasty)
        self.assertEqual([f for f in os.listdir(self.tmp)], [f for f in os.listdir(self.tmp) if f.startswith("wd")])

    def test_has_text_exit_codes(self):
        write_json(self.path("a.json"), {"text": "Hi"})
        write_json(self.path("b.json"), {"text": " "})
        self.assertEqual(py("cta_copy.py", "has-text", self.path("a.json"), cwd=self.tmp).returncode, 0)
        self.assertEqual(py("cta_copy.py", "has-text", self.path("b.json"), cwd=self.tmp).returncode, 3)


@NEEDS_FFMPEG
class TailTest(Tmp):
    def setUp(self):
        super().setUp()
        self.wd = self.path("wd")
        os.makedirs(os.path.join(self.wd, "work"))
        self.bed = os.path.join(self.wd, "work", "base.mp4")
        make_video(self.bed, seconds=4)   # a tone to the very last frame: speech fills the clip

    def tail(self, brief, card="on", cta=None, typed=None):
        write_json(os.path.join(self.wd, "brief.json"), brief)
        if cta is not None:
            write_json(os.path.join(self.wd, "inputs", "cta", "cta.json"), cta)
        if typed is not None:
            os.makedirs(os.path.join(self.wd, "inputs", "cta"), exist_ok=True)
            write_text(os.path.join(self.wd, "inputs", "cta", "cta.md"), typed)
        return py("end_card_tail.py", "work/base.mp4", card, "3.0", cwd=self.wd)

    def test_no_copy_no_tail(self):
        before = duration(self.bed)
        r = self.tail({"brand": {"name": "Acme"}})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("no CTA copy", r.stdout)
        self.assertAlmostEqual(duration(self.bed), before, delta=0.05)

    def test_card_off_no_tail(self):
        before = duration(self.bed)
        self.assertEqual(self.tail({"brand": {"cta": "GO"}}, card="off").returncode, 0)
        self.assertAlmostEqual(duration(self.bed), before, delta=0.05)

    def test_copy_gets_a_tail_from_any_source(self):
        for kw in ({"brief": {"brand": {"cta": "COMMENT GUIDE"}}}, {"brief": {"brand": {}}, "typed": "Join now\n"}):
            with self.subTest(kw=kw):
                make_video(self.bed, seconds=4)
                before = duration(self.bed)
                r = self.tail(**kw)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertGreater(duration(self.bed), before + 3.0)
                self.assertLessEqual(duration(self.bed), before + 3.6)

    def test_unreadable_inputs_stop(self):
        write_text(os.path.join(self.wd, "brief.json"), "{not json")
        r = py("end_card_tail.py", "work/base.mp4", "on", "3.0", cwd=self.wd)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("cannot read", r.stderr)


class CardScriptTest(Tmp):
    def setUp(self):
        super().setUp()
        write_json(self.path("plan.json"), {"brand": {"bg": "#0F172A", "accent": "#F97316", "fg": "#F1F5F9"}})
        self.gsap = self.path("gsap.min.js")
        write_text(self.gsap, "/* stand-in */")

    def build(self, cta, plan=None, project=False):
        if plan is not None:
            write_json(self.path("plan.json"), plan)
        write_json(self.path("cta.json"), cta)
        args = [self.path("plan.json"), self.path("cta.json"), self.path("card.json")]
        if project:
            args += ["--project", self.path("proj"), "--gsap", self.gsap]
        return py("cta-card.py", *args, cwd=self.tmp)

    def test_empty_text_stops_and_writes_nothing(self):
        for cta in ({}, {"text": ""}, {"text": "  ", "brandName": "Acme"}):
            r = self.build(cta)
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertIn("never invents copy", r.stderr)
            self.assertFalse(os.path.exists(self.path("card.json")))

    def test_no_handle_means_no_handle_layer(self):
        r = self.build({"text": "COMMENT GUIDE", "brandName": "Acme"})
        self.assertEqual(r.returncode, 0, r.stderr)
        layers = {l["type"]: l for l in load_json(self.path("card.json"))["layers"]}
        self.assertEqual(layers["hero"]["text"], "COMMENT GUIDE")
        self.assertEqual(layers["kicker"]["text"], "ACME")
        self.assertNotIn("handle", layers)

    def test_text_is_escaped_in_the_page(self):
        r = self.build({"text": '<img src=x onerror=alert(1)> & "q"', "handle": "<script>x</script>"}, project=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(self.path("proj", "index.html"), encoding="utf-8") as fh:
            page = fh.read()
        self.assertNotIn("<img", page)
        self.assertNotIn("<script>x", page)
        self.assertIn("&lt;img", page)

    def test_a_web_address_as_the_handle_loses_its_scheme(self):
        r = self.build({"text": "BOOK NOW", "handle": "https://www.brand.example/book"}, project=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(self.path("proj", "index.html"), encoding="utf-8") as fh:
            page = fh.read()
        self.assertNotRegex(page, r"(?i)https?:")
        self.assertIn("brand.example&#47;book", page)

    def test_an_address_in_the_text_stops_the_card(self):
        for cta in ({"text": "go to https://x.example"}, {"text": "BOOK", "brandName": "javascript:x"}, {"text": "BOOK", "handle": "url(//x)"}):
            r = self.build(cta)
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertIn("The render check refuses", r.stderr)

    def test_every_named_font_is_declared_locally(self):
        r = self.build({"text": "BOOK NOW"}, project=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(self.path("proj", "index.html"), encoding="utf-8") as fh:
            page = fh.read()
        for family in ("Oswald", "Inter"):
            self.assertIn('@font-face { font-family: "%s"; src: local("%s"); }' % (family, family), page)

    def test_bad_colour_is_refused(self):
        r = self.build({"text": "Hi"}, plan={"brand": {"bg": "red;}</style><script>", "accent": "#F97316", "fg": "#F1F5F9"}})
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("6-digit hex", r.stderr)


class NoGenericCopyTest(unittest.TestCase):
    def test_no_recipe_text_writes_generic_copy(self):
        bad = re.compile(r"""or f?["']Follow |:-FOLLOW FOR MORE|or ["']FOLLOW FOR MORE["']""")
        for root, dirs, files in os.walk(RECIPE_DIR):
            dirs[:] = [d for d in dirs if d not in ("test", "__pycache__")]
            for name in files:
                if name.endswith((".md", ".py", ".json", ".sh")):
                    path = os.path.join(root, name)
                    with open(path, encoding="utf-8") as fh:
                        self.assertIsNone(bad.search(fh.read()), "generic end-card copy in " + path)


if __name__ == "__main__":
    unittest.main()
