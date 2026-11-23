"""Offline contract proof for r-reels-faceless, not a three-host render claim.

No paid provider/network call, server, model download or live order. Small
synthetic FFmpeg probes run only in owned temporary directories.
"""
import ast
import copy
import importlib.util
import json
import os
from pathlib import Path, PureWindowsPath
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("faceless_contracts", ROOT / "scripts/contracts.py")
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


def claim():
    snapshot = {"version": 1, "brandId": "brand-a", "palette": {"background": "#102030", "text": "#FFFFFF"},
                "fonts": {"headingFont": "Example Sans"},
                "renderProfile": {"version": 1, "cta": {"line": "Read the guide"},
                                  "elevenlabs": {"voiceId": "syntheticVoice123", "stability": 0.4}}}
    brand = {"id": "brand-a", "name": "Synthetic Brand", **{k: snapshot[k] for k in ("palette", "fonts", "renderProfile")},
             "providerKeys": {"elevenlabs": "fake-private-value"}}
    return {"id": "order-a", "brandId": "brand-a", "brandDna": snapshot,
            "taskOrder": {"orderId": "order-a", "brand": brand}}


def beats():
    return {"bed_duration": 10, "beats": [
        {"index": 0, "kind": "graphics", "slug": "beat0-hook", "start": 0, "end": 5,
         "scene": {"title_html": "A clear hook", "type": "hook"}},
        {"index": 1, "kind": "graphics", "slug": "beat1-cta", "start": 5, "end": 10,
         "scene": {"title_html": "Read the guide", "type": "cta"}}]}


class PrivateClaim(unittest.TestCase):
    def test_frozen_identity_defaults_and_no_provider_secrets(self):
        original, brief = claim(), {"intent": "Keep this", "options": {"grade": "off"}}
        before = copy.deepcopy(original)
        result = c.private_brand(original, brief)
        self.assertEqual(original, before)
        self.assertEqual(brief, {"intent": "Keep this", "options": {"grade": "off"}})
        self.assertEqual(result["brand"]["cta"], "Read the guide")
        self.assertEqual(result["brand"]["handle"], "")
        self.assertEqual(result["brand"]["palette"]["bg"], "#102030")
        self.assertEqual(result["brand"]["typography"]["display"], "Example Sans")
        self.assertEqual(result["brand"]["elevenlabs"]["stability"], 0.4)
        self.assertNotIn("fake-private-value", json.dumps(result))

    def test_wrong_order_brand_or_snapshot_fails_without_mutation(self):
        for mutate in (lambda v: v["taskOrder"].update(orderId="other"),
                       lambda v: v["taskOrder"]["brand"].update(id="other"),
                       lambda v: v["brandDna"].update(brandId="other"),
                       lambda v: v["brandDna"].update(version=True),
                       lambda v: v["brandDna"].update(extra="unknown"),
                       lambda v: v["taskOrder"]["brand"].update(palette={"bg": "#FFFFFF"})):
            value = claim()
            mutate(value)
            before = copy.deepcopy(value)
            with self.assertRaisesRegex(ValueError, "Invalid or mismatched"):
                c.private_brand(value, {})
            self.assertEqual(value, before)

    def test_arbitrary_profile_fields_and_bad_palette_refused(self):
        for path, bad in (("renderProfile", {"apiKey": "fake"}), ("palette", {"bg": "url(private)"}),
                          ("renderProfile", []), ("fonts", {"display": "x" * 101})):
            value = claim()
            value["brandDna"][path] = bad
            value["taskOrder"]["brand"][path] = bad
            with self.assertRaises(ValueError):
                c.private_brand(value, {})


