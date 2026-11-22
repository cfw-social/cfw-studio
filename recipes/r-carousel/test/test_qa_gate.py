#!/usr/bin/env python3
"""Runs the real b-qa-gate block on a slide, with this recipe's acceptance.json.

  python3 -I test/test_qa_gate.py -v   (from this recipe's folder)

No network, no account. Needs ffmpeg and ffprobe on PATH. Each test works in a
throwaway work folder, as the recipe's step 3 does: the gate runs from the work
folder and its input and output stay inside it.
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
LOOK_IDS = ["no_clipped_text", "legible_contrast", "consistent_margins",
            "on_brand_palette", "premium_hierarchy"]


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def make_slide(path, w=1080, h=1350, source="testsrc2"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    "%s%ssize=%dx%d:rate=1" % (source, ":" if "=" in source else "=", w, h), "-frames:v", "1", path], check=True)


class QaGateOnSlide(unittest.TestCase):
    def setUp(self):
        if not os.path.exists(CHECK):
            self.skipTest("blocks/b-qa-gate is not present")
        self.work = tempfile.mkdtemp(prefix="car-qa-")

    def tearDown(self):
        shutil.rmtree(self.work, ignore_errors=True)

    def gate(self, *args):
        return subprocess.run([sys.executable, "-I", CHECK, *args], cwd=self.work,
                              capture_output=True, text=True)

    def check_slide(self, n=1):
        out = "work/qa/slide_%d.json" % n
        return self.gate("--kind", "image", "--spec", SPEC,
                         "--input", "saves/slide_%d.png" % n, "--out", out), out

    def test_spec_uses_only_kinds_the_gate_owns(self):
        make_slide(os.path.join(self.work, "saves", "slide_1.png"))
        p, out = self.check_slide()
        self.assertIn(p.returncode, (0, 4), p.stdout + p.stderr)
        card = load(os.path.join(self.work, out))
        for row in card["checks"]:
            self.assertNotIn("not supported", row["detail"].lower(), row)
        self.assertEqual(sorted(r["id"] for r in card["checks"] if r["status"] == "LOOK"),
                         sorted(LOOK_IDS))

    def test_slide_passes_then_finalizes_with_all_yes(self):
        make_slide(os.path.join(self.work, "saves", "slide_1.png"))
        p, out = self.check_slide()
        self.assertEqual(p.returncode, 4, p.stdout + p.stderr)  # mechanical pass, looks owed
        answers = {i: {"answer": "yes", "note": "looked"} for i in LOOK_IDS}
        with open(os.path.join(self.work, "work", "qa", "answers_1.json"), "w") as fh:
            json.dump(answers, fh)
        f = self.gate("--finalize", out, "--answers", "work/qa/answers_1.json",
                      "--out", "work/qa/final_1.json")
        self.assertEqual(f.returncode, 0, f.stdout + f.stderr)
        final = load(os.path.join(self.work, "work", "qa", "final_1.json"))
        self.assertEqual(final["verdict"], "PASS")

    def test_a_no_answer_fails_the_slide(self):
        make_slide(os.path.join(self.work, "saves", "slide_1.png"))
        p, out = self.check_slide()
        answers = {i: {"answer": "yes", "note": ""} for i in LOOK_IDS}
        answers["legible_contrast"] = {"answer": "no", "note": "grey on dark"}
        with open(os.path.join(self.work, "work", "qa", "answers_1.json"), "w") as fh:
            json.dump(answers, fh)
        f = self.gate("--finalize", out, "--answers", "work/qa/answers_1.json",
                      "--out", "work/qa/final_1.json")
        self.assertEqual(f.returncode, 1, f.stdout + f.stderr)

    def test_missing_answer_fails_the_slide(self):
        make_slide(os.path.join(self.work, "saves", "slide_1.png"))
        p, out = self.check_slide()
        answers = {i: {"answer": "yes", "note": ""} for i in LOOK_IDS[:-1]}
        with open(os.path.join(self.work, "work", "qa", "answers_1.json"), "w") as fh:
            json.dump(answers, fh)
        f = self.gate("--finalize", out, "--answers", "work/qa/answers_1.json",
                      "--out", "work/qa/final_1.json")
        self.assertEqual(f.returncode, 1, f.stdout + f.stderr)

    def test_wrong_size_fails(self):
        make_slide(os.path.join(self.work, "saves", "slide_1.png"), w=540, h=675)
        p, _ = self.check_slide()
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)

    def test_blank_slide_fails(self):
        make_slide(os.path.join(self.work, "saves", "slide_1.png"), source="color=c=black")
        p, _ = self.check_slide()
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
