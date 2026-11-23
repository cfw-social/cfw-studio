#!/usr/bin/env python3
"""Two per-beat proofs the steps need, as one runnable script. Standard library plus ffmpeg.

  proofs.py psnr   --video saves/body_video.mp4 --beats saves/beat_list.json [--offset 0.0]
  proofs.py volume --video saves/assembled_video.mp4 --beats saves/beat_list.json [--offset 0.0]

psnr    For every graphics beat, compare the frame at 20% and the frame at 80% of its span (FFmpeg PSNR). A finite
        value at or below 45 dB means the picture moves; infinite or 50 and above means frozen (FAIL); 45 to 50 needs
        correction (FAIL). Needs a video.
volume  For every beat window, FFmpeg `volumedetect` mean volume must be finite and above -40 dB (the voice runs
        under the whole reel). Needs audio.

--offset is where beat 0 starts in the video: 0.0 for the body video and the assembled reel, 0.4 for the final
candidate (the 0.4 s cover freeze in front). Paths must be inside the current folder. ffmpeg runs as an argument
list with `-protocol_whitelist file` before each input. Exit 0 all beats passed, 1 a beat failed, 2 bad usage.
"""
import argparse
import json
import math
import os
import re
import subprocess
import sys

sys.dont_write_bytecode = True


def inside(path):
    base = os.path.realpath(os.getcwd())
    real = os.path.realpath(path)
    return real == base or real.startswith(base + os.sep)


def run(args):
    return subprocess.run(["ffmpeg", "-hide_banner", "-nostdin"] + args, capture_output=True, text=True, timeout=600).stderr


def psnr(video, t1, t2):
    # Each input is cut to two frames with an input `-t` and its audio is dropped with an input `-an`, so both
    # inputs reach their end and the psnr filter flushes and prints its summary. Stopping the run with
    # `-frames:v 1` instead races the filter: on ffmpeg 8.1 the summary is often never printed (10 of 30 runs
    # printed it on one file), and more often so on a file with an audio track. The value is the average over
    # the two frames of each side.
    err = run(["-an", "-protocol_whitelist", "file", "-ss", "%.3f" % t1, "-t", "0.07", "-i", video,
               "-an", "-protocol_whitelist", "file", "-ss", "%.3f" % t2, "-t", "0.07", "-i", video,
               "-filter_complex", "[0:v][1:v]psnr", "-f", "null", "-"])
    m = re.search(r"average:(\S+)", err)
    if not m:
        raise ValueError("no PSNR value in ffmpeg's output")
    return float("inf") if m.group(1) == "inf" else float(m.group(1))


def mean_volume(video, start, span):
    err = run(["-protocol_whitelist", "file", "-ss", "%.3f" % start, "-t", "%.3f" % span, "-i", video, "-vn", "-af", "volumedetect",
               "-f", "null", "-"])
    m = re.search(r"mean_volume: (\S+) dB", err)
    if not m:
        raise ValueError("no mean volume in ffmpeg's output (does the file have audio?)")
    return float(m.group(1))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Per-beat PSNR and volume proofs.")
    ap.add_argument("cmd", choices=["psnr", "volume"])
    ap.add_argument("--video", required=True)
    ap.add_argument("--beats", required=True)
    ap.add_argument("--offset", type=float, default=0.0)
    a = ap.parse_args(argv)
    if not (inside(a.video) and inside(a.beats)) or not math.isfinite(a.offset) or not 0 <= a.offset <= 5:
        sys.stderr.write("proofs.py: paths must be inside the work folder and --offset 0 to 5\n")
        return 2
    try:
        with open(a.beats, encoding="utf-8") as fh:
            beats = json.load(fh)["beats"]
        bad = []
        for b in beats:
            s, e = float(b["start"]) + a.offset, float(b["end"]) + a.offset
            span = e - s
            if a.cmd == "psnr":
                if b.get("kind") != "graphics":
                    continue
                v = psnr(a.video, s + span * 0.2, s + span * 0.8)
                ok = math.isfinite(v) and v <= 45
                print("%s beat %d %s psnr %.1f dB" % ("PASS" if ok else "FAIL", b["index"], b.get("slug", ""), v))
            else:
                v = mean_volume(a.video, s, span)
                ok = math.isfinite(v) and v > -40
                print("%s beat %d mean volume %.1f dB" % ("PASS" if ok else "FAIL", b["index"], v))
            if not ok:
                bad.append(b["index"])
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as e:
        print("FAIL proofs: %s" % e)
        return 1
    if bad:
        print("FAIL %s: beats %s" % (a.cmd, bad))
        return 1
    print("PASS %s: every beat passed" % a.cmd)
    return 0


if __name__ == "__main__":
    sys.exit(main())