class BeatSafety(unittest.TestCase):
    def test_normal_beats_and_safe_native_paths(self):
        value = beats()
        self.assertIs(c.validate_beats(value, 10), value)
        for beat in value["beats"]:
            native = PureWindowsPath("C:/Private order") / "gfx" / beat["slug"] / "index.html"
            self.assertEqual(native.drive, "C:")
            self.assertTrue(str(native).startswith("C:\\Private order\\gfx\\beat"))

    def test_traversal_shell_text_duplicate_and_unordered_refused(self):
        for slug in ("../escape", "C:\\escape", "a/b", "a'b", "$(whoami)", "..", "", "a" * 81):
            value = beats()
            value["beats"][0]["slug"] = slug
            with self.assertRaisesRegex(ValueError, "slug"):
                c.validate_beats(value, 10)
        value = beats()
        value["beats"][1]["slug"] = value["beats"][0]["slug"]
        with self.assertRaises(ValueError):
            c.validate_beats(value, 10)

    def test_gap_wrong_cta_blank_and_wrong_bed_refused(self):
        for mutate in (lambda v: v["beats"][0].update(end=4),
                       lambda v: v["beats"][0].update(index=1),
                       lambda v: v["beats"][0]["scene"].update(title_html=""),
                       lambda v: v["beats"][1]["scene"].update(type="standard"),
                       lambda v: v.update(bed_duration=11),
                       lambda v: v["beats"][1].update(end=float("inf"))):
            value = beats()
            mutate(value)
            with self.assertRaises(ValueError):
                c.validate_beats(value, 10)


class NativeInstructions(unittest.TestCase):
    def test_active_python_examples_parse_and_no_shell_execution_blocks(self):
        docs = [ROOT / "SKILL.md", *(ROOT / "steps").glob("*.md")]
        examples = 0
        for path in docs:
            text = path.read_text()
            self.assertNotRegex(text, r"```(?:bash|sh|zsh|powershell)\b", path.name)
            self.assertNotIn("eval \"$", text)
            self.assertNotIn("--dangerously-skip" + "-permissions", text)
            for code in re.findall(r"```python\n(.*?)```", text, re.S):
                ast.parse(code, filename=path.name)
                examples += 1
        self.assertGreaterEqual(examples, 4)

    def test_source_version_and_truthful_requirements(self):
        manifest = json.loads((ROOT / "manifest.json").read_text())
        self.assertEqual(manifest["recipeVersion"], "2026.11.7")
        self.assertEqual(set(manifest["needs"]["os"]), {"windows", "macos", "linux"})
        self.assertIn("whisper-cpp", manifest["needs"]["tools"])
        self.assertEqual(manifest["recipe"], "r-reels-faceless")
        self.assertNotIn("imagemagick", manifest["needs"]["tools"])
        saves = [s["id"] for step in manifest["steps"] for s in step.get("saves", [])]
        self.assertIn("qa_report", saves)
        for step in manifest["steps"]:
            if "instructions" in step:
                self.assertTrue((ROOT / step["instructions"]).is_file())

    def test_contract_module_has_no_executor_or_network(self):
        tree = ast.parse((ROOT / "scripts/contracts.py").read_text())
        imports = {node.names[0].name for node in ast.walk(tree) if isinstance(node, ast.Import)}
        self.assertEqual(imports, {"json", "math", "re"})


