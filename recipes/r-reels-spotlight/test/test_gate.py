#!/usr/bin/env python3
"""acceptance.json against the real b-qa-gate, and the spec copy script.

  python3 -I recipes/r-reels-spotlight/test/test_gate.py -v

The tests run `blocks/b-qa-gate/check.py` (the repository layout: blocks beside the recipe) on small
media made with ffmpeg. They prove that no check kind in acceptance.json is unknown or unsupported
to the gate, and that the guards the gate does not own are not listed as gate checks.
"""
import importlib.util
import json
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import BLOCKS, FFMPEG, NEEDS_FFMPEG, RECIPE_DIR, Tmp, load_json, py, read, write_json, write_text

CHECK = os.path.join(BLOCKS, "b-qa-gate", "check.py")
SPEC = os.path.join(RECIPE_DIR, "acceptance.json")


def all_checks(spec):
    yield from spec["checks"]
    for step in spec["steps"].values():
        yield from step["checks"]


def gate(*args, cwd):
    return subprocess.run([sys.executable, "-I", CHECK, *args], cwd=cwd, capture_output=True, text=True, timeout=300,
                          env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8"})


class AcceptanceKindsTest(unittest.TestCase):
    def test_only_kinds_the_gate_owns_or_perceptual(self):
        spec_ = importlib.util.spec_from_file_location("qa_gate_check", CHECK)
        mod = importlib.util.module_from_spec(spec_)
        spec_.loader.exec_module(mod)
        owned = set(mod.KINDS["reel"]) | {"perceptual"}
        kinds = {c["type"] for c in all_checks(load_json(SPEC))}
        self.assertEqual(kinds - owned, set())
        self.assertNotIn("spotlight_plan_guard", kinds)
        self.assertNotIn("spotlight_beats_guard", kinds)

    def test_the_recipe_guards_are_scripts_the_steps_run(self):
        self.assertIn("plan_guard.py", read("steps/03-plan-edit.md"))
        self.assertIn("beats_guard.py", read("steps/04-plan-broll.md"))

    def test_check_ids_are_unique(self):
        ids = [c["id"] for c in all_checks(load_json(SPEC))]
        self.assertEqual(len(ids), len(set(ids)))


class GateSpecTest(Tmp):
    def run_it(self, *extra, bed="22.5"):
        return py("gate_spec.py", "--spec", SPEC, "--bed-duration", bed, "--out", self.path("run.json"), *extra)

    def test_the_bed_length_is_written_only_where_the_gate_needs_it(self):
        r = self.run_it()
        self.assertEqual(r.returncode, 0, r.stderr)
        src, out = load_json(SPEC), load_json(self.path("run.json"))
        for a, b in zip(all_checks(src), all_checks(out)):
            want = dict(a)
            if a["type"] in ("json_words_nonempty", "luma_floor_windows"):
                want["expected_duration_s"] = 22.5
            self.assertEqual(b, want, a["id"])

    def test_no_broll_drops_the_look_and_the_window_source_and_nothing_else(self):
        self.assertEqual(self.run_it("--no-broll").returncode, 0)
        out = load_json(self.path("run.json"))
        ids = {c["id"] for c in all_checks(out)}
        self.assertNotIn("broll_beats_correct", ids)
        windows = [c for c in all_checks(out) if c["type"] == "luma_floor_windows"][0]
        self.assertEqual(windows["windows_from"], ["edit_plan.takeovers"])
        self.assertEqual(len(ids), len({c["id"] for c in all_checks(load_json(SPEC))}) - 1)

    def test_a_bad_length_is_refused(self):
        for bad in ("0", "-3", "nan", "9999"):
            with self.subTest(bad):
                self.assertNotEqual(self.run_it(bed=bad).returncode, 0)


@NEEDS_FFMPEG
class RealGateRunTest(Tmp):
    """Run the real gate on the spec: no check may come back as unsupported or unknown."""

    def setUp(self):
        super().setUp()
        self.wd = self.path("wd")
        os.makedirs(os.path.join(self.wd, "saves"))
        os.makedirs(os.path.join(self.wd, "prior"))
        os.makedirs(os.path.join(self.wd, "work"))
        subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x808080:s=1080x1920:r=30:d=22",
                        "-f", "lavfi", "-i", "sine=f=440:d=22", "-shortest", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "35",
                        "-pix_fmt", "yuv420p", "-c:a", "aac", os.path.join(self.wd, "saves", "final_video.mp4")], check=True)
        run = py("gate_spec.py", "--spec", SPEC, "--bed-duration", "22", "--out", os.path.join(self.wd, "work", "run.json"))
        self.assertEqual(run.returncode, 0, run.stderr)

    def scorecard(self, name):
        return load_json(os.path.join(self.wd, "work", name))

    def no_unsupported(self, card):
        for row in card["checks"]:
            self.assertNotRegex(row["detail"], r"not supported|not known", "%s: %s" % (row["id"], row["detail"]))

    def test_the_final_checks_run_and_the_looks_are_owed(self):
        r = gate("--kind", "reel", "--spec", "work/run.json", "--input", "saves/final_video.mp4", "--out", "work/scorecard.json", cwd=self.wd)
        self.assertIn(r.returncode, (0, 1, 4), r.stdout + r.stderr)
        card = self.scorecard("scorecard.json")
        self.no_unsupported(card)
        kinds = {row["type"] for row in card["checks"]}
        self.assertIn("perceptual", kinds)
        self.assertEqual(sum(1 for row in card["checks"] if row["status"] == "LOOK"), 8)
        mech = {row["id"]: row["status"] for row in card["checks"] if row["status"] != "LOOK"}
        for must in ("duration_window", "canvas_1080x1920", "frame_not_black"):
            self.assertEqual(mech[must], "PASS", mech)

    def test_the_interim_step_checks_run(self):
        w = self.wd
        # speakerbed: the bed picture
        r = gate("--kind", "reel", "--spec", "work/run.json", "--step", "speakerbed", "--input", "saves/final_video.mp4", "--out", "work/c1.json", cwd=w)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        # transcribe: words close to the end of a 22 s bed
        write_json(os.path.join(w, "saves", "transcripts.json"), {"words": [{"text": "hi", "start": 0.0, "end": 0.4}, {"text": "there", "start": 19.0, "end": 20.5}], "broll_cues": []})
        r = gate("--kind", "reel", "--spec", "work/run.json", "--step", "transcribe", "--input", "saves/transcripts.json", "--out", "work/c2.json", cwd=w)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        # transcribe with a last word far short of the bed must FAIL (the tail rule is live)
        write_json(os.path.join(w, "saves", "transcripts.json"), {"words": [{"text": "hi", "start": 0.0, "end": 0.4}], "broll_cues": []})
        r = gate("--kind", "reel", "--spec", "work/run.json", "--step", "transcribe", "--input", "saves/transcripts.json", "--out", "work/c2b.json", cwd=w)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        # render_scenes: windows read from the edit plan and the beat list in prior/
        write_json(os.path.join(w, "prior", "edit_plan.json"), {"takeovers": [{"start": 3, "end": 6}]})
        write_json(os.path.join(w, "prior", "beat_list.json"), {"beats": [{"kind": "broll", "start": 10, "end": 13}, {"kind": "graphics", "start": 14, "end": 16}]})
        r = gate("--kind", "reel", "--spec", "work/run.json", "--step", "render_scenes", "--input", "saves/final_video.mp4", "--out", "work/c3.json", cwd=w)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rows = self.scorecard("c3.json")["checks"]
        self.assertEqual(rows[0]["status"], "PASS")
        # research and script: the server steps' checks
        write_json(os.path.join(w, "saves", "sources.json"), [{"title": "t", "url": "u"}])
        r = gate("--kind", "reel", "--spec", "work/run.json", "--step", "research", "--input", "saves/sources.json", "--out", "work/c4.json", cwd=w)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        write_text(os.path.join(w, "saves", "approved_script.md"), " ".join(["word"] * 100))
        r = gate("--kind", "reel", "--spec", "work/run.json", "--step", "script", "--input", "saves/approved_script.md", "--out", "work/c5.json", cwd=w)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_without_the_no_broll_flag_a_missing_beat_list_fails_loudly(self):
        write_json(os.path.join(self.wd, "prior", "edit_plan.json"), {"takeovers": []})
        r = gate("--kind", "reel", "--spec", "work/run.json", "--step", "render_scenes", "--input", "saves/final_video.mp4", "--out", "work/c6.json", cwd=self.wd)
        self.assertEqual(r.returncode, 1)
        self.assertIn("beat_list.json was not found", json.dumps(self.scorecard("c6.json")))


if __name__ == "__main__":
    unittest.main()
