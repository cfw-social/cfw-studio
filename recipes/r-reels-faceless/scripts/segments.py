#!/usr/bin/env python3
"""Normalise every beat to one 1080x1920, 30 fps, silent segment and join them. Standard library plus ffmpeg.

  segments.py --beats saves/beat_list.json --bed-duration 30.0 --out saves/body_video.mp4

For beat N (the beat's `index`):
  graphics beat  work/seg/gfx-<slug>.mp4   (the page rendered with b-hyperframes)  ->  work/seg/seg-000N.mp4
  b-roll beat    broll.clip, window broll.in to broll.in + span                    ->  work/seg/seg-000N.mp4
then work/seg/concat.txt (relative names, in index order) is written and joined to --out with the concat
demuxer, `-safe 1`. The beat list is checked first (check_beats rules). Every file must be inside the current
folder; a b-roll clip must be inside inputs/. ffmpeg runs as an argument list with `-protocol_whitelist file`
before every input. Exit 0 done, 1 a check or ffmpeg failed, 2 bad usage or paths, 3 ffmpeg missing.
"""
import argparse
import math
import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import contracts  # noqa: E402

VF = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30,format=yuv420p"


def inside(path, root):
    real, base = os.path.realpath(path), os.path.realpath(root)
    return real == base or real.startswith(base + os.sep)


def ffmpeg(args):
    p = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-y"] + args, capture_output=True, text=True, timeout=1800)
    if p.returncode != 0:
        raise RuntimeError("ffmpeg failed: " + " ".join(p.stderr.split())[:200])


def no_link(path):
    if os.path.islink(path):
        raise ValueError("%s is a symbolic link; refusing to write through it" % os.path.basename(path))


def write_via_temp(final, write):
    """Run write(tmp_path) on a fresh exclusive temporary file in the target folder, then os.replace it into place.
    A link at the final name is refused, and the temporary name is never one a caller could have planted."""
    no_link(final)
    folder = os.path.dirname(os.path.abspath(final))
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".seg-", suffix=os.path.splitext(final)[1] or ".tmp")
    os.close(fd)
    try:
        write(tmp)
        no_link(final)
        os.replace(tmp, final)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Normalise and join the beat segments.")
    ap.add_argument("--beats", required=True)
    ap.add_argument("--bed-duration", required=True, type=float)
    ap.add_argument("--out", required=True)
    ap.add_argument("--inputs-dir", default="inputs")
    ap.add_argument("--seg-dir", default="work/seg")
    a = ap.parse_args(argv)
    cwd = os.getcwd()
    if not (math.isfinite(a.bed_duration) and a.bed_duration > 0) or not all(inside(p, cwd) for p in (a.beats, a.out, a.seg_dir)) \
            or os.path.islink(a.out) or not a.out.lower().endswith(".mp4"):
        sys.stderr.write("segments.py: bad --bed-duration, or a path outside the work folder, or --out is a link or not .mp4\n")
        return 2
    if not shutil.which("ffmpeg"):
        sys.stderr.write("segments.py: ffmpeg is not installed\n")
        return 3
    try:
        with open(a.beats, encoding="utf-8") as fh:
            plan = json.load(fh)
        contracts.validate_beats(plan, a.bed_duration)
        no_link(a.seg_dir)
        os.makedirs(a.seg_dir, exist_ok=True)
        if not inside(a.seg_dir, cwd):
            raise ValueError("the segment folder is outside the work folder")
        lines = []
        for beat in plan["beats"]:
            i = beat["index"]
            span = round(float(beat["end"]) - float(beat["start"]), 3)
            seg = os.path.join(a.seg_dir, "seg-%04d.mp4" % i)
            if beat["kind"] == "broll":
                b = beat.get("broll") or {}
                clip = b.get("clip")
                if not isinstance(clip, str) or not os.path.isfile(clip) or not inside(clip, os.path.join(cwd, a.inputs_dir)):
                    raise ValueError("beat %d: the clip is not a file inside %s" % (i, a.inputs_dir))
                t_in = contracts.number(b.get("in"))
                if t_in < 0:
                    raise ValueError("beat %d: negative window start" % i)
                write_via_temp(seg, lambda t: ffmpeg(["-protocol_whitelist", "file", "-ss", str(t_in), "-t", str(span), "-i", clip,
                                                      "-an", "-vf", VF, "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-f", "mp4", t]))
            else:
                src = os.path.join(a.seg_dir, "gfx-%s.mp4" % beat["slug"])
                if not os.path.isfile(src) or not inside(src, cwd):
                    raise ValueError("beat %d: %s is missing (render the page first)" % (i, src))
                write_via_temp(seg, lambda t: ffmpeg(["-protocol_whitelist", "file", "-i", src, "-an", "-vf", VF, "-t", str(span),
                                                      "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-f", "mp4", t]))
            lines.append("file 'seg-%04d.mp4'\n" % i)
        lst = os.path.join(a.seg_dir, "concat.txt")

        def put_list(t):
            with open(t, "w", encoding="utf-8") as fh:
                fh.write("".join(lines))
        write_via_temp(lst, put_list)
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        write_via_temp(a.out, lambda t: ffmpeg(["-f", "concat", "-safe", "1", "-protocol_whitelist", "file", "-i", lst, "-an",
                                                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30", "-t", str(a.bed_duration),
                                                "-movflags", "+faststart", "-f", "mp4", t]))
    except (ValueError, KeyError, TypeError, OSError, RuntimeError, subprocess.TimeoutExpired) as e:
        print("FAIL segments: %s" % e)
        return 1
    print("PASS segments: %d beats joined into %s" % (len(plan["beats"]), a.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
