"""Shared helpers for the recipe tests. No network, no paid call, no private file."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
RECIPE_DIR = os.path.dirname(HERE)
SCRIPTS = os.path.join(RECIPE_DIR, "scripts")
BLOCKS = os.path.join(os.path.dirname(os.path.dirname(RECIPE_DIR)), "blocks")
FFMPEG, FFPROBE = shutil.which("ffmpeg"), shutil.which("ffprobe")
NEEDS_FFMPEG = unittest.skipUnless(FFMPEG and FFPROBE, "needs ffmpeg and ffprobe")


def read(rel):
    with open(os.path.join(RECIPE_DIR, rel), encoding="utf-8") as fh:
        return fh.read()


def write_json(path, obj):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh)


def write_text(path, text):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def py(script, *args, cwd=None, env=None, input=None, timeout=120):
    """Run scripts/<script> with this Python, isolated (-I), and return the CompletedProcess."""
    e = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": cwd or "/tmp", "LANG": "C.UTF-8"}
    e.update(env or {})
    return subprocess.run([sys.executable, "-I", os.path.join(SCRIPTS, script), *args], cwd=cwd, env=e,
                          capture_output=True, text=True, input=input, timeout=timeout)


class Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def path(self, *p):
        return os.path.join(self.tmp, *p)


def make_video(path, seconds=2, size="64x64", tone=True):
    """A tiny H.264 clip, with an audio tone when asked."""
    cmd = [FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=s=%s:r=30:d=%s" % (size, seconds)]
    if tone:
        cmd += ["-f", "lavfi", "-i", "sine=f=440:d=%s" % seconds, "-shortest", "-ac", "2", "-c:a", "aac"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", path]
    subprocess.run(cmd, check=True)


def duration(path):
    return float(subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                                capture_output=True, text=True, check=True).stdout)
