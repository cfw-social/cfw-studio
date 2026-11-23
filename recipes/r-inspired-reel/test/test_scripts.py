#!/usr/bin/env python3
"""Tests for the r-inspired-reel scripts. No account, no private file, no network.

  python3 -I -m unittest discover -s recipes/r-inspired-reel/test -v     (from the repository root)

Media is made with ffmpeg in temporary folders. A test that needs ffmpeg is skipped, by name, when it is
missing. The transcripts here are made up.
"""
import json
import os
import re
import stat
import sys
import unittest

import helpers as H
from helpers import REF_TEXT, WorkDir, make_avatar_video, make_cut_video, timed, valid_format, write, read

import format_schema  # noqa: E402  (path set by helpers)
from rs_common import Stop  # noqa: E402


def words_file(wd, name="ref/words.json", text=REF_TEXT, **kw):
    write(wd.p(name), json.dumps(timed(text, **kw)))


class Overlap(WorkDir):
    REF = "the quick brown fox jumps over the lazy dog near the river bank today"

    def check(self, script, ref=None, *extra):
        write(self.p("script.txt"), script)
        write(self.p("ref.txt"), self.REF if ref is None else ref)
        return self.run_script("check_overlap.py", "--script", "script.txt", "--reference", "ref.txt", *extra)

    def test_six_in_a_row_is_refused(self):
        r = self.check("I once saw that the quick brown fox jumps over a gate")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("OVERLAP: FAIL", r.stdout)
        self.assertIn("longest shared run 6", r.stdout)

    def test_five_in_a_row_is_accepted(self):
        r = self.check("I once saw that the quick brown fox jumps and ran off")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("longest shared run 5", r.stdout)

    def test_longer_run_reports_its_length(self):
        r = self.check("so the quick brown fox jumps over the lazy dog near it")
        self.assertEqual(r.returncode, 1)
        self.assertIn("longest shared run 10", r.stdout)

    def test_case_and_punctuation_are_ignored(self):
        r = self.check("Well... THE Quick, brown fox -- jumps (over) the lazy dog!")
        self.assertEqual(r.returncode, 1, r.stdout)

    def test_apostrophes_and_hyphens_are_ignored(self):
        r = self.check("Don't stop-and-think", ref="dont stop and think about it now")
        self.assertEqual(r.returncode, 0)  # 4 shared words only
        r = self.check("Don't stop-and-think about it now ok", ref="dont stop and think about it now")
        self.assertEqual(r.returncode, 1)

    def test_one_changed_word_breaks_the_run(self):
        r = self.check("the quick brown fox leaps over the lazy dog near it")
        self.assertEqual(r.returncode, 0)

    def test_reports_position_not_words(self):
        r = self.check("hello again my friend the quick brown fox jumps over a gate")
        self.assertEqual(r.returncode, 1)
        self.assertIn("script words 5 to 10", r.stdout)
        for word in ("quick", "brown", "fox"):
            self.assertNotIn(word, r.stdout + r.stderr)

    def test_empty_script_and_empty_reference_are_refused(self):
        r = self.check("   \n ")
        self.assertEqual(r.returncode, 2)
        self.assertIn("script has no words", r.stderr)
        r = self.check("some words here", ref="")
        self.assertEqual(r.returncode, 2)
        self.assertIn("reference transcript has no words", r.stderr)
        write(self.p("empty.txt"), "")
        r = self.run_script("check_overlap.py", "--script", "empty.txt", "--reference", "empty.txt")
        self.assertEqual(r.returncode, 2)

    def test_words_list_as_reference_and_script(self):
        words_file(self, "ref/words.json")
        write(self.p("new.json"), json.dumps(timed("Honestly the tap pressure is not what the label says anywhere")))
        r = self.run_script("check_overlap.py", "--script", "new.json", "--reference", "ref/words.json")
        self.assertEqual(r.returncode, 1)  # "the tap pressure is not what the label says" shares 9 words
        write(self.p("new2.json"), json.dumps(timed("Honestly the tap pressure is wrong and the label lies")))
        r = self.run_script("check_overlap.py", "--script", "new2.json", "--reference", "ref/words.json")
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_out_file_holds_numbers_only(self):
        r = self.check("I once saw that the quick brown fox jumps over a gate", None, "--out", "overlap.json")
        self.assertEqual(r.returncode, 1)
        data = json.loads(read(self.p("overlap.json")))
        self.assertEqual(data["verdict"], "FAIL")
        self.assertEqual(data["longest_shared_run"], 6)
        self.assertEqual(data["runs"], [{"script_word": 5, "length": 6}])
        for v in data.values():
            self.assertNotIsInstance(v, str) if v not in ("overlap", "FAIL") else None
        text = read(self.p("overlap.json"))
        for word in ("quick", "brown", "fox"):
            self.assertNotIn(word, text)

    def test_bad_json_and_limit(self):
        write(self.p("bad.json"), "{not json")
        write(self.p("s.txt"), "hello there")
        r = self.run_script("check_overlap.py", "--script", "s.txt", "--reference", "bad.json")
        self.assertEqual(r.returncode, 2)
        r = self.run_script("check_overlap.py", "--script", "s.txt", "--reference", "s.txt", "--limit", "1")
        self.assertEqual(r.returncode, 2)

    def test_custom_limit(self):
        r = self.check("I once saw that the quick brown fox jumps and ran off", None, "--limit", "5")
        self.assertEqual(r.returncode, 1)


class Schema(unittest.TestCase):
    def bad(self, obj):
        with self.assertRaises(Stop):
            format_schema.validate_format(obj)

    def test_valid(self):
        self.assertIsNotNone(format_schema.validate_format(valid_format()))

    def test_text_keys_and_labels_are_refused(self):
        self.bad(valid_format(transcript="Did you know your garden hose is lying to you"))
        self.bad(valid_format(structure="Did you know your garden hose is lying"))
        f = valid_format()
        f["beats"][0]["label"] = "Did you know"
        self.bad(f)
        f = valid_format()
        f["beats"][0]["text"] = "a sentence"
        self.bad(f)
        f = valid_format()
        f["hook"]["text"] = "a sentence"
        self.bad(f)
        self.bad(valid_format(orientation="the garden hose"))
        self.bad(valid_format(cut_times_s=["a sentence"]))
        self.bad(valid_format(wpm="fast"))
        self.bad(valid_format(wpm=float("nan")))
        self.bad(valid_format(wpm=True))


