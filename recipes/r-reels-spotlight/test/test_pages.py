#!/usr/bin/env python3
"""Every page this recipe fills must pass the b-hyperframes local-only check.

  python3 -I recipes/r-reels-spotlight/test/test_pages.py -v

They fill the takeover templates, the typing scene (through the b-typing-ui filler) and the end card
with harmless and hostile text, then run `blocks/b-hyperframes/scripts/check_local.py` on the folder:
nothing may load from the network and every named font must have a local @font-face. No render is
done here. They need the blocks beside the recipe (the repository layout).
"""
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import BLOCKS, RECIPE_DIR, Tmp, py, write_json, write_text

CHECK = os.path.join(BLOCKS, "b-hyperframes", "scripts", "check_local.py")
HOSTILE = '<script>fetch("x")</script> <img src=x onerror=alert(1)> WebSocket innerHTML {{BG}} \\ "q" \'s\''

TAKEOVERS = [
    {"start": 2.5, "end": 5.5, "template": "tk-stat", "fill": {"EYEBROW": HOSTILE, "STAT": "3X", "LABEL": HOSTILE}},
    {"start": 10, "end": 13, "template": "tk-keyword", "fill": {"WORD": HOSTILE, "SUPPORT": HOSTILE}},
    {"start": 18, "end": 21, "template": "tk-list", "fill": {"TITLE": 'Grow <span class="accent">%s</span>' % HOSTILE, "ITEM1": HOSTILE, "ITEM2": "b", "ITEM3": "c"}},
    {"start": 26, "end": 29, "template": "tk-quote", "fill": {"QUOTE": 'Make it <span class="accent">pop</span> ' + HOSTILE, "ATTR": HOSTILE}},
    {"start": 34, "end": 40, "template": "tk-typing-ui", "fill": {"PROMPT": HOSTILE + "\nsecond line", "LABEL": "AI chat", "CARD_LABEL": "The prompt", "BOTTOM_TAG": "tag", "TYPING_SPEED": "1.2"}},
]


def local_check(comp, cwd):
    return subprocess.run([sys.executable, "-I", CHECK, "--comp", comp], cwd=cwd, capture_output=True, text=True,
                          env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8"})


class FilledPagesAreLocalOnly(Tmp):
    def setUp(self):
        super().setUp()
        self.wd = self.path("wd")
        write_text(os.path.join(self.wd, "vendor", "gsap.min.js"), "/* stand-in for the pinned library */")
        write_text(os.path.join(self.wd, "work", "base.mp4"), "stand-in")

    def test_every_takeover_template_with_hostile_text(self):
        write_json(os.path.join(self.wd, "work", "plan.json"), {"duration": 44.0, "brand": {"bg": "#0F172A", "accent": "#F97316", "fg": "#F1F5F9"}, "takeovers": TAKEOVERS})
        r = py("build_takeovers.py", "work", RECIPE_DIR, BLOCKS, "vendor/gsap.min.js", cwd=self.wd)
        self.assertEqual(r.returncode, 0, r.stderr)
        c = local_check("work/comp", self.wd)
        self.assertEqual(c.returncode, 0, c.stdout + c.stderr)
        self.assertIn("LOCAL_ONLY: PASS", c.stdout)

    def test_every_template_with_plain_text(self):
        plain = [dict(t, fill={k: "Plain words" if k not in ("STAT", "TYPING_SPEED") else v for k, v in t["fill"].items()}) for t in TAKEOVERS]
        write_json(os.path.join(self.wd, "work", "plan.json"), {"duration": 44.0, "brand": {"bg": "#0F172A", "accent": "#F97316", "fg": "#F1F5F9"}, "takeovers": plain})
        self.assertEqual(py("build_takeovers.py", "work", RECIPE_DIR, BLOCKS, "vendor/gsap.min.js", cwd=self.wd).returncode, 0)
        c = local_check("work/comp", self.wd)
        self.assertEqual(c.returncode, 0, c.stdout + c.stderr)

    def test_the_end_card_with_a_hostile_handle(self):
        write_json(os.path.join(self.wd, "work", "plan.json"), {"brand": {"bg": "#0F172A", "accent": "#F97316", "fg": "#F1F5F9"}})
        write_json(os.path.join(self.wd, "work", "cta.json"), {"text": "COMMENT GUIDE " + HOSTILE, "brandName": "Acme", "handle": "https://brand.example/book"})
        r = py("cta-card.py", "work/plan.json", "work/cta.json", "work/cta-card.json", "--project", "work/cta-card", "--gsap", "vendor/gsap.min.js", cwd=self.wd)
        self.assertEqual(r.returncode, 0, r.stderr)
        c = local_check("work/cta-card", self.wd)
        self.assertEqual(c.returncode, 0, c.stdout + c.stderr)
        self.assertIn("LOCAL_ONLY: PASS", c.stdout)

    def test_the_check_would_catch_an_undeclared_font(self):
        # guards the guard: the same page with its @font-face lines removed must fail
        write_json(os.path.join(self.wd, "work", "plan.json"), {"duration": 14.0, "brand": {"bg": "#0F172A", "accent": "#F97316", "fg": "#F1F5F9"},
                                                                 "takeovers": [TAKEOVERS[1]]})
        self.assertEqual(py("build_takeovers.py", "work", RECIPE_DIR, BLOCKS, "vendor/gsap.min.js", cwd=self.wd).returncode, 0)
        page = os.path.join(self.wd, "work", "comp", "compositions", "tk0.html")
        with open(page, encoding="utf-8") as fh:
            text = fh.read()
        with open(page, "w", encoding="utf-8") as fh:
            fh.write("\n".join(l for l in text.splitlines() if "@font-face" not in l))
        c = local_check("work/comp", self.wd)
        self.assertEqual(c.returncode, 1)
        self.assertIn("@font-face", c.stderr)


if __name__ == "__main__":
    unittest.main()
