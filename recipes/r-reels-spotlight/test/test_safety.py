#!/usr/bin/env python3
"""Static safety and consistency tests for the recipe files.

  python3 -I recipes/r-reels-spotlight/test/test_safety.py -v

They read the recipe's own files; no tool runs except a stub `node`.
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import BLOCKS, RECIPE_DIR, SCRIPTS, load_json, read, write_json


def files(*exts):
    for root, dirs, names in os.walk(RECIPE_DIR):
        dirs[:] = [d for d in dirs if d not in ("test", "__pycache__")]
        for n in names:
            if n.endswith(exts):
                yield os.path.join(root, n)


def text(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class SafetyRulesTest(unittest.TestCase):
    def test_no_shell_eval_or_shell_true_or_agent_with_checks_off(self):
        bad = re.compile(r"(?m)(^|[;&|(]\s*|\s)eval[ \t]+[\"'$]|shell\s*=\s*True|os\.system|dangerously|--yolo|bypassPermissions")
        for p in files(".md", ".py", ".sh"):
            self.assertIsNone(bad.search(text(p)), "unsafe construct in " + os.path.relpath(p, RECIPE_DIR))

    def test_no_private_pack_paths_or_runners(self):
        bad = re.compile(r"\.hub|CFW_RENDER|cfw-upload|cfw-transcribe|propose_composition|\.claude/skills|\.agents/skills|HOME/\.")
        for p in files(".md", ".py", ".sh", ".json", ".html"):
            self.assertIsNone(bad.search(text(p)), "private path or tool in " + os.path.relpath(p, RECIPE_DIR))

    def test_no_remote_script_or_stylesheet_in_a_template(self):
        for p in files(".html"):
            self.assertIsNone(re.search(r"(src|href)\s*=\s*[\"']https?:", text(p)), p)
            self.assertIsNone(re.search(r"@import|url\(\s*[\"']?https?:", text(p)), p)

    def test_blocks_are_reached_only_through_the_blocks_dir(self):
        for p in files(".md", ".sh", ".py"):
            for m in re.finditer(r"blocks/([A-Za-z0-9_-]+)/", text(p)):
                self.assertTrue(m.group(1).startswith("b-") or m.group(1) == "_template", (p, m.group(0)))
        for p in files(".md"):
            for line in text(p).splitlines():
                if "blocks/" in line and not line.lstrip().startswith("#"):
                    self.assertRegex(line, r"(\.\./\.\./blocks/|\$BLOCKS_DIR|\$\{?BLOCKS_DIR|BLOCKS_DIR=|\$PREMIUM|blocks dir|blocks live)", line)

    def test_the_recipe_carries_no_sound_effect_copy(self):
        self.assertFalse(os.path.exists(os.path.join(RECIPE_DIR, "assets")), "the eight sound effects live in blocks/b-reel-premium/assets/sfx/")
        for p in files(".wav", ".mp3"):
            self.fail("audio file in the recipe: " + p)

    def test_no_script_reads_env_files_or_keys(self):
        for p in files(".py", ".sh"):
            t = text(p)
            self.assertIsNone(re.search(r"\.env\b|vault|API_KEY|SECRET", t), p)
            self.assertIsNone(re.search(r"os\.environ|getenv", t.replace("os.environ.get(\"PATH\"", "")), "scripts take input from arguments and files, not the environment: " + p)

    def test_no_network_client_in_a_script(self):
        for p in files(".py"):
            self.assertIsNone(re.search(r"urllib|requests|http\.client|socket|urlopen", text(p)), p)

    def test_the_renderer_is_reached_only_through_b_hyperframes(self):
        for p in files(".md", ".sh", ".py"):
            self.assertIsNone(re.search(r"npx\s|npm\s+(?:pack|install|i\b)|hyperframes\s+(?:render|lint|validate|transcribe)", text(p)),
                              "call the renderer only through b-hyperframes: " + os.path.relpath(p, RECIPE_DIR))
        self.assertFalse(os.path.exists(os.path.join(SCRIPTS, "fetch_gsap.sh")), "the block's fetch_gsap.py is the one fetch")

    def test_no_step_asks_the_planner_for_transcript_match(self):
        for p in files(".md", ".sh", ".py"):
            for line in text(p).splitlines():
                if "plan.js" in line or "--order" in line:
                    self.assertNotIn("transcript-match", line, p)
        self.assertNotIn("--allow-empty-copy", read("steps/04-plan-broll.md"))

    def test_tweens_in_the_templates_name_their_targets_literally(self):
        # the renderer's lint cannot resolve `scope + ".x"`, and then reports overlaps that are not there
        for name in ("keyword", "list", "quote", "stat"):
            page = read("templates/tk-%s.html" % name)
            self.assertIsNone(re.search(r"tl\.(?:fromTo|to|from|set)\(\s*scope\s*\+", page), name)

    def test_no_text_names_a_removed_tool(self):
        for p in files(".md", ".sh", ".py", ".json", ".html"):
            self.assertIsNone(re.search(r"overlay_beats|render-overlay|eval-run|eval_run|run_broll_plan|whisper_json_to_words|mlx_whisper", text(p)),
                              "removed tool named in " + os.path.relpath(p, RECIPE_DIR))

    def test_no_folder_or_block_has_an_old_name(self):
        for p in files(".md", ".sh", ".py", ".json", ".html"):
            self.assertIsNone(re.search(r"(?<![a-z0-9])(?:p|c|f)-(?:reel|broll|typing|audio|hyper|qa|shorts|eval|overlay|gsap|production|spotlight)", text(p)),
                              "old name in " + os.path.relpath(p, RECIPE_DIR))


def code_blocks(rel):
    return re.findall(r"```bash\n(.*?)```", read(rel), re.S)


def logical_commands(block):
    """The block's commands, continuation lines joined; here-documents are skipped."""
    out, cur, here = [], "", None
    for line in block.split("\n"):
        if here:
            if line.strip() == here:
                here = None
            continue
        cur += line if not cur else " " + line.strip()
        if cur.rstrip().endswith("\\"):
            cur = cur.rstrip()[:-1]
            continue
        m = re.search(r"<<-?\s*'?(\w+)'?", cur)
        if m:
            here = m.group(1)
        out.append(cur)
        cur = ""
    return out