class Measure(WorkDir):
    def setUp(self):
        super().setUp()
        self.need_ffmpeg()

    def measure(self, *extra, shots=(5, 5, 5, 5)):
        make_cut_video(self.p("inputs", "reference_reel", "ref.mp4"), shots=shots)
        return self.run_script("measure_format.py", "--input-dir", "inputs/reference_reel", "--words", "ref/words.json",
                               "--out", "saves/format.json", *extra)

    def test_known_cuts_and_numbers(self):
        words_file(self, gap=0.3, pause=0.4)
        r = self.measure()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        fmt = json.loads(read(self.p("saves", "format.json")))
        self.assertEqual(fmt["duration_s"], 20.0)
        self.assertEqual((fmt["width"], fmt["height"], fmt["orientation"]), (90, 160, "portrait"))
        self.assertEqual(fmt["cut_count"], 3)
        for got, want in zip(fmt["cut_times_s"], (5.0, 10.0, 15.0)):
            self.assertAlmostEqual(got, want, delta=0.1)
        self.assertAlmostEqual(fmt["cuts_per_10s"], 1.5, places=2)
        self.assertAlmostEqual(fmt["mean_shot_s"], 5.0, places=2)
        words = timed(REF_TEXT, gap=0.3, pause=0.4)
        self.assertEqual(fmt["word_count"], len(words))
        span = words[-1]["end"] - words[0]["start"]
        self.assertAlmostEqual(fmt["wpm"], len(words) / (span / 60), delta=0.2)
        self.assertEqual(fmt["hook"]["type"], "question")
        self.assertEqual(fmt["hook"]["type_source"], "rules")
        self.assertEqual(fmt["fps"], 30.0)

    def test_beats_cover_the_speech_and_shares_sum_to_one(self):
        words_file(self, gap=0.3, pause=0.4)
        self.assertEqual(self.measure().returncode, 0)
        fmt = json.loads(read(self.p("saves", "format.json")))
        beats = fmt["beats"]
        self.assertEqual(beats[0]["label"], "hook")
        self.assertEqual(beats[-1]["label"], "cta")
        self.assertTrue(all(b["label"].startswith("point_") for b in beats[1:-1]))
        self.assertAlmostEqual(sum(b["share"] for b in beats), 1.0, delta=0.02)
        self.assertEqual(sum(b["words"] for b in beats), fmt["word_count"])
        for a, b in zip(beats, beats[1:]):
            self.assertAlmostEqual(a["end_s"], b["start_s"], places=2)
        self.assertEqual(fmt["structure"], "hook, %d points, cta" % (len(beats) - 2))

    def test_format_holds_no_sentence_from_the_reference(self):
        words_file(self, gap=0.3, pause=0.4)
        self.assertEqual(self.measure().returncode, 0)
        text = read(self.p("saves", "format.json"))
        from rs_common import normalize
        toks = normalize(REF_TEXT)
        low = " ".join(normalize(text))
        for i in range(len(toks) - 2):  # no run of even three reference words, in any form
            self.assertNotIn(" ".join(toks[i:i + 3]), low)
        for distinctive in ("garden", "hose", "nozzle", "washer", "kink", "season", "tap"):
            self.assertNotIn(distinctive, low.split())
        data = json.loads(text)
        strings = [v for v in json.dumps(data).split('"') if re.search(r"[a-z ]{5,}", v)]
        allowed = {"format_version", "duration_s", "orientation", "portrait", "scene_threshold", "cut_times_s",
                   "type_source", "rules", "structure", "cut_count", "cuts_per_10s", "mean_shot_s", "speech_span_s",
                   "first_word_at_s", "word_count", "speech_share", "hook", "question", "beats", "point_1",
                   "point_2", "point_3", "start_s", "end_s", "share", "words", "label", "seconds", "type", "wpm",
                   "width", "height", "fps"}
        for s in strings:
            ok = s in allowed or re.fullmatch(r"hook(, \d points?)?(, cta)?", s) or re.fullmatch(r"point_\d|cta", s)
            self.assertTrue(ok, "unexpected text in format.json: %r" % s)

    def test_hook_type_given_by_the_person(self):
        words_file(self, gap=0.3, pause=0.4)
        r = self.measure("--hook-type", "story")
        self.assertEqual(r.returncode, 0)
        fmt = json.loads(read(self.p("saves", "format.json")))
        self.assertEqual((fmt["hook"]["type"], fmt["hook"]["type_source"]), ("story", "given"))

    def test_hook_type_rules(self):
        from measure_format import hook_type
        ws = lambda t: timed(t)
        for text, want in (("Why does coffee go cold so fast?", "question"),
                           ("Ninety percent of cups are too thin.", "stat"),
                           ("I spilled a whole pot last week.", "story"),
                           ("Your cup is the problem.", "claim")):
            w = ws(text)
            self.assertEqual(hook_type(w, [0, len(w) - 1]), want, text)

    def test_three_cuts_at_two_four_six(self):
        words_file(self, gap=0.1, pause=0.1)
        r = self.measure(shots=(2, 2, 2, 2))
        self.assertEqual(r.returncode, 0, r.stderr)
        fmt = json.loads(read(self.p("saves", "format.json")))
        self.assertEqual(fmt["cut_count"], 3)
        self.assertEqual(fmt["duration_s"], 8.0)

    def test_too_few_words_is_refused(self):
        words_file(self, text="Hello there friend. Only a few words.")
        r = self.measure()
        self.assertEqual(r.returncode, 1)
        self.assertIn("fewer than 15 words", r.stderr)
        self.assertFalse(os.path.exists(self.p("saves", "format.json")))

    def test_bad_threshold_and_two_videos(self):
        words_file(self, gap=0.3, pause=0.4)
        self.assertEqual(self.measure("--scene-threshold", "nan").returncode, 2)
        self.assertEqual(self.measure("--scene-threshold", "5").returncode, 2)
        make_cut_video(self.p("inputs", "reference_reel", "two.mp4"), shots=(5,))
        self.assertEqual(self.measure().returncode, 2)


