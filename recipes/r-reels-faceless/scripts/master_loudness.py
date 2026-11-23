#!/usr/bin/env python3
"""Two-pass loudness master for the faceless reel. Standard library plus ffmpeg.

  master_loudness.py --in work/premium/polished.mp4 --out saves/assembled_video.mp4 [--target -14]

Pass 1 measures with ffmpeg's loudnorm (JSON). Pass 2 applies loudnorm with those measured values and
linear=true; the picture is copied, the sound is AAC 192k, 48 kHz, stereo and is cut to the picture's length (the
loudness filter and the AAC encoder both add a little tail, up to 100 ms and then one 21 ms AAC frame). A missing or non-finite
measurement is a failure: there is no one-pass fallback. ffmpeg is run with an argument list and
`-protocol_whitelist file`, so a path can only name a local file. Both paths must be inside the current
folder; the output is written to a temporary name and renamed into place. Exit 0 done, 1 failed, 2 bad
usage, 3 ffmpeg missing.
"""
import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys


def inside_cwd(path):
    root = os.path.realpath(os.getcwd())
    real = os.path.realpath(path)
    return real == root or real.startswith(root + os.sep)


def measure_args(src, target):
    return ["ffmpeg", "-hide_banner", "-nostdin", "-protocol_whitelist", "file", "-i", src, "-vn",
            "-af", "loudnorm=I=%g:TP=-1.5:LRA=11:print_format=json" % target, "-f", "null", "-"]


def parse_stats(stderr):
    blocks = re.findall(r"\{[^{}]*\}", stderr, re.S)
    if not blocks:
        raise ValueError("no loudness measurement in ffmpeg's output")
    data = json.loads(blocks[-1])
    need = ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")
    out = {}
    for key in need:
        value = float(data[key])
        if not math.isfinite(value):
            raise ValueError("a loudness measurement is not finite")
        out[key] = value
    return out


def picture_seconds(src):
    """The video stream's own length, so the mastered sound can be cut to it."""
    p = subprocess.run(["ffprobe", "-v", "error", "-protocol_whitelist", "file", "-select_streams", "v:0", "-show_entries",
                        "stream=duration", "-of", "csv=p=0", src], capture_output=True, text=True, timeout=120)
    value = float(p.stdout.strip().splitlines()[0])
    if p.returncode != 0 or not math.isfinite(value) or value <= 0:
        raise ValueError("could not read the picture length")
    return value


def apply_filter(stats, target):
    return ("loudnorm=I=%g:TP=-1.5:LRA=11:measured_I=%g:measured_TP=%g:measured_LRA=%g:measured_thresh=%g:"
            "offset=%g:linear=true:print_format=summary"
            % (target, stats["input_i"], stats["input_tp"], stats["input_lra"], stats["input_thresh"],
               stats["target_offset"]))


def main(argv=None):
    p = argparse.ArgumentParser(description="Two-pass loudness master.")
    p.add_argument("--in", dest="src", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--target", type=float, default=-14.0)
    a = p.parse_args(argv)
    if not -30 <= a.target <= -5 or not (inside_cwd(a.src) and inside_cwd(a.out)) or os.path.islink(a.out) \
            or os.path.realpath(a.src) == os.path.realpath(a.out) or not os.path.isfile(a.src):
        sys.stderr.write("master_loudness.py: bad target, or a path outside the work folder, or output equals input\n")
        return 2
    if not shutil.which("ffmpeg"):
        sys.stderr.write("master_loudness.py: ffmpeg is not installed\n")
        return 3
    try:
        first = subprocess.run(measure_args(a.src, a.target), capture_output=True, text=True, timeout=1800)
        if first.returncode != 0:
            raise ValueError("the measuring pass failed")
        stats = parse_stats(first.stderr)
        picture = picture_seconds(a.src)
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        tmp = os.path.join(os.path.dirname(os.path.abspath(a.out)), ".master-%d.mp4" % os.getpid())
        second = subprocess.run(
            ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-protocol_whitelist", "file", "-i", a.src,
             "-map", "0:v", "-map", "0:a", "-c:v", "copy", "-af", apply_filter(stats, a.target), "-t", "%.3f" % picture,
             "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", "-movflags", "+faststart", tmp],
            capture_output=True, text=True, timeout=1800)
        if second.returncode != 0:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise ValueError("the mastering pass failed")
        os.replace(tmp, a.out)
    except (ValueError, KeyError, OSError, subprocess.TimeoutExpired) as e:
        sys.stderr.write("master_loudness.py: FAILED - %s\n" % e)
        return 1
    print("mastered to %g LUFS (measured before: %.1f LUFS, %.1f dBTP): %s" % (a.target, stats["input_i"], stats["input_tp"], a.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
