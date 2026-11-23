#!/usr/bin/env python3
"""Tests for scripts/record.py.  python3 -I test/test_record.py -v   (no network, no key)"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "record.py")
AUDIT = ["1=PASS", "2=PASS", "3=PASS", "4=PASS", "5=PASS", "6=PASS"]


class Record(unittest.TestCase):
    def setUp(self):
        self.wd = os.path.realpath(tempfile.mkdtemp(prefix="rec-"))

    def tearDown(self):
        shutil.rmtree(self.wd, ignore_errors=True)

    def run_rec(self, *args):
        return subprocess.run([sys.executable, "-I", SCRIPT] + list(args), cwd=self.wd, capture_output=True, text=True)

    def task(self, n, tid="task_1", att="1", div="PASS"):
        return self.run_rec("task", "--n", str(n), "--task-id", tid, "--attempts", att, "--divergence", div)

    def load(self, name):
        with open(os.path.join(self.wd, "work", name), encoding="utf-8") as fh:
            return json.load(fh)

    def test_task_adds_and_replaces_entries(self):
        self.assertEqual(self.task(1).returncode, 0)
        self.assertEqual(self.task(2, "task_2", "2").returncode, 0)
        self.assertEqual(self.task(1, "task_9", "3").returncode, 0)
        d = self.load("tasks.json")
        self.assertEqual(d, {"1": {"task_id": "task_9", "attempts": 3, "divergence": "PASS"},
                             "2": {"task_id": "task_2", "attempts": 2, "divergence": "PASS"}})
        self.assertEqual(os.listdir(os.path.join(self.wd, "work")), ["tasks.json"])   # no temp file left

    def test_ref_audit_shape(self):
        p = self.run_rec("ref-audit", "--task-id", "task_1", "--model", "z-image", "--attempts", "2",
                         "--audit", *AUDIT, "--note", "second try  fixed\nglasses")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.load("ref_audit.json"), {"task_id": "task_1", "model": "z-image", "attempts": 2,
                         "audit": {str(i): "PASS" for i in range(1, 7)}, "notes": ["second try fixed glasses"]})

    def test_bad_arguments_write_nothing(self):
        bad = [
            self.task(0), self.task(7), self.task(1, "../x"), self.task(1, "a b"), self.task(1, att="0"),
            self.task(1, div="MAYBE"),
            self.run_rec("ref-audit", "--task-id", "t", "--model", "z;rm", "--attempts", "1", "--audit", *AUDIT),
            self.run_rec("ref-audit", "--task-id", "t", "--model", "m", "--attempts", "1", "--audit", *AUDIT[:5], "6=OK"),
            self.run_rec("ref-audit", "--task-id", "t", "--model", "m", "--attempts", "1", "--audit", *(AUDIT[:5] + ["5=PASS"])),
            self.run_rec("ref-audit", "--task-id", "t", "--model", "m", "--attempts", "1", "--audit", "1=PASS"),
            self.run_rec("nope"),
        ]
        for p in bad:
            self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.wd, "work", "tasks.json")))
        self.assertFalse(os.path.exists(os.path.join(self.wd, "work", "ref_audit.json")))

    def test_refuses_a_linked_work_folder_and_linked_file(self):
        outside = tempfile.mkdtemp(prefix="rec-out-")
        try:
            os.symlink(outside, os.path.join(self.wd, "work"))
            self.assertEqual(self.task(1).returncode, 2)
            self.assertEqual(os.listdir(outside), [])
            os.unlink(os.path.join(self.wd, "work"))
            os.makedirs(os.path.join(self.wd, "work"))
            os.symlink(os.path.join(outside, "x.json"), os.path.join(self.wd, "work", "tasks.json"))
            self.assertEqual(self.task(1).returncode, 2)
            self.assertEqual(os.listdir(outside), [])
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_unreadable_existing_file_is_refused_not_overwritten(self):
        os.makedirs(os.path.join(self.wd, "work"))
        with open(os.path.join(self.wd, "work", "tasks.json"), "w") as fh:
            fh.write("not json")
        self.assertEqual(self.task(1).returncode, 2)
        with open(os.path.join(self.wd, "work", "tasks.json")) as fh:
            self.assertEqual(fh.read(), "not json")


if __name__ == "__main__":
    unittest.main()