class LocalToolProof(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "native Node not installed")
    def test_planner_no_broll_and_pinned_broll_never_spawn_nested_host(self):
        dependency = ROOT.parent.parent / "blocks/b-broll-sync/scripts"
        self.assertTrue(dependency.is_dir(), "blocks/b-broll-sync is missing")
        with tempfile.TemporaryDirectory(prefix="faceless native - ' ") as directory:
            wd = Path(directory)
            marker = wd / "nested-attempt.txt"
            (wd / "deny-child.cjs").write_text("const cp=require('child_process'); cp.spawnSync=cp.execSync=()=>{require('fs').appendFileSync("
                                               + json.dumps(str(marker)) + ",'attempt');throw new Error('Nested process forbidden')};")
            (wd / "words.json").write_text(json.dumps([{"text": "word%d" % i, "start": i / 2, "end": i / 2 + 0.4} for i in range(20)]))
            (wd / "brand.json").write_text("{}")
            (wd / "inputs").mkdir()
            (wd / "inputs" / "clip.mp4").write_bytes(b"stand-in")
            for broll in (False, True):
                scenes = [{"id": "hook", "kind": "graphic", "start": 0, "end": 4, "headline": "A clear hook", "type": "hook"},
                          {"id": "content", "kind": "graphic", "start": 4, "end": 6, "headline": "One point", "type": "stat"},
                          {"id": "cta", "kind": "graphic", "start": 6, "end": 10, "headline": "Read the guide", "type": "cta"}]
                if broll:
                    scenes[1] = {"id": "broll", "kind": "broll", "start": 4, "end": 6, "asset": "clip.mp4", "in": 0}
                    (wd / "broll.json").write_text(json.dumps([{"clip": "inputs/clip.mp4", "duration": 3, "cues": []}]))
                (wd / "scenes.json").write_text(json.dumps({"version": 1, "bed_duration": 10, "scenes": scenes}))
                args = ["node", "--require", str(wd / "deny-child.cjs"), str(dependency / "plan.js"),
                        "--transcript", "words.json", "--scene-plan", "scenes.json", "--bed-dur", "10",
                        "--brand", "brand.json", "--order", "as-given", "--out", "beats.json"]
                if broll:
                    args += ["--broll", "broll.json"]
                result = subprocess.run(args, cwd=wd, text=True, capture_output=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse(marker.exists(), "Planner attempted a forbidden nested process, even if its error was caught")
                value = json.loads((wd / "beats.json").read_text())
                c.validate_beats(value, 10)
                self.assertEqual(any(b["kind"] == "broll" for b in value["beats"]), broll)
            refused = subprocess.run(args[:-2] + ["--order", "transcript-match", "--out", "beats.json"], cwd=wd,
                                     text=True, capture_output=True, timeout=30)
            self.assertEqual(refused.returncode, 2, "the removed ordering must be refused")

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "native FFmpeg tools not installed")
    def test_relative_safe_concat_in_unicode_space_quote_parent(self):
        with tempfile.TemporaryDirectory(prefix="faceless native — ' ") as directory:
            wd = Path(directory)
            for index, colour in enumerate(("red", "blue")):
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                                "color=c=%s:s=32x32:r=30:d=0.2" % colour, "-c:v", "libx264", "-pix_fmt", "yuv420p",
                                str(wd / ("seg-%04d.mp4" % index))], check=True, capture_output=True, timeout=30)
            (wd / "concat.txt").write_text("file 'seg-0000.mp4'\nfile 'seg-0001.mp4'\n", encoding="utf-8")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "1", "-i", str(wd / "concat.txt"),
                            "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(wd / "joined.mp4")],
                           check=True, capture_output=True, timeout=30)
            probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height:format=duration",
                                    "-of", "json", str(wd / "joined.mp4")], check=True, capture_output=True, text=True, timeout=30)
            value = json.loads(probe.stdout)
            self.assertEqual((value["streams"][0]["width"], value["streams"][0]["height"]), (32, 32))
            self.assertAlmostEqual(float(value["format"]["duration"]), 0.4, places=1)


def run_script(name, *args, cwd):
    return subprocess.run([sys.executable, "-I", str(ROOT / "scripts" / name), *args], cwd=cwd, text=True,
                          capture_output=True, timeout=120)


