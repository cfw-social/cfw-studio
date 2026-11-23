#!/usr/bin/env python3
"""The recipe's caption-group rule, which the plan checker in b-reel-premium does not enforce. Standard library only.

  check_captions.py --plan work/premium/plan.json

The rule (the one rule; the step text says the same):
  * every caption group holds 2 to 4 words;
  * the only exception is the LAST group, which may hold 1 word, and only when it could not join the group before
    it, that is when the group before it already holds 4 words. A plan that is a single 1-word group fails;
  * a pause of 150 ms or more, or a sentence end, is a place to break a group only when both sides keep at least
    2 words. A break that would leave one word on its own is not made: the word joins the neighbour.
This prints every group that breaks the rule and exits 1. b-reel-premium's check_plan.py accepts 1 to 8 words, so
run both. The plan file must be inside the current folder. Exit 0 passed, 1 a group breaks the rule, 2 bad usage.
"""
import argparse
import json
import os
import sys

sys.dont_write_bytecode = True


def check(plan):
    groups = plan.get("caption_groups") if isinstance(plan, dict) else None
    if not isinstance(groups, list) or not groups:
        return ["the plan has no caption_groups"]
    problems = []
    last = len(groups) - 1
    counts = []
    for i, g in enumerate(groups):
        words = g.get("words") if isinstance(g, dict) else None
        if not isinstance(words, list):
            problems.append("group %d has no words list" % i)
            counts.append(None)
            continue
        counts.append(len(words))
    for i, n in enumerate(counts):
        if n is None:
            continue
        if n == 0:
            problems.append("group %d is empty" % i)
        elif n > 4:
            problems.append("group %d has %d words; at most 4" % (i, n))
        elif n == 1:
            first = groups[i]["words"][0].get("w", "?") if isinstance(groups[i]["words"][0], dict) else "?"
            if i != last:
                problems.append("group %d is the one word %r on its own; only the last group may be a single word" % (i, str(first)[:20]))
            elif i == 0:
                problems.append("the only group is the one word %r" % str(first)[:20])
            elif counts[i - 1] is not None and counts[i - 1] < 4:
                problems.append("the last group is the one word %r but could join group %d, which holds %d words (a 1-word last "
                                "group is allowed only after a 4-word group)" % (str(first)[:20], i - 1, counts[i - 1]))
    return problems


def main(argv=None):
    ap = argparse.ArgumentParser(description="Check caption groups hold 2 to 4 words.")
    ap.add_argument("--plan", required=True)
    a = ap.parse_args(argv)
    base = os.path.realpath(os.getcwd())
    real = os.path.realpath(a.plan)
    if not (real == base or real.startswith(base + os.sep)):
        sys.stderr.write("check_captions.py: the plan must be inside the work folder\n")
        return 2
    try:
        with open(a.plan, encoding="utf-8") as fh:
            plan = json.load(fh)
    except (OSError, ValueError):
        sys.stderr.write("check_captions.py: the plan is missing or not JSON\n")
        return 2
    problems = check(plan)
    for p in problems[:30]:
        print("FAIL captions: " + p)
    if problems:
        return 1
    print("PASS captions: %d groups, each 2 to 4 words (a last single word only after a 4-word group)" % len(plan["caption_groups"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
