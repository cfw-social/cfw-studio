"""Tests for b-qa-gate. They need ffmpeg and ffprobe, no account and no private file.

Run from the repository root:
    python3 -m unittest discover -s blocks/b-qa-gate/test -v
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock

HERE = os.path.dirname(os.path.abspath(__file__))
CHECK = os.path.join(os.path.dirname(HERE), "check.py")
FF = ["ffmpeg", "-v", "error", "-y"]
X264 = ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"]
LOUD = "sine=f=1000:d={d},volume=2.43"          # about -14 LUFS


def put(path, text):
    with open(path, "w") as fh:
        fh.write(text)


def rb(path):
    with open(path, "rb") as fh:
        return fh.read()


def get(path):
    with open(path) as fh:
        return fh.read()


def ff(*args):
    subprocess.run([*FF, *args], check=True)


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
            raise unittest.SkipTest("ffmpeg and ffprobe are required")
        cls.work = os.path.realpath(tempfile.mkdtemp(prefix="qa-gate-test-"))
        cls.old = os.getcwd()
        os.chdir(cls.work)

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls.old)
        shutil.rmtree(cls.work, ignore_errors=True)

    def spec(self, checks, name="spec.json", **extra):
        path = os.path.join(self.work, name)
        with open(path, "w") as fh:
            json.dump({"recipe": "demo", "checks": checks, **extra}, fh)
        return name

    def run_check(self, kind, spec, inp, out="scorecard.json", extra=(), env=None, cwd=None):
        p = subprocess.run([sys.executable, "-I", CHECK, "--kind", kind, "--spec", spec,
                            "--input", inp, "--out", out, *extra],
                           cwd=cwd or self.work, capture_output=True, text=True, env=env)
        card = None
        path = os.path.join(cwd or self.work, out)
        if p.returncode in (0, 1, 4) and os.path.isfile(path):
            card = json.loads(get(path))
        return p, card

    @staticmethod
    def row(card, cid):
        return next(r for r in card["checks"] if r["id"] == cid)


class ReelTests(Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ff("-f", "lavfi", "-i", "testsrc2=s=1080x1920:r=30:d=3", "-f", "lavfi", "-i", LOUD.format(d=3),
           "-shortest", *X264, "-c:a", "aac", "good.mp4")
        ff("-f", "lavfi", "-i", "testsrc2=s=1080x1920:r=30:d=3", *X264, "silent.mp4")
        ff("-f", "lavfi", "-i", "color=black:s=1080x1920:r=30:d=3", "-f", "lavfi", "-i", LOUD.format(d=3),
           "-shortest", *X264, "-c:a", "aac", "black.mp4")
        ff("-f", "lavfi", "-i", "testsrc2=s=640x360:r=24:d=3", "-f", "lavfi", "-i", LOUD.format(d=3),
           "-shortest", *X264, "-c:a", "aac", "small24.mp4")
        # dark navy card with a white headline bar: a valid dark cover
        ff("-f", "lavfi", "-i", "color=c=0x101828:s=1080x1920:r=30:d=3,drawbox=x=100:y=800:w=880:h=300:color=white:t=fill",
           "-f", "lavfi", "-i", LOUD.format(d=3), "-shortest", *X264, "-c:a", "aac", "darkcard.mp4")
        # flat dark card, nothing on it
        ff("-f", "lavfi", "-i", "color=c=0x101828:s=1080x1920:r=30:d=3", "-f", "lavfi", "-i", LOUD.format(d=3),
           "-shortest", *X264, "-c:a", "aac", "flatdark.mp4")
        # first second black, then bright
        ff("-f", "lavfi", "-i", "color=black:s=320x240:r=30:d=1", "-f", "lavfi", "-i", "testsrc2=s=320x240:r=30:d=2",
           "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]", "-map", "[v]", *X264, "halfblack.mp4")

    def test_good_reel_passes_every_mechanical_check(self):
        s = self.spec([
            {"id": "gate", "type": "qa_gate", "format": "reel"},
            {"id": "dur", "type": "duration_window", "min_s": 2, "max_s": 4},
            {"id": "size", "type": "dims", "w": 1080, "h": 1920},
            {"id": "fps", "type": "fps", "expect": 30},
            {"id": "audio", "type": "audio_present"},
            {"id": "lufs", "type": "loudness", "target": -14, "tol": 1.5},
            {"id": "vol", "type": "mean_volume", "min_db": -32, "max_db": -8},
            {"id": "luma", "type": "luma_floor", "crop": "1080:1920:0:0", "floor": 16},
            {"id": "cover", "type": "contrast_floor", "crop": "1080:1920:0:0", "samples": [0]},
        ])
        p, card = self.run_check("reel", s, "good.mp4")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(card["verdict"], "PASS")
        self.assertEqual(card["counts"]["fail"], 0)
        self.assertEqual(card["frames"], [])
        ids = {r["id"] for r in card["checks"]}
        self.assertTrue({"gate.video", "gate.audio", "gate.size", "gate.fps", "gate.duration",
                         "gate.loudness", "gate.cover"} <= ids)

    def test_looks_are_listed_and_exit_is_4(self):
        s = self.spec([
            {"id": "size", "type": "dims", "w": 1080, "h": 1920},
            {"id": "text", "type": "perceptual", "desc": "(a) No text is clipped."},
        ])
        p, card = self.run_check("reel", s, "good.mp4")
        self.assertEqual(p.returncode, 4)
        self.assertEqual(card["verdict"], "PASS_WITH_LOOKS")
        row = self.row(card, "text")
        self.assertEqual((row["status"], row["question"]), ("LOOK", "(a) No text is clipped."))
        self.assertEqual(len(card["frames"]), 7)
        for f in card["frames"]:
            self.assertFalse(os.path.isabs(f))
            self.assertTrue(os.path.isfile(os.path.join(self.work, f)))

    def test_a_failure_beats_a_look(self):
        s = self.spec([{"id": "size", "type": "dims", "w": 10, "h": 10},
                       {"id": "text", "type": "perceptual", "desc": "q"}])
        p, card = self.run_check("reel", s, "good.mp4")
        self.assertEqual(p.returncode, 1)
        self.assertEqual(card["verdict"], "FAIL")

    def test_scorecard_has_no_absolute_path(self):
        s = self.spec([{"id": "text", "type": "perceptual", "desc": "q"},
                       {"id": "size", "type": "dims", "w": 1080, "h": 1920}])
        os.makedirs("sub", exist_ok=True)
        p, _ = self.run_check("reel", s, "good.mp4", out="sub/card.json")
        raw = get(os.path.join(self.work, "sub", "card.json"))
        self.assertNotIn(self.work, raw)
        self.assertEqual(json.loads(raw)["input"], "good.mp4")
        for f in json.loads(raw)["frames"]:
            self.assertTrue(f.startswith("sub/"))

    def test_silent_reel_fails_audio_checks(self):
        s = self.spec([{"id": "gate", "type": "qa_gate", "format": "reel"},
                       {"id": "audio", "type": "audio_present"},
                       {"id": "lufs", "type": "loudness"},
                       {"id": "vol", "type": "mean_volume", "min_db": -32, "max_db": -8}])
        p, card = self.run_check("reel", s, "silent.mp4")
        self.assertEqual(p.returncode, 1)
        for cid in ("gate.audio", "gate.loudness", "audio", "lufs", "vol"):
            self.assertEqual(self.row(card, cid)["status"], "FAIL", cid)
        self.assertEqual(self.row(card, "gate.size")["status"], "PASS")

    def test_wrong_size_and_fps_fail(self):
        s = self.spec([{"id": "gate", "type": "qa_gate", "format": "reel"}])
        p, card = self.run_check("reel", s, "small24.mp4")
        self.assertEqual(p.returncode, 1)
        self.assertEqual(self.row(card, "gate.size")["status"], "FAIL")
        self.assertIn("640x360", self.row(card, "gate.size")["detail"])
        self.assertEqual(self.row(card, "gate.fps")["status"], "FAIL")
        s = self.spec([{"id": "gate", "type": "qa_gate", "format": "reel", "expect_fps": 24}])
        _, card = self.run_check("reel", s, "small24.mp4")
        self.assertEqual(self.row(card, "gate.fps")["status"], "PASS")

    def test_loudness_outside_tolerance_fails(self):
        s = self.spec([{"id": "lufs", "type": "loudness", "target": -23, "tol": 1}])
        p, card = self.run_check("reel", s, "good.mp4")
        self.assertEqual(p.returncode, 1)
        self.assertIn("LUFS", self.row(card, "lufs")["detail"])

    def test_black_reel_fails_not_black_and_cover(self):
        s = self.spec([{"id": "luma", "type": "luma_floor", "crop": "1080:1920:0:0", "floor": 16},
                       {"id": "cover", "type": "contrast_floor", "crop": "1080:1920:0:0", "samples": [0]},
                       {"id": "gate", "type": "qa_gate"}])
        p, card = self.run_check("reel", s, "black.mp4")
        self.assertEqual(p.returncode, 1)
        for cid in ("luma", "cover", "gate.cover"):
            self.assertEqual(self.row(card, cid)["status"], "FAIL", cid)

    def test_dark_card_with_bright_headline_passes_cover_but_flat_dark_fails(self):
        s = self.spec([{"id": "cover", "type": "contrast_floor", "crop": "1080:1920:0:0", "samples": [0]}])
        p, card = self.run_check("reel", s, "darkcard.mp4")
        self.assertEqual(p.returncode, 0, p.stdout)
        p, card = self.run_check("reel", s, "flatdark.mp4")
        self.assertEqual(p.returncode, 1)

    def test_luma_floor_windows(self):
        w = {"crop": "320:240:0:0", "floor": 16, "samples": [0.9]}
        s = self.spec([{"id": "late", "type": "luma_floor_windows", "windows": [[1.2, 2.8]], **w},
                       {"id": "early", "type": "luma_floor_windows", "windows": [[0.1, 0.9]], **w},
                       {"id": "src", "type": "luma_floor_windows", "windows_from": ["plan.takeovers"], **w},
                       {"id": "len", "type": "luma_floor_windows", "windows": [[1.2, 2.8]],
                        "expected_duration_s": 9, **w},
                       {"id": "tol", "type": "luma_floor_windows", "windows": [[1.2, 2.8]],
                        "duration_tolerance_s": 0.5, **w}])
        p, card = self.run_check("reel", s, "halfblack.mp4")
        self.assertEqual(self.row(card, "late")["status"], "PASS", self.row(card, "late"))
        self.assertEqual(self.row(card, "early")["status"], "FAIL")
        self.assertIn("windows_from", self.row(card, "src")["detail"])
        self.assertEqual(self.row(card, "len")["status"], "FAIL")
        self.assertEqual(self.row(card, "tol")["status"], "FAIL")

    def test_spoken_duration_window_reads_a_script(self):
        put("script.md", "# Title\n" + " ".join(["word"] * 75) + "\n- - -\n")
        put("short.md", "only five words in here")
        s = self.spec([{"id": "spoken", "type": "spoken_duration_window", "min_s": 20, "max_s": 60, "wpm": 150}])
        p, card = self.run_check("reel", s, "script.md")
        self.assertEqual(p.returncode, 0, p.stdout)       # 76 words (title counts) = 30.4 s
        p, card = self.run_check("reel", s, "short.md")
        self.assertEqual(p.returncode, 1)
        self.assertIn("5 words", self.row(card, "spoken")["detail"])
        p, card = self.run_check("reel", s, "good.mp4")   # not text
        self.assertEqual(p.returncode, 1)

    def test_windows_from_reads_files_inside_the_work_folder(self):
        os.makedirs("saves", exist_ok=True)
        put("saves/edit_plan.json", json.dumps({"takeovers": [{"start": 1.2, "end": 2.8, "template": "x"}]}))
        put("beat_list.json", json.dumps({"beats": [{"kind": "graphics", "start": 0.1, "end": 0.9},
                                                     {"kind": "broll", "start": 1.3, "end": 2.5}]}))
        w = {"crop": "320:240:0:0", "floor": 16, "samples": [0.9]}
        s = self.spec([
            {"id": "ok", "type": "luma_floor_windows", "windows_from": ["edit_plan.takeovers", "beat_list.broll"], **w},
            {"id": "mixed", "type": "luma_floor_windows", "windows": [[0.1, 0.9]], "windows_from": ["edit_plan.takeovers"], **w},
            {"id": "nofile", "type": "luma_floor_windows", "windows_from": ["nothere.takeovers"], **w},
            {"id": "nokey", "type": "luma_floor_windows", "windows_from": ["edit_plan.beats"], **w},
            {"id": "badname", "type": "luma_floor_windows", "windows_from": ["../x.takeovers"], **w},
            {"id": "badref", "type": "luma_floor_windows", "windows_from": ["edit_plan"], **w},
        ])
        p, card = self.run_check("reel", s, "halfblack.mp4")
        self.assertEqual(self.row(card, "ok")["status"], "PASS", self.row(card, "ok"))
        self.assertEqual(self.row(card, "mixed")["status"], "FAIL")
        for cid in ("nofile", "nokey", "badname", "badref"):
            self.assertEqual(self.row(card, cid)["status"], "FAIL", cid)
        put("saves/edit_plan.json", json.dumps({"takeovers": [{"start": "1", "end": 2}]}))
        s = self.spec([{"id": "str", "type": "luma_floor_windows", "windows_from": ["edit_plan.takeovers"], **w}])
        p, card = self.run_check("reel", s, "halfblack.mp4")
        self.assertEqual(self.row(card, "str")["status"], "FAIL")

    def test_windows_from_refuses_files_outside_the_work_folder(self):
        outside = tempfile.mkdtemp()
        try:
            put(os.path.join(outside, "edit_plan.json"), json.dumps({"takeovers": [{"start": 1.2, "end": 2.8}]}))
            if os.path.lexists("prior"):
                os.unlink("prior")
            os.symlink(outside, "prior")
            for f in ("edit_plan.json", os.path.join("saves", "edit_plan.json")):
                if os.path.exists(f):
                    os.unlink(f)
            s = self.spec([{"id": "out", "type": "luma_floor_windows", "windows_from": ["edit_plan.takeovers"],
                            "crop": "320:240:0:0", "samples": [0.9]}])
            p, card = self.run_check("reel", s, "halfblack.mp4")
            self.assertEqual(self.row(card, "out")["status"], "FAIL")
            self.assertIn("outside the work folder", self.row(card, "out")["detail"])
        finally:
            os.unlink("prior")
            shutil.rmtree(outside, ignore_errors=True)

    def test_json_array_nonempty(self):
        put("sources.json", json.dumps([{"title": "a", "url": "https://example.com"}]))
        put("empty.json", "[]")
        put("obj.json", "{}")
        put("blank.json", json.dumps([{"title": "a", "url": " "}]))
        s = self.spec([{"id": "src", "type": "json_array_nonempty", "min_items": 1, "item_keys": ["title", "url"]}])
        self.assertEqual(self.run_check("reel", s, "sources.json")[0].returncode, 0)
        for f in ("empty.json", "obj.json", "blank.json", "script.md"):
            put("script.md", "not json")
            self.assertEqual(self.run_check("reel", s, f)[0].returncode, 1, f)

    def test_json_words_nonempty(self):
        def words(*pairs):
            return json.dumps({"words": [{"text": "w", "start": a, "end": b} for a, b in pairs]})
        put("w_ok.json", words((0, 0.4), (0.5, 0.9), (1.0, 1.4)))
        put("w_back.json", words((0, 0.4), (1.0, 1.4), (0.5, 0.9)))
        put("w_empty.json", words())
        put("w_text.json", json.dumps({"words": [{"start": 0, "end": 1}]}))
        put("w_str.json", json.dumps({"words": [{"text": "a", "start": "0", "end": 1}]}))
        s = self.spec([{"id": "w", "type": "json_words_nonempty", "min_items": 1, "path": "words"}])
        self.assertEqual(self.run_check("reel", s, "w_ok.json")[0].returncode, 0)
        for f in ("w_back.json", "w_empty.json", "w_text.json", "w_str.json"):
            self.assertEqual(self.run_check("reel", s, f)[0].returncode, 1, f)
        s = self.spec([{"id": "w", "type": "json_words_nonempty", "expected_duration_s": 4.5, "tail_tolerance_s": 4.5}])
        self.assertEqual(self.run_check("reel", s, "w_ok.json")[0].returncode, 0)
        s = self.spec([{"id": "w", "type": "json_words_nonempty", "expected_duration_s": 9, "tail_tolerance_s": 4.5}])
        self.assertEqual(self.run_check("reel", s, "w_ok.json")[0].returncode, 1)
        s = self.spec([{"id": "w", "type": "json_words_nonempty", "tail_tolerance_s": 4.5}])
        self.assertEqual(self.run_check("reel", s, "w_ok.json")[0].returncode, 1)

    def test_json_words_bare_array(self):
        def arr(*pairs):
            return json.dumps([{"text": "w", "start": a, "end": b} for a, b in pairs])
        put("a_ok.json", arr((0, 0.4), (0.5, 0.9)))
        put("a_empty.json", arr())
        put("a_bad_text.json", json.dumps([{"text": "a", "start": 0, "end": 1}, {"start": 1, "end": 2}]))
        put("a_bad_num.json", json.dumps([{"text": "a", "start": 0, "end": "1"}]))
        put("a_back.json", arr((0, 0.4), (1.0, 1.4), (0.5, 0.9)))
        s = self.spec([{"id": "w", "type": "json_words_nonempty"}])
        self.assertEqual(self.run_check("reel", s, "a_ok.json")[0].returncode, 0)
        for f in ("a_empty.json", "a_bad_text.json", "a_bad_num.json", "a_back.json"):
            self.assertEqual(self.run_check("reel", s, f)[0].returncode, 1, f)
        # an object without the list is still refused
        put("o_none.json", json.dumps({"other": []}))
        self.assertEqual(self.run_check("reel", s, "o_none.json")[0].returncode, 1)

    def test_step_checks(self):
        path = os.path.join(self.work, "stepspec.json")
        put(path, json.dumps({"recipe": "demo", "checks": [{"id": "x", "type": "dims", "w": 1, "h": 1}],
                              "steps": {"bed": {"checks": [{"id": "bed_audio", "type": "audio_present"}]}}}))
        p, card = self.run_check("reel", "stepspec.json", "good.mp4", extra=["--step", "bed"])
        self.assertEqual(p.returncode, 0)
        self.assertEqual(card["step"], "bed")
        self.assertEqual([r["id"] for r in card["checks"]], ["bed_audio"])
        p, _ = self.run_check("reel", "stepspec.json", "good.mp4", extra=["--step", "nope"])
        self.assertEqual(p.returncode, 2)


class StrictTests(Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ff("-f", "lavfi", "-i", "testsrc2=s=320x240:r=30:d=1", *X264, "v.mp4")

    def test_unknown_kinds_fail_and_are_named(self):
        s = self.spec([{"id": "a", "type": "custom", "script": "x.sh"},
                       {"id": "b", "type": "spotlight_plan_guard"},
                       {"id": "c", "type": "spotlight_beats_guard"},
                       {"id": "d"},
                       "not an object"])
        for kind in ("reel", "image"):
            p, card = self.run_check(kind, s, "v.mp4")
            self.assertEqual(p.returncode, 1)
            self.assertEqual(card["counts"]["pass"], 0)
            self.assertIn("'custom'", self.row(card, "a")["detail"])
            self.assertIn("'spotlight_plan_guard'", self.row(card, "b")["detail"])
            self.assertIn("'spotlight_beats_guard'", self.row(card, "c")["detail"])
            self.assertEqual(self.row(card, "d")["status"], "FAIL")
            self.assertEqual(self.row(card, "check-5")["status"], "FAIL")

    def test_a_kind_from_the_other_entry_is_refused(self):
        s = self.spec([{"id": "a", "type": "duration_window", "min_s": 0, "max_s": 9},
                       {"id": "b", "type": "aspect_ratio", "w": 4, "h": 3}])
        p, card = self.run_check("image", s, "v.mp4")
        self.assertEqual(self.row(card, "a")["status"], "FAIL")
        self.assertIn("--kind image", self.row(card, "a")["detail"])
        self.assertEqual(self.row(card, "b")["status"], "PASS")
        p, card = self.run_check("reel", s, "v.mp4")
        self.assertIn("--kind reel", self.row(card, "b")["detail"])

    def test_bad_numbers_never_reach_a_tool(self):
        s = self.spec([
            {"id": "a", "type": "duration_window", "min_s": "1;rm -rf x", "max_s": 9},
            {"id": "b", "type": "dims", "w": True, "h": 240},
            {"id": "c", "type": "dims", "w": 320.5, "h": 240},
            {"id": "d", "type": "loudness", "target": "-14"},
            {"id": "e", "type": "luma_floor", "crop": "320:240:0:0;touch pwned", "floor": 16},
            {"id": "f", "type": "luma_floor", "crop": "320:240:0:0", "floor": 16, "samples": [2]},
            {"id": "g", "type": "fps", "expect": 1e999},
            {"id": "h", "type": "luma_floor", "crop": "0:0:0:0"},
        ])
        p, card = self.run_check("reel", s, "v.mp4")
        self.assertEqual(p.returncode, 1)
        for cid in "abcdefgh":
            self.assertEqual(self.row(card, cid)["status"], "FAIL", cid)
        self.assertFalse(os.path.exists(os.path.join(self.work, "pwned")))

    def test_missing_tools_fail(self):
        empty = tempfile.mkdtemp(dir=self.work)
        s = self.spec([{"id": "size", "type": "dims", "w": 320, "h": 240},
                       {"id": "q", "type": "perceptual", "desc": "look"}])
        env = {"PATH": empty}
        p, card = self.run_check("reel", s, "v.mp4", env=env)
        self.assertEqual(p.returncode, 1)
        self.assertEqual(self.row(card, "tools")["status"], "FAIL")
        self.assertIn("ffmpeg", self.row(card, "tools")["detail"])
        self.assertEqual(self.row(card, "size")["status"], "FAIL")

    def test_usage_errors_exit_2(self):
        s = self.spec([{"id": "size", "type": "dims", "w": 320, "h": 240}])
        outside = tempfile.mkdtemp()
        try:
            shutil.copy("v.mp4", os.path.join(outside, "v.mp4"))
            cases = [
                ("input outside the work folder", ("reel", s, os.path.join(outside, "v.mp4"), "c.json")),
                ("output outside the work folder", ("reel", s, "v.mp4", os.path.join(outside, "c.json"))),
                ("output through ..", ("reel", s, "v.mp4", "../c.json")),
                ("missing input", ("reel", s, "none.mp4", "c.json")),
                ("missing spec", ("reel", "none.json", "v.mp4", "c.json")),
                ("output is the work folder", ("reel", s, "v.mp4", ".")),
            ]
            for label, (k, sp, i, o) in cases:
                p, _ = self.run_check(k, sp, i, out=o)
                self.assertEqual(p.returncode, 2, label)
            put("empty.json", '{"checks": []}')
            put("bad.json", "{nope")
            p, _ = self.run_check("reel", "empty.json", "v.mp4")
            self.assertEqual(p.returncode, 2)
            p, _ = self.run_check("reel", "bad.json", "v.mp4")
            self.assertEqual(p.returncode, 2)
            p, _ = self.run_check("video", s, "v.mp4")
            self.assertEqual(p.returncode, 2)
            self.assertFalse(os.path.exists(os.path.join(outside, "c.json")))
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_symlink_out_of_the_work_folder_is_refused(self):
        outside = tempfile.mkdtemp()
        try:
            os.symlink(os.path.join(outside, "v.mp4"), "link.mp4")
            shutil.copy("v.mp4", os.path.join(outside, "v.mp4"))
            s = self.spec([{"id": "size", "type": "dims", "w": 320, "h": 240}])
            p, _ = self.run_check("reel", s, "link.mp4")
            self.assertEqual(p.returncode, 2)
        finally:
            os.unlink("link.mp4")
            shutil.rmtree(outside, ignore_errors=True)


class ImageTests(Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ff("-f", "lavfi", "-i", "testsrc2=s=1080x1350", "-frames:v", "1", "good.png")
        ff("-f", "lavfi", "-i", "testsrc2=s=2160x2700", "-frames:v", "1", "retina.png")
        ff("-f", "lavfi", "-i", "color=black:s=1080x1350", "-frames:v", "1", "black.png")
        ff("-f", "lavfi", "-i", "color=c=0x808080:s=1080x1350", "-frames:v", "1", "flat.png")
        ff("-f", "lavfi", "-i", "testsrc2=s=1080x1080", "-frames:v", "1", "square.png")
        ff("-f", "lavfi", "-i", "color=black:s=1080x1350,drawbox=x=0:y=0:w=1080:h=100:color=white:t=fill",
           "-frames:v", "1", "bar.png")
        ff("-f", "lavfi", "-i", "testsrc2=s=1080x1350", "-frames:v", "1", "good.jpg")

    SPEC = [
        {"id": "size", "type": "dims", "w": 1080, "h": 1350},
        {"id": "ratio", "type": "aspect_ratio", "w": 1080, "h": 1350},
        {"id": "luma", "type": "luma_floor", "crop": "1080:1350:0:0", "floor": 16, "samples": [0.5]},
        {"id": "flat", "type": "not_flat", "min_range": 32},
    ]

    def test_good_image_passes(self):
        for name in ("good.png", "good.jpg"):
            p, card = self.run_check("image", self.spec(self.SPEC), name)
            self.assertEqual(p.returncode, 0, p.stdout)
            self.assertEqual(card["frames"], [])
            self.assertEqual(card["input"], name)

    def test_black_image_fails_not_black(self):
        p, card = self.run_check("image", self.spec(self.SPEC), "black.png")
        self.assertEqual(p.returncode, 1)
        self.assertEqual(self.row(card, "luma")["status"], "FAIL")
        self.assertEqual(self.row(card, "flat")["status"], "FAIL")

    def test_flat_image_fails_not_flat_but_is_not_black(self):
        p, card = self.run_check("image", self.spec(self.SPEC), "flat.png")
        self.assertEqual(p.returncode, 1)
        self.assertEqual(self.row(card, "luma")["status"], "PASS")
        self.assertEqual(self.row(card, "flat")["status"], "FAIL")

    def test_mostly_blank_image_with_one_bar_is_not_flat(self):
        p, card = self.run_check("image", self.spec(self.SPEC[3:]), "bar.png")
        self.assertEqual(p.returncode, 0, p.stdout)

    def test_ratio_and_size(self):
        p, card = self.run_check("image", self.spec(self.SPEC), "square.png")
        self.assertEqual(self.row(card, "size")["status"], "FAIL")
        self.assertEqual(self.row(card, "ratio")["status"], "FAIL")
        p, card = self.run_check("image", self.spec(self.SPEC), "retina.png")   # 2x: ratio ok, exact size not
        self.assertEqual(self.row(card, "ratio")["status"], "PASS")
        self.assertEqual(self.row(card, "size")["status"], "FAIL")
        s = self.spec([{"id": "min", "type": "aspect_ratio", "w": 4, "h": 5, "min_w": 1080}])
        p, card = self.run_check("image", s, "retina.png")
        self.assertEqual(p.returncode, 0)
        s = self.spec([{"id": "min", "type": "aspect_ratio", "w": 4, "h": 5, "min_w": 4000}])
        p, card = self.run_check("image", s, "retina.png")
        self.assertEqual(p.returncode, 1)

    def test_image_looks_exit_4_without_frames(self):
        s = self.spec([{"id": "size", "type": "dims", "w": 1080, "h": 1350},
                       {"id": "q", "type": "perceptual", "desc": "(a) Text fits."}])
        p, card = self.run_check("image", s, "good.png")
        self.assertEqual(p.returncode, 4)
        self.assertEqual(card["frames"], [])

    def test_not_an_image_fails(self):
        put("notimg.png", "hello")
        p, card = self.run_check("image", self.spec(self.SPEC[:1]), "notimg.png")
        self.assertEqual(p.returncode, 1)


class FinalizeTests(Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ff("-f", "lavfi", "-i", "testsrc2=s=1080x1350", "-frames:v", "1", "good.png")
        ff("-f", "lavfi", "-i", "color=black:s=1080x1350", "-frames:v", "1", "black.png")
        cls.looks = [{"id": "size", "type": "dims", "w": 1080, "h": 1350},
                     {"id": "q1", "type": "perceptual", "desc": "(a) one"},
                     {"id": "q2", "type": "perceptual", "desc": "(b) two"}]

    def card(self, image="good.png", name="card.json"):
        p, _ = self.run_check("image", self.spec(self.looks, name="fspec.json"), image, out=name)
        return name, p.returncode

    def finalize(self, card, answers, out="final.json"):
        put("answers.json", json.dumps(answers))
        p = subprocess.run([sys.executable, "-I", CHECK, "--finalize", card, "--answers", "answers.json", "--out", out],
                           cwd=self.work, capture_output=True, text=True)
        final = json.loads(get(os.path.join(self.work, out))) if p.returncode in (0, 1) else None
        return p, final

    def test_all_yes_gives_pass(self):
        card, rc = self.card()
        self.assertEqual(rc, 4)
        p, final = self.finalize(card, {"q1": {"answer": "yes", "note": "fits"}, "q2": {"answer": "yes"}})
        self.assertEqual(p.returncode, 0, p.stdout)
        self.assertEqual(final["verdict"], "PASS")
        self.assertTrue(final["finalized"])
        self.assertEqual(final["counts"], {"pass": 4, "fail": 0, "look": 0})
        row = self.row(final, "q1")
        self.assertEqual((row["status"], row["answer"], row["note"], row["question"]), ("PASS", "yes", "fits", "(a) one"))
        self.assertNotIn(self.work, json.dumps(final))

    def test_a_no_fails(self):
        card, _ = self.card()
        p, final = self.finalize(card, {"q1": {"answer": "yes"}, "q2": {"answer": "no", "note": "text clipped"}})
        self.assertEqual(p.returncode, 1)
        self.assertEqual(final["verdict"], "FAIL")
        self.assertIn("text clipped", self.row(final, "q2")["detail"])

    def test_a_missing_answer_fails(self):
        card, _ = self.card()
        p, final = self.finalize(card, {"q1": {"answer": "yes"}})
        self.assertEqual(p.returncode, 1)
        self.assertEqual(self.row(final, "q2")["status"], "FAIL")
        self.assertIn("no answer", self.row(final, "q2")["detail"])

    def test_bad_answers_fail(self):
        card, _ = self.card()
        for bad in ({"answer": "maybe"}, "yes", {"answer": True}, {"answer": "yes", "note": 5}):
            p, final = self.finalize(card, {"q1": bad, "q2": {"answer": "yes"}})
            self.assertEqual(p.returncode, 1, bad)
            self.assertEqual(self.row(final, "q1")["status"], "FAIL", bad)

    def test_an_answer_for_an_unknown_id_fails_and_is_named(self):
        card, _ = self.card()
        p, final = self.finalize(card, {"q1": {"answer": "yes"}, "q2": {"answer": "yes"},
                                        "size": {"answer": "yes"}, "ghost": {"answer": "yes"}})
        self.assertEqual(p.returncode, 1)
        self.assertEqual(final["verdict"], "FAIL")
        details = [r for r in final["checks"] if r["type"] == "answer"]
        self.assertEqual(sorted(r["id"] for r in details), ["answer:ghost", "answer:size"])

    def test_a_failed_scorecard_cannot_become_pass(self):
        card, rc = self.card("black.png", "failed.json")
        put("fspec2.json", json.dumps({"checks": [{"id": "size", "type": "dims", "w": 1, "h": 1},
                                                   {"id": "q1", "type": "perceptual", "desc": "x"}]}))
        p, _ = self.run_check("image", "fspec2.json", "good.png", out="failed.json")
        self.assertEqual(p.returncode, 1)
        p, final = self.finalize("failed.json", {"q1": {"answer": "yes"}})
        self.assertEqual(p.returncode, 1)
        self.assertEqual(final["verdict"], "FAIL")
        self.assertEqual(self.row(final, "size")["status"], "FAIL")

    def test_notes_are_plain_and_capped(self):
        card, _ = self.card()
        p, final = self.finalize(card, {"q1": {"answer": "yes", "note": "<b>x</b>\x07" + "y" * 900},
                                        "q2": {"answer": "yes"}})
        note = self.row(final, "q1")["note"]
        self.assertEqual(len(note), 500)
        self.assertNotIn("\x07", note)
        self.assertTrue(note.startswith("<b>x</b>"))

    def test_paths_must_be_inside_the_work_folder_and_no_double_finalize(self):
        card, _ = self.card()
        outside = tempfile.mkdtemp()
        try:
            put("answers.json", "{}")
            for args in (["--finalize", card, "--answers", "answers.json", "--out", os.path.join(outside, "f.json")],
                         ["--finalize", card, "--answers", "answers.json", "--out", "../f.json"],
                         ["--finalize", os.path.join(outside, "c.json"), "--answers", "answers.json", "--out", "f.json"],
                         ["--finalize", card, "--answers", os.path.join(outside, "a.json"), "--out", "f.json"],
                         ["--finalize", card, "--out", "f.json"],
                         ["--finalize", card, "--answers", "answers.json", "--out", "f.json", "--kind", "image"],
                         ["--answers", "answers.json"]):
                p = subprocess.run([sys.executable, "-I", CHECK, *args], cwd=self.work, capture_output=True, text=True)
                self.assertEqual(p.returncode, 2, args)
            self.assertFalse(os.path.exists(os.path.join(outside, "f.json")))
            p, final = self.finalize(card, {"q1": {"answer": "yes"}, "q2": {"answer": "yes"}}, out="done.json")
            self.assertEqual(p.returncode, 0)
            p = subprocess.run([sys.executable, "-I", CHECK, "--finalize", "done.json", "--answers", "answers.json",
                                "--out", "again.json"], cwd=self.work, capture_output=True, text=True)
            self.assertEqual(p.returncode, 2)
        finally:
            shutil.rmtree(outside, ignore_errors=True)


class ReviewFixTests(Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ff("-f", "lavfi", "-i", "testsrc2=s=1080x1350", "-frames:v", "1", "good.png")
        ff("-f", "lavfi", "-i", "testsrc2=s=64x64", "-frames:v", "1", "tiny.png")
        ff("-f", "lavfi", "-i", "testsrc2=s=320x240:r=30:d=1", *X264, "v.mp4")

    def cli(self, *args):
        return subprocess.run([sys.executable, "-I", CHECK, *args], cwd=self.work, capture_output=True, text=True)

    def test_swapped_input_fails_at_finalize(self):
        s = self.spec([{"id": "q", "type": "perceptual", "desc": "look"}], name="swap.json")
        shutil.copy("good.png", "swap.png")
        p, card = self.run_check("image", s, "swap.png", out="swap-card.json")
        self.assertEqual(p.returncode, 4)
        self.assertEqual(len(card["input_sha256"]), 64)
        self.assertEqual(card["input_bytes"], os.path.getsize("swap.png"))
        put("swap-ans.json", json.dumps({"q": {"answer": "yes"}}))
        args = ["--finalize", "swap-card.json", "--answers", "swap-ans.json", "--out", "swap-final.json"]
        self.assertEqual(self.cli(*args).returncode, 0)          # unchanged input: ok
        shutil.copy("tiny.png", "swap.png")                       # swap it
        p = self.cli(*args)
        self.assertEqual(p.returncode, 1)
        final = json.loads(get("swap-final.json"))
        self.assertEqual(final["verdict"], "FAIL")
        self.assertEqual(self.row(final, "input_unchanged")["status"], "FAIL")
        self.assertIn("changed", self.row(final, "input_unchanged")["detail"])

    def test_missing_input_fails_at_finalize(self):
        s = self.spec([{"id": "q", "type": "perceptual", "desc": "look"}], name="miss.json")
        shutil.copy("good.png", "miss.png")
        self.run_check("image", s, "miss.png", out="miss-card.json")
        os.unlink("miss.png")
        put("miss-ans.json", json.dumps({"q": {"answer": "yes"}}))
        p = self.cli("--finalize", "miss-card.json", "--answers", "miss-ans.json", "--out", "miss-final.json")
        self.assertEqual(p.returncode, 1)
        self.assertIn("missing", self.row(json.loads(get("miss-final.json")), "input_unchanged")["detail"])

    def test_scorecard_without_a_hash_cannot_pass(self):
        s = self.spec([{"id": "q", "type": "perceptual", "desc": "look"}], name="nh.json")
        shutil.copy("good.png", "nh.png")
        self.run_check("image", s, "nh.png", out="nh-card.json")
        card = json.loads(get("nh-card.json"))
        del card["input_sha256"]
        put("nh-card.json", json.dumps(card))
        put("nh-ans.json", json.dumps({"q": {"answer": "yes"}}))
        p = self.cli("--finalize", "nh-card.json", "--answers", "nh-ans.json", "--out", "nh-final.json")
        self.assertEqual(p.returncode, 1)

    def test_huge_integers_are_a_clean_fail(self):
        big = 10 ** 300
        s = self.spec([
            {"id": "a", "type": "luma_floor_windows", "windows": [[0, big]], "crop": "320:240:0:0"},
            {"id": "b", "type": "dims", "w": big, "h": 240},
            {"id": "c", "type": "luma_floor", "crop": "320:240:0:0", "samples": [big]},
            {"id": "d", "type": "duration_window", "min_s": -big},
            {"id": "e", "type": "luma_floor_windows", "windows": [{"start": 0, "end": big}], "crop": "320:240:0:0"},
        ])
        p, card = self.run_check("reel", s, "v.mp4")
        self.assertEqual(p.returncode, 1, p.stderr)
        self.assertNotIn("Traceback", p.stderr)
        for cid in "abcde":
            self.assertEqual(self.row(card, cid)["status"], "FAIL", cid)
        put("hw.json", json.dumps({"words": [{"text": "a", "start": 0, "end": big}]}))
        s = self.spec([{"id": "w", "type": "json_words_nonempty"}])
        p, card = self.run_check("reel", s, "hw.json")
        self.assertEqual(p.returncode, 1)
        self.assertNotIn("Traceback", p.stderr)

    def test_deeply_nested_spec_never_gives_a_traceback(self):
        put("deep.json", "[" * 200000 + "]" * 200000)
        p, _ = self.run_check("reel", "deep.json", "v.mp4")
        self.assertEqual(p.returncode, 2)
        self.assertNotIn("Traceback", p.stderr)
        nest = "[" * 400 + "]" * 400
        put("deep2.json", '{"checks": [{"id": "a", "type": "dims", "w": %s, "h": 1}]}' % nest)
        p, card = self.run_check("reel", "deep2.json", "v.mp4")
        self.assertEqual(p.returncode, 1)
        self.assertEqual(self.row(card, "a")["status"], "FAIL")
        put("deep.json", "[" * 200000 + "]" * 200000)
        p, _ = self.run_check("reel", "deep.json", "deep.json")   # a nested JSON input is a clean fail too
        self.assertNotIn("Traceback", p.stderr)

    def test_unexpected_error_in_a_check_is_a_fail_row(self):
        spec = importlib.util.spec_from_file_location("qa_check", CHECK)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        def boom(ctx, c):
            raise RuntimeError("x")
        mod.KINDS["reel"]["boom"] = boom
        ctx = mod.Ctx("reel", mod.Tools(), os.path.join(self.work, "v.mp4"), self.work)
        rows = mod.run_checks(ctx, [{"id": "b", "type": "boom"}], ctx.tools)
        self.assertEqual(rows[-1]["status"], "FAIL")
        self.assertIn("RuntimeError", rows[-1]["detail"])

    def test_stale_scorecard_is_removed_before_a_run(self):
        put("stale.json", '{"scorecard_version": 1, "verdict": "PASS"}')
        p = self.cli("--kind", "reel", "--spec", "nope.json", "--input", "v.mp4", "--out", "stale.json")
        self.assertEqual(p.returncode, 2)
        self.assertFalse(os.path.exists("stale.json"))
        put("stale.json", '{"scorecard_version": 1, "verdict": "PASS"}')
        put("a.json", "{}")
        p = self.cli("--finalize", "nothere.json", "--answers", "a.json", "--out", "stale.json")
        self.assertEqual(p.returncode, 2)
        self.assertFalse(os.path.exists("stale.json"))

    def test_symlinked_frames_folder_is_refused(self):
        outside = tempfile.mkdtemp()
        try:
            os.symlink(outside, "fr-frames")
            s = self.spec([{"id": "q", "type": "perceptual", "desc": "look"}], name="fr.json")
            p, card = self.run_check("reel", s, "v.mp4", out="fr.json.out")  # frames folder: fr.json-frames
            os.unlink("fr-frames")
            os.symlink(outside, "fr2-frames")
            p, card = self.run_check("reel", s, "v.mp4", out="fr2.json")
            self.assertEqual(p.returncode, 1)
            self.assertEqual(self.row(card, "frames")["status"], "FAIL")
            self.assertEqual(card["frames"], [])
            self.assertEqual(os.listdir(outside), [])
            # a planted symlink for one frame file inside a real folder
            os.unlink("fr2-frames")
            os.makedirs("fr3-frames")
            target = os.path.join(outside, "victim.png")
            put(target, "keep")
            os.symlink(target, os.path.join("fr3-frames", "frame-00.png"))
            p, card = self.run_check("reel", s, "v.mp4", out="fr3.json")
            self.assertEqual(get(target), "keep")
            self.assertEqual(p.returncode, 4)
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_out_cannot_be_an_input_spec_or_answer_file(self):
        before = os.path.getsize("v.mp4")
        s = self.spec([{"id": "d", "type": "dims", "w": 320, "h": 240}], name="oi.json")
        self.assertEqual(self.cli("--kind", "reel", "--spec", s, "--input", "v.mp4", "--out", "v.mp4").returncode, 2)
        self.assertEqual(os.path.getsize("v.mp4"), before)
        self.assertEqual(self.cli("--kind", "reel", "--spec", s, "--input", "v.mp4", "--out", s).returncode, 2)
        self.assertEqual(json.loads(get(s))["recipe"], "demo")
        put("oa.json", json.dumps({}))
        p, _ = self.run_check("image", self.spec([{"id": "q", "type": "perceptual", "desc": "x"}], name="oq.json"),
                              "good.png", out="oc.json")
        for out in ("oc.json", "oa.json"):
            self.assertEqual(self.cli("--finalize", "oc.json", "--answers", "oa.json", "--out", out).returncode, 2, out)
        self.assertTrue(os.path.exists("oc.json"))

    def test_every_tool_call_is_limited_to_the_file_protocol(self):
        spec = importlib.util.spec_from_file_location("qa_check2", CHECK)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        seen = []

        class R:
            returncode, stdout, stderr = 0, b"", b""
        t = mod.Tools()
        with unittest.mock.patch.object(subprocess, "run", lambda argv, **kw: (seen.append(argv), R())[1]):
            t.run("ffprobe", ["-v", "error", "-i", "x"])
            t.run("ffmpeg", ["-i", "x", "-frames:v", "1", "out.png"])
        self.assertEqual(len(seen), 2)
        for argv in seen:
            i = argv.index("-i")
            self.assertEqual(argv[i - 2:i], ["-protocol_whitelist", "file"])


class FinalizeOverwriteTests(Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ff("-f", "lavfi", "-i", "testsrc2=s=64x64:r=30:d=1", *X264, "in.mp4")
        ff("-f", "lavfi", "-i", "testsrc2=s=64x64", "-frames:v", "1", "img.png")

    def cli(self, *args):
        return subprocess.run([sys.executable, "-I", CHECK, *args], cwd=self.work, capture_output=True, text=True)

    def make(self, tag="x", cid="q"):
        spec = self.spec([{"id": cid, "type": "perceptual", "desc": "look"}], name=f"{tag}-spec.json")
        shutil.copy("in.mp4", f"{tag}-in.mp4")
        p, _ = self.run_check("reel", spec, f"{tag}-in.mp4", out=f"{tag}-card.json")
        self.assertEqual(p.returncode, 4, p.stderr)
        put(f"{tag}-ans.json", json.dumps({cid: {"answer": "yes"}}))
        return spec, f"{tag}-in.mp4", f"{tag}-card.json", f"{tag}-ans.json"

    def test_finalize_never_overwrites_its_inputs(self):
        spec, inp, card, ans = self.make("fo")
        snap = {f: rb(f) for f in (spec, inp, card, ans)}
        for victim in (inp, spec, card, ans):
            p = self.cli("--finalize", card, "--answers", ans, "--out", victim)
            self.assertEqual(p.returncode, 2, victim)
            self.assertNotIn("Traceback", p.stderr)
        for f, data in snap.items():
            self.assertEqual(rb(f), data, f)     # byte for byte

    def test_finalize_refuses_the_recorded_spec_name(self):
        spec, inp, card, ans = self.make("sn")
        os.makedirs("elsewhere", exist_ok=True)
        put(os.path.join("elsewhere", spec), "keep")
        p = self.cli("--finalize", card, "--answers", ans, "--out", os.path.join("elsewhere", spec))
        self.assertEqual(p.returncode, 2)
        self.assertEqual(get(os.path.join("elsewhere", spec)), "keep")

    def test_an_unrelated_existing_file_is_never_overwritten(self):
        spec, inp, card, ans = self.make("un")
        for name, text in (("other.txt", "hello"), ("other.json", '{"a": 1}'), ("broken.json", "{nope")):
            put(name, text)
            p = self.cli("--finalize", card, "--answers", ans, "--out", name)
            self.assertEqual(p.returncode, 2, name)
            p = self.cli("--kind", "reel", "--spec", spec, "--input", inp, "--out", name)
            self.assertEqual(p.returncode, 2, name)
            self.assertEqual(get(name), text)
        put("old.json", '{"scorecard_version": 1, "verdict": "PASS"}')      # an old scorecard may be replaced
        self.assertEqual(self.cli("--finalize", card, "--answers", ans, "--out", "old.json").returncode, 0)
        self.assertEqual(json.loads(get("old.json"))["finalized"], True)

    def test_a_refusal_leaves_a_previous_scorecard_alone(self):
        spec, inp, card, ans = self.make("pr")
        before = get(card)
        self.assertEqual(self.cli("--finalize", card, "--answers", ans, "--out", inp).returncode, 2)
        self.assertEqual(get(card), before)
        self.assertTrue(os.path.exists(inp))

    def test_printed_text_cannot_forge_a_line(self):
        evil = "a\nFAIL forged: x\u2028y\u2029z\x85w\r"
        spec = self.spec([{"id": evil, "type": "dims", "w": 1, "h": 1}], name="ev-spec.json")
        p, _ = self.run_check("reel", spec, "in.mp4", out="ev-card.json")
        lines = p.stdout.splitlines()
        self.assertEqual(p.stdout.count("\n"), len(lines))
        self.assertFalse(any(l.startswith("FAIL forged") for l in lines))
        self.assertEqual(len([l for l in lines if l.startswith("FAIL")]), 1)
        for ch in ("\u2028", "\u2029", "\x85", "\r"):
            self.assertNotIn(ch, p.stdout)
        spec, inp, card, ans = self.make("ev2", cid="id\nFAIL forged")
        put(ans, json.dumps({"id\nFAIL forged": {"answer": "no", "note": "n\nFAIL forged2\u2028z"},
                            "ghost\nFAIL forged3": {"answer": "yes"}}))
        p = self.cli("--finalize", card, "--answers", ans, "--out", "ev2-final.json")
        self.assertEqual(p.returncode, 1)
        lines = p.stdout.splitlines()
        self.assertTrue(all(l.startswith(("FAIL ", "verdict:", "scorecard:")) for l in lines), lines)
        self.assertEqual(len([l for l in lines if l.startswith("FAIL forged")]), 0)
        final = json.loads(get("ev2-final.json"))
        self.assertIn("\n", self.row(final, "id\nFAIL forged")["note"])   # stored text is kept
        p = self.cli("--kind", "reel", "--spec", spec, "--input", inp, "--out", "o.json", "--step", "x\nFAIL forged4")
        self.assertEqual(p.returncode, 2)
        self.assertEqual(len(p.stderr.splitlines()), 1)


class SourceTests(unittest.TestCase):
    def test_source_is_plain(self):
        src = get(CHECK)
        for bad in ("shell=True", "os.system", "os.popen", "import socket", "urllib", "http.client",
                    "requests", "eval(", "exec(", "glob", "os.walk", "environ", "expanduser", "bash"):
            self.assertNotIn(bad, src, bad)

    def test_block_has_no_shell_scripts(self):
        root = os.path.dirname(HERE)
        for base, _, files in os.walk(root):
            for f in files:
                self.assertFalse(f.endswith((".sh", ".bash")), f)


if __name__ == "__main__":
    unittest.main()
