#!/usr/bin/env python3
"""The last gate: deliver the final reel only if a finalized scorecard says PASS for exactly this file.

  python3 verify_final.py --scorecard work/final-scorecard.json --input premium/polished.mp4
                          --spec RECIPE/acceptance.json --final saves/final.mp4 --report saves/qa_report.json

Exits non-zero unless the scorecard is from b-qa-gate's --finalize, its verdict is PASS, no row is
FAIL or LOOK, every check id in the recipe's acceptance.json has a PASS row, and the sha-256 and size
it recorded match --input as it is now (a swapped or re-encoded file fails). Only then does it write
the final video and the report. Nothing is written on a failure.
"""
import argparse
import hashlib
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rs_common import Stop, main, read_bytes, read_json, resolve, work_root, write_atomic  # noqa: E402


def sha256(path):
    h, n = hashlib.sha256(), 0
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
            n += len(chunk)
    return h.hexdigest(), n


def problems_with(card, spec_ids, digest, size):
    bad = []
    if not isinstance(card, dict) or card.get("kind") != "reel" or card.get("recipe") != "r-inspired-reel":
        return ["not a reel scorecard for this recipe"]
    if card.get("finalized") is not True:
        bad.append("the scorecard was not finalized (the looks are not answered)")
    if card.get("verdict") != "PASS":
        bad.append("the verdict is %s, not PASS" % card.get("verdict"))
    rows = card.get("checks")
    if not isinstance(rows, list) or not rows:
        return bad + ["the scorecard has no rows"]
    for r in rows:
        if not isinstance(r, dict) or r.get("status") != "PASS":
            bad.append("row %s is %s" % (str(r.get("id"))[:40] if isinstance(r, dict) else "?", r.get("status") if isinstance(r, dict) else "bad"))
    ids = {str(r.get("id")) for r in rows if isinstance(r, dict)}
    for want in spec_ids:
        if want not in ids and not any(i.startswith(want + ".") for i in ids):
            bad.append("no row for the check %s" % want)
    if card.get("input_sha256") != digest or card.get("input_bytes") != size:
        bad.append("the file was changed after the scorecard was made")
    return bad


def run(argv):
    ap = argparse.ArgumentParser(prog="verify_final.py", description=__doc__.split("\n\n")[0])
    for k in ("scorecard", "input", "spec", "final", "report"):
        ap.add_argument("--" + k, required=True)
    ap.add_argument("--workdir")
    a = ap.parse_args(argv)
    root = work_root(a.workdir)
    src = resolve(root, a.input, must_exist=True, kind="file")
    final, report = resolve(root, a.final), resolve(root, a.report)
    if len({src, final, report, resolve(root, a.scorecard)}) != 4:
        raise Stop("the four paths must all be different")
    card_bytes = read_bytes(resolve(root, a.scorecard, must_exist=True, kind="file"), 2_000_000)
    try:
        card = json.loads(card_bytes.decode("utf-8"))
    except ValueError:
        raise Stop("the scorecard is not valid JSON", 1)
    spec_path = os.path.abspath(a.spec)
    if os.path.islink(spec_path) or not os.path.isfile(spec_path):
        raise Stop("--spec must be a regular file")
    try:
        spec = json.loads(read_bytes(spec_path, 1_000_000).decode("utf-8"))
        spec_ids = [str(c["id"]) for c in spec["checks"]]
    except (ValueError, KeyError, TypeError):
        raise Stop("could not read the check ids from the spec")
    digest, size = sha256(src)
    bad = problems_with(card, spec_ids, digest, size)
    if bad:
        print("DELIVERY: REFUSED")
        for b in bad:
            print("  " + b)
        return 1
    write_atomic(root, a.report, card_bytes)
    os.makedirs(os.path.dirname(final), exist_ok=True)
    resolve(root, a.final)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(final), prefix=".tmp-", suffix=".part")
    try:
        with os.fdopen(fd, "wb") as out, open(src, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                out.write(chunk)
        if sha256(tmp) != (digest, size):
            raise Stop("the saved file does not match the checked file", 1)
        os.replace(tmp, final)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        if os.path.exists(report):
            os.remove(report)
        raise
    print("DELIVERY: PASS (%s, %d bytes, sha-256 %s)" % (a.final, size, digest[:12]))
    return 0


if __name__ == "__main__":
    main(run)