class ShapeAndSpec(WorkDir):
    def setUp(self):
        super().setUp()
        write(self.p("format.json"), json.dumps(valid_format()))

    @staticmethod
    def para(n, word="alpha"):
        return " ".join("%s%d" % (word, i) for i in range(n)) + "."

    def script(self, counts):
        text = "\n\n".join(self.para(n, "w%d" % i) for i, n in enumerate(counts))
        write(self.p("script.txt"), text)
        return self.run_script("check_script_shape.py", "--format", "format.json", "--script", "script.txt",
                               "--narration-out", "narration.txt")

    def test_matching_shape_passes_and_writes_narration(self):
        r = self.script([20, 60, 20])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("SHAPE: PASS", r.stdout)
        narr = read(self.p("narration.txt"))
        self.assertEqual(len(narr.strip().splitlines()), 1)
        self.assertTrue(narr.startswith("w00 w01 "))

    def test_wrong_paragraph_count_total_and_share(self):
        r = self.script([50, 50])
        self.assertEqual(r.returncode, 1)
        self.assertIn("2 paragraphs; the format has 3 beats", r.stdout)
        self.assertFalse(os.path.exists(self.p("narration.txt")))
        self.assertEqual(self.script([20, 60, 40]).returncode, 1)   # 120 words, 20 percent over
        r = self.script([40, 20, 40])                                # right total, wrong shares
        self.assertEqual(r.returncode, 1)
        self.assertIn("paragraph 2 (point_1)", r.stdout)

    def test_markup_and_headings_are_refused(self):
        write(self.p("script.txt"), "# Hook\n\nhello there\n\n[pause] more words\n\nbye")
        r = self.run_script("check_script_shape.py", "--format", "format.json", "--script", "script.txt")
        self.assertEqual(r.returncode, 1)
        self.assertIn("plain spoken text", r.stdout)

    def test_hint_out_is_short_plain_and_its_own_file(self):
        long_script = "\n\n".join(" ".join("word%d" % i for i in range(n)) + "." for n in (40, 120, 40))
        write(self.p("script.txt"), long_script)
        write(self.p("format.json"), json.dumps(valid_format(word_count=200)))
        r = self.run_script("check_script_shape.py", "--format", "format.json", "--script", "script.txt", "--hint-out", "hint.txt")
        self.assertEqual(r.returncode, 0, r.stdout)
        hint = read(self.p("hint.txt"))
        self.assertLessEqual(len(hint.strip()), 1900)
        self.assertFalse(hint.strip().endswith("wor"))
        self.assertEqual(len(hint.strip().splitlines()), 1)
        r = self.run_script("check_script_shape.py", "--format", "format.json", "--script", "script.txt", "--hint-out", "script.txt")
        self.assertEqual(r.returncode, 2)

    def test_narration_out_cannot_be_the_script(self):
        write(self.p("script.txt"), self.para(20) + "\n\n" + self.para(60) + "\n\n" + self.para(20))
        r = self.run_script("check_script_shape.py", "--format", "format.json", "--script", "script.txt",
                            "--narration-out", "script.txt")
        self.assertEqual(r.returncode, 2)

    def test_dirty_format_is_refused(self):
        write(self.p("format.json"), json.dumps(valid_format(transcript="a sentence")))
        r = self.script([20, 60, 20])
        self.assertEqual(r.returncode, 1)
        self.assertIn("unexpected key", r.stderr)

    def spec(self, dur, tol=None):
        write(self.p("format.json"), json.dumps(valid_format(duration_s=dur)))
        args = ["--format", "format.json", "--spec", os.path.join(H.RECIPE, "acceptance.json"), "--out", "order.json"]
        if tol:
            args += ["--tolerance", tol]
        return self.run_script("make_spec.py", *args)

    def test_spec_window_follows_the_reference_length(self):
        r = self.spec(40.0)
        self.assertEqual(r.returncode, 0, r.stderr)
        spec = json.loads(read(self.p("order.json")))
        win = next(c for c in spec["checks"] if c["type"] == "duration_window")
        self.assertEqual((win["min_s"], win["max_s"]), (34.0, 46.0))
        others = [c for c in spec["checks"] if c["type"] != "duration_window"]
        orig = [c for c in json.loads(read(os.path.join(H.RECIPE, "acceptance.json")))["checks"] if c["type"] != "duration_window"]
        self.assertEqual(others, orig)

    def test_spec_window_is_clamped_and_refused_when_empty(self):
        r = self.spec(95.0)
        self.assertEqual(r.returncode, 0)
        win = next(c for c in json.loads(read(self.p("order.json")))["checks"] if c["type"] == "duration_window")
        self.assertEqual(win["max_s"], 100)
        self.assertEqual(self.spec(2.0).returncode, 1)      # window 1.7 to 2.3 is below the hard minimum of 10
        self.assertEqual(self.spec(40.0, "nan").returncode, 2)


class Prepare(WorkDir):
    def setUp(self):
        super().setUp()
        self.need_ffmpeg()

    def prep(self, *extra):
        return self.run_script("prepare_reference.py", "--input-dir", "inputs/reference_reel", "--outdir", "ref", *extra)

    def test_extracts_16k_mono_audio_and_leaves_the_file_alone(self):
        src = self.p("inputs", "reference_reel", "clip.mp4")
        make_cut_video(src, shots=(8, 8))
        before = H.read_bytes(src)
        r = self.prep()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        import wave
        with wave.open(self.p("ref", "audio.wav")) as w:
            self.assertEqual((w.getframerate(), w.getnchannels()), (16000, 1))
            self.assertAlmostEqual(w.getnframes() / 16000, 16.0, delta=0.3)
        self.assertEqual(H.read_bytes(src), before)
        self.assertEqual([n for n in os.listdir(self.p("ref")) if n.startswith(".tmp")], [])

    def test_refuses_no_file_two_files_no_sound_and_wrong_length(self):
        os.makedirs(self.p("inputs", "reference_reel"))
        self.assertEqual(self.prep().returncode, 2)
        make_cut_video(self.p("inputs", "reference_reel", "a.mp4"), shots=(8, 8))
        make_cut_video(self.p("inputs", "reference_reel", "b.mov"), shots=(8, 8))
        self.assertEqual(self.prep().returncode, 2)
        os.remove(self.p("inputs", "reference_reel", "b.mov"))
        os.remove(self.p("inputs", "reference_reel", "a.mp4"))
        make_cut_video(self.p("inputs", "reference_reel", "mute.mp4"), shots=(8, 8), audio=False)
        r = self.prep()
        self.assertEqual(r.returncode, 1)
        self.assertIn("no sound track", r.stderr)
        os.remove(self.p("inputs", "reference_reel", "mute.mp4"))
        make_cut_video(self.p("inputs", "reference_reel", "short.mp4"), shots=(3, 3))
        r = self.prep()
        self.assertEqual(r.returncode, 1)
        self.assertIn("must be from 15 to 90 s", r.stderr)

    def test_a_non_video_is_refused_without_a_traceback(self):
        write(self.p("inputs", "reference_reel", "fake.mp4"), "this is not a video")
        r = self.prep()
        self.assertEqual(r.returncode, 1)