class StepDisciplineTest(unittest.TestCase):
    STEPS = ["steps/0%d-%s.md" % (i, n) for i, n in enumerate(
        ["", "prepare-footage", "transcribe", "plan-edit", "plan-broll", "render-scenes", "assemble", "final-checks"]) if n]
    # commands that may fail on purpose or whose exit code is read by the next line
    ALLOWED = ("b-qa-gate/check.py\" --kind reel --spec work/acceptance.run.json --input work/final_video.mp4",)

    def test_every_command_stops_the_step_when_it_fails(self):
        risky = re.compile(r"(python3|node|ffmpeg|ffprobe|cp|mkdir|printf|read|rm)\b")
        for rel in self.STEPS:
            for block in code_blocks(rel):
                for cmd in logical_commands(block):
                    c = cmd.strip()
                    if not c or c.startswith(("#", "}", "fi", "else", "done", "then", "elif", "if ", "for ", "while ")):
                        continue
                    core = re.sub(r"^[A-Za-z_]+=(\$\()?", "", c)
                    if not (risky.match(core) or re.match(r"\[ .* \] && ", c)):
                        continue
                    if c.count('"') % 2 == 1 and "<<" not in c:     # first line of a multi-line quoted command
                        continue
                    if any(a in c for a in self.ALLOWED):
                        continue
                    self.assertTrue("|| exit" in c or "|| {" in c or ("grep" in c and ("|| echo" in c or "|| true" in c)), "%s: a command can fail without stopping the step: %s" % (rel, c[:100]))

    def test_the_gate_run_reads_its_exit_code(self):
        self.assertRegex(read("steps/07-final-checks.md"), r"GATE=\$\?\n.*\n\[ \"\$GATE\" -eq 0 \] \|\| \[ \"\$GATE\" -eq 4 \] \|\| exit 1")

    def test_every_ffmpeg_and_ffprobe_input_is_limited_to_files(self):
        for rel in self.STEPS + ["steps/_shared.md"]:
            for block in code_blocks(rel):
                for cmd in logical_commands(block):
                    for call in re.finditer(r"\b(ffmpeg|ffprobe)\b[^|;]*", cmd):
                        piece = call.group(0)
                        if piece.lstrip().startswith(("ffmpeg ", "ffprobe ")) and ("-i " in piece or "ffprobe " in piece) and "lavfi" not in piece.split("-i ")[0][-40:]:
                            self.assertIn("protocol_whitelist file", piece, "%s: %s" % (rel, piece[:90]))
        for name in os.listdir(SCRIPTS):
            if not name.endswith(".py"):
                continue
            src = text(os.path.join(SCRIPTS, name))
            for m in re.finditer(r"\"-i\", ", src):
                self.assertIn("protocol_whitelist", src[max(0, m.start() - 240):m.start()], "%s: an ffmpeg input without -protocol_whitelist" % name)
            for m in re.finditer(r"\"ffprobe\", \"-v\", \"error\", ", src):
                self.assertTrue(src[m.end():].startswith('"-protocol_whitelist", "file"'), "%s: ffprobe without -protocol_whitelist" % name)

    def test_the_concat_list_is_safe(self):
        t = read("steps/07-final-checks.md")
        self.assertNotIn("-safe 0", t)
        self.assertNotIn("$PWD", t)
        self.assertIn("-f concat -safe 1 -protocol_whitelist file -i work/concat-cover.txt", t)

    def test_no_script_uses_assert(self):
        for p in files(".py"):
            self.assertIsNone(re.search(r"(?m)^\s*assert\b", text(p)), "assert is switched off by python -O: " + os.path.relpath(p, RECIPE_DIR))

    def test_no_order_file_name_is_typed_into_a_command(self):
        t = read("steps/02-transcribe.md")
        self.assertIn("while IFS= read -r CLIP; do", t)
        self.assertNotIn("demo.mp4", t)
        for rel in self.STEPS:
            self.assertNotRegex("\n".join(code_blocks(rel)), r"inputs/broll/[A-Za-z0-9_-]+\.(?:mp4|mov)", rel)

    def test_nothing_reaches_saves_before_the_delivery_check_passes(self):
        t = "\n".join(code_blocks("steps/07-final-checks.md"))
        first_save = t.index("cp work/final_video.mp4 saves/final_video.mp4")
        self.assertLess(t.index('final_gate.py" delivery work/final-scorecard.json work/acceptance.run.json work/final_video.mp4'), first_save)
        self.assertNotRegex(t[:first_save], r"saves/(final_video|cover)")
        self.assertIn('delivery work/final-scorecard.json work/acceptance.run.json saves/final_video.mp4', t[first_save:])

    def test_options_are_arrays_never_unquoted_strings(self):
        for rel in self.STEPS:
            for cmd in logical_commands("\n".join(code_blocks(rel))):
                self.assertNotRegex(cmd, r"(?<![\"{$A-Z_])\$[A-Z][A-Z_]*(?:ARGS|FLAGS|OPTS|BROLL)\b(?!\[)", "%s: %s" % (rel, cmd[:90]))
        self.assertIn('"${GATE_ARGS[@]}"', read("steps/05-render-scenes.md"))
        self.assertIn('"${GATE_ARGS[@]}"', read("steps/07-final-checks.md"))

    def test_the_shared_rules_say_the_shell_the_paths_and_the_copy(self):
        t = read("steps/_shared.md")
        for needle in ("run with **zsh**", "bash was not used", "**absolute**", "cp -R saves/. prior/", "automatically",
                       "WCAG contrast notes", "overlapping_gsap_tweens", "composition_file_too_large", "is never ignored"):
            self.assertIn(needle, t)
        self.assertRegex(t, r'RECIPE_DIR="\$\(cd /absolute/path/to/the/repository/recipes/r-reels-spotlight[a-z-]* && pwd\)"')
        self.assertIn('BLOCKS_DIR="$(cd "$RECIPE_DIR/../../blocks" && pwd)"', t)

    def test_the_minimal_plans_in_the_steps_pass_the_guards(self):
        import json, shutil, subprocess, tempfile
        def first_json(rel, marker):
            t = read(rel)
            i = t.index(marker)
            return re.search(r"```json\n(.*?)```", t[i:], re.S).group(1)
        edit = json.loads(first_json("steps/03-plan-edit.md", "complete minimal"))
        scene = json.loads(first_json("steps/04-plan-broll.md", "complete minimal"))
        self.assertEqual(scene["version"], 1)
        self.assertIn('"version": 1` is required', read("steps/04-plan-broll.md"))
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        write_json(os.path.join(d, "edit.json"), edit)
        write_json(os.path.join(d, "scene.json"), scene)
        r = subprocess.run([sys.executable, "-I", os.path.join(SCRIPTS, "plan_guard.py"), os.path.join(d, "edit.json"), "12.0"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        check = os.path.join(BLOCKS, "b-reel-premium", "scripts", "check_plan.py")
        r = subprocess.run([sys.executable, "-I", check, "--plan", os.path.join(d, "edit.json"), "--duration", "12.0", "--cover-tolerance", "4.5", "--workdir", d],
                           capture_output=True, text=True, cwd=d)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        if shutil.which("node"):
            v = os.path.join(BLOCKS, "b-broll-sync", "scripts", "validate-scene-plan.js")
            r = subprocess.run(["node", v, "scene.json", "--bed-dur", "12"], cwd=d, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_the_looks_example_is_not_pre_filled(self):
        t = read("steps/07-final-checks.md")
        self.assertNotRegex(t, r'"answer":\s*"(?:yes|no)"')
        self.assertNotIn("cat > work/answers.json", t)

    def test_step_05_runs_the_plan_guard_again(self):
        t = "\n".join(code_blocks("steps/05-render-scenes.md"))
        self.assertIn('plan_guard.py" work/plan.json', t)
        self.assertLess(t.index('scripts/plan_guard.py"'), t.index('scripts/build_takeovers.py"'))


class ConsistencyTest(unittest.TestCase):
    def test_every_script_a_step_calls_exists(self):
        for p in files(".md"):
            for m in list(re.finditer(r"RECIPE_DIR\"?/scripts/([A-Za-z0-9_.-]+\.(?:py|sh))", text(p))) + \
                    list(re.finditer(r"(?<![\w/.-])scripts/([A-Za-z0-9_.-]+\.(?:py|sh))", text(p))):
                self.assertTrue(os.path.isfile(os.path.join(SCRIPTS, m.group(1))), "%s names a missing script %s" % (p, m.group(0)))

    def test_manifest_steps_point_at_real_files(self):
        manifest = load_json(os.path.join(RECIPE_DIR, "manifest.json"))
        for step in manifest["steps"]:
            if step.get("instructions"):
                self.assertTrue(os.path.isfile(os.path.join(RECIPE_DIR, step["instructions"])), step["id"])
        self.assertTrue(os.path.isfile(os.path.join(RECIPE_DIR, "steps", "_shared.md")))

    def test_every_manifest_check_has_an_acceptance_entry(self):
        manifest = load_json(os.path.join(RECIPE_DIR, "manifest.json"))
        acc = load_json(os.path.join(RECIPE_DIR, "acceptance.json"))
        ids = {c["id"] for c in acc["checks"]}
        for s in acc["steps"].values():
            ids |= {c["id"] for c in s["checks"]}
        for step in manifest["steps"]:
            for c in step.get("checks", []):
                self.assertIn(c["id"], ids, c["id"])

    def test_the_sfx_names_agree_between_the_guard_and_the_block(self):
        pick = lambda t, pat: set(re.findall(r"\"([a-z]+-[a-z]+|riser|click|pop|swipe)\"", re.search(pat, t).group(0)))
        block = os.path.join(BLOCKS, "b-reel-premium", "scripts", "plan_lib.py")
        self.assertTrue(os.path.isfile(block), "this test needs the b-reel-premium block beside the recipe")
        theirs = pick(text(block), r"SFX_NAMES = \([^)]*\)")
        self.assertEqual(pick(read("scripts/plan_guard.py"), r"SFX_NAMES = \{[^}]*\}"), theirs)
        self.assertEqual(len(theirs), 8)
        self.assertTrue(os.path.isfile(os.path.join(BLOCKS, "b-reel-premium", "assets", "sfx", "pop.wav")))

    def test_the_gain_limit_matches_the_block(self):
        block = text(os.path.join(BLOCKS, "b-reel-premium", "scripts", "plan_lib.py"))
        self.assertEqual(re.search(r"MAX_SFX_GAIN = ([0-9.]+)", block).group(1), "0.6")
        self.assertIn("<= 0.6", read("scripts/plan_guard.py"))

    def test_the_planner_reads_both_accent_keys(self):
        self.assertIn("`brand.accent`, else `brand.palette.accent`", read("steps/03-plan-edit.md"))

    def test_step_01_has_one_tail_section(self):
        self.assertEqual(read("steps/01-prepare-footage.md").count("### 4b. Give the end card a silent tail"), 1)

    def test_step_07_runs_the_gate_answers_the_looks_and_finalizes(self):
        t = read("steps/07-final-checks.md")
        for needle in ("b-qa-gate/check.py\" --kind reel", "--finalize work/scorecard.json", "gate_spec.py", "final_gate.py\" delivery work/final-scorecard.json work/acceptance.run.json work/final_video.mp4"):
            self.assertIn(needle, t)

    def test_a_labelled_filter_graph_is_never_passed_with_vf(self):
        # ffmpeg takes a labelled graph only through -filter_complex; with -vf it exits 234.
        vf = re.compile(r"""-vf["']?,?\s*\(?\s*((?:[fr]?"[^"\n]*"|'[^'\n]*')(?:\s*(?:[fr]?"[^"\n]*"|'[^'\n]*'))*)""")
        label = re.compile(r"\[[A-Za-z0-9_]+(?::[A-Za-z0-9_]+)?\]")
        for p in files(".md", ".py", ".sh"):
            for m in vf.finditer(text(p)):
                self.assertIsNone(label.search(m.group(1)), "%s: -vf %s" % (p, m.group(1)[:60]))


if __name__ == "__main__":
    unittest.main()
