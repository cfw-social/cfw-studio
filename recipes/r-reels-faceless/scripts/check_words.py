#!/usr/bin/env python3
"""Check b-audio's words.json against the voice bed and write transcripts.json. Standard library only.

  check_words.py --words work/words.json --bed-duration 41.2 --out saves/transcripts.json [--min-words 20]

words.json is a list of {"text", "start", "end"} in seconds (b-audio's format). This is the recipe's
`words_found` check: at least --min-words timed words, finite times, no word ending before it starts,
starts never going backwards, every word inside the bed (0.5 s codec slack). It never invents or moves
a time. Files must be inside the current folder. Exit 0 passed, 1 failed, 2 bad usage.
"""
import argparse
import json
import math
import os
import sys


def inside_cwd(path):
    root = os.path.realpath(os.getcwd())
    real = os.path.realpath(path)
    return real == root or real.startswith(root + os.sep)


def check(words, bed, min_words):
    problems = []
    if not isinstance(words, list):
        return ["words.json must be a list"]
    if len(words) < min_words:
        problems.append("only %d timed words, need at least %d" % (len(words), min_words))
    prev_start = -1.0
    for i, w in enumerate(words):
        if not isinstance(w, dict) or not isinstance(w.get("text"), str) or not w["text"].strip():
            problems.append("word %d has no text" % i)
            continue
        s, e = w.get("start"), w.get("end")
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in (s, e)):
            problems.append("word %d has a time that is not a finite number" % i)
            continue
        if e < s or s < 0:
            problems.append("word %d ends before it starts" % i)
        if s < prev_start - 1e-6:
            problems.append("word %d starts before the word before it" % i)
        if e > bed + 0.5:
            problems.append("word %d ends after the voice bed" % i)
        prev_start = s
        if len(problems) > 20:
            problems.append("more problems not listed")
            break
    return problems


def main(argv=None):
    p = argparse.ArgumentParser(description="Check b-audio words and write transcripts.json.")
    p.add_argument("--words", required=True)
    p.add_argument("--bed-duration", required=True, type=float)
    p.add_argument("--out", required=True)
    p.add_argument("--min-words", type=int, default=20)
    a = p.parse_args(argv)
    if not (math.isfinite(a.bed_duration) and 0 < a.bed_duration <= 3600) or a.min_words < 1:
        sys.stderr.write("check_words.py: bad --bed-duration or --min-words\n")
        return 2
    if not (inside_cwd(a.words) and inside_cwd(a.out)) or os.path.islink(a.out):
        sys.stderr.write("check_words.py: every path must be inside the work folder, and the output not a link\n")
        return 2
    try:
        with open(a.words, encoding="utf-8") as fh:
            words = json.load(fh)
    except (OSError, ValueError):
        sys.stderr.write("check_words.py: words file is missing or not JSON\n")
        return 2
    problems = check(words, a.bed_duration, a.min_words)
    if problems:
        for line in problems:
            print("FAIL words_found: " + line)
        return 1
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    tmp = a.out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"duration": a.bed_duration,
                   "words": [{"text": w["text"].strip(), "start": float(w["start"]), "end": float(w["end"])} for w in words]},
                  fh, ensure_ascii=False)
    os.replace(tmp, a.out)
    print("PASS words_found: %d timed words inside %.2f s" % (len(words), a.bed_duration))
    return 0


if __name__ == "__main__":
    sys.exit(main())
