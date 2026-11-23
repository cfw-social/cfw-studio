#!/usr/bin/env python3
"""Offline tests for r-ai-image steps 02 and 03 (contact sheet and re-split).

  python3 -I test/test_image_steps.py -v

No network and no paid APIs. Needs python3, bash and ffmpeg, which the recipe needs too. Every
test runs the step's OWN code block, read from the step file, in a throwaway step workdir, so an
edit that brings a fault back fails.

- 02 generate: the contact sheet is tiled with ffmpeg for every allowed count (1, 2, 3, 4, 6),
  under `set -e`, in every installed shell (bash, macOS bash 3.2, zsh).
- 03 qa_gate: the re-split loop crops images 2..N back out of the sheet for N >= 2 and leaves
  image 1 alone, and every image comes back pixel for pixel.
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
RECIPE = os.path.dirname(HERE)
STEP02 = os.path.join(RECIPE, "steps", "02-generate.md")
STEP03 = os.path.join(RECIPE, "steps", "03-qa-gate.md")

W, H = 120, 90  # a small canvas keeps the ffmpeg runs fast
COUNTS = (1, 2, 3, 4, 6)  # manifest `count` choices
COLOURS = ["0xC0392B", "0x27AE60", "0x2980B9", "0x8E44AD", "0xD35400", "0x16A085"]


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def bash_block(path, heading):
    """The first ```bash block after `heading` in a step file."""
    text = read(path)
    at = text.index(heading)
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


def run_block(shell, wd, prelude, block):
    script = "set -eu\n" + prelude + "\n" + block + "\n"
    return subprocess.run([shell, "-c", script], cwd=wd, capture_output=True, text=True)


def rgb(path):
    """Raw 8-bit RGB pixels, for an exact pixel comparison."""
    return subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                          capture_output=True, check=True).stdout


def dims(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                          "-of", "csv=p=0", path], capture_output=True, text=True, check=True).stdout.strip()
    return tuple(int(v) for v in out.split(","))


def tile(path, x, y, out):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", path, "-vf", "crop=%d:%d:%d:%d" % (W, H, x, y),
                    "-frames:v", "1", out], capture_output=True, check=True)
    return rgb(out)


def cols_for(n):
    return 1 if n <= 1 else (2 if n <= 4 else 3)  # the step's own COLS rule


def solid(path, colour, w=W, h=H):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=%s:s=%dx%d" % (colour, w, h),
                    "-frames:v", "1", path], capture_output=True, check=True)


def make_images(wd, n):
    """work/img-1..n.png: one solid colour per image at the test canvas."""
    os.makedirs(os.path.join(wd, "work"), exist_ok=True)
    for i in range(1, n + 1):
        solid(os.path.join(wd, "work", "img-%d.png" % i), COLOURS[i - 1])


class ImageStepCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg is required (the recipe needs it too)"

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="aiimg-")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def for_each(self, check):
        for shell in shells():
            for n in COUNTS:
                with self.subTest(shell=shell, n=n):
                    check(shell, n)


class GenerateContactSheet(ImageStepCase):
    """Step 02's "Write the saves" block tiles the sheet with ffmpeg only."""

    def test_step_uses_no_other_image_tool(self):
        text = read(STEP02) + read(STEP03)
        for word in ("convert ", "montage", "magick"):
            self.assertNotIn(word, text)

    def test_sheet_for_every_count(self):
        self.for_each(self.check_sheet)

    def check_sheet(self, shell, n):
        wd = tempfile.mkdtemp(dir=self.root)
        make_images(wd, n)
        os.makedirs(os.path.join(wd, "saves"))
        write(os.path.join(wd, "prior", "prompts.json"), json.dumps(
            {"count": n, "aspect_ratio": "1:1", "model": "test-model", "negative": "", "images": []}))
        write(os.path.join(wd, "work", "tasks.json"), json.dumps(
            {str(i): {"task_id": "task-%d" % i, "attempts": 1} for i in range(1, n + 1)}))
        p = run_block(shell, wd, "W=%d H=%d COUNT=%d" % (W, H, n), bash_block(STEP02, "### 3. Write the saves"))
        self.assertEqual(p.returncode, 0, "02 generate failed:\n" + p.stderr)
        saves = os.path.join(wd, "saves")
        meta = json.loads(read(os.path.join(saves, "images.json")))
        cols = meta["cols"]
        self.assertEqual((meta["count"], cols), (n, cols_for(n)))
        rows = -(-n // cols)
        sheet = os.path.join(saves, "contact_sheet.png")
        self.assertEqual(dims(sheet), (cols * W, rows * H))  # the image_dims check
        for k in range(rows * cols):
            got = tile(sheet, (k % cols) * W, (k // cols) * H, os.path.join(self.root, "t.png"))
            if k < n:
                want = rgb(os.path.join(wd, "work", "img-%d.png" % (k + 1)))
                self.assertEqual(got, want, "sheet tile %d is not image %d" % (k + 1, k + 1))
            else:
                self.assertEqual(set(got), {0}, "padding tile %d is not black" % (k + 1))
        self.assertEqual(rgb(os.path.join(saves, "image_1.png")), rgb(os.path.join(wd, "work", "img-1.png")))


class QaGateResplit(ImageStepCase):
    """Step 03's re-split loop does nothing for one image and crops 2..N for N >= 2."""

    def test_resplit_for_every_count(self):
        self.for_each(self.check_resplit)

    def check_resplit(self, shell, n):
        # prior/ as step 02 leaves it, built here without step 02 so this test stands alone.
        src = tempfile.mkdtemp(dir=self.root)
        make_images(src, n)
        cols = cols_for(n)
        prior = os.path.join(src, "prior")
        os.makedirs(prior)
        if n == 1:
            shutil.copy(os.path.join(src, "work", "img-1.png"), os.path.join(prior, "contact_sheet.png"))
        else:
            inputs, layout = [], []
            for i in range(1, n + 1):
                inputs += ["-i", os.path.join(src, "work", "img-%d.png" % i)]
                layout.append("%d_%d" % ((i - 1) % cols * W, (i - 1) // cols * H))
            subprocess.run(["ffmpeg", "-y", "-v", "error"] + inputs + [
                "-filter_complex", "xstack=inputs=%d:layout=%s" % (n, "|".join(layout)), "-frames:v", "1",
                os.path.join(prior, "contact_sheet.png")], capture_output=True, check=True)
        shutil.copy(os.path.join(src, "work", "img-1.png"), os.path.join(prior, "image_1.png"))
        with open(os.path.join(prior, "image_1.png"), "rb") as fh:
            sha1 = hashlib.sha256(fh.read()).hexdigest()
        write(os.path.join(prior, "images.json"), json.dumps(
            {"width": W, "height": H, "count": n, "cols": cols, "model": "test-model",
             "images": [{"n": 1, "sha256": sha1}]}))

        wd = tempfile.mkdtemp(dir=self.root)
        os.makedirs(os.path.join(wd, "work"))
        shutil.copytree(prior, os.path.join(wd, "prior"))
        prelude = "W=%d H=%d N=%d COLS=%d" % (W, H, n, cols)
        p = run_block(shell, wd, prelude, bash_block(STEP03, "### 1. Re-split the batch from the contact sheet"))
        self.assertEqual(p.returncode, 0, "03 re-split failed:\n" + p.stderr)
        made = sorted((f for f in os.listdir(os.path.join(wd, "work")) if f.startswith("img-")),
                      key=lambda f: int(re.search(r"(\d+)", f).group(1)))
        self.assertEqual(made, ["img-%d.png" % i for i in range(1, n + 1)])
        for i in range(1, n + 1):
            self.assertEqual(rgb(os.path.join(wd, "work", "img-%d.png" % i)),
                             rgb(os.path.join(src, "work", "img-%d.png" % i)), "image %d changed in transit" % i)


if __name__ == "__main__":
    unittest.main(verbosity=2, warnings="ignore")
