#!/usr/bin/env python3
"""Check that a new script has the reference's shape, then write the narration text.

  python3 check_script_shape.py --format format.json --script script.txt [--narration-out narration.txt] [--hint-out hint.txt]

The script is plain spoken text: one paragraph per beat, paragraphs separated by a blank line.
Checks: same number of paragraphs as beats in format.json; total words within --tolerance (default
0.10) of the reference's word count; each paragraph's share of the words within --beat-slack
(default 0.12) of its beat's share of the time; no markup characters; at most 5000 characters.
--hint-out writes a short list of the script's longer words (at most 30), the only kind of hint that
helps whisper.cpp; a hint made of whole sentences can stop it after a few words.
Exit 0 pass, 1 does not match (reasons listed), 2 bad input.
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from format_schema import validate_format  # noqa: E402
from rs_common import Stop, main, normalize, number, require_latin, read_json, read_text, resolve, work_root, write_atomic  # noqa: E402

MAX_CHARS = 5000


def run(argv):
    ap = argparse.ArgumentParser(prog="check_script_shape.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--format", required=True)
    ap.add_argument("--script", required=True)
    ap.add_argument("--narration-out")
    ap.add_argument("--hint-out", help="write a short word list (the script's longer words) here, as a hint for b-audio")
    ap.add_argument("--tolerance", default="0.10")
    ap.add_argument("--beat-slack", default="0.12")
    ap.add_argument("--workdir")
    a = ap.parse_args(argv)
    tol = number(a.tolerance, "--tolerance", 0.01, 0.5)
    slack = number(a.beat_slack, "--beat-slack", 0.01, 0.5)
    root = work_root(a.workdir)
    fmt = validate_format(read_json(root, a.format))
    text = read_text(root, a.script, 200_000).replace("\r\n", "\n")
    require_latin(text)
    problems = []
    if len(text) > MAX_CHARS:
        problems.append("the script is longer than %d characters" % MAX_CHARS)
    if re.search(r"[\[\]{}<>]", text) or re.search(r"(?m)^\s*(#|[-*]\s)", text):
        problems.append("the script must be plain spoken text: no brackets, tags, headings or bullet marks")
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    counts = [len(normalize(p)) for p in paras]
    total = sum(counts)
    beats = fmt["beats"]
    if len(paras) != len(beats):
        problems.append("the script has %d paragraphs; the format has %d beats (%s)"
                        % (len(paras), len(beats), fmt["structure"]))
    if total == 0:
        problems.append("the script has no words")
    else:
        target = fmt["word_count"]
        if abs(total - target) > tol * target:
            problems.append("the script has %d words; aim for %d, give or take %d%%"
                            % (total, round(target), round(tol * 100)))
        if len(paras) == len(beats):
            for n, (c, b) in enumerate(zip(counts, beats), 1):
                share = c / total
                if abs(share - b["share"]) > slack:
                    problems.append("paragraph %d (%s) holds %d%% of the words; the beat takes about %d%% of the time"
                                    % (n, b["label"], round(share * 100), round(b["share"] * 100)))
    if problems:
        print("SHAPE: FAIL")
        for p in problems:
            print("  " + p)
        return 1
    if a.narration_out:
        if resolve(root, a.narration_out) == resolve(root, a.script):
            raise Stop("--narration-out must not be the script file")
        write_atomic(root, a.narration_out, (" ".join(" ".join(p.split()) for p in paras) + "\n").encode("utf-8"))
    if a.hint_out:
        seen, words = set(), []
        for w in re.findall(r"[^\W\d_][\w'-]*", text):   # words as written (names keep their capitals)
            if len(w) >= 6 and w.casefold() not in seen:
                seen.add(w.casefold())
                words.append(w)
        hint = ", ".join(words[:30]) + "."
        taken = [resolve(root, a.script)] + ([resolve(root, a.narration_out)] if a.narration_out else [])
        if resolve(root, a.hint_out) in taken:
            raise Stop("--hint-out must be its own file")
        write_atomic(root, a.hint_out, (hint + "\n").encode("utf-8"))
    print("SHAPE: PASS (%d words, %d beats: %s)" % (total, len(beats), fmt["structure"]))
    return 0


if __name__ == "__main__":
    main(run)
