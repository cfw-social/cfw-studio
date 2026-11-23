#!/usr/bin/env python3
"""The delivery check: stop unless the final video passed the gate and is the file that passed. Standard library only.

  python3 check_delivery.py --video saves/final_video.mp4 --scorecard work/final-scorecard.json [--spec acceptance.json]

Passes (exit 0) only when the scorecard written by `b-qa-gate/check.py --finalize`:
  - is a reel scorecard for this recipe's spec file name,
  - is finalized (every look answered), has the verdict PASS, no failed row and no look left, and
  - records the SHA-256 and byte size of exactly the video file named by --video.
A failing, unfinalized or missing scorecard, a missing answer, or a video that was swapped or changed after
the check is exit 1, with every reason printed. Exit 2: bad arguments or an unreadable file.

A scorecard is a record, not proof: this script does not look at the pictures and cannot tell a hand-edited
scorecard from a real one. It makes the step stop when the recorded result is not a clean PASS for this very file.
"""
import argparse
import hashlib
import json
import os
import sys


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def problems(card, video, spec_name):
    out = []
    if not isinstance(card, dict) or card.get("scorecard_version") != 1:
        return ["the file is not a b-qa-gate scorecard"]
    if card.get("kind") != "reel":
        out.append("the scorecard is for kind %r, not reel" % card.get("kind"))
    if card.get("spec") != spec_name:
        out.append("the scorecard was made with spec %r, not %r" % (card.get("spec"), spec_name))
    if card.get("finalized") is not True:
        out.append("the scorecard is not finalized: answer every look and run check.py --finalize")
    if card.get("verdict") != "PASS":
        out.append("the verdict is %r, not PASS" % card.get("verdict"))
    counts = card.get("counts") if isinstance(card.get("counts"), dict) else {}
    if counts.get("fail") != 0 or counts.get("look") != 0:
        out.append("the scorecard still has failed or unanswered rows (counts %r)" % counts)
    rows = card.get("checks") if isinstance(card.get("checks"), list) else []
    bad = [str(r.get("id")) for r in rows if not isinstance(r, dict) or r.get("status") != "PASS"]
    if bad or not rows:
        out.append("rows that are not PASS: %s" % (", ".join(bad) if bad else "there are no rows"))
    if card.get("input_sha256") != sha256(video):
        out.append("the video is not the file the gate checked (its SHA-256 differs from the scorecard's record)")
    if card.get("input_bytes") != os.path.getsize(video):
        out.append("the video's size differs from the scorecard's record")
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--video", required=True)
    p.add_argument("--scorecard", required=True)
    p.add_argument("--spec", default="acceptance.json", help="the spec's file name the scorecard must record")
    a = p.parse_args(argv)
    try:
        with open(a.scorecard, encoding="utf-8") as fh:
            card = json.load(fh)
        if not os.path.isfile(a.video):
            raise OSError("no video")
    except (OSError, ValueError):
        sys.stderr.write("check_delivery.py: FAILED - the video or the scorecard cannot be read (is the gate run and finalized?)\n")
        return 2
    found = problems(card, a.video, os.path.basename(a.spec))
    if found:
        print("DELIVERY BLOCKED:")
        for f in found:
            print("  x " + f)
        return 1
    print("DELIVERY OK: %s passed the gate (sha256 %s...)" % (a.video, card["input_sha256"][:12]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
