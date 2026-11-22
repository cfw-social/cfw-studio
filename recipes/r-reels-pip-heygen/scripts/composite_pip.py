#!/usr/bin/env python3
"""Put the speaker on the background as a rounded, ringed card; keep the voice bed; add the end card.

  python3 composite_pip.py --background prior/background.mp4 --voice prior/voice_track.mp4 \
      --mask work/pip-mask.png [--frame work/pip-frame.png] --out work/composed.mp4 \
      --bed-dur 30.5 [--card 364x504] [--margin 110] [--pad 30] \
      [--cta-mov work/cta-card.mov --cta-start 27.5 --cta-dur 3]

One ffmpeg run, started with an argument list (no shell, nothing from the order in a command
line). The card is FILLED, not fitted: scale to cover, then a top-biased crop, so it shows no bars
and the head is not cut. The mask's luma is the card's alpha. The frame (ring and shadow, `pad`
px larger than the card on every side) goes under the card. The voice bed's audio is copied, not
re-encoded. The picture is held on its last frame if it is short, and the output is cut at
--bed-dur. With --cta-mov, that transparent clip is laid over the last seconds.
Exit 0 written, 1 ffmpeg failed, 2 bad arguments.
"""
import argparse
import os
import re
import subprocess
import sys


def build_command(a):
    m = re.fullmatch(r"([0-9]+)x([0-9]+)", a.card)
    if not m:
        raise ValueError("--card must be WxH, for example 364x504")
    cw, ch = int(m.group(1)), int(m.group(2))
    if not (0 < cw <= 1080 and 0 < ch <= 1920):
        raise ValueError("--card is outside the 1080x1920 canvas")
    if not (0 <= a.margin <= 600 and 0 <= a.pad <= 200 and 0 < a.bed_dur <= 600):
        raise ValueError("--margin, --pad or --bed-dur is out of range")
    ring = a.frame is not None
    ins = [a.background, a.voice, a.mask] + ([a.frame] if ring else []) + ([a.cta_mov] if a.cta_mov else [])
    for path in ins:
        if not os.path.isfile(path):
            raise ValueError("input %s is missing" % path)
    cmd = ["ffmpeg", "-v", "error", "-y", "-protocol_whitelist", "file", "-i", a.background,
           "-protocol_whitelist", "file", "-i", a.voice,
           "-protocol_whitelist", "file", "-loop", "1", "-framerate", "30", "-i", a.mask]
    n = 3
    if ring:
        cmd += ["-protocol_whitelist", "file", "-loop", "1", "-framerate", "30", "-i", a.frame]
        n += 1
    cta = n if a.cta_mov else None
    if cta:
        cmd += ["-protocol_whitelist", "file", "-i", a.cta_mov]
    g = ["[1:v]scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d:(iw-ow)/2:0,setsar=1,format=yuva444p[fit]" % (cw, ch, cw, ch),
         "[fit][2:v]alphamerge[card]",
         "[0:v]tpad=stop_mode=clone:stop_duration=2,format=yuv420p[bg]"]
    last = "bg"
    if ring:
        g.append("[%s][3:v]overlay=(W-w)/2:(H-h-%d):format=auto:shortest=0[ringed]" % (last, a.margin - a.pad))
        last = "ringed"
    g.append("[%s][card]overlay=(W-w)/2:(H-h-%d):format=auto:shortest=0[%s]" % (last, a.margin, "pip" if cta else "v"))
    if cta:
        g.append("[%d:v]trim=duration=%g,setpts=PTS-STARTPTS+%g/TB[cta]" % (cta, a.cta_dur, a.cta_start))
        g.append("[pip][cta]overlay=enable='between(t,%g,%g)':eof_action=pass[v]" % (a.cta_start, a.bed_dur))
    cmd += ["-filter_complex", ";".join(g), "-map", "[v]", "-map", "1:a", "-c:v", "libx264", "-preset", "medium",
            "-crf", "19", "-pix_fmt", "yuv420p", "-r", "30", "-c:a", "copy", "-t", "%g" % a.bed_dur,
            "-movflags", "+faststart", a.out]
    return cmd


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--background", required=True)
    p.add_argument("--voice", required=True)
    p.add_argument("--mask", required=True)
    p.add_argument("--frame", default=None, help="ring and shadow PNG; leave out for a card with no ring")
    p.add_argument("--out", required=True)
    p.add_argument("--bed-dur", required=True, type=float)
    p.add_argument("--card", default="364x504")
    p.add_argument("--margin", type=int, default=110, help="gap between the card and the bottom edge")
    p.add_argument("--pad", type=int, default=30, help="ring + shadow size; the frame is this much larger on each side")
    p.add_argument("--cta-mov", default=None)
    p.add_argument("--cta-start", type=float, default=0.0)
    p.add_argument("--cta-dur", type=float, default=3.0)
    a = p.parse_args(argv)
    try:
        cmd = build_command(a)
    except ValueError as e:
        sys.stderr.write("composite_pip.py: FAILED - %s\n" % e)
        return 2
    try:
        done = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    except OSError:
        sys.stderr.write("composite_pip.py: FAILED - ffmpeg could not be started\n")
        return 1
    if done.returncode != 0:
        sys.stderr.write("composite_pip.py: FAILED - ffmpeg said: %s\n" % done.stderr.strip()[-600:])
        return 1
    print("composed %s" % a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