class WordsAndBeatsChecks(unittest.TestCase):
    def words(self, n=24, step=0.4):
        return [{"text": "w%d" % i, "start": round(i * step, 3), "end": round(i * step + 0.3, 3)} for i in range(n)]

    def test_check_words_passes_and_writes_transcripts_inside_the_folder(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "words.json").write_text(json.dumps(self.words()))
            r = run_script("check_words.py", "--words", "words.json", "--bed-duration", "10", "--out", "saves/transcripts.json", cwd=d)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            saved = json.loads(Path(d, "saves/transcripts.json").read_text())
            self.assertEqual(len(saved["words"]), 24)
            self.assertEqual(saved["duration"], 10)

    def test_check_words_refuses_bad_words(self):
        bad = {"too few": self.words(5), "backwards start": self.words()[:20] + [{"text": "x", "start": 0.1, "end": 0.2}],
               "ends before start": [dict(w, end=w["start"] - 0.1) if i == 3 else w for i, w in enumerate(self.words())],
               "after the bed": self.words(40), "nan time": [dict(w, start=float("nan")) if i == 2 else w for i, w in enumerate(self.words())],
               "no text": [dict(w, text=" ") if i == 1 else w for i, w in enumerate(self.words())]}
        for label, words in bad.items():
            with tempfile.TemporaryDirectory() as d:
                Path(d, "words.json").write_text(json.dumps(words))
                r = run_script("check_words.py", "--words", "words.json", "--bed-duration", "10", "--out", "t.json", cwd=d)
                self.assertEqual(r.returncode, 1, label + r.stdout + r.stderr)
                self.assertFalse(Path(d, "t.json").exists(), label)

    def test_check_words_refuses_paths_outside_the_folder(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as other:
            Path(other, "words.json").write_text(json.dumps(self.words()))
            r = run_script("check_words.py", "--words", str(Path(other, "words.json")), "--bed-duration", "10", "--out", "t.json", cwd=d)
            self.assertEqual(r.returncode, 2)

    def test_check_beats_needs_real_clips_inside_inputs(self):
        plan = {"bed_duration": 10, "beats": [
            {"index": 0, "kind": "graphics", "slug": "beat0-a", "start": 0, "end": 4, "scene": {"title_html": "A", "type": "hook"}},
            {"index": 1, "kind": "broll", "start": 4, "end": 7, "broll": {"clip": "inputs/a.mp4", "in": 0, "out": 3}},
            {"index": 2, "kind": "graphics", "slug": "beat2-cta", "start": 7, "end": 10, "scene": {"title_html": "B", "type": "cta"}}]}
        with tempfile.TemporaryDirectory() as d:
            Path(d, "inputs").mkdir()
            Path(d, "beats.json").write_text(json.dumps(plan))
            r = run_script("check_beats.py", "--beats", "beats.json", "--bed-duration", "10", cwd=d)
            self.assertEqual(r.returncode, 1, "a missing clip must fail")
            Path(d, "inputs/a.mp4").write_bytes(b"x")
            r = run_script("check_beats.py", "--beats", "beats.json", "--bed-duration", "10", cwd=d)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("b-roll 30%", r.stdout)
            plan["beats"][1]["broll"]["out"] = 1
            Path(d, "beats.json").write_text(json.dumps(plan))
            self.assertEqual(run_script("check_beats.py", "--beats", "beats.json", "--bed-duration", "10", cwd=d).returncode, 1,
                             "a window shorter than the beat must fail")
            plan["beats"][1]["broll"].update(out=3, clip="../outside.mp4")
            Path(d, "beats.json").write_text(json.dumps(plan))
            self.assertEqual(run_script("check_beats.py", "--beats", "beats.json", "--bed-duration", "10", cwd=d).returncode, 1)


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "native FFmpeg tools not installed")
class LoudnessMaster(unittest.TestCase):
    def test_two_pass_master_reaches_the_target_and_keeps_the_picture(self):
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=gray:s=160x284:r=30:d=6", "-f", "lavfi",
                            "-i", "sine=f=220:d=6", "-af", "tremolo=f=3:d=0.7,volume=0.1", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                            "-c:a", "aac", "in.mp4"], cwd=d, check=True, capture_output=True, timeout=60)
            r = run_script("master_loudness.py", "--in", "in.mp4", "--out", "saves/out.mp4", cwd=d)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            m = subprocess.run(["ffmpeg", "-hide_banner", "-i", "saves/out.mp4", "-af", "ebur128", "-f", "null", "-"], cwd=d,
                               capture_output=True, text=True, timeout=60)
            lufs = float(re.findall(r"I:\s+(-?[\d.]+) LUFS", m.stderr)[-1])
            self.assertLess(abs(lufs + 14), 1.5, m.stderr[-300:])
            info = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,width,height,channels,sample_rate",
                                              "-of", "json", "saves/out.mp4"], cwd=d, capture_output=True, text=True).stdout)
            names = {x["codec_name"] for x in info["streams"]}
            self.assertEqual(names, {"h264", "aac"})

    def test_refuses_paths_outside_the_folder_and_same_file(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as other:
            Path(d, "in.mp4").write_bytes(b"x")
            for args in (["--in", "in.mp4", "--out", str(Path(other, "o.mp4"))], ["--in", "in.mp4", "--out", "in.mp4"],
                         ["--in", str(Path(other, "i.mp4")), "--out", "o.mp4"], ["--in", "in.mp4", "--out", "o.mp4", "--target", "5"]):
                self.assertEqual(run_script("master_loudness.py", *args, cwd=d).returncode, 2, args)

    def test_unparsable_or_missing_measurement_is_a_failure(self):
        spec2 = importlib.util.spec_from_file_location("master_loudness", ROOT / "scripts/master_loudness.py")
        m = importlib.util.module_from_spec(spec2)
        spec2.loader.exec_module(m)
        for text in ("no json here", '{"input_i": "-inf", "input_tp": "-1", "input_lra": "1", "input_thresh": "-40", "target_offset": "0"}',
                     '{"input_i": "-20"}'):
            with self.assertRaises((ValueError, KeyError)):
                m.parse_stats(text)
        stats = m.parse_stats('x {"input_i": "-20.1", "input_tp": "-3", "input_lra": "5", "input_thresh": "-30", "target_offset": "0.4"}')
        self.assertIn("linear=true", m.apply_filter(stats, -14.0))


class StepsMatchBlocks(unittest.TestCase):
    """The steps may call only block and recipe scripts that exist, by relative path variables."""

    def docs(self):
        return [ROOT / "SKILL.md", ROOT / "README.md", *sorted((ROOT / "steps").glob("*.md"))]

    def test_every_block_and_recipe_path_in_the_docs_exists(self):
        blocks = ROOT.parent.parent / "blocks"
        seen = 0
        for path in self.docs():
            text = path.read_text()
            for rel in set(re.findall(r"\$BLOCKS_DIR/(b-[a-z-]+/[\w./-]+?)(?=[\s`)\x22]|$)", text)):
                self.assertTrue((blocks / rel).exists(), "%s names a missing block file: %s" % (path.name, rel))
                seen += 1
            for rel in set(re.findall(r"\$RECIPE_DIR/([\w./-]+?)(?=[\s`)\x22]|$)", text)):
                self.assertTrue((ROOT / rel).exists(), "%s names a missing recipe file: %s" % (path.name, rel))
                seen += 1
        self.assertGreater(seen, 25)

    def test_no_step_uses_the_folder_variables_unquoted(self):
        bare = re.compile(r'(?<!")\$\{?(RECIPE_DIR|BLOCKS_DIR)\b')
        for path in self.docs():
            for number, line in enumerate(path.read_text().splitlines(), 1):
                self.assertIsNone(bare.search(line), "%s line %d uses a folder variable without quotes" % (path.name, number))

    def test_every_block_named_in_the_readme_table_exists_and_every_used_block_is_listed(self):
        text = (ROOT / "README.md").read_text()
        table = text[text.index("## Blocks it uses"):text.index("## The steps")]
        listed = set(re.findall(r"`(b-[a-z-]+)`", table))
        used = set()
        for path in self.docs():
            used |= set(re.findall(r"\$BLOCKS_DIR/(b-[a-z-]+)/", path.read_text()))
        self.assertEqual(listed, used)
        for name in listed:
            self.assertTrue((ROOT.parent.parent / "blocks" / name / "README.md").is_file(), name)

    def test_the_recipe_carries_no_scripts_a_block_replaces_and_no_retired_names(self):
        for gone in ("typing_fill.py", "comp_check.py", "mux.py", "check_plan.py", "transcribe.py", "fetch_gsap.py", "gsap.min.js"):
            self.assertFalse(list(ROOT.rglob(gone)), gone)
        old = re.compile(r"(^|[^a-z0-9])(p|c|f)-[a-z]{3,}")
        for path in [*self.docs(), ROOT / "manifest.json", ROOT / "acceptance.json", ROOT / "LEARNINGS.md", *(ROOT / "scripts").glob("*.py"),
                     ROOT / "templates/card.html"]:
            self.assertIsNone(old.search(path.read_text()), "%s still has an old name" % path.name)
        for path in self.docs():
            text = path.read_text()
            for word in ("npx", "hyperframes@", "transcript-match", "over" + "lay-fx", "eval" + "-runner", "flo" + "e"):
                if word == "transcript-match" and path.name in ("03-plan-beats.md", "LEARNINGS.md", "README.md"):
                    continue
                self.assertNotIn(word, text.lower(), "%s mentions %s" % (path.name, word))


if __name__ == "__main__":
    unittest.main()
