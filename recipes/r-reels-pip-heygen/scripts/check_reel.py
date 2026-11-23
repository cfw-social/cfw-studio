#!/usr/bin/env python3
"""Three small checks on a video of this recipe. Needs ffmpeg and ffprobe. Writes nothing.

  python3 check_reel.py duration --video F --expect SECONDS [--tol 0.15]
  python3 check_reel.py range    --video F --min SECONDS --max SECONDS
  python3 check_reel.py frames   --video F [--floor 16]
  python3 check_reel.py voice    --video F --beats prior/beat_list.json

range     the video's length is from --min to --max seconds.
duration  the video's length is within --tol seconds of --expect.
frames    the first frame, the last frame and six sampled frames (5, 20, 40, 60, 80, 95 percent)
          each have a mean brightness above --floor (0 to 255); a black frame fails.
voice     the audio has a real mean volume (above -70 dB, not silence) under every beat of the beat list, so the
          voice bed runs unbroken under the whole reel.
Exit 0 passed, 1 a check failed (the reason is printed), 2 bad arguments or an unreadable file.
"""
import argparse
import json
import re
import subprocess
import sys


SILENT_DB = -70.0   # digital silence measures about -91 dB; speech at the bed level is near -16 dB


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def length(video):
    p = run(["ffprobe", "-v", "error", "-protocol_whitelist", "file", "-show_entries", "format=duration", "-of", "csv=p=0", video])
    try:
        return float(p.stdout.strip())
    except ValueError:
        raise SystemExit("check_reel.py: cannot read the length of %s" % video)


def luma(video, t):
    p = run(["ffmpeg", "-hide_banner", "-protocol_whitelist", "file", "-ss", "%.3f" % max(t, 0.0), "-i", video, "-frames:v", "1",
             "-vf", "signalstats,metadata=print:key=lavfi.signalstats.YAVG", "-f", "null", "-"])
    m = re.search(r"YAVG=([0-9.]+)", p.stderr + p.stdout)
    return float(m.group(1)) if m else None


def cmd_duration(a):
    got = length(a.video)
    if abs(got - a.expect) > a.tol:
        print("FAIL: length %.2f s, expected %.2f s (tolerance %.2f)" % (got, a.expect, a.tol))
        return 1
    print("length OK: %.2f s" % got)
    return 0


def cmd_range(a):
    got = length(a.video)
    if not a.min <= got <= a.max:
        print("FAIL: length %.2f s, outside %.1f to %.1f s" % (got, a.min, a.max))
        return 1
    print("length OK: %.2f s" % got)
    return 0


def cmd_frames(a):
    d = length(a.video)
    points = [("first", 0.0)] + [("%d%%" % p, d * p / 100.0) for p in (5, 20, 40, 60, 80, 95)] + [("last", d - 0.1)]
    bad = []
    for name, t in points:
        y = luma(a.video, t)
        if y is None or y <= a.floor:
            bad.append("%s frame (t=%.1fs) brightness %s" % (name, t, "unreadable" if y is None else "%.1f" % y))
    if bad:
        print("FAIL: black or unreadable: " + "; ".join(bad))
        return 1
    print("frames OK: %d sampled, all above %g" % (len(points), a.floor))
    return 0


def cmd_voice(a):
    try:
        with open(a.beats, encoding="utf-8") as fh:
            beats = json.load(fh)["beats"]
        windows = sorted((float(b["start"]), float(b["end"])) for b in beats)
    except (OSError, ValueError, KeyError, TypeError):
        raise SystemExit("check_reel.py: %s is not a beat list" % a.beats)
    bad = []
    for s, e in windows:
        p = run(["ffmpeg", "-hide_banner", "-protocol_whitelist", "file", "-ss", "%.3f" % s, "-t", "%.3f" % (e - s), "-i", a.video,
                 "-af", "volumedetect", "-f", "null", "-"])
        m = re.search(r"mean_volume: (-?[0-9.]+|-inf) dB", p.stderr)
        if not m or m.group(1) == "-inf" or float(m.group(1)) < SILENT_DB:
            bad.append("%.1f-%.1f" % (s, e))
    if bad:
        print("FAIL: the voice is silent under beat(s) %s" % ", ".join(bad))
        return 1
    print("voice OK under %d beats" % len(windows))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("duration"); d.add_argument("--video", required=True)
    d.add_argument("--expect", required=True, type=float); d.add_argument("--tol", type=float, default=0.15)
    r = sub.add_parser("range"); r.add_argument("--video", required=True)
    r.add_argument("--min", required=True, type=float); r.add_argument("--max", required=True, type=float)
    f = sub.add_parser("frames"); f.add_argument("--video", required=True); f.add_argument("--floor", type=float, default=16.0)
    v = sub.add_parser("voice"); v.add_argument("--video", required=True); v.add_argument("--beats", required=True)
    a = p.parse_args(argv)
    try:
        return {"duration": cmd_duration, "range": cmd_range, "frames": cmd_frames, "voice": cmd_voice}[a.cmd](a)
    except SystemExit as e:
        if isinstance(e.code, str):
            sys.stderr.write(e.code + "\n")
            return 2
        raise


if __name__ == "__main__":
    sys.exit(main())