class BaseReel(WorkDir):
    def setUp(self):
        super().setUp()
        self.need_ffmpeg()

    def test_canvas_fps_loudness_and_length(self):
        make_avatar_video(self.p("work", "avatar.mp4"), seconds=6, size="270x480")
        r = self.run_script("make_base_reel.py", "--avatar", "work/avatar.mp4", "--out", "saves/base_reel.mp4")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        info = H.subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height,avg_frame_rate,sample_rate,channels:format=duration",
                                 "-of", "json", self.p("saves", "base_reel.mp4")], capture_output=True, text=True)
        data = json.loads(info.stdout)
        video = next(s for s in data["streams"] if s["codec_type"] == "video")
        audio = next(s for s in data["streams"] if s["codec_type"] == "audio")
        self.assertEqual((video["width"], video["height"]), (1080, 1920))
        self.assertEqual(video["avg_frame_rate"], "30/1")
        self.assertEqual((audio["sample_rate"], audio["channels"]), ("48000", 2))
        self.assertAlmostEqual(float(data["format"]["duration"]), 6.0, delta=0.2)
        meas = H.subprocess.run(["ffmpeg", "-nostdin", "-i", self.p("saves", "base_reel.mp4"), "-af", "ebur128", "-f", "null", "-"],
                                capture_output=True, text=True).stderr
        lufs = float(re.findall(r"I:\s+(-?[0-9.]+) LUFS", meas)[-1])
        self.assertAlmostEqual(lufs, -14.0, delta=1.0)

    def test_wide_video_is_padded_not_stretched(self):
        make_avatar_video(self.p("work", "wide.mp4"), seconds=4, size="480x270")
        r = self.run_script("make_base_reel.py", "--avatar", "work/wide.mp4", "--out", "reel/base.mp4", "--pad-color", "#102030")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = H.subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                                "-of", "csv=p=0", self.p("reel", "base.mp4")], capture_output=True, text=True).stdout.strip()
        self.assertEqual(out, "1080,1920")

    def test_silent_and_missing_sound_are_refused(self):
        make_avatar_video(self.p("work", "silent.mp4"), seconds=3, silent=True)
        r = self.run_script("make_base_reel.py", "--avatar", "work/silent.mp4", "--out", "saves/base_reel.mp4")
        self.assertEqual(r.returncode, 1)
        self.assertIn("silent", r.stderr)
        self.assertFalse(os.path.exists(self.p("saves", "base_reel.mp4")))
        make_cut_video(self.p("work", "mute.mp4"), shots=(3,), audio=False)
        r = self.run_script("make_base_reel.py", "--avatar", "work/mute.mp4", "--out", "saves/base_reel.mp4")
        self.assertEqual(r.returncode, 1)

    def test_bad_numbers_and_colours_are_refused_before_ffmpeg(self):
        make_avatar_video(self.p("work", "a.mp4"), seconds=3)
        for args in (["--lufs", "nan"], ["--lufs", "50"], ["--pad-color", "red;rm"], ["--pad-color", "12345"]):
            r = self.run_script("make_base_reel.py", "--avatar", "work/a.mp4", "--out", "o.mp4", *args)
            self.assertEqual(r.returncode, 2, args)
        self.assertFalse(os.path.exists(self.p("o.mp4")))

    def test_output_cannot_be_the_input(self):
        make_avatar_video(self.p("work", "a.mp4"), seconds=3)
        r = self.run_script("make_base_reel.py", "--avatar", "work/a.mp4", "--out", "work/a.mp4")
        self.assertEqual(r.returncode, 2)


class Cleanup(WorkDir):
    def setUp(self):
        super().setUp()
        words_file(self)
        write(self.p("ref", "words.meta.json"), json.dumps({"text": REF_TEXT, "input": "ref/audio.wav"}))
        write(self.p("ref", "audio.wav"), "RIFFfake-audio", "w")
        write(self.p("saves", "format.json"), json.dumps(valid_format()))
        write(self.p("saves", "script.md"), "A brand new script about watering tomatoes in the morning light.\n")
        write(self.p("work", "narration.txt"), "A brand new script about watering tomatoes in the morning light.\n")

    def test_removes_transcript_meta_and_audio_and_passes(self):
        r = self.run_script("cleanup_reference.py", "--receipt", "saves/cleanup.json")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("CLEANUP: PASS (3 items removed)", r.stdout)
        self.assertFalse(os.path.exists(self.p("ref")))
        self.assertEqual(json.loads(read(self.p("saves", "cleanup.json"))),
                         {"check": "cleanup", "verdict": "PASS", "items_removed": 3})
        r = self.run_script("cleanup_reference.py", "--check-only")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("nothing left of the reference", r.stdout)
        # the new script and the format are untouched
        self.assertTrue(os.path.exists(self.p("saves", "script.md")))
        self.assertTrue(os.path.exists(self.p("saves", "format.json")))

    def test_check_fails_when_a_file_is_left_behind(self):
        r = self.run_script("cleanup_reference.py", "--check-only")
        self.assertEqual(r.returncode, 1)
        self.assertIn("CLEANUP CHECK: FAIL", r.stdout)
        self.assertIn("still there: ref/words.json", r.stdout)
        self.assertIn("still there: ref/audio.wav", r.stdout)
        self.assertTrue(os.path.exists(self.p("ref", "words.json")))   # check-only deletes nothing
        # a stray file planted after a clean-up is caught too
        self.assertEqual(self.run_script("cleanup_reference.py").returncode, 0)
        write(self.p("ref", "late.wav"), "x")
        r = self.run_script("cleanup_reference.py", "--check-only")
        self.assertEqual(r.returncode, 1)
        self.assertIn("ref/late.wav", r.stdout)

    def test_empty_ref_folder_is_fine(self):
        self.assertEqual(self.run_script("cleanup_reference.py").returncode, 0)
        os.makedirs(self.p("ref"))
        self.assertEqual(self.run_script("cleanup_reference.py", "--check-only").returncode, 0)

    @unittest.skipIf(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0), "needs a non-root POSIX user")
    def test_a_file_that_cannot_be_deleted_fails_the_run(self):
        os.chmod(self.p("ref"), stat.S_IRUSR | stat.S_IXUSR)
        try:
            r = self.run_script("cleanup_reference.py")
        finally:
            os.chmod(self.p("ref"), stat.S_IRWXU)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("FAIL", r.stdout)

    def test_a_run_of_reference_words_in_another_file_fails_but_reference_is_still_deleted(self):
        write(self.p("work", "notes.txt"), "I wrote: every kink in the line steals half the flow, then more.")
        write(self.p("saves", "extra.json"), json.dumps({"caption": "The nozzle you bought wears out in a single season"}))
        r = self.run_script("cleanup_reference.py")
        self.assertEqual(r.returncode, 1)
        self.assertIn("work/notes.txt", r.stdout)
        self.assertIn("saves/extra.json", r.stdout)
        self.assertNotIn("script.md", r.stdout)
        self.assertNotIn("kink", r.stdout)           # reports the file, not the words
        self.assertFalse(os.path.exists(self.p("ref")))

    def test_five_words_are_not_a_leak(self):
        write(self.p("work", "notes.txt"), "every kink in the line then stops")  # 5 reference words
        self.assertEqual(self.run_script("cleanup_reference.py").returncode, 0)

    def test_a_sentence_in_format_json_fails(self):
        write(self.p("saves", "format.json"), json.dumps(valid_format(transcript="Did you know your garden hose is lying to you")))
        r = self.run_script("cleanup_reference.py")
        self.assertEqual(r.returncode, 1)
        self.assertIn("unexpected key", r.stdout)
        self.assertIn("a run of reference words is in saves/format.json", r.stdout)

    def test_the_persons_inputs_folder_is_never_touched_or_flagged(self):
        write(self.p("inputs", "reference_reel", "notes.txt"), REF_TEXT)
        r = self.run_script("cleanup_reference.py")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertTrue(os.path.exists(self.p("inputs", "reference_reel", "notes.txt")))

    def test_hostile_cases_follow_no_links(self):
        if not hasattr(os, "symlink"):
            self.skipTest("no symlinks")
        secret = os.path.join(self.outside, "keep.txt")
        write(secret, "keep me")
        os.symlink(secret, self.p("ref", "link.txt"))
        r = self.run_script("cleanup_reference.py")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(read(secret), "keep me")             # the link went, its target stayed
        # the ref folder itself is a link: refused, not followed
        os.symlink(self.outside, self.p("ref"))
        r = self.run_script("cleanup_reference.py")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(read(secret), "keep me")


