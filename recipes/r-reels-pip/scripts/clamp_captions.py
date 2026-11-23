#!/usr/bin/env python3
"""Keep captions off the end card. Standard library only.

  python3 clamp_captions.py words SRC DEST   copy the words (SRC may be {"words": [...]} or a list) to DEST,
                                             dropping words that start inside the end-card window and cutting
                                             one that runs into it
  python3 clamp_captions.py plan PLAN        the same for a b-reel-premium plan's caption_groups, in place

The window is `cta_start` in work/cta-window.json (or the file named by the CTA_WINDOW environment
variable). With no window (no end card) the words are copied unchanged and the plan is not touched.
Exit 0 done, 1 something still overlaps the window or the input is unusable, 2 bad arguments.
"""
import json, os, sys

EPS = 1e-3

def limit_of():
    path = os.environ.get("CTA_WINDOW") or "work/cta-window.json"
    if not os.path.exists(path):
        return None
    data = json.load(open(path))
    if not isinstance(data, dict):
        return None
    start = data.get("cta_start")
    if start is None:
        return None
    return float(start)

def start_of(row):
    if isinstance(row, dict) and "start" in row:
        return float(row["start"])
    if isinstance(row, dict) and "s" in row:
        return float(row["s"])
    return None

def end_of(row):
    if isinstance(row, dict) and "end" in row:
        return float(row["end"])
    if isinstance(row, dict) and "e" in row:
        return float(row["e"])
    return None

def clamp_row(row, limit):
    s = start_of(row)
    if s is not None and s >= limit - EPS:
        return None
    e = end_of(row)
    if e is not None and e > limit:
        if "end" in row:
            row["end"] = limit
        if "e" in row:
            row["e"] = limit
    return row

def overlaps(row, limit):
    s = start_of(row)
    e = end_of(row)
    if s is not None and s >= limit - EPS:
        return True
    if e is not None and e > limit + 1e-6:
        return True
    return False

def dump(path, obj):
    with open(path, "w") as fh:
        json.dump(obj, fh)
        fh.write("\n")

def main():
    if len(sys.argv) < 3:
        sys.stderr.write("usage: clamp_captions.py words SRC DEST | plan PLAN\n")
        return 2
    mode = sys.argv[1]
    limit = limit_of()
    if mode == "words":
        if len(sys.argv) != 4:
            sys.stderr.write("usage: clamp_captions.py words SRC DEST\n")
            return 2
        src, dest = sys.argv[2], sys.argv[3]
        data = json.load(open(src))
        words = data["words"] if isinstance(data, dict) and "words" in data else data
        if not isinstance(words, list):
            sys.stderr.write("clamp_captions: words payload is not a list\n")
            return 1
        out = []
        for w in words:
            if limit is None or not isinstance(w, dict):
                out.append(w)
                continue
            c = clamp_row(dict(w), limit)
            if c is not None:
                out.append(c)
        if limit is not None:
            for w in out:
                if isinstance(w, dict) and overlaps(w, limit):
                    sys.stderr.write("clamp_captions: word still overlaps the CTA window\n")
                    return 1
        dump(dest, out)
        return 0
    if mode == "plan":
        plan_path = sys.argv[2]
        if not os.path.exists(plan_path):
            return 0
        plan = json.load(open(plan_path))
        if limit is not None and isinstance(plan, dict) and isinstance(plan.get("caption_groups"), list):
            kept = []
            for g in plan["caption_groups"]:
                if not isinstance(g, dict):
                    kept.append(g)
                    continue
                gs = start_of(g)
                if gs is not None and gs >= limit - EPS:
                    continue
                g = dict(g)
                words = g.get("words")
                if isinstance(words, list):
                    nw = []
                    for w in words:
                        if not isinstance(w, dict):
                            nw.append(w)
                            continue
                        c = clamp_row(dict(w), limit)
                        if c is not None:
                            nw.append(c)
                    g["words"] = nw
                    if not nw:
                        continue
                ge = end_of(g)
                if ge is not None and ge > limit:
                    if "end" in g:
                        g["end"] = limit
                    if "e" in g:
                        g["e"] = limit
                kept.append(g)
            plan["caption_groups"] = kept
            for g in kept:
                if not isinstance(g, dict):
                    continue
                if overlaps(g, limit):
                    sys.stderr.write("clamp_captions: caption group still overlaps the CTA window\n")
                    return 1
                for w in g.get("words") or []:
                    if isinstance(w, dict) and overlaps(w, limit):
                        sys.stderr.write("clamp_captions: plan word still overlaps the CTA window\n")
                        return 1
        if isinstance(plan, (dict, list)):
            dump(plan_path, plan)
        return 0
    sys.stderr.write("clamp_captions: unknown mode %s\n" % mode)
    return 2

if __name__ == "__main__":
    sys.exit(main())
