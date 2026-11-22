#!/usr/bin/env python3
"""Small helper for step 3 of r-carousel. Standard library only. No network, no shell.

Run it from the order's work folder (the folder that holds saves/, work/, slides/).
Every path it reads or writes is relative to that folder, must stay inside it, and may
not be a link. Files are written to a fresh temporary name and renamed into place.

  finish.py spec     --recipe-dir DIR --width 1080 --height 1350
  finish.py slides   --count N --width 1080 --height 1350
  finish.py qa       --count N --blocks-dir DIR
  finish.py finalize --count N --blocks-dir DIR
  finish.py report   --count N --rounds R

spec      writes work/acceptance.json: the recipe's acceptance.json for this canvas.
slides    copies slides/slide-N.png to saves/slide_N.png, then writes saves/cover.png,
          saves/slide_sheet.png and saves/slides.json.
qa        runs b-qa-gate (kind image) on each saves/slide_N.png -> work/qa/slide_N.json.
finalize  after the looks are answered in work/qa/answers_N.json, finalizes each slide
          -> work/qa/final_N.json.
report    writes saves/qa_report.json from the final scorecards. Fails unless all PASS.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys

ROOT = os.path.realpath(os.getcwd())
COUNTS = (3, 5, 7, 10)


def fail(msg):
    print("finish.py: " + msg, file=sys.stderr)
    sys.exit(1)


def inside(path):
    real = os.path.realpath(path)
    return real == ROOT or real.startswith(ROOT + os.sep)


def safe_dir(rel):
    """Make a folder below the work folder. Refuse a link at any level."""
    cur = ROOT
    for part in rel.split("/"):
        cur = os.path.join(cur, part)
        if os.path.islink(cur):
            fail("%s is a link" % os.path.relpath(cur, ROOT))
        if not os.path.exists(cur):
            os.mkdir(cur)
        elif not os.path.isdir(cur):
            fail("%s is not a folder" % os.path.relpath(cur, ROOT))
    if not inside(cur):
        fail("%s resolves outside the work folder" % rel)
    return cur


def safe_read(rel):
    p = os.path.join(ROOT, rel)
    if os.path.islink(p) or not os.path.isfile(p) or not inside(p):
        fail("%s is missing, a link, or not a regular file inside the work folder" % rel)
    return p


def place(folder, name, write):
    """write(tmp_path) makes the file; then it is renamed to folder/name."""
    d = safe_dir(folder)
    dest = os.path.join(d, name)
    if os.path.islink(dest) or os.path.isdir(dest):
        fail("%s/%s is a link or a folder" % (folder, name))
    tmp = os.path.join(d, ".tmp-%s-%s" % (os.urandom(6).hex(), name))
    try:
        write(tmp)
        os.replace(tmp, dest)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    if not inside(dest):
        fail("%s/%s resolves outside the work folder" % (folder, name))
    return dest


def run(argv):
    p = subprocess.run(argv, capture_output=True, text=True)
    return p


def dims(path):
    p = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=width,height", "-of", "csv=p=0", path])
    if p.returncode != 0:
        fail("ffprobe could not read %s" % os.path.basename(path))
    return p.stdout.strip()


def count_arg(n):
    if n not in COUNTS:
        fail("count must be one of 3, 5, 7, 10")
    return n


def bytes_writer(data):
    def w(tmp):
        with open(tmp, "wb") as fh:
            fh.write(data)
    return w


def write_json(folder, name, data):
    def w(tmp):
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
    place(folder, name, w)


def cmd_spec(a):
    if a.width != 1080 or a.height not in (1080, 1350):
        fail("width must be 1080 and height 1080 or 1350")
    src = os.path.join(os.path.realpath(a.recipe_dir), "acceptance.json")
    with open(src, encoding="utf-8") as fh:
        spec = json.load(fh)
    for c in spec["checks"]:
        if c.get("type") == "dims":
            c.update(id="canvas_%dx%d" % (a.width, a.height), w=a.width, h=a.height)
        if c.get("crop"):
            c["crop"] = "%d:%d:0:0" % (a.width, a.height)
    write_json("work", "acceptance.json", spec)
    print("wrote work/acceptance.json for %dx%d" % (a.width, a.height))


def cmd_slides(a):
    n = count_arg(a.count)
    want = "%d,%d" % (a.width, a.height)
    entries = []
    paths = []
    for i in range(1, n + 1):
        src = safe_read("slides/slide-%d.png" % i)
        with open(src, "rb") as fh:
            data = fh.read()
        if data[:8] != b"\x89PNG\r\n\x1a\n":
            fail("slides/slide-%d.png is not a PNG" % i)
        if dims(src) != want:
            fail("slides/slide-%d.png is not %dx%d" % (i, a.width, a.height))
        dest = place("saves", "slide_%d.png" % i, bytes_writer(data))
        paths.append(dest)
        entries.append({"n": i, "file": "saves/slide_%d.png" % i,
                        "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})
    with open(paths[0], "rb") as fh:
        first = fh.read()
    place("saves", "cover.png", bytes_writer(first))

    def sheet(tmp):
        argv = ["ffmpeg", "-v", "error", "-y"]
        for p in paths:
            argv += ["-i", p]
        argv += ["-filter_complex", "vstack=inputs=%d" % n, "-frames:v", "1", tmp]
        r = run(argv)
        if r.returncode != 0:
            fail("ffmpeg could not build the sheet: " + r.stderr.strip()[:200])
    sheet_path = place("saves", "slide_sheet.png", sheet)
    if dims(sheet_path) != "%d,%d" % (a.width, a.height * n):
        fail("slide_sheet.png has the wrong size")
    write_json("saves", "slides.json", {"width": a.width, "height": a.height,
                                        "count": n, "slides": entries})
    print("saved %d slides, cover, slide_sheet.png and slides.json" % n)


def gate(blocks_dir):
    check = os.path.join(os.path.realpath(blocks_dir), "b-qa-gate", "check.py")
    if not os.path.isfile(check):
        fail("b-qa-gate/check.py not found under the blocks folder")
    return check


def cmd_qa(a):
    n = count_arg(a.count)
    check = gate(a.blocks_dir)
    safe_read("work/acceptance.json")
    safe_dir("work/qa")
    bad = 0
    for i in range(1, n + 1):
        r = run([sys.executable, "-I", check, "--kind", "image", "--spec", "work/acceptance.json",
                 "--input", "saves/slide_%d.png" % i, "--out", "work/qa/slide_%d.json" % i])
        print("slide %d: exit %d  %s" % (i, r.returncode, r.stdout.strip().replace("\n", " | ")))
        bad += r.returncode not in (0, 4)
    if bad:
        fail("%d slide(s) failed the mechanical checks; fix the HTML and render again" % bad)


def cmd_finalize(a):
    n = count_arg(a.count)
    check = gate(a.blocks_dir)
    bad = 0
    for i in range(1, n + 1):
        r = run([sys.executable, "-I", check, "--finalize", "work/qa/slide_%d.json" % i,
                 "--answers", "work/qa/answers_%d.json" % i, "--out", "work/qa/final_%d.json" % i])
        print("slide %d: exit %d  %s" % (i, r.returncode, r.stdout.strip().replace("\n", " | ")))
        bad += r.returncode != 0
    if bad:
        fail("%d slide(s) did not pass" % bad)


def cmd_report(a):
    n = count_arg(a.count)
    out = []
    for i in range(1, n + 1):
        with open(safe_read("work/qa/final_%d.json" % i), encoding="utf-8") as fh:
            card = json.load(fh)
        notes = ["%s: %s" % (c["id"], c["note"]) for c in card.get("checks", []) if c.get("note")]
        out.append({"n": i, "verdict": card.get("verdict"), "scorecard": "work/qa/final_%d.json" % i,
                    "notes": notes})
        if card.get("verdict") != "PASS" or card.get("finalized") is not True:
            write_json("saves", "qa_report.json", {"rounds": a.rounds, "slides": out})
            fail("slide %d is not a finalized PASS" % i)
    write_json("saves", "qa_report.json", {"rounds": a.rounds, "slides": out})
    print("wrote saves/qa_report.json: all %d slides PASS" % n)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in (("spec", cmd_spec), ("slides", cmd_slides), ("qa", cmd_qa),
                     ("finalize", cmd_finalize), ("report", cmd_report)):
        p = sub.add_parser(name)
        p.set_defaults(fn=fn)
        if name == "spec":
            p.add_argument("--recipe-dir", required=True)
        if name in ("spec", "slides"):
            p.add_argument("--width", type=int, required=True)
            p.add_argument("--height", type=int, required=True)
        if name != "spec":
            p.add_argument("--count", type=int, required=True)
        if name in ("qa", "finalize"):
            p.add_argument("--blocks-dir", required=True)
        if name == "report":
            p.add_argument("--rounds", type=int, required=True)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
