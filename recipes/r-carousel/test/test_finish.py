#!/usr/bin/env python3
"""Tests for finish.py, step 3's helper, and the full gate flow through it.

  python3 -I test/test_finish.py -v   (from this recipe's folder)

No network, no account. Needs ffmpeg and ffprobe on PATH. Each test works in a
throwaway work folder, as the step does.
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
FINISH = os.path.join(RECIPE, "finish.py")
BLOCKS = os.path.normpath(os.path.join(RECIPE, "..", "..", "blocks"))
LOOKS = ["no_clipped_text", "legible_contrast", "consistent_margins", "on_brand_palette", "premium_hierarchy"]


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


class Finish(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="car-fin-")
        self.outside = tempfile.mkdtemp(prefix="car-out-")

    def tearDown(self):
        shutil.rmtree(self.work, ignore_errors=True)
        shutil.rmtree(self.outside, ignore_errors=True)

    def slides(self, n=3, h=1350, w=1080):
        os.makedirs(os.path.join(self.work, "slides"), exist_ok=True)
        for i in range(1, n + 1):
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                            "testsrc2=size=%dx%d:rate=1" % (w, h), "-frames:v", "1",
                            os.path.join(self.work, "slides", "slide-%d.png" % i)], check=True)

    def fin(self, *args):
        return subprocess.run([sys.executable, "-I", FINISH, *args], cwd=self.work,
                              capture_output=True, text=True)

    def path(self, *p):
        return os.path.join(self.work, *p)

    def answer_all(self, n, no=None):
        for i in range(1, n + 1):
            ans = {k: {"answer": "yes", "note": "looked"} for k in LOOKS}
            if no == i:
                ans["legible_contrast"] = {"answer": "no", "note": "grey on dark"}
            os.makedirs(self.path("work", "qa"), exist_ok=True)
            with open(self.path("work", "qa", "answers_%d.json" % i), "w") as fh:
                json.dump(ans, fh)

    def test_whole_flow_portrait(self):
        self.slides(3)
        p = self.fin("slides", "--count", "3", "--width", "1080", "--height", "1350")
        self.assertEqual(p.returncode, 0, p.stderr)
        for f in ("slide_1.png", "slide_2.png", "slide_3.png", "cover.png", "slide_sheet.png", "slides.json"):
            self.assertTrue(os.path.isfile(self.path("saves", f)), f)
        idx = load(self.path("saves", "slides.json"))
        self.assertEqual((idx["width"], idx["height"], idx["count"]), (1080, 1350, 3))
        self.assertEqual([s["n"] for s in idx["slides"]], [1, 2, 3])
        self.assertEqual(len(idx["slides"][0]["sha256"]), 64)
        self.assertFalse(os.path.exists(self.path("saves", "slide_4.png")))
        self.assertEqual([f for f in os.listdir(self.path("saves")) if f.startswith(".tmp-")], [])
        p = self.fin("spec", "--recipe-dir", RECIPE, "--width", "1080", "--height", "1350")
        self.assertEqual(p.returncode, 0, p.stderr)
        p = self.fin("qa", "--count", "3", "--blocks-dir", BLOCKS)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("exit 4", p.stdout)
        self.answer_all(3)
        p = self.fin("finalize", "--count", "3", "--blocks-dir", BLOCKS)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        p = self.fin("report", "--count", "3", "--rounds", "1")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        rep = load(self.path("saves", "qa_report.json"))
        self.assertEqual([s["verdict"] for s in rep["slides"]], ["PASS"] * 3)

    def test_square_spec_and_flow(self):
        self.slides(3, h=1080)
        p = self.fin("spec", "--recipe-dir", RECIPE, "--width", "1080", "--height", "1080")
        self.assertEqual(p.returncode, 0, p.stderr)
        spec = load(self.path("work", "acceptance.json"))
        dims = [c for c in spec["checks"] if c["type"] == "dims"][0]
        self.assertEqual((dims["id"], dims["w"], dims["h"]), ("canvas_1080x1080", 1080, 1080))
        self.assertEqual([c["crop"] for c in spec["checks"] if c.get("crop")], ["1080:1080:0:0"])
        self.assertEqual(self.fin("slides", "--count", "3", "--width", "1080", "--height", "1080").returncode, 0)
        p = self.fin("qa", "--count", "3", "--blocks-dir", BLOCKS)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_a_no_answer_fails_report(self):
        self.slides(3)
        self.fin("slides", "--count", "3", "--width", "1080", "--height", "1350")
        self.fin("spec", "--recipe-dir", RECIPE, "--width", "1080", "--height", "1350")
        self.fin("qa", "--count", "3", "--blocks-dir", BLOCKS)
        self.answer_all(3, no=2)
        self.assertNotEqual(self.fin("finalize", "--count", "3", "--blocks-dir", BLOCKS).returncode, 0)
        p = self.fin("report", "--count", "3", "--rounds", "1")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("slide 2", p.stderr)

    def test_wrong_size_refused(self):
        self.slides(3, h=1080)
        p = self.fin("slides", "--count", "3", "--width", "1080", "--height", "1350")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("not 1080x1350", p.stderr)

    def test_bad_count_refused(self):
        p = self.fin("slides", "--count", "4", "--width", "1080", "--height", "1350")
        self.assertNotEqual(p.returncode, 0)

    def test_saves_folder_that_is_a_link_refused(self):
        self.slides(3)
        os.symlink(self.outside, self.path("saves"))
        p = self.fin("slides", "--count", "3", "--width", "1080", "--height", "1350")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("is a link", p.stderr)
        self.assertEqual(os.listdir(self.outside), [])

    def test_output_file_that_is_a_link_refused(self):
        self.slides(3)
        os.makedirs(self.path("saves"))
        os.symlink(os.path.join(self.outside, "x.png"), self.path("saves", "slide_2.png"))
        p = self.fin("slides", "--count", "3", "--width", "1080", "--height", "1350")
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual(os.listdir(self.outside), [])

    def test_slide_input_that_is_a_link_refused(self):
        self.slides(3)
        real = os.path.join(self.outside, "real.png")
        shutil.move(self.path("slides", "slide-2.png"), real)
        os.symlink(real, self.path("slides", "slide-2.png"))
        p = self.fin("slides", "--count", "3", "--width", "1080", "--height", "1350")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("a link", p.stderr)

    def test_qa_folder_that_is_a_link_refused(self):
        self.slides(3)
        self.fin("slides", "--count", "3", "--width", "1080", "--height", "1350")
        self.fin("spec", "--recipe-dir", RECIPE, "--width", "1080", "--height", "1350")
        os.symlink(self.outside, self.path("work", "qa"))
        p = self.fin("qa", "--count", "3", "--blocks-dir", BLOCKS)
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual(os.listdir(self.outside), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
