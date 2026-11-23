#!/usr/bin/env python3
"""Write the two small record files the steps keep in the work folder.

  record.py task      --n 1 --task-id ID --attempts 1 --divergence PASS
  record.py ref-audit --task-id ID --model KEY --attempts 1 --audit 1=PASS 2=PASS 3=PASS 4=PASS 5=PASS 6=PASS [--note TEXT]

task      updates work/tasks.json, adding or replacing the entry for scene N:
          {"<n>": {"task_id": "...", "attempts": 1, "divergence": "PASS"}}
ref-audit writes work/ref_audit.json:
          {"task_id": "...", "model": "...", "attempts": 1, "audit": {"1": "PASS", ...}, "notes": []}

Everything comes in as separate arguments and is checked before anything is written. The only
files it writes are those two, inside the current (work) folder, replaced in one step. It reads no
other file, makes no network call and reads no key. Exit 0 written, 2 bad arguments.
"""
import argparse
import json
import os
import re
import sys
import tempfile

TASK_ID = re.compile(r"[A-Za-z0-9_-]{1,128}")
MODEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_./-]{0,63}")


class Bad(Exception):
    pass


def target(name):
    """work/<name> inside the current folder, never a link, never outside it."""
    base = os.path.realpath(os.getcwd())
    folder = os.path.join(base, "work")
    if os.path.islink(folder) or os.path.realpath(folder) != folder:
        raise Bad("work/ must be a plain folder inside the current folder")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name)
    if os.path.islink(path) or os.path.isdir(path):
        raise Bad("work/%s must be a plain file" % name)
    return path


def save(path, data):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".rec-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=1)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def common(a):
    if not TASK_ID.fullmatch(a.task_id):
        raise Bad("--task-id must be letters, digits, _ or - (1 to 128 characters)")
    if not 1 <= a.attempts <= 10:
        raise Bad("--attempts must be 1 to 10")


def do_task(a):
    common(a)
    if not 1 <= a.n <= 6:
        raise Bad("--n must be 1 to 6")
    if a.divergence not in ("PASS", "FAIL"):
        raise Bad("--divergence must be PASS or FAIL")
    path = target("tasks.json")
    tasks = {}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                tasks = json.load(fh)
        except (OSError, ValueError):
            raise Bad("work/tasks.json is not readable JSON; remove it and record the scenes again")
        if not isinstance(tasks, dict):
            raise Bad("work/tasks.json must hold a JSON object")
    tasks[str(a.n)] = {"task_id": a.task_id, "attempts": a.attempts, "divergence": a.divergence}
    save(path, tasks)
    print("recorded scene %d in work/tasks.json" % a.n)


def do_audit(a):
    common(a)
    if not MODEL.fullmatch(a.model):
        raise Bad("--model is not a valid model key")
    audit = {}
    for item in a.audit:
        k, _, v = item.partition("=")
        if k not in "123456" or len(k) != 1 or v not in ("PASS", "FAIL"):
            raise Bad("--audit entries look like 1=PASS (attribute 1 to 6, PASS or FAIL)")
        audit[k] = v
    if sorted(audit) != list("123456"):
        raise Bad("--audit needs all six attributes, 1 to 6, once each")
    notes = [" ".join(n.split())[:300] for n in a.note]
    save(target("ref_audit.json"), {"task_id": a.task_id, "model": a.model, "attempts": a.attempts,
                                    "audit": audit, "notes": notes})
    print("recorded the reference audit in work/ref_audit.json")


def main(argv):
    ap = argparse.ArgumentParser(prog="record.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("task")
    t.add_argument("--n", type=int, required=True)
    t.add_argument("--task-id", required=True)
    t.add_argument("--attempts", type=int, required=True)
    t.add_argument("--divergence", required=True)
    r = sub.add_parser("ref-audit")
    r.add_argument("--task-id", required=True)
    r.add_argument("--model", required=True)
    r.add_argument("--attempts", type=int, required=True)
    r.add_argument("--audit", nargs=6, required=True)
    r.add_argument("--note", action="append", default=[])
    try:
        a = ap.parse_args(argv)
        (do_task if a.cmd == "task" else do_audit)(a)
    except Bad as e:
        sys.stderr.write("record.py: %s\n" % e)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
