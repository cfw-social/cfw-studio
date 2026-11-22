#!/usr/bin/env python3
"""The files this recipe shares with ../r-reels-pip are byte for byte the same, so the two cannot drift apart.

  python3 -I recipes/r-reels-pip-heygen/test/test_shared_files.py -v

The shared set is every script (except this recipe's own two), every page template, the words check and the
two script test files of the base recipe. A difference, a file missing here, or a script here that the base
does not have and that is not on the short own-files list, fails the test.
"""
import os
import sys
import unittest

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
HEYGEN = os.path.dirname(HERE)
BASE = os.path.join(os.path.dirname(HEYGEN), "r-reels-pip")
OWN_SCRIPTS = {"heygen_inputs.py", "verify-skill.sh"}
SHARED_DIRS = ("scripts", "templates", "checks")
SHARED_TESTS = ("test_card_and_cta.py", "test_scripts.py")


def read(path):
    with open(path, "rb") as fh:
        return fh.read()


class SharedFilesMatchTheBase(unittest.TestCase):
    def test_the_base_recipe_is_beside_this_one(self):
        self.assertTrue(os.path.isdir(BASE), BASE)

    def test_every_shared_file_is_identical(self):
        for d in SHARED_DIRS:
            for name in sorted(os.listdir(os.path.join(BASE, d))):
                if name in OWN_SCRIPTS or name.startswith("__") or name.endswith(".pyc"):
                    continue
                mine = os.path.join(HEYGEN, d, name)
                self.assertTrue(os.path.isfile(mine), "%s/%s is missing here" % (d, name))
                self.assertEqual(read(mine), read(os.path.join(BASE, d, name)), "%s/%s differs from the base recipe" % (d, name))
        for name in SHARED_TESTS:
            self.assertEqual(read(os.path.join(HERE, name)), read(os.path.join(BASE, "test", name)), name)

    def test_no_unexplained_extra_script_here(self):
        base = set(os.listdir(os.path.join(BASE, "scripts")))
        here = {f for f in os.listdir(os.path.join(HEYGEN, "scripts")) if not f.startswith("__")}
        self.assertEqual(here - base, {"heygen_inputs.py"})
        self.assertEqual(os.listdir(os.path.join(HEYGEN, "templates")).sort(), os.listdir(os.path.join(BASE, "templates")).sort())


if __name__ == "__main__":
    unittest.main()
