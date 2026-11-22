#!/usr/bin/env python3
"""Cut the b-roll beats, check every beat has a clip, and join them into the background track.

  python3 assemble_background.py --beats prior/beat_list.json --voice prior/voice_track.mp4 \
          --out saves/background.mp4 [--beats-dir work/bg_beats]

Graphics beats must already be rendered to work/bg_beats/bg_beat<N>.mp4 (build_cards.py, then
b-hyperframes). Each b-roll beat is cut from its clip (named in the beat list, which b-broll-sync
has checked to be a file inside inputs/) scaled to COVER 1080x1920, no audio. The clips are joined
and cut to the voice bed's length: 1080x1920, 30 fps, H.264, no audio. ffmpeg is started with
argument lists, never through a shell. Exit 0 written, 1 a beat is missing or ffmpeg failed.
"""
import argparse
import json
import os
import subprocess
import sys

VF = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30,format=yuv420p"


def number(v, name):
    if type(v) not in (int, float) or v != v or abs(v) == float("inf"):
        raise ValueError("%s is not a number" % name)
    return float(v)


def beat_index(b):
    """Checked before it becomes part of a file name: a plain whole number 0 to 999."""
    i = b.get("index") if isinstance(b, dict) else None
    if type(i) is not int or not 0 <= i < 1000:
        raise ValueError("a beat has an index that is not a whole number from 0 to 999 (%r)" % (i,))
    return i


def clip_path(value):
    """A b-roll clip must be a real file inside inputs/ (links followed), whatever the beat list says."""
    real = os.path.realpath(str(value))
    root = os.path.realpath("inputs")
    if os.path.commonpath([root, real]) != root or not os.path.isfile(real):
        raise ValueError("b-roll clip %r is not a file inside inputs/" % str(value)[:80])
    return os.path.relpath(real)


def ffmpeg(args):
    done = subprocess.run(["ffmpeg", "-v", "error", "-y"] + args, capture_output=True, text=True)
    if done.returncode != 0:
        raise RuntimeError(done.stderr.strip()[-500:])


def bed_length(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-protocol_whitelist", "file", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True).stdout.strip()
    return float(out)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--beats", required=True)
    p.add_argument("--voice", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--beats-dir", default="work/bg_beats")
    a = p.parse_args(argv)
    try:
        with open(a.beats, encoding="utf-8") as fh:
            beats = json.load(fh)["beats"]
        if not isinstance(beats, list):
            raise ValueError("the beat list has no beats")
        for b in beats:
            beat_index(b)
        beats = sorted(beats, key=lambda b: number(b.get("start"), "a beat's start"))
        os.makedirs(a.beats_dir, exist_ok=True)
        names = []
        for b in beats:
            name = "bg_beat%d.mp4" % beat_index(b)
            path = os.path.join(a.beats_dir, name)
            if b["kind"] == "broll":
                br = b["broll"]
                ffmpeg(["-ss", "%g" % number(br.get("in"), "a b-roll in point"),
                        "-t", "%g" % (number(b.get("end"), "a beat's end") - number(b.get("start"), "a beat's start")),
                        "-protocol_whitelist", "file", "-i", clip_path(br.get("clip")), "-vf", VF, "-an",
                        "-c:v", "libx264", "-preset", "medium", "-crf", "20", path])
            if not os.path.isfile(path) or os.path.getsize(path) == 0:
                raise RuntimeError("beat %d has no rendered clip (%s)" % (beat_index(b), path))
            names.append(name)
        listing = os.path.join(a.beats_dir, "concat.txt")
        with open(listing, "w", encoding="utf-8") as fh:
            fh.write("".join("file '%s'\n" % n for n in names))
        bed = bed_length(a.voice)
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        ffmpeg(["-protocol_whitelist", "file", "-f", "concat", "-safe", "1", "-i", listing, "-vf", VF, "-t", "%g" % bed, "-an", "-c:v", "libx264",
                "-preset", "medium", "-crf", "20", "-movflags", "+faststart", a.out])
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as e:
        sys.stderr.write("assemble_background.py: FAILED - %s\n" % e)
        return 1
    print("background %s (%d beats, %.2f s)" % (a.out, len(names), bed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