class Evasions(WorkDir):
    """Ways to dress up a copied run so a plain word match misses it. Each must still be caught."""
    REF = "the quick brown fox jumps over the lazy dog near the river bank today"

    def check(self, script, ref=None):
        write(self.p("script.txt"), script)
        write(self.p("ref.txt"), self.REF if ref is None else ref)
        return self.run_script("check_overlap.py", "--script", "script.txt", "--reference", "ref.txt")

    def test_invisible_and_format_characters_inside_words(self):
        for ch, name in (("\u200b", "zero-width space"), ("\u200d", "zero-width joiner"), ("\u200c", "non-joiner"),
                         ("\u00ad", "soft hyphen"), ("\u2060", "word joiner"), ("\ufeff", "byte order mark")):
            r = self.check("so the qu%sick brown fox jum%sps over the lazy dog" % (ch, ch))
            self.assertEqual(r.returncode, 1, name + r.stdout)

    def test_combining_accents_and_compatibility_forms(self):
        self.assertEqual(self.check("so the qu\u0301ick bro\u0308wn fox jumps over the lazy dog").returncode, 1)
        self.assertEqual(self.check("so the quick brown fox jumps over the l\u00e4zy dog").returncode, 1)
        self.assertEqual(self.check("so the \uff51\uff55\uff49\uff43\uff4b brown fox jumps over the lazy").returncode, 1)  # full-width

    def test_hyphens_in_the_script_and_in_the_reference(self):
        self.assertEqual(self.check("so the qui-ck bro-wn fox jumps over the lazy dog").returncode, 1)     # hyphen inside a word
        self.assertEqual(self.check("so the-quick-brown-fox-jumps-over the lazy dog").returncode, 1)       # hyphens between words
        self.assertEqual(self.check("so the quick brown fox jumps over the lazy dog", ref="the qui-ck brown fox jum-ps over the lazy dog").returncode, 1)
        self.assertEqual(self.check("so thequick brown fox jumps over the lazy", ref="the-quick brown fox jumps over the lazy").returncode, 1)
        self.assertEqual(self.check("so the \u2011quick\u2014brown fox jumps over the lazy dog").returncode, 1)  # other dashes

    def test_odd_apostrophes_and_case(self):
        r = self.check("DON\u2019T you l\u2018ike it near the river", ref="dont you like it near the river")
        self.assertEqual(r.returncode, 1)

    def test_look_alike_letters_are_refused_with_a_clear_message(self):
        for text in ("so the quick brown fox jumps over the l\u0430zy dog",     # Cyrillic a
                     "so the quick brown f\u043ex jumps over the lazy dog",      # Cyrillic o
                     "so the \u03bfver the lazy",                                   # Greek omicron
                     "caf\u00e9 \u65e5\u672c"):
            r = self.check(text)
            self.assertEqual(r.returncode, 2, text)
            self.assertIn("outside the Latin script", r.stderr)
            self.assertNotIn("Traceback", r.stderr)

    def test_unusual_latin_look_alikes_are_refused_and_named(self):
        for ch, name in (("\u1d0d", "SMALL CAPITAL M"), ("\u0251", "ALPHA"), ("\u0131", "DOTLESS I"), ("\ua731", "SMALL CAPITAL S"),
                         ("\u1d0f", "SMALL CAPITAL O"), ("\u00e6", "LATIN SMALL LETTER AE"), ("\u0142", "L WITH STROKE")):
            r = self.check("so the quick brown fox jumps over the lazy d%sg" % ch)
            self.assertEqual(r.returncode, 2, name)
            self.assertIn("outside the Latin script a to z", r.stderr)
            self.assertIn(ch, r.stderr)                     # the refused character is named
            self.assertIn("U+%04X" % ord(ch), r.stderr)
        r = self.check("\u1d0d\u1d0f\ua731\u1d1b is a word")
        self.assertEqual(r.returncode, 2)

    def test_punctuation_inside_a_word_cannot_hide_a_run(self):
        ref = "the quick brown people jumps over the lazy dog today"
        for script in ("so the quick brown peo.ple jumps over the lazy dog", "so the quick brown peo/ple jumps over the lazy dog",
                       "so the quick brown peo:ple jumps over the lazy dog", "so the quick brown p_e_o_p_l_e jumps over the lazy dog",
                       "so the quick brown peo..ple jumps over the lazy dog", "so the quick brown peo,ple jumps over the lazy dog"):
            self.assertEqual(self.check(script, ref=ref).returncode, 1, script)
        # and in the reference
        self.assertEqual(self.check("so the quick brown people jumps over the lazy dog",
                                    ref="the quick brown peo.ple jumps over the lazy dog today").returncode, 1)
        # a full stop between real sentences still counts as a boundary: five words each side is fine
        self.assertEqual(self.check("the quick brown fox. jumps over the lazy dog", ref="the quick brown fox jumps over the lazy dog").returncode, 1)

    def test_odd_control_characters_are_refused(self):
        self.assertEqual(self.check("so the quick\u2800brown fox").returncode, 2)
        self.assertEqual(self.check("so the quick\x01brown fox").returncode, 2)

    def test_plain_latin_with_accents_is_fine(self):
        self.assertEqual(self.check("A caf\u00e9 near the r\u00edo, na\u00efve fa\u00e7ade, stra\u00dfe").returncode, 0)

    def test_shape_check_refuses_look_alikes_too(self):
        write(self.p("format.json"), json.dumps(valid_format()))
        write(self.p("script.txt"), "w\u043erd " * 20 + "\n\n" + "word " * 60 + "\n\n" + "word " * 20)
        r = self.run_script("check_script_shape.py", "--format", "format.json", "--script", "script.txt")
        self.assertEqual(r.returncode, 2)


