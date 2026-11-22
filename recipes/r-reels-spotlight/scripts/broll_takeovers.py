#!/usr/bin/env python3
# usage: python3 scripts/broll_takeovers.py   (from the step work folder)
# Trim each b-roll beat, FIT the whole clip and fill the frame edges with a blurred copy. Silent.
# Reads work/beat_list.json, writes work/broll_takeovers/broll_tk<N>.mp4 (N is the beat's whole-number
# index, nothing else from the file becomes part of a path). Any bad value or failed ffmpeg stops it.
import json
import math
import os
import subprocess
import sys

ROOT = os.path.realpath("inputs/broll") + os.sep
OUT = "work/broll_takeovers"


def num(v, what):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        sys.exit("broll_takeovers: %s must be a number (got %r)" % (what, v))
    return float(v)


def beat_fields(b):
    if not isinstance(b, dict):
        sys.exit("broll_takeovers: a beat is not an object")
    idx = b.get("index")
    if isinstance(idx, bool) or not isinstance(idx, int) or not 0 <= idx <= 100000:
        sys.exit("broll_takeovers: a beat index must be a whole number from 0 to 100000 (got %r)" % (idx,))
    br = b.get("broll")
    if not isinstance(br, dict) or not isinstance(br.get("clip"), str):
        sys.exit("broll_takeovers: beat %d has no broll clip" % idx)
    t_in, t_out = num(br.get("in"), "beat %d in" % idx), num(br.get("out"), "beat %d out" % idx)
    if not 0 <= t_in < t_out:
        sys.exit("broll_takeovers: beat %d needs 0 <= in < out" % idx)
    return idx, br["clip"], t_in, t_out


with open("work/beat_list.json", encoding="utf-8") as fh:
    bl = json.load(fh)
beats = bl.get("beats") if isinstance(bl, dict) else None
if not isinstance(beats, list):
    sys.exit("broll_takeovers: beat_list.json has no beats list")
os.makedirs(OUT, exist_ok=True)
for old in os.listdir(OUT):                       # a clip left by an earlier run is never reused
    if old.startswith("broll_tk") and old.endswith(".mp4"):
        os.unlink(os.path.join(OUT, old))
for b in [b for b in beats if isinstance(b, dict) and b.get("kind") == "broll"]:
    idx, clip, t_in, t_out = beat_fields(b)
    real = os.path.realpath(clip)
    if not real.startswith(ROOT) or not os.path.isfile(real):   # only the order's own b-roll folder is read
        sys.exit("b-roll beat %s points outside inputs/broll: %r" % (idx, clip))
    out_path = "%s/broll_tk%d.mp4" % (OUT, idx)
    r = subprocess.run(["ffmpeg", "-y", "-ss", "%.3f" % t_in, "-t", "%.3f" % (t_out - t_in), "-protocol_whitelist", "file", "-i", real,
        "-filter_complex", ("[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=40:2,setsar=1[bg];"
                "[0:v]scale=1080:1920:force_original_aspect_ratio=decrease,setsar=1[fg];"
                "[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p,fps=30[bv]"),
        "-map", "[bv]", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", out_path])
    if r.returncode != 0 or not os.path.isfile(out_path) or os.path.getsize(out_path) == 0:
        sys.exit("broll_takeovers: ffmpeg failed for beat %d" % idx)
    print("[spotlight] broll clip %d: %s [%.2f..%.2f] -> %s" % (idx, clip, t_in, t_out, out_path))
