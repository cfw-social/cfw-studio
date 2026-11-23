#!/usr/bin/env python3
"""Keep this recipe and r-reels-spotlight from drifting apart, and run the real b-qa-gate on this spec.

  python3 -I recipes/r-reels-spotlight-heygen/test/test_variant.py -v

Every script and template the two recipes share must be byte for byte the same. Steps 02 to 07 are the
same files too; only step 00 (new), step 01 (reads prior/talking_head.mp4), the shared-rules file, the
manifest, the acceptance spec, SKILL.md and README differ.
"""
import filecmp
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import BLOCKS, FFMPEG, NEEDS_FFMPEG, RECIPE_DIR, Tmp, load_json, py

BASE = os.path.join(os.path.dirname(RECIPE_DIR), "r-reels-spotlight")
CHECK = os.path.join(BLOCKS, "b-qa-gate", "check.py")
ONLY_HERE_SCRIPTS = {"heygen_inputs.py", "check_avatar.py"}
SAME_STEPS = [n for n in sorted(os.listdir(os.path.join(BASE, "steps"))) if n[:2] in ("02", "03", "04", "05", "06", "07")]


def listing(root, sub):
    return sorted(n for n in os.listdir(os.path.join(root, sub)) if not n.startswith("__"))


class NoDriftTest(unittest.TestCase):
    def test_the_base_recipe_is_beside_this_one(self):
        self.assertTrue(os.path.isdir(BASE), "this test needs recipes/r-reels-spotlight beside the recipe")

    def test_scripts_are_the_same_files(self):
        here = [n for n in listing(RECIPE_DIR, "scripts") if n not in ONLY_HERE_SCRIPTS]
        self.assertEqual(here, listing(BASE, "scripts"))
        for n in here:
            self.assertTrue(filecmp.cmp(os.path.join(RECIPE_DIR, "scripts", n), os.path.join(BASE, "scripts", n), shallow=False),
                            "scripts/%s differs from r-reels-spotlight; copy it over byte for byte" % n)

    def test_templates_are_the_same_files(self):
        self.assertEqual(listing(RECIPE_DIR, "templates"), listing(BASE, "templates"))
        for n in listing(BASE, "templates"):
            self.assertTrue(filecmp.cmp(os.path.join(RECIPE_DIR, "templates", n), os.path.join(BASE, "templates", n), shallow=False), n)

    def test_steps_two_to_seven_are_the_same_files(self):
        self.assertEqual(len(SAME_STEPS), 6)
        for n in SAME_STEPS:
            self.assertTrue(filecmp.cmp(os.path.join(RECIPE_DIR, "steps", n), os.path.join(BASE, "steps", n), shallow=False), "steps/" + n)

    def test_the_steps_that_differ_are_exactly_the_expected_ones(self):
        here, base = set(listing(RECIPE_DIR, "steps")), set(listing(BASE, "steps"))
        self.assertEqual(here - base, {"00-generate-avatar.md"})
        self.assertEqual(base - here, set())
        for n in ("01-prepare-footage.md", "_shared.md"):
            self.assertFalse(filecmp.cmp(os.path.join(RECIPE_DIR, "steps", n), os.path.join(BASE, "steps", n), shallow=False), n)

    def test_the_copied_tests_are_the_base_tests_with_the_recipe_name_changed(self):
        for n in ("test_cta.py", "test_media.py", "test_pages.py", "test_planning.py", "test_safety.py", "_common.py"):
            with open(os.path.join(BASE, "test", n), encoding="utf-8") as fh:
                base = fh.read().replace("r-reels-spotlight", "r-reels-spotlight-heygen")
            with open(os.path.join(RECIPE_DIR, "test", n), encoding="utf-8") as fh:
                self.assertEqual(fh.read(), base, "test/%s drifted from the base recipe's test" % n)


class SpecTest(unittest.TestCase):
    def test_acceptance_is_the_base_spec_plus_the_avatar_step_minus_the_research_step(self):
        here, base = load_json(os.path.join(RECIPE_DIR, "acceptance.json")), load_json(os.path.join(BASE, "acceptance.json"))
        self.assertEqual(here["checks"], base["checks"])
        self.assertEqual(set(here["steps"]) - set(base["steps"]), {"generate_avatar"})
        self.assertEqual(set(base["steps"]) - set(here["steps"]), {"research"})
        for k in set(here["steps"]) & set(base["steps"]):
            a, b = dict(here["steps"][k]), dict(base["steps"][k])
            if k == "script":    # here the script is an input of the order, not a server step's save
                self.assertEqual(a.pop("artifact"), "inputs/script/script.txt")
                b.pop("artifact")
            self.assertEqual(a, b, k)

    def test_every_manifest_check_has_an_acceptance_entry_and_the_ids_are_not_shipped(self):
        manifest = load_json(os.path.join(RECIPE_DIR, "manifest.json"))
        acc = load_json(os.path.join(RECIPE_DIR, "acceptance.json"))
        ids = {c["id"] for c in acc["checks"]} | {c["id"] for s in acc["steps"].values() for c in s["checks"]}
        for step in manifest["steps"]:
            for c in step.get("checks", []):
                self.assertIn(c["id"], ids)
        self.assertEqual(manifest["steps"][0]["id"], "generate_avatar")
        self.assertEqual(manifest["steps"][0]["maxCheckRetries"], 0, "a retry here would be a second paid render")
        self.assertEqual(manifest["needs"]["providers"], ["heygen"])
        self.assertEqual([i["id"] for i in manifest["inputs"]], ["script", "avatar_id", "voice_id", "broll", "cta"])
        self.assertEqual([x["id"] for x in manifest["steps"][0]["saves"]], ["talking_head", "avatar_render"])

    def test_the_tools_the_readme_requires_are_in_the_manifest(self):
        need = set(load_json(os.path.join(RECIPE_DIR, "manifest.json"))["needs"]["tools"])
        self.assertTrue({"ffmpeg", "ffprobe", "npm", "npx", "python3", "whisper-cli"} <= need, need)


@NEEDS_FFMPEG
class RealGateTest(Tmp):
    def test_every_kind_runs_in_the_real_gate_and_the_avatar_step_passes(self):
        wd = self.path("wd")
        os.makedirs(os.path.join(wd, "saves"))
        subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x808080:s=1080x1920:r=30:d=22",
                        "-f", "lavfi", "-i", "sine=f=440:d=22", "-shortest", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "35",
                        "-pix_fmt", "yuv420p", "-c:a", "aac", os.path.join(wd, "saves", "talking_head.mp4")], check=True)
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8"}
        spec = os.path.join(RECIPE_DIR, "acceptance.json")
        r = subprocess.run([sys.executable, "-I", CHECK, "--kind", "reel", "--spec", spec, "--step", "generate_avatar",
                            "--input", "saves/talking_head.mp4", "--out", "work/c.json"], cwd=wd, capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        # the final checks on the same clip: nothing may come back unsupported or unknown
        g = py("gate_spec.py", "--spec", spec, "--bed-duration", "22", "--out", os.path.join(wd, "work", "run.json"))
        self.assertEqual(g.returncode, 0, g.stderr)
        r = subprocess.run([sys.executable, "-I", CHECK, "--kind", "reel", "--spec", "work/run.json", "--input", "saves/talking_head.mp4",
                            "--out", "work/final.json"], cwd=wd, capture_output=True, text=True, env=env)
        self.assertIn(r.returncode, (0, 1, 4))
        for row in load_json(os.path.join(wd, "work", "final.json"))["checks"]:
            self.assertNotRegex(row["detail"], r"not supported|not known", row["id"])


if __name__ == "__main__":
    unittest.main()