class SchemaHardening(unittest.TestCase):
    def bad(self, **over):
        with self.assertRaises(Stop):
            format_schema.validate_format(valid_format(**over))

    def test_labels_are_matched_in_full(self):
        f = valid_format()
        f["beats"][0]["label"] = "hook\n"
        with self.assertRaises(Stop):
            format_schema.validate_format(f)
        self.bad(structure="hook, 1 point, cta\n")
        f = valid_format()
        f["beats"][1]["label"] = "point_1\n"
        with self.assertRaises(Stop):
            format_schema.validate_format(f)

    def test_exact_types(self):
        self.bad(format_version=True)
        self.bad(format_version=1.0)
        self.bad(width=1080.0)
        self.bad(word_count=True)
        self.bad(cut_count=6.0)
        f = valid_format()
        f["beats"][0]["words"] = 20.0
        with self.assertRaises(Stop):
            format_schema.validate_format(f)
        self.bad(wpm=214.3333)           # not rounded to two decimals
        self.bad(duration_s=30.001)

    def test_cut_times_are_few_increasing_inside_and_rounded(self):
        self.bad(cut_times_s=[4.0, 3.0, 8.0, 9.0, 10.0, 11.0])          # not increasing
        self.bad(cut_times_s=[4.0, 4.0, 8.0, 9.0, 10.0, 11.0])          # repeated
        self.bad(cut_times_s=[4.0, 8.0, 12.0, 16.0, 20.0, 31.0])        # outside the clip
        self.bad(cut_times_s=[0.0, 8.0, 12.0, 16.0, 20.0, 24.0])        # not after the start
        self.bad(cut_times_s=[4.123, 8.0, 12.0, 16.0, 20.0, 24.0])      # not rounded
        self.bad(cut_times_s=[4.25, 8.0, 12.0, 16.0, 20.0, 24.0])       # two decimals: cut times take one
        many = [round(0.1 + i * 0.1, 1) for i in range(400)]
        self.bad(cut_times_s=many, cut_count=400)                       # over 10 a second of a 30 s clip is 300
        self.bad(cut_count=5)                                           # count must match the list
        self.bad(cut_times_s=[4.0, True, 12.0, 16.0, 20.0, 24.0])

    def test_a_clip_can_hold_up_to_ten_cuts_a_second(self):
        ok = [round(0.1 * i, 2) for i in range(1, 300)]
        format_schema.validate_format(valid_format(cut_times_s=ok, cut_count=len(ok), duration_s=30.0))


class VerifyFinal(WorkDir):
    SPEC = os.path.join(H.RECIPE, "acceptance.json")

    def setUp(self):
        super().setUp()
        write(self.p("premium", "polished.mp4"), "pretend video bytes " * 100)
        self.sha = __import__("hashlib").sha256(H.read_bytes(self.p("premium", "polished.mp4"))).hexdigest()
        self.ids = [c["id"] for c in json.loads(read(self.SPEC))["checks"]]

    def card(self, **over):
        rows = [{"id": i if i != "qa_gate" else "qa_gate.video", "status": "PASS"} for i in self.ids]
        c = {"scorecard_version": 1, "recipe": "r-inspired-reel", "kind": "reel", "finalized": True, "verdict": "PASS",
             "input": "premium/polished.mp4", "input_sha256": self.sha, "input_bytes": 2000, "checks": rows}
        c.update(over)
        write(self.p("work", "final-scorecard.json"), json.dumps(c))

    def run_it(self):
        return self.run_script("verify_final.py", "--scorecard", "work/final-scorecard.json", "--input", "premium/polished.mp4",
                               "--spec", self.SPEC, "--final", "saves/final.mp4", "--report", "saves/qa_report.json")

    def assert_nothing_saved(self, r):
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("REFUSED", r.stdout)
        self.assertFalse(os.path.exists(self.p("saves", "final.mp4")))
        self.assertFalse(os.path.exists(self.p("saves", "qa_report.json")))

    def test_a_finalized_pass_for_this_file_is_delivered(self):
        self.card()
        r = self.run_it()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(H.read_bytes(self.p("saves", "final.mp4")), H.read_bytes(self.p("premium", "polished.mp4")))
        self.assertEqual(json.loads(read(self.p("saves", "qa_report.json")))["verdict"], "PASS")

    def test_a_fail_scorecard_is_refused(self):
        self.card(verdict="FAIL")
        self.assert_nothing_saved(self.run_it())

    def test_a_failed_row_in_a_pass_scorecard_is_refused(self):
        c = json.loads(read(self.p("work", "final-scorecard.json"))) if os.path.exists(self.p("work", "final-scorecard.json")) else None
        self.card()
        c = json.loads(read(self.p("work", "final-scorecard.json")))
        c["checks"][0]["status"] = "FAIL"
        write(self.p("work", "final-scorecard.json"), json.dumps(c))
        self.assert_nothing_saved(self.run_it())

    def test_an_unfinalized_scorecard_with_looks_owed_is_refused(self):
        self.card(finalized=False, verdict="PASS_WITH_LOOKS")
        self.assert_nothing_saved(self.run_it())
        self.card(finalized=False)            # a hand-edited verdict without finalizing
        self.assert_nothing_saved(self.run_it())

    def test_a_missing_answer_row_is_refused(self):
        self.card()
        c = json.loads(read(self.p("work", "final-scorecard.json")))
        c["checks"] = [r for r in c["checks"] if r["id"] != "avatar_on_screen"]
        write(self.p("work", "final-scorecard.json"), json.dumps(c))
        r = self.run_it()
        self.assert_nothing_saved(r)
        self.assertIn("avatar_on_screen", r.stdout)

    def test_a_swapped_or_changed_final_file_is_refused(self):
        self.card()
        write(self.p("premium", "polished.mp4"), "a different video entirely " * 100)
        r = self.run_it()
        self.assert_nothing_saved(r)
        self.assertIn("changed after the scorecard", r.stdout)
        self.card(input_bytes=1)
        self.assert_nothing_saved(self.run_it())

    def test_wrong_recipe_kind_or_garbage_is_refused(self):
        self.card(recipe="r-other")
        self.assert_nothing_saved(self.run_it())
        write(self.p("work", "final-scorecard.json"), "[1, 2]")
        self.assert_nothing_saved(self.run_it())
        write(self.p("work", "final-scorecard.json"), "not json")
        self.assertEqual(self.run_it().returncode, 1)

    def test_paths_must_differ_and_stay_inside(self):
        self.card()
        r = self.run_script("verify_final.py", "--scorecard", "work/final-scorecard.json", "--input", "premium/polished.mp4",
                            "--spec", self.SPEC, "--final", "premium/polished.mp4", "--report", "saves/qa_report.json")
        self.assertEqual(r.returncode, 2)
        r = self.run_script("verify_final.py", "--scorecard", "work/final-scorecard.json", "--input", "premium/polished.mp4",
                            "--spec", self.SPEC, "--final", "../outside/final.mp4", "--report", "saves/qa_report.json")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(os.listdir(self.outside), [])
        self.assertFalse(os.path.exists(self.p("saves", "qa_report.json")))


