#!/usr/bin/env python3
"""Refuse a script that shares a run of six or more words in a row with the reference transcript.

  python3 check_overlap.py --script script.txt --reference ref/words.json [--limit 6] [--out overlap.json]

Both files are plain text or a words list (b-audio's words.json). Case, punctuation, apostrophes,
accents, zero-width and other invisible characters are ignored, and a hyphen inside a word is tried both as a split and as a join. A script with letters outside the Latin script is refused. Exit 0: the longest shared run is shorter than the limit. Exit 1: a
shared run was found (its position in the script is printed, never its words). Exit 2: bad input,
including an empty script or an empty reference. The optional --out file holds numbers only.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rs_common import (Stop, file_text, main, normalize, require_latin, resolve, variants,  # noqa: E402
                       work_root, write_json)

MAX_WORDS = 20000


def shared_runs(script, ref, limit):
    """Maximal shared runs (start in script, length) of at least `limit` words, and the longest run."""
    where = {}
    for j, w in enumerate(ref):
        where.setdefault(w, []).append(j)
    runs, longest = [], 0
    for i, w in enumerate(script):
        for j in where.get(w, ()):
            if i > 0 and j > 0 and script[i - 1] == ref[j - 1]:
                continue  # not the start of a maximal run
            n = 0
            while i + n < len(script) and j + n < len(ref) and script[i + n] == ref[j + n]:
                n += 1
            longest = max(longest, n)
            if n >= limit:
                runs.append((i, n))
    return sorted(set(runs)), longest


def run(argv):
    ap = argparse.ArgumentParser(prog="check_overlap.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--script", required=True)
    ap.add_argument("--reference", required=True)
    ap.add_argument("--limit", type=int, default=6)
    ap.add_argument("--out")
    ap.add_argument("--workdir")
    a = ap.parse_args(argv)
    if not 2 <= a.limit <= 50:
        raise Stop("--limit must be from 2 to 50")
    root = work_root(a.workdir)
    script_text, ref_text = file_text(root, a.script), file_text(root, a.reference)
    require_latin(script_text)
    pairs = list(zip(variants(script_text), variants(ref_text)))
    script, ref = pairs[0]
    if not script:
        raise Stop("the script has no words")
    if not ref:
        raise Stop("the reference transcript has no words; nothing to compare against")
    if len(script) > MAX_WORDS or len(ref) > MAX_WORDS:
        raise Stop("a file has more than %d words" % MAX_WORDS)
    runs, longest = set(), 0
    for sw, rw in pairs:       # hyphens split words, then hyphens join words: a run in either counts
        r, n = shared_runs(sw, rw, a.limit)
        runs |= set(r)
        longest = max(longest, n)
    runs = sorted(runs)
    verdict = "FAIL" if runs else "PASS"
    if a.out:
        out = resolve(root, a.out)
        for other in (a.script, a.reference):
            if os.path.abspath(out) == os.path.abspath(resolve(root, other)):
                raise Stop("--out must not be an input file")
        write_json(root, a.out, {"check": "overlap", "limit": a.limit, "script_words": len(script),
                                 "reference_words": len(ref), "longest_shared_run": longest,
                                 "verdict": verdict,
                                 "runs": [{"script_word": s + 1, "length": n} for s, n in runs]})
    if runs:
        print("OVERLAP: FAIL (longest shared run %d words, limit %d)" % (longest, a.limit))
        for s, n in runs:
            print("  script words %d to %d are in the reference; rewrite them" % (s + 1, s + n))
        return 1
    print("OVERLAP: PASS (longest shared run %d words, limit %d)" % (longest, a.limit))
    return 0


if __name__ == "__main__":
    main(run)
