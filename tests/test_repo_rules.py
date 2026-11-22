"""Repository rules for blocks and recipes. Standard library only.

Run from anywhere:  python3 tests/test_repo_rules.py
Also collected by pytest (see pytest.ini).
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BLOCKS = ROOT / "blocks"
RECIPES = ROOT / "recipes"
EXCEPTIONS = Path(__file__).resolve().parent / "repo_rules_exceptions.txt"
BLOCK_REF = re.compile(r"\.\./\.\./blocks/(b-[A-Za-z0-9_-]+)")
TEXT_SUFFIXES = {".md", ".yaml", ".yml", ".json", ".py", ".js", ".mjs", ".sh", ".txt", ".html"}


def block_dirs():
    return sorted(p for p in BLOCKS.glob("b-*") if p.is_dir())


def recipe_dirs():
    return sorted(p for p in RECIPES.glob("r-*") if p.is_dir())


def is_test_file(p):
    return p.is_file() and (p.name.startswith("test") or ".test." in p.name)


def blocks_named_by(recipe):
    names = set()
    for f in recipe.rglob("*"):
        if f.is_file() and f.suffix in TEXT_SUFFIXES:
            names.update(BLOCK_REF.findall(f.read_text(encoding="utf-8", errors="replace")))
    return names


def read_exceptions():
    out = {}
    if EXCEPTIONS.exists():
        for line in EXCEPTIONS.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and ":" in line:
                name, reason = line.split(":", 1)
                if reason.strip():
                    out[name.strip()] = reason.strip()
    return out


class RepoRules(unittest.TestCase):
    def test_each_block_has_readme_skill_and_a_test(self):
        for b in block_dirs():
            with self.subTest(block=b.name):
                self.assertTrue((b / "README.md").is_file(), "no README.md")
                self.assertTrue((b / "SKILL.md").is_file(), "no SKILL.md")
                tests = b / "test"
                self.assertTrue(tests.is_dir(), "no test folder")
                self.assertTrue(any(is_test_file(f) for f in tests.rglob("*")), "no test file")

    def test_each_block_readme_has_a_proof_table(self):
        for b in block_dirs():
            with self.subTest(block=b.name):
                text = (b / "README.md").read_text(encoding="utf-8")
                self.assertRegex(text, r"(?m)^## Proof\s*$", "no '## Proof' heading")
                self.assertRegex(text, r"(?m)^\| What \| Status \| Detail \|\s*$", "no Proof table header")

    def test_no_old_style_names(self):
        for area in (BLOCKS, RECIPES):
            for p in area.iterdir():
                if p.is_dir():
                    with self.subTest(folder=f"{area.name}/{p.name}"):
                        self.assertNotRegex(p.name, r"^[pcf]-", "old-style name")

    def test_recipe_block_paths_exist(self):
        for r in recipe_dirs():
            for name in sorted(blocks_named_by(r)):
                with self.subTest(recipe=r.name, block=name):
                    self.assertTrue((BLOCKS / name).is_dir(), f"{r.name} names {name}, which does not exist")

    def test_each_block_is_named_by_two_recipes_or_excepted(self):
        recipes = recipe_dirs()
        if not recipes:
            self.skipTest("recipes/ holds no r-* folder yet; recipe templates are added separately")
        used = {}
        for r in recipes:
            for name in blocks_named_by(r):
                used.setdefault(name, set()).add(r.name)
        exceptions = read_exceptions()
        for b in block_dirs():
            with self.subTest(block=b.name):
                if len(used.get(b.name, ())) < 2:
                    self.assertIn(b.name, exceptions,
                                  f"{b.name} is named by {len(used.get(b.name, ()))} recipe(s); "
                                  f"it needs two, or a one-line reason in {EXCEPTIONS.name}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
