#!/usr/bin/env python3
"""The recipe's files agree with each other and with the blocks they call.

  python3 -I recipes/r-reels-pip/test/test_recipe_files.py -v

Offline. Reads the recipe's files and the blocks in ../../blocks. One test runs the real
blocks/b-qa-gate/check.py on a small generated reel and proves that no check kind of
acceptance.json is "not supported".
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
RECIPE = os.path.dirname(HERE)
BLOCKS = os.path.join(os.path.dirname(os.path.dirname(RECIPE)), "blocks")
GATE = os.path.join(BLOCKS, "b-qa-gate", "check.py")
FFMPEG = shutil.which("ffmpeg") and shutil.which("ffprobe")


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def recipe_files():
    for root, dirs, files in os.walk(RECIPE):
        dirs[:] = [d for d in dirs if d not in ("__pycache__",)]
        for name in files:
            yield os.path.join(root, name)


STEPS = sorted(f for f in os.listdir(os.path.join(RECIPE, "steps")) if f.endswith(".md"))


class FilesAgree(unittest.TestCase):
    def setUp(self):
        self.skill = read(os.path.join(RECIPE, "SKILL.md"))
        self.manifest = json.loads(read(os.path.join(RECIPE, "manifest.json")))
        self.steps = {n: read(os.path.join(RECIPE, "steps", n)) for n in STEPS}

    def test_names(self):
        self.assertIn("name: r-reels-pip", self.skill)
        self.assertEqual(self.manifest["recipe"], "r-reels-pip")
        self.assertEqual(json.loads(read(os.path.join(RECIPE, "acceptance.json")))["recipe"], "r-reels-pip")
        self.assertEqual(os.path.basename(RECIPE), "r-reels-pip")

    def test_skill_md_is_short_and_holds_no_command_blocks(self):
        self.assertLess(len(self.skill.splitlines()), 200)
        self.assertNotRegex(self.skill, r"```(bash|sh)\b", "commands live in steps/")

    def test_every_manifest_step_has_a_file_named_in_skill_md_and_every_save_is_named(self):
        for step in self.manifest["steps"]:
            self.assertTrue(os.path.isfile(os.path.join(RECIPE, step["instructions"])), step["instructions"])
            self.assertIn(step["instructions"], self.skill)
            for save in step["saves"]:
                self.assertIn(save["id"], self.skill)

    def test_blocks_declared_are_the_blocks_the_steps_call_and_they_exist(self):
        front = re.search(r"^blocks: \[(.*)\]$", self.skill, re.M)
        declared = {b.strip() for b in front.group(1).split(",")}
        used = set()
        for text in self.steps.values():
            used |= {m for m in re.findall(r"\bb-[a-z0-9]+(?:-[a-z0-9]+)*", text) if os.path.isdir(os.path.join(BLOCKS, m))}
        self.assertEqual(used, declared)
        for b in declared:
            self.assertTrue(os.path.isdir(os.path.join(BLOCKS, b)), b)

    def test_every_block_file_a_step_names_exists(self):
        for name, text in self.steps.items():
            for rel in re.findall(r'\$BLOCKS_DIR/(b-[a-z0-9-]+/[A-Za-z0-9_./-]+)', text):
                self.assertTrue(os.path.isfile(os.path.join(BLOCKS, rel)), "%s names %s" % (name, rel))

    def test_every_recipe_script_a_step_names_exists_and_none_is_unused(self):
        named = set()
        for name, text in self.steps.items():
            for rel in re.findall(r'\$RECIPE_DIR/((?:scripts|checks)/[A-Za-z0-9_./-]+)', text):
                self.assertTrue(os.path.isfile(os.path.join(RECIPE, rel)), "%s names %s" % (name, rel))
                named.add(os.path.basename(rel))
        scripts = {f for f in os.listdir(os.path.join(RECIPE, "scripts")) if f.endswith((".py", ".sh"))}
        unused = scripts - named - {"cta_copy.py", "verify-skill.sh"}   # cta_copy is imported by cta_takeover
        self.assertEqual(unused, set())

    def test_steps_use_the_block_scripts_the_way_their_readmes_document(self):
        text = "\n".join(self.steps.values())
        for needle in ("transcribe.py", "--tool whisper-cpp", "--tool-version", "validate-scene-plan.js", "plan.js",
                       "check_plan.py", "build_comp.py", "mux.py", "qa.py", "hf_install.py", "fetch_gsap.py --outdir vendor",
                       "hf_render.py", "--format mov", "--quiet", "--captions-mov", "--no-captions", "--grade", "--cover-tolerance", "check.py\" --kind reel", "--finalize", "--answers"):
            self.assertIn(needle, text, needle)
        for banned in ("npx hyperframes", "hyperframes transcribe", "typing_prompt", "check_premium_plan", "eval-run", "qa-gate.sh",
                       "--visuals", "dangerously", "eval ", "bash -c", "curl ", "wget ", "overlay-", "transcript-match --"):
            self.assertNotIn(banned, text, banned)
        self.assertNotRegex(text.lower(), r"overlay.fx|overlay beats|overlay_beats|overlay step")

    def test_no_old_names_private_words_or_paths_anywhere_in_the_recipe(self):
        words = ["/Us" + "ers/", "vas" + "anth", "hyphen" + "labs", "growth" + "systems", "railway" + r"\.app", "@gm" + "ail.com",
                 "cfw-" + "render", "her" + "mes", "run_" + "skill", "skill-" + "runner", r"\.h" + "ub/", "/home/" + "node",
                 "WI[0-9]+", "CFW-[0-9]+", "VAS-[0-9]+", "sync-" + "skills", "fl" + "oe", "eval-" + "runner", "overlay-" + "fx",
                 "skip-" + "permissions"]
        private = re.compile("|".join(words), re.I)
        old = re.compile(r"(^|[^a-z0-9])(p|c|f)-[a-z]{3,}")
        for path in recipe_files():
            if path.endswith(".png") or os.path.basename(path) == os.path.basename(__file__):
                continue
            text = read(path)
            for rx, what in ((private, "private word"), (old, "old name")):
                m = rx.search(text)
                self.assertIsNone(m, "%s in %s: %r" % (what, os.path.relpath(path, RECIPE), m.group(0) if m else ""))

    def test_every_ffmpeg_and_ffprobe_call_allows_only_the_file_protocol(self):
        """README: -protocol_whitelist file before each input of every ffmpeg and ffprobe call in the steps and scripts."""
        for name, text in self.steps.items():
            for block in re.findall(r"```bash\n(.*?)```", text, re.S):
                logical = block.replace("\\\n", " ")
                for line in logical.splitlines():
                    for m in re.finditer(r"\bff(?:mpeg|probe)\b(?=\s+-)", line):
                        # every call on the line: the text up to the next call must hold the whitelist
                        rest = line[m.start():]
                        nxt = re.search(r"\bff(?:mpeg|probe)\b(?=\s+-)", rest[1:])
                        call = rest[:nxt.start() + 1] if nxt else rest
                        self.assertIn("protocol_whitelist", call, "%s: %s" % (name, call[:90]))
            for m in re.finditer(r"\['ffprobe'[^\]]*\]", text):
                self.assertIn("protocol_whitelist", m.group(0), name)
        for path in recipe_files():
            if path.endswith(".py") and os.sep + "scripts" + os.sep in path:
                text = read(path)
                calls = len(re.findall(r'\["(?:ffmpeg|ffprobe)"', text))
                self.assertGreaterEqual(text.count("protocol_whitelist"), calls, os.path.basename(path))

    def test_step_06_stops_on_a_failed_gate_and_saves_the_final_video_only_after_the_delivery_check(self):
        text = self.steps["06-final-checks.md"]
        self.assertIn("check_delivery.py", text)
        self.assertIn("--input work/final_video.mp4", text)
        self.assertNotRegex(text, r'echo "(gate|finalize) exit: \$\?"\n(?!\[)')   # an echo of the exit code alone does not stop anything
        self.assertLess(text.index("check_delivery.py\" --video work/final_video.mp4"), text.index("cp work/final_video.mp4 saves/final_video.mp4"))
        self.assertNotIn("-movflags +faststart saves/final_video.mp4", text)

    def test_option_lists_are_arrays_never_unquoted_text_strings(self):
        """zsh does not split an unquoted string: every $..ARGS must be "${NAME[@]}" and every one is assigned with ( )."""
        for name, text in self.steps.items():
            for m in re.finditer(r'\$\{?[A-Za-z_]*(?:ARGS|OPTS|FLAGS)\b[^\s]*', text):
                self.assertRegex(m.group(0), r'^\$\{[A-Za-z_]+\[@\]\}"', "%s: %s" % (name, m.group(0)))
                self.assertEqual(text[m.start() - 1], '"', "%s: %s is not quoted" % (name, m.group(0)))
            for m in re.finditer(r'\b[A-Z_]*(?:ARGS|OPTS|FLAGS)=([^\s]?)', text):
                self.assertEqual(m.group(1), "(", "%s: an option list is assigned as text" % name)

    def test_recipe_dir_must_be_absolute_and_every_step_checks_it(self):
        for name, text in self.steps.items():
            if name == "_shared.md":
                self.assertIn("absolute", text)
                continue
            self.assertIn('case "$RECIPE_DIR" in /*) ;; *)', text, name)
            self.assertIn('BLOCKS_DIR="$(cd "$RECIPE_DIR/../../blocks" && pwd)" || exit 1', text, name)
            self.assertNotRegex(text, r'(?<!")\$(RECIPE_DIR|BLOCKS_DIR)\b', name)
            self.assertNotIn("RECIPE_DIR=recipes/", text, name)
        self.assertNotIn("RECIPE_DIR=recipes/", self.steps["_shared.md"])

    def test_manifest_checks_and_step_06_list_every_acceptance_id(self):
        acc = json.loads(read(os.path.join(RECIPE, "acceptance.json")))
        ids = [c["id"] for c in acc["checks"]]
        final = [s for s in self.manifest["steps"] if s["id"] == "final_checks"][0]
        self.assertEqual([c["id"] for c in final["checks"]], ids)
        looks = [c for c in acc["checks"] if c["type"] == "perceptual"]
        self.assertEqual(len(looks), 9)
        for c in looks:
            self.assertIn("`%s`" % c["id"], self.steps["06-final-checks.md"], c["id"])

    def test_the_shared_notes_say_shells_prior_and_ignorable_warnings(self):
        s = self.steps["_shared.md"]
        for needle in ("zsh", "mkdir -p prior && cp saves/* prior/", "overlapping_gsap_tweens", "An **error** is never ignored"):
            self.assertIn(needle, s, needle)

    def test_the_minimal_scene_plan_in_step_03_is_valid_for_the_real_validator(self):
        node = shutil.which("node")
        if not node or not os.path.isfile(os.path.join(BLOCKS, "b-broll-sync", "scripts", "validate-scene-plan.js")):
            self.skipTest("needs node and blocks/b-broll-sync")
        text = self.steps["03-plan-beats.md"]
        plan = re.search(r"```json\n(\{ \"version\": 1.*?)```", text, re.S).group(1)
        d = tempfile.mkdtemp(prefix="pip-plan-")
        try:
            with open(os.path.join(d, "plan.json"), "w") as fh:
                fh.write(plan)
            p = subprocess.run([node, os.path.join(BLOCKS, "b-broll-sync", "scripts", "validate-scene-plan.js"), "plan.json", "--bed-dur", "30"],
                               cwd=d, capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            self.assertIn('"version": 1', plan)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_the_sound_effects_are_not_copied_into_the_recipe(self):
        self.assertEqual([f for f in recipe_files() if f.endswith((".wav", ".mp3"))], [])


@unittest.skipUnless(FFMPEG and os.path.isfile(GATE), "needs ffmpeg and blocks/b-qa-gate")
class AcceptanceRunsInTheGate(unittest.TestCase):
    """The spec only uses check kinds b-qa-gate owns: none is reported as not supported."""

    @classmethod
    def setUpClass(cls):
        cls.d = tempfile.mkdtemp(prefix="pip-gate-")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=1080x1920:r=30:d=21",
                        "-f", "lavfi", "-i", "sine=frequency=300:sample_rate=48000:duration=21", "-af", "loudnorm=I=-14:TP=-1.5",
                        "-ar", "48000", "-ac", "2", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac",
                        "-shortest", "final.mp4"], cwd=cls.d, check=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", "final.mp4", "-an", "-c:v", "copy", "silent.mp4"], cwd=cls.d, check=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.d, ignore_errors=True)

    def gate(self, args):
        return subprocess.run([sys.executable, GATE] + args, cwd=self.d, capture_output=True, text=True)

    def rows(self, name):
        with open(os.path.join(self.d, name), encoding="utf-8") as fh:
            return json.load(fh)["checks"]

    def test_every_check_kind_in_the_spec_is_known(self):
        spec = os.path.join(RECIPE, "acceptance.json")
        p = self.gate(["--kind", "reel", "--spec", spec, "--input", "final.mp4", "--out", "sc.json"])
        self.assertIn(p.returncode, (0, 4), p.stdout + p.stderr)
        rows = self.rows("sc.json")
        for r in rows:
            self.assertNotIn("not supported", r["detail"].lower(), r)
            self.assertNotIn("unknown", r["detail"].lower(), r)
            self.assertIn(r["status"], ("PASS", "LOOK"), r)
        ids = {r["id"] for r in rows}
        self.assertTrue({"qa_gate.loudness", "duration_window", "canvas_1080x1920", "frame_not_black", "face_whole_in_pip"} <= ids)
        looks = [r["id"] for r in rows if r["status"] == "LOOK"]
        self.assertEqual(len(looks), 9)
        answers = {i: {"answer": "yes", "note": "test"} for i in looks}
        with open(os.path.join(self.d, "answers.json"), "w") as fh:
            json.dump(answers, fh)
        f = self.gate(["--finalize", "sc.json", "--answers", "answers.json", "--out", "final-sc.json"])
        self.assertEqual(f.returncode, 0, f.stdout + f.stderr)

    def test_the_two_interim_lists_run(self):
        spec = os.path.join(RECIPE, "acceptance.json")
        p = self.gate(["--kind", "reel", "--spec", spec, "--step", "voicebed", "--input", "final.mp4", "--out", "bed.json"])
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual({r["id"] for r in self.rows("bed.json")}, {"bed_loudness", "bed_has_speech"})
        q = self.gate(["--kind", "reel", "--spec", spec, "--step", "background", "--input", "silent.mp4", "--out", "bg.json"])
        self.assertEqual(q.returncode, 0, q.stdout + q.stderr)
        self.assertEqual({r["id"] for r in self.rows("bg.json")}, {"bg_track_dims", "bg_track_not_black"})

    def run_step6(self, answers):
        """Step 06's own gate and finalize blocks, on the generated reel, with the given answers."""
        wd = tempfile.mkdtemp(dir=self.d)
        os.makedirs(os.path.join(wd, "work"))
        os.makedirs(os.path.join(wd, "saves"))
        shutil.copy(os.path.join(self.d, "final.mp4"), os.path.join(wd, "work", "final_video.mp4"))
        blocks = re.findall(r"```bash\n(.*?)```", read(os.path.join(RECIPE, "steps", "06-final-checks.md")), re.S)
        gate = [b for b in blocks if "--kind reel" in b][0]
        final = [b for b in blocks if "--finalize" in b][0]
        env = dict(os.environ, RECIPE_DIR=RECIPE, BLOCKS_DIR=BLOCKS)
        g = subprocess.run(["bash", "-c", gate], cwd=wd, env=env, capture_output=True, text=True)
        self.assertEqual(g.returncode, 0, g.stdout + g.stderr)
        with open(os.path.join(wd, "work", "scorecard.json"), encoding="utf-8") as fh:
            looks = [r["id"] for r in json.load(fh)["checks"] if r["status"] == "LOOK"]
        with open(os.path.join(wd, "work", "answers.json"), "w") as fh:
            json.dump(answers(looks), fh)
        f = subprocess.run(["bash", "-c", final], cwd=wd, env=env, capture_output=True, text=True)
        return wd, f

    def test_step_06_delivers_only_after_every_look_is_answered_yes(self):
        wd, f = self.run_step6(lambda looks: {i: {"answer": "yes", "note": "test"} for i in looks})
        self.assertEqual(f.returncode, 0, f.stdout + f.stderr)
        self.assertTrue(os.path.isfile(os.path.join(wd, "saves", "final_video.mp4")))
        self.assertIn("DELIVERY OK", f.stdout)

    def test_step_06_stops_on_a_no_a_missing_answer_and_a_failed_gate(self):
        for name, answers in (("a no", lambda looks: {i: {"answer": "no" if k == 0 else "yes", "note": "t"} for k, i in enumerate(looks)}),
                              ("a missing answer", lambda looks: {i: {"answer": "yes", "note": "t"} for i in looks[1:]})):
            wd, f = self.run_step6(answers)
            self.assertNotEqual(f.returncode, 0, name)
            self.assertFalse(os.path.exists(os.path.join(wd, "saves", "final_video.mp4")), name)
        # a failed gate: the video is black, so the gate exits 1 and the gate block itself stops
        wd = tempfile.mkdtemp(dir=self.d)
        os.makedirs(os.path.join(wd, "work"))
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=black:s=1080x1920:d=2", "-pix_fmt", "yuv420p",
                        os.path.join(wd, "work", "final_video.mp4")], check=True)
        gate = [b for b in re.findall(r"```bash\n(.*?)```", read(os.path.join(RECIPE, "steps", "06-final-checks.md")), re.S) if "--kind reel" in b][0]
        g = subprocess.run(["bash", "-c", gate + "\necho REACHED_AFTER_GATE"], cwd=wd, env=dict(os.environ, RECIPE_DIR=RECIPE, BLOCKS_DIR=BLOCKS),
                           capture_output=True, text=True)
        self.assertNotEqual(g.returncode, 0)
        self.assertNotIn("REACHED_AFTER_GATE", g.stdout)

    def test_a_swapped_final_video_is_caught_against_a_real_scorecard(self):
        wd, f = self.run_step6(lambda looks: {i: {"answer": "yes", "note": "t"} for i in looks})
        self.assertEqual(f.returncode, 0)
        with open(os.path.join(wd, "saves", "final_video.mp4"), "ab") as fh:
            fh.write(b"tampered")
        p = subprocess.run([sys.executable, os.path.join(RECIPE, "scripts", "check_delivery.py"), "--video", "saves/final_video.mp4",
                            "--scorecard", "work/final-scorecard.json"], cwd=wd, capture_output=True, text=True)
        self.assertEqual(p.returncode, 1)
        self.assertIn("not the file the gate checked", p.stdout)

    def test_an_unknown_kind_would_fail_not_skip(self):
        spec = {"recipe": "x", "checks": [{"id": "z", "kind": "mechanical", "type": "overlay_guard"}]}
        with open(os.path.join(self.d, "bad-spec.json"), "w") as fh:
            json.dump(spec, fh)
        p = self.gate(["--kind", "reel", "--spec", "bad-spec.json", "--input", "final.mp4", "--out", "bad.json"])
        self.assertEqual(p.returncode, 1)
        self.assertEqual(self.rows("bad.json")[0]["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
