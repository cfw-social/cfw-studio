#!/usr/bin/env python3
"""usage: python3 scripts/broll_overlay.py   (from the step work folder)

Composite the pre-rendered b-roll takeovers onto work/visuals.mp4, each at its beat window.
Reads work/beat_list.json and the clips scripts/broll_takeovers.py wrote, named from each beat's
whole-number index (no path is taken from the beat list). Writes work/scenes.mp4, which is removed first so a
stale file is never used. Any bad value or failed ffmpeg stops it with a non-zero exit.
ffmpeg is started with an argument list, never through a shell.
"""
import json
import math
import os
import shutil
import subprocess
import sys

OUT = "work/scenes.mp4"


def num(v, what):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        sys.exit("broll_overlay: %s must be a number (got %r)" % (what, v))
    return float(v)


if os.path.lexists(OUT):
    os.unlink(OUT)
if not os.path.isfile("work/visuals.mp4"):
    sys.exit("broll_overlay: work/visuals.mp4 is missing")
with open("work/beat_list.json", encoding="utf-8") as fh:
    bl = json.load(fh)
beats = bl.get("beats") if isinstance(bl, dict) else None
if not isinstance(beats, list):
    sys.exit("broll_overlay: beat_list.json has no beats list")
bb = []
for b in beats:
    if not isinstance(b, dict) or b.get("kind") != "broll":
        continue
    idx = b.get("index")
    if isinstance(idx, bool) or not isinstance(idx, int) or not 0 <= idx <= 100000:
        sys.exit("broll_overlay: a beat index must be a whole number (got %r)" % (idx,))
    path = "work/broll_takeovers/broll_tk%d.mp4" % idx
    if not os.path.isfile(path):
        sys.exit("broll_overlay: %s is missing; run scripts/broll_takeovers.py first" % path)
    s, e = num(b.get("start"), "beat %d start" % idx), num(b.get("end"), "beat %d end" % idx)
    if not 0 <= s < e:
        sys.exit("broll_overlay: beat %d needs 0 <= start < end" % idx)
    bb.append((path, s, e))
if not bb:
    shutil.copyfile("work/visuals.mp4", OUT)
    raise SystemExit(0)
cmd = ["ffmpeg", "-y", "-protocol_whitelist", "file", "-i", "work/visuals.mp4"]
for path, _, _ in bb:
    cmd += ["-protocol_whitelist", "file", "-i", path]
parts, cur = [], "[0:v]"
for i, (_, s, e) in enumerate(bb):
    nxt = "[ov%d]" % i if i < len(bb) - 1 else "[vfinal]"
    parts.append("[%d:v]setpts=PTS-STARTPTS+%.3f/TB[brl%d];%s[brl%d]overlay=enable='between(t,%.3f,%.3f)':eof_action=pass%s" % (i + 1, s, i, cur, i, s, e, nxt))
    cur = nxt
cmd += ["-filter_complex", ";".join(parts), "-map", "[vfinal]", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-preset", "medium", "-crf", "19", "-r", "30", "-movflags", "+faststart", OUT]
r = subprocess.run(cmd)
if r.returncode != 0 or not os.path.isfile(OUT) or os.path.getsize(OUT) == 0:
    sys.exit("broll_overlay: ffmpeg failed")