class CleanupHardening(WorkDir):
    def setUp(self):
        super().setUp()
        words_file(self)
        write(self.p("saves", "format.json"), json.dumps(valid_format()))
        write(self.p("work", "keep.txt"), "my own notes")

    def test_dot_the_work_folder_and_other_names_are_refused_and_nothing_is_deleted(self):
        for arg in (".", "./", "", "..", self.work, "inputs", "saves", "ref/sub", "work/ref", "REF"):
            r = self.run_script("cleanup_reference.py", "--ref-dir", arg)
            self.assertEqual(r.returncode, 2, "%r: %s%s" % (arg, r.stdout, r.stderr))
        self.assertTrue(os.path.exists(self.p("work", "keep.txt")))
        self.assertTrue(os.path.exists(self.p("saves", "format.json")))
        self.assertTrue(os.path.exists(self.p("ref", "words.json")))
        self.assertEqual(self.run_script("cleanup_reference.py", "--ref-dir", "ref").returncode, 0)
        self.assertTrue(os.path.exists(self.p("work", "keep.txt")))

    def test_the_scan_reads_any_text_file_whatever_its_extension(self):
        run = "every kink in the line steals half the flow"
        for name in ("work/notes.dat", "work/NOTES", "saves/extra.yaml", "premium/comp/index.html", "work/sub/deep/a.py", "saves/sheet.csv"):
            write(self.p(name), "copied: " + run)
        r = self.run_script("cleanup_reference.py")
        self.assertEqual(r.returncode, 1)
        for name in ("work/notes.dat", "work/NOTES", "saves/extra.yaml", "premium/comp/index.html", "work/sub/deep/a.py", "saves/sheet.csv"):
            self.assertIn(name, r.stdout)

    def test_the_scan_catches_dressed_up_runs_and_skips_binary_and_large_files(self):
        write(self.p("work", "zw.txt"), "every ki\u200bnk in the li\u00adne steals half the flow")
        write(self.p("work", "hy.txt"), "every kink-in-the-line steals half the flow")
        write(self.p("work", "bin.dat"), b"\x00\x01every kink in the line steals half the flow\x00".decode("latin-1"), "w")
        write(self.p("work", "big.txt"), "x " * 1_200_000 + "every kink in the line steals half the flow")
        r = self.run_script("cleanup_reference.py")
        self.assertEqual(r.returncode, 1)
        self.assertIn("work/zw.txt", r.stdout)
        self.assertIn("work/hy.txt", r.stdout)
        self.assertIn("not scanned: work/bin.dat", r.stdout)      # a file it cannot see is named, not passed
        self.assertIn("not scanned: work/big.txt", r.stdout)

    def test_a_file_the_scan_cannot_read_fails_it_and_is_named(self):
        write(self.p("work", "big.txt"), "x " * 1_200_000)
        write(self.p("work", "utf16.txt"), "hello there".encode("utf-16"), "wb")
        import gzip
        write(self.p("work", "notes.gz"), gzip.compress(b"every kink in the line steals half the flow"), "wb")
        write(self.p("work", "blob.bin"), bytes(range(256)), "wb")
        r = self.run_script("cleanup_reference.py")
        self.assertEqual(r.returncode, 1, r.stdout)
        for name in ("big.txt", "utf16.txt", "notes.gz", "blob.bin"):
            self.assertIn("not scanned: work/" + name, r.stdout)
        self.assertFalse(os.path.exists(self.p("ref")))           # the reference is still deleted

    def test_known_media_made_by_the_recipe_is_allowed_but_a_fake_one_is_not(self):
        write(self.p("work", "a.wav"), b"RIFF\x00\x00\x00\x00WAVEdata", "wb")
        write(self.p("work", "b.mp4"), b"\x00\x00\x00\x18ftypmp42\x00\x00", "wb")
        write(self.p("work", "c.png"), b"\x89PNG\r\n\x1a\n\x00", "wb")
        r = self.run_script("cleanup_reference.py")
        self.assertEqual(r.returncode, 0, r.stdout)
        words_file(self)
        write(self.p("work", "fake.wav"), b"\x00\x01not a wav at all", "wb")
        r = self.run_script("cleanup_reference.py")
        self.assertEqual(r.returncode, 1)
        self.assertIn("not scanned: work/fake.wav", r.stdout)

    @unittest.skipUnless(hasattr(os, "symlink"), "no symlinks")
    def test_a_link_is_listed_not_followed(self):
        secret = os.path.join(self.outside, "s.txt")
        write(secret, "x")
        os.symlink(secret, self.p("work", "linked.txt"))
        os.symlink(self.outside, self.p("work", "linkdir"))
        r = self.run_script("cleanup_reference.py")
        self.assertEqual(r.returncode, 1)
        self.assertIn("not scanned: work/linked.txt", r.stdout)
        self.assertIn("not scanned: work/linkdir", r.stdout)
        self.assertEqual(read(secret), "x")


