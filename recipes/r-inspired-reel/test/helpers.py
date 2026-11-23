"""Shared helpers for the r-inspired-reel tests: small ffmpeg-made media, words files, a work folder."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
RECIPE = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(RECIPE))
BLOCKS = os.path.join(REPO, "blocks")
SCRIPTS = os.path.join(RECIPE, "scripts")
STEPS = os.path.join(RECIPE, "steps")
sys.path.insert(0, SCRIPTS)

FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
KEY = "test-key-not-real"

# A made-up transcript. No real person said it; the tests only need known words.
REF_TEXT = ("Did you know your garden hose is lying to you? Here is why. "
            "First, the tap pressure is not what the label says. "
            "Second, every kink in the line steals half the flow. "
            "Third, the nozzle you bought wears out in a single season. "
            "So check the washer before you blame the tap. "
            "Follow along for more garden tricks every week.")


def timed(text, start=0.3, gap=0.33, dur=0.25, pause=0.5):
    """Word entries in b-audio's format, one every `gap` seconds, with a longer pause after a sentence."""
    out, t = [], start
    for w in text.split():
        out.append({"text": w, "start": round(t, 3), "end": round(t + dur, 3)})
        t += gap + (pause if w.rstrip("'\")").endswith((".", "?", "!")) else 0)
    return out


def ff(*args):
    os.makedirs(os.path.dirname(args[-1]), exist_ok=True)
    p = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", *args], capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError("ffmpeg failed: " + p.stderr[-300:])


def make_cut_video(path, shots=(5, 5, 5, 5), size="90x160", audio=True, tone_db=-20):
    """Solid colour shots joined with hard cuts, with an optional sine tone. Cuts fall at the running sums."""
    colours = ["red", "blue", "green", "yellow", "purple", "orange"]
    cmd, labels = [], ""
    for i, d in enumerate(shots):
        cmd += ["-f", "lavfi", "-i", "color=c=%s:s=%s:d=%s:r=30" % (colours[i % len(colours)], size, d)]
        labels += "[%d]" % i
    cmd += ["-f", "lavfi", "-i", "sine=f=300:d=%s:r=48000" % sum(shots)]
    fc = "%sconcat=n=%d:v=1:a=0[v]" % (labels, len(shots))
    cmd += ["-filter_complex", fc, "-map", "[v]"]
    if audio:
        cmd += ["-map", "%d:a" % len(shots), "-af", "volume=%ddB" % tone_db, "-c:a", "aac"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-shortest", path]
    ff(*cmd)


def make_avatar_video(path, seconds=20, size="270x480", silent=False):
    """A stand-in for HeyGen's output: a moving test pattern with a tone (or silence)."""
    src = "anullsrc=r=48000:cl=stereo" if silent else "sine=f=220:r=48000"
    ff("-f", "lavfi", "-i", "testsrc2=s=%s:d=%s:r=30" % (size, seconds), "-f", "lavfi", "-i", src,
       "-t", str(seconds), "-af", "volume=-24dB", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
       "-movflags", "+faststart", path)


def write(path, text, mode="w"):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, mode, **({} if "b" in mode else {"encoding": "utf-8"})) as fh:
        fh.write(text)


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def script_cmd(name, *args):
    return [sys.executable, "-I", os.path.join(SCRIPTS, name), *args]


def valid_format(**over):
    """A hand-made format.json (no media needed) with three beats."""
    fmt = {
        "format_version": 1, "duration_s": 30.0, "width": 1080, "height": 1920, "orientation": "portrait",
        "fps": 30.0, "speech_span_s": 28.0, "first_word_at_s": 0.4, "word_count": 100, "wpm": 214.3,
        "speech_share": 0.93, "cut_count": 6, "cuts_per_10s": 2.0, "mean_shot_s": 4.29,
        "scene_threshold": 0.3, "cut_times_s": [4.0, 8.0, 12.0, 16.0, 20.0, 24.0],
        "hook": {"type": "question", "type_source": "rules", "seconds": 4.0},
        "beats": [
            {"label": "hook", "start_s": 0.4, "end_s": 6.0, "share": 0.2, "words": 20},
            {"label": "point_1", "start_s": 6.0, "end_s": 22.8, "share": 0.6, "words": 60},
            {"label": "cta", "start_s": 22.8, "end_s": 28.4, "share": 0.2, "words": 20},
        ],
        "structure": "hook, 1 point, cta",
    }
    fmt.update(over)
    if "cut_times_s" not in over:     # keep the cut list inside a shorter clip
        fmt["cut_times_s"] = [c for c in fmt["cut_times_s"] if c < fmt["duration_s"]]
        fmt.setdefault("cut_count", None)
        if "cut_count" not in over:
            fmt["cut_count"] = len(fmt["cut_times_s"])
    return fmt


class WorkDir(unittest.TestCase):
    """A fresh work folder (real path) and a sibling folder that scripts must never write to."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="insp-")
        self.addCleanup(self._tmp.cleanup)
        base = os.path.realpath(self._tmp.name)
        self.work = os.path.join(base, "work")
        self.outside = os.path.join(base, "outside")
        os.makedirs(self.work)
        os.makedirs(self.outside)

    def p(self, *parts):
        return os.path.join(self.work, *parts)

    def run_script(self, name, *args, cwd=None):
        r = subprocess.run(script_cmd(name, *args), cwd=cwd or self.work, capture_output=True, text=True, timeout=600)
        self.assertNotIn("Traceback", r.stdout + r.stderr)
        return r

    def need_ffmpeg(self):
        if not FFMPEG:
            self.skipTest("ffmpeg and ffprobe are not installed")


def read_bytes(path):
    with open(path, "rb") as fh:
        return fh.read()
