#!/usr/bin/env python3
"""Put the final video in saves/ only after a finalized PASS scorecard for exactly this file. Standard library only.

  deliver_final.py --candidate work/final-candidate.mp4 --scorecard work/final-scorecard.json --out saves/final_video.mp4

The scorecard is the one `b-qa-gate/check.py --finalize` wrote. It must say verdict PASS, finalized true, no
failing row and no look still owed; its `input` must be this candidate; and its `input_sha256` must equal the
SHA-256 of the candidate's bytes now. Anything else is exit 1 and nothing is written. The copy goes through a
temporary file in the output folder and `os.replace`; a symlinked output is refused. A scorecard is a record, not
proof: this stops a skipped or stale gate, not a hand-edited scorecard. Exit 0 delivered, 1 refused, 2 bad usage.
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile

sys.dont_write_bytecode = True


def inside(path, root):
    real, base = os.path.realpath(path), os.path.realpath(root)
    return real == base or real.startswith(base + os.sep)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Deliver the final video only after a finalized PASS.")
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--scorecard", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    cwd = os.getcwd()
    if not all(inside(p, cwd) for p in (a.candidate, a.scorecard, a.out)) or os.path.islink(a.out) \
            or os.path.realpath(a.out) == os.path.realpath(a.candidate) or not a.out.lower().endswith(".mp4"):
        sys.stderr.write("deliver_final.py: paths must be inside the work folder, the output a new .mp4 that is not a link\n")
        return 2
    problems = []
    try:
        with open(a.scorecard, encoding="utf-8") as fh:
            card = json.load(fh)
        if not isinstance(card, dict):
            raise ValueError
    except (OSError, ValueError):
        print("REFUSED: the scorecard is missing or not JSON")
        return 1
    if card.get("verdict") != "PASS":
        problems.append("the verdict is %r, not PASS" % str(card.get("verdict"))[:20])
    if card.get("finalized") is not True:
        problems.append("the scorecard was not finalized (answer the looks with --finalize)")
    counts = card.get("counts") if isinstance(card.get("counts"), dict) else {}
    if counts.get("fail") != 0 or counts.get("look") != 0:
        problems.append("the scorecard still has failing or unanswered rows")
    rows = card.get("checks") if isinstance(card.get("checks"), list) else []
    if not rows or any(not isinstance(r, dict) or r.get("status") != "PASS" for r in rows):
        problems.append("a scorecard row is not PASS")
    if os.path.realpath(os.path.join(cwd, str(card.get("input", "")))) != os.path.realpath(a.candidate):
        problems.append("the scorecard was made for a different file")
    if not os.path.isfile(a.candidate):
        problems.append("the candidate file is missing")
    elif card.get("input_sha256") != sha256(a.candidate):
        problems.append("the file changed after the scorecard was made")
    if problems:
        for p in problems:
            print("REFUSED: " + p)
        return 1
    out_dir = os.path.dirname(os.path.abspath(a.out))
    os.makedirs(out_dir, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=out_dir, prefix=".final-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as dst, open(a.candidate, "rb") as src:
            shutil.copyfileobj(src, dst)
        if sha256(tmp) != card["input_sha256"]:
            raise OSError("copy mismatch")
        os.replace(tmp, a.out)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    print("DELIVERED: %s" % a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