class PathSafety(WorkDir):
    """Every script writes only inside the work folder: outside paths and planted links are refused."""

    def setUp(self):
        super().setUp()
        self.need_ffmpeg()
        make_cut_video(self.p("inputs", "reference_reel", "ref.mp4"), shots=(8, 8))
        words_file(self, gap=0.3, pause=0.4)
        write(self.p("saves", "format.json"), json.dumps(valid_format()))
        write(self.p("script.txt"), " ".join("a%d" % i for i in range(20)) + ".\n\n" + " ".join("b%d" % i for i in range(60))
              + ".\n\n" + " ".join("c%d" % i for i in range(20)) + ".")
        make_avatar_video(self.p("work", "avatar.mp4"), seconds=3)
        self.spec = os.path.join(H.RECIPE, "acceptance.json")

    def cases(self, out):
        """(script, arguments) for each script, with `out` as its one output path."""
        return {
            "check_overlap.py": ["--script", "script.txt", "--reference", "ref/words.json", "--out", out],
            "check_script_shape.py": ["--format", "saves/format.json", "--script", "script.txt", "--narration-out", out],
            "check_script_shape.py hint": ["--format", "saves/format.json", "--script", "script.txt", "--hint-out", out],
            "measure_format.py": ["--input-dir", "inputs/reference_reel", "--words", "ref/words.json", "--out", out],
            "make_spec.py": ["--format", "saves/format.json", "--spec", self.spec, "--out", out],
            "make_base_reel.py": ["--avatar", "work/avatar.mp4", "--out", out],
            "prepare_reference.py": ["--input-dir", "inputs/reference_reel", "--outdir", out],
            "cleanup_reference.py": ["--ref-dir", out],
        }

    def assert_refused(self, name, args, what):
        before = sorted(os.listdir(self.outside))
        r = self.run_script(name.split()[0], *args)
        self.assertEqual(r.returncode, 2, "%s (%s): %s" % (name, what, r.stdout + r.stderr))
        self.assertEqual(sorted(os.listdir(self.outside)), before, "%s wrote outside (%s)" % (name, what))

    def test_a_path_outside_the_work_folder_is_refused(self):
        for name, args in self.cases("../outside/out.dat").items():
            self.assert_refused(name, args, "relative outside")
        for name, args in self.cases(os.path.join(self.outside, "out.dat")).items():
            self.assert_refused(name, args, "absolute outside")
        self.assertFalse(os.path.exists(os.path.join(self.outside, "out.dat")))

    def test_dot_dot_inside_a_path_is_refused(self):
        for name, args in self.cases("saves/../saves/out.dat").items():
            self.assert_refused(name, args, "dot dot")

    @unittest.skipUnless(hasattr(os, "symlink"), "no symlinks")
    def test_a_planted_link_is_refused(self):
        target = os.path.join(self.outside, "victim.txt")
        write(target, "original")
        os.symlink(target, self.p("planted.out"))
        os.symlink(self.outside, self.p("linkdir"))
        for name, args in self.cases("planted.out").items():
            self.assert_refused(name, args, "link as target")
            self.assertEqual(read(target), "original", name)
        for name, args in self.cases("linkdir/out.dat").items():
            self.assert_refused(name, args, "link as folder")
            self.assertEqual(read(target), "original")
        self.assertEqual(sorted(os.listdir(self.outside)), ["victim.txt"])

    @unittest.skipUnless(hasattr(os, "symlink"), "no symlinks")
    def test_a_linked_input_is_refused(self):
        secret = os.path.join(self.outside, "words.json")
        write(secret, json.dumps(timed(REF_TEXT)))
        os.symlink(secret, self.p("linked-words.json"))
        r = self.run_script("check_overlap.py", "--script", "script.txt", "--reference", "linked-words.json")
        self.assertEqual(r.returncode, 2)
        self.assertIn("link is refused", r.stderr)

    def test_a_bad_reference_folder_never_gives_a_traceback(self):
        r = self.run_script("prepare_reference.py", "--input-dir", "nowhere", "--outdir", "ref")
        self.assertEqual(r.returncode, 2)
        r = self.run_script("measure_format.py", "--input-dir", "../outside", "--words", "ref/words.json", "--out", "x.json")
        self.assertEqual(r.returncode, 2)


class Hygiene(unittest.TestCase):
    def test_every_ffmpeg_call_uses_an_argument_list_and_the_file_protocol_only(self):
        for name in sorted(os.listdir(H.SCRIPTS)):
            if not name.endswith(".py"):
                continue
            text = read(os.path.join(H.SCRIPTS, name))
            self.assertNotIn("shell=True", text, name)
            self.assertNotIn("os.system", text, name)
            self.assertNotIn("eval(", text, name)
            if '"ffmpeg"' in text or '"ffprobe"' in text:
                self.assertIn('"-protocol_whitelist", "file"', text, name)
                self.assertEqual(text.count('"-i"'), text.count('"-protocol_whitelist", "file"'), name)  # one per input

    def test_scripts_import_no_network_module(self):
        for name in sorted(os.listdir(H.SCRIPTS)):
            if name.endswith(".py"):
                text = read(os.path.join(H.SCRIPTS, name))
                for mod in ("socket", "urllib", "http.client", "requests", "ftplib", "smtplib"):
                    self.assertNotRegex(text, r"(?m)^\s*(import|from)\s+%s\b" % re.escape(mod), "%s imports %s" % (name, mod))

    def test_scripts_are_short(self):
        for name in sorted(os.listdir(H.SCRIPTS)):
            if name.endswith(".py"):
                self.assertLess(len(read(os.path.join(H.SCRIPTS, name)).splitlines()), 350, name)

    def test_acceptance_uses_only_kinds_the_gate_owns(self):
        spec = json.loads(read(os.path.join(H.RECIPE, "acceptance.json")))
        owned = {"qa_gate", "duration_window", "dims", "mean_volume", "perceptual", "loudness", "luma_floor"}
        for c in spec["checks"]:
            self.assertIn(c["type"], owned, c["id"])

    def test_manifest_matches_the_step_files(self):
        m = json.loads(read(os.path.join(H.RECIPE, "manifest.json")))
        for s in m["steps"]:
            self.assertTrue(os.path.isfile(os.path.join(H.RECIPE, s["instructions"])), s["instructions"])
        saves = {sv["id"] for s in m["steps"] for sv in s["saves"]}
        self.assertEqual(saves, {"format", "script", "overlap", "cleanup", "base_reel", "render_record", "final", "qa_report"})
        self.assertNotIn("reference_reel", saves)
        self.assertNotIn("transcript", " ".join(saves))


if __name__ == "__main__":
    unittest.main(verbosity=2)
