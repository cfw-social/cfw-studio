#!/usr/bin/env python3
"""Offline tests for r-ai-character's fail-loud guards in steps 02 and 03.

  python3 -I test/test_step_guards.py -v

Missing reference, missing generate.py and missing ffmpeg must each stop the step with one
plain line BEFORE any paid call. The step's own setup bash blocks run in a throwaway workdir;
no network, no Kie call, no real key. (A missing key is tested against the real generate.py
in test_end_to_end.py.)
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
BASH = shutil.which("bash")
STEPS = os.path.join(os.path.dirname(HERE), "steps")


def block(name, after):
    text = open(os.path.join(STEPS, name), encoding="utf-8").read()
    start = text.index(after)
    m = re.search(r"```bash\n(.*?)```", text[start:], re.S)
    return m.group(1)


class Guards(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="aichar-")
        self.recipe = os.path.join(self.root, "recipes", "r-ai-character")   # BLOCKS_DIR is RECIPE_DIR/../../blocks
        os.makedirs(self.recipe)
        self.blocks = os.path.join(self.root, "blocks")
        self.wd = os.path.join(self.root, "wd")
        os.makedirs(os.path.join(self.wd, "prior"))
        json.dump({"recipe": "r-ai-character"}, open(os.path.join(self.wd, "brief.json"), "w"))
        json.dump({"num_scenes": 3}, open(os.path.join(self.wd, "prior", "story_arc.json"), "w"))
        json.dump({"lock_prompt": "x", "type": "human"}, open(os.path.join(self.wd, "prior", "character_lock.json"), "w"))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def vendor(self):
        d = os.path.join(self.blocks, "b-kie-ai", "scripts")
        os.makedirs(d)
        open(os.path.join(d, "generate.py"), "w").write("#!/usr/bin/env python3\n")

    def run_block(self, code, path=None):
        env = dict(os.environ, RECIPE_DIR=self.recipe)
        env.pop("BLOCKS_DIR", None)
        env.pop("KIE_AI_API_KEY", None)
        if path is not None:
            env["PATH"] = path
        return subprocess.run([BASH, "-c", "set -eu\n" + code], cwd=self.wd, env=env, capture_output=True, text=True)

    def test_scene_step_needs_a_reference_file(self):
        self.vendor()
        code = block("03-scene-images.md", "## How")
        p = self.run_block(code)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("prior/char_ref.png is missing or empty", p.stdout)
        open(os.path.join(self.wd, "prior", "char_ref.png"), "wb").close()      # empty file
        p = self.run_block(code)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("char_ref.png is missing or empty", p.stdout)
        open(os.path.join(self.wd, "prior", "char_ref.png"), "wb").write(b"\x89PNG")
        p = self.run_block(code)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_steps_stop_when_recipe_dir_is_unset(self):
        for name in ("02-character-ref.md", "03-scene-images.md", "04-qa-gate.md"):
            env = {k: v for k, v in os.environ.items() if k not in ("RECIPE_DIR", "BLOCKS_DIR")}
            p = subprocess.run([BASH, "-c", "set -eu\n" + block(name, "## How")], cwd=self.wd, env=env, capture_output=True, text=True)
            self.assertNotEqual(p.returncode, 0)
            self.assertIn("RECIPE_DIR is not set", p.stdout)

    def test_scene_step_names_a_missing_script(self):
        open(os.path.join(self.wd, "prior", "char_ref.png"), "wb").write(b"\x89PNG")
        code = block("03-scene-images.md", "## How")
        p = self.run_block(code)                                                # no generate.py
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("generate.py is missing", p.stdout)

    def test_reference_step_names_missing_script_and_ffmpeg(self):
        code = block("02-character-ref.md", "## How")
        p = self.run_block(code)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("generate.py is missing", p.stdout)
        self.vendor()
        bare = os.path.join(self.root, "bin")
        os.makedirs(bare)
        for tool in ("python3", "ls", "head", "mkdir", "dirname"):
            found = shutil.which(tool)
            if found:
                os.symlink(found, os.path.join(bare, tool))
        p = self.run_block(code, path=bare)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("ffmpeg is not installed", p.stdout)

    def test_unreadable_reference_picture_is_named(self):
        self.vendor()
        os.makedirs(os.path.join(self.wd, "inputs", "reference_image"))
        open(os.path.join(self.wd, "inputs", "reference_image", "x.png"), "w").write("not an image")
        code = block("02-character-ref.md", "## How") + "\n" + block("02-character-ref.md", "### 2. Create, poll, download")
        code = code.split("  KIE_AI_API_KEY=")[0] + "fi\n"                   # stop before the paid call
        p = self.run_block(code)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("could not be read", p.stdout)


if __name__ == "__main__":
    unittest.main()
