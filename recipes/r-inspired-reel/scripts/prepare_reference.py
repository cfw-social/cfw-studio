#!/usr/bin/env python3
"""Take in the reference file the person supplied and extract its audio for transcription.

  python3 prepare_reference.py --input-dir inputs/reference_reel --outdir ref [--min-s 15] [--max-s 90]

The folder must hold exactly one video file (.mp4 .mov .m4v .webm) with a picture and a sound
track. The audio goes to OUTDIR/audio.wav (16 kHz, mono). The video itself is only read, never
changed, and never used in the new reel. There is no download: the person supplies the file.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rs_common import (Stop, main, need_tools, number, probe, rel, run as run_tool,  # noqa: E402
                       single_video, temp_in, work_root)

MAX_BYTES = 2 * 1024 ** 3


def run(argv):
    ap = argparse.ArgumentParser(prog="prepare_reference.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--min-s", default="15")
    ap.add_argument("--max-s", default="90")
    ap.add_argument("--workdir")
    a = ap.parse_args(argv)
    lo, hi = number(a.min_s, "--min-s", 1, 600), number(a.max_s, "--max-s", 1, 1800)
    if lo >= hi:
        raise Stop("--min-s must be smaller than --max-s")
    root = work_root(a.workdir)
    need_tools("ffmpeg", "ffprobe")
    video = single_video(root, a.input_dir)
    if os.path.getsize(video) > MAX_BYTES:
        raise Stop("the reference file is larger than 2 GiB")
    info = probe(video)
    if not info["has_video"]:
        raise Stop("the reference has no picture", 1)
    if not info["has_audio"]:
        raise Stop("the reference has no sound track, so there is nothing to transcribe", 1)
    if not lo <= info["duration"] <= hi:
        raise Stop("the reference is %.1f s; it must be from %g to %g s" % (info["duration"], lo, hi), 1)
    target, tmp = temp_in(root, os.path.join(a.outdir, "audio.wav"), ".wav")
    try:
        p = run_tool(["ffmpeg", "-nostdin", "-v", "error", "-y", "-protocol_whitelist", "file", "-i", video,
                      "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", "-f", "wav", tmp], 900)
        if p.returncode != 0 or os.path.getsize(tmp) < 1000:
            raise Stop("could not extract the audio", 1)
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    print("REFERENCE: %.1f s, audio at %s" % (info["duration"], rel(root, target)))
    return 0


if __name__ == "__main__":
    main(run)
