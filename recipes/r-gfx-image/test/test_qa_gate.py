#!/usr/bin/env python3
"""Runs the real b-qa-gate block on a card, with this recipe's acceptance.json.

  python3 -I -B -m unittest discover -s test -v   (from this recipe's folder)

No network, no account. Needs ffmpeg, ffprobe and ImageMagick (`convert`) on PATH, and the
block folder beside this recipe (../../blocks/b-qa-gate/). Each test works in a throwaway
work folder, as step 4 does: the gate runs from the work folder and its input and output
stay inside it.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
RECIPE = os.path.dirname(HERE)
CHECK = os.path.normpath(os.path.join(RECIPE, "..", "..", "blocks", "b-qa-gate", "check.py"))
SPEC = os.path.join(RECIPE, "acceptance.json")
LOOK_IDS = ["no_text_clipping", "legible_contrast", "on_brand_palette",
            "premium_hierarchy", "consistent_margins"]
MECHANICAL_TYPES = {"dims", "luma_floor", "not_flat"}


def make_card(path, w=1080, h=1080, kind="card"):
    """A card-like PNG: dark background with a lighter surface and an accent bar."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if kind == "black":
        args = ["-size", "%dx%d" % (w, h), "xc:black"]
    elif kind == "flat":
        args = ["-size", "%dx%d" % (w, h), "xc:#0B1220"]
    else:
        args = ["-size", "%dx%d" % (w, h), "xc:#0B1220",
                "-fill", "#131C2E", "-draw", "roundrectangle 96,200 %d,%d 28,28" % (w - 96, h - 200),
                "-fill", "#22C55E", "-draw", "rectangle 96,96 400,120",
                "-fill", "#F4F6FA", "-draw", "rectangle 140,260 %d,330" % (w - 300)]
    subprocess.run(["convert", *args, path], check=True)


class QaGateOnCard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for tool in ("ffmpeg", "ffprobe", "convert"):
            if not shutil.which(tool):
                raise unittest.SkipTest("%s is not on PATH" % tool)
        if not os.path.exists(CHECK):
            raise unittest.SkipTest("blocks/b-qa-gate is not present")

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="gfx-qa-")

    def tearDown(self):
        shutil.rmtree(self.work, ignore_errors=True)

    def gate(self, *args):
        return subprocess.run([sys.executable, "-I", CHECK, *args], cwd=self.work,
                              capture_output=True, text=True)

    def check_card(self, spec=SPEC, n=1):
        out = "work/scorecard-%d.json" % n
        return self.gate("--kind", "image", "--spec", spec,
                         "--input", "work/img-%d.png" % n, "--out", out), out

    def answers(self, overrides=None, drop=None):
        data = {i: {"answer": "yes", "note": "looked"} for i in LOOK_IDS}
        data.update(overrides or {})
        data.pop(drop, None)
        with open(os.path.join(self.work, "work", "answers-1.json"), "w") as fh:
            json.dump(data, fh)

    def finalize(self, out):
        return self.gate("--finalize", out, "--answers", "work/answers-1.json",
                         "--out", "work/final-scorecard-1.json")

    def test_spec_uses_only_kinds_the_gate_owns(self):
        spec = json.load(open(SPEC))
        self.assertEqual({c["type"] for c in spec["checks"]} - {"perceptual"}, MECHANICAL_TYPES)
        make_card(os.path.join(self.work, "work", "img-1.png"))
        p, out = self.check_card()
        self.assertIn(p.returncode, (0, 4), p.stdout + p.stderr)
        card = json.load(open(os.path.join(self.work, out)))
        for row in card["checks"]:
            self.assertNotIn("not supported", row["detail"].lower(), row)
            self.assertNotIn("unknown", row["detail"].lower(), row)
        self.assertEqual(sorted(r["id"] for r in card["checks"] if r["status"] == "LOOK"), sorted(LOOK_IDS))

    def test_card_passes_then_finalizes_with_all_yes(self):
        make_card(os.path.join(self.work, "work", "img-1.png"))
        p, out = self.check_card()
        self.assertEqual(p.returncode, 4, p.stdout + p.stderr)  # mechanical pass, looks owed
        self.answers()
        f = self.finalize(out)
        self.assertEqual(f.returncode, 0, f.stdout + f.stderr)
        final = json.load(open(os.path.join(self.work, "work", "final-scorecard-1.json")))
        self.assertEqual(final["verdict"], "PASS")

    def test_a_no_answer_fails_the_card(self):
        make_card(os.path.join(self.work, "work", "img-1.png"))
        _, out = self.check_card()
        self.answers({"legible_contrast": {"answer": "no", "note": "grey on dark"}})
        self.assertEqual(self.finalize(out).returncode, 1)

    def test_missing_answer_fails_the_card(self):
        make_card(os.path.join(self.work, "work", "img-1.png"))
        _, out = self.check_card()
        self.answers(drop="premium_hierarchy")
        self.assertEqual(self.finalize(out).returncode, 1)

    def test_wrong_size_fails(self):
        make_card(os.path.join(self.work, "work", "img-1.png"), w=540, h=540)
        p, _ = self.check_card()
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)

    def test_black_card_fails(self):
        make_card(os.path.join(self.work, "work", "img-1.png"), kind="black")
        p, _ = self.check_card()
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)

    def test_flat_card_fails(self):
        make_card(os.path.join(self.work, "work", "img-1.png"), kind="flat")
        p, _ = self.check_card()
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)

    def test_portrait_copy_of_the_spec_as_step_4_writes_it(self):
        """Step 4 rewrites the canvas and the crop for another format; the gate accepts that copy."""
        spec = json.load(open(SPEC))
        for c in spec["checks"]:
            if c["id"] == "canvas_1080x1080":
                c.update(id="canvas_1080x1920", w=1080, h=1920)
            if c.get("crop"):
                c["crop"] = "1080:1920:0:0"
        os.makedirs(os.path.join(self.work, "work"), exist_ok=True)
        with open(os.path.join(self.work, "work", "acceptance.json"), "w") as fh:
            json.dump(spec, fh)
        make_card(os.path.join(self.work, "work", "img-1.png"), w=1080, h=1920)
        p, _ = self.check_card(spec="work/acceptance.json")
        self.assertEqual(p.returncode, 4, p.stdout + p.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
