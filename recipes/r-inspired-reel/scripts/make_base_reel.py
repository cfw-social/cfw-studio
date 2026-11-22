#!/usr/bin/env python3
"""Fit the avatar narration video to a 1080x1920, 30 fps reel at -14 LUFS.

  python3 make_base_reel.py --avatar work/avatar.mp4 --out reel/base.mp4 [--lufs -14] [--pad-color 14181F]

Picture: scaled to fit 1080x1920 (padded with --pad-color if the shape differs), 30 fps, H.264.
Sound: two-pass loudness normalisation (measure, then apply), AAC 192k, 48 kHz, stereo. The
captions step keeps this sound as it is, so the level is set here, once.
"""
import argparse
import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rs_common import (Stop, hex6, main, need_tools, number, probe, rel, resolve, run as run_tool,  # noqa: E402
                       temp_in, work_root)


def measure(video, lufs):
    af = "loudnorm=I=%.1f:TP=-1.5:LRA=11:print_format=json" % lufs
    p = run_tool(["ffmpeg", "-nostdin", "-hide_banner", "-protocol_whitelist", "file", "-i", video,
                  "-vn", "-af", af, "-f", "null", "-"], 900)
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", p.stderr, re.S)
    if p.returncode != 0 or not m:
        raise Stop("could not measure the loudness", 1)
    try:
        data = json.loads(m.group(0))
        vals = {k: float(data[k]) for k in ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")}
    except (ValueError, KeyError):
        raise Stop("could not read the loudness measure", 1)
    if not all(math.isfinite(v) for v in vals.values()):
        raise Stop("the narration is silent; nothing to normalise", 1)
    return vals


def run(argv):
    ap = argparse.ArgumentParser(prog="make_base_reel.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--avatar", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--lufs", default="-14")
    ap.add_argument("--pad-color", default="14181F")
    ap.add_argument("--workdir")
    a = ap.parse_args(argv)
    lufs = number(a.lufs, "--lufs", -30, -5)
    pad = hex6(a.pad_color, "--pad-color")
    root = work_root(a.workdir)
    need_tools("ffmpeg", "ffprobe")
    src = resolve(root, a.avatar, must_exist=True, kind="file")
    if os.path.abspath(resolve(root, a.out)) == os.path.abspath(src):
        raise Stop("--out must not be the input")
    info = probe(src)
    if not info["has_video"] or not info["has_audio"]:
        raise Stop("the avatar video needs a picture and a sound track", 1)
    m = measure(src, lufs)
    af = ("loudnorm=I=%.1f:TP=-1.5:LRA=11:measured_I=%.2f:measured_TP=%.2f:measured_LRA=%.2f:"
          "measured_thresh=%.2f:offset=%.2f:linear=true,aresample=48000"
          % (lufs, m["input_i"], m["input_tp"], m["input_lra"], m["input_thresh"], m["target_offset"]))
    vf = ("scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=0x%s,"
          "setsar=1,fps=30,format=yuv420p" % pad)
    target, tmp = temp_in(root, a.out, ".mp4")
    try:
        p = run_tool(["ffmpeg", "-nostdin", "-v", "error", "-y", "-protocol_whitelist", "file", "-i", src,
                      "-vf", vf, "-af", af, "-c:v", "libx264", "-crf", "19", "-preset", "medium",
                      "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
                      "-movflags", "+faststart", "-f", "mp4", tmp], 1800)
        if p.returncode != 0:
            raise Stop("ffmpeg could not make the reel", 1)
        out = probe(tmp)
        if abs(out["duration"] - info["duration"]) > 0.5:
            raise Stop("the reel length changed by more than half a second", 1)
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    print("BASE_REEL: %s (%.1f s)" % (rel(root, target), out["duration"]))
    return 0


if __name__ == "__main__":
    main(run)
