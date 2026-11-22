#!/usr/bin/env python3
"""Check a polished reel against the reel it came from, then write the premium stamp.

  python3 qa.py --reel-in work/assembled.mp4 --reel-out work/premium/polished.mp4 \
      --frames-dir work/premium/qa [--captions on|off] [--sfx on|off] [--workdir work]

--grade is required: pass the plan's grade. With --grade off it also compares the average colour of the input and output frames (Y, U and V, in levels of
255, whole frame) at the same four points and fails if any differs by more than --max-shift (default 1.5). The
footage is not re-rendered, so on a reel with no grade the only change is the caption pixels and one encode.
With a grade, the colour is meant to change and this check is skipped. The grade and whether the check ran
are recorded in .gate/premium.json.

Checks: the output decodes cleanly, it has exactly the input's picture frame count and frame rate, and it has
video and audio. Saves four frames (at 10, 35, 60 and 85 percent) as PNG files in --frames-dir for a
person or a vision step to look at. Only after all checks pass does it write .gate/premium.json beside the
output, recording what was applied. The stamp does not replace looking at the frames.

Exit codes: 0 done, 1 a check failed, 2 bad arguments, 3 ffmpeg or ffprobe missing.
"""
import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import plan_lib as pl  # noqa: E402

FRAME = 1.0 / 30.0
DEFAULT_MAX_SHIFT = 1.5


def build_parser():
    ap = argparse.ArgumentParser(prog="qa.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--reel-in", required=True)
    ap.add_argument("--reel-out", required=True)
    ap.add_argument("--frames-dir", required=True)
    ap.add_argument("--captions", choices=("on", "off"), default="on")
    ap.add_argument("--sfx", choices=("on", "off"), default="on")
    ap.add_argument("--grade", required=True, choices=("warm-amber", "clean-bright", "off"),
                    help="the plan's grade (required). With off, the colour of the footage is compared; "
                         "with a grade the colour is meant to change and that check is skipped")
    ap.add_argument("--max-shift", type=float, default=DEFAULT_MAX_SHIFT,
                    help="largest allowed change of average Y, U or V in levels of 255 (default %s)" % DEFAULT_MAX_SHIFT)
    ap.add_argument("--workdir", default=".")
    return ap


def frame_means(path, t, size):
    """Average Y, U, V (0-255) of the frame at t seconds."""
    w, h = size
    raw = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-ss", "%.2f" % t, "-protocol_whitelist", "file", "-i", path,
                          "-frames:v", "1", "-pix_fmt", "yuv420p", "-f", "rawvideo", "-"],
                         capture_output=True, check=False).stdout
    ny, nc = w * h, (w // 2) * (h // 2)
    if len(raw) < ny + 2 * nc:
        raise pl.PlanError(["could not read a frame at %.2f s from %s" % (t, os.path.basename(path))])
    return (sum(raw[:ny]) / ny, sum(raw[ny:ny + nc]) / nc, sum(raw[ny + nc:ny + 2 * nc]) / nc)


def main(argv):
    args = build_parser().parse_args(argv)
    probs = []
    colour_check = "skipped (a grade is applied)"
    try:
        root = pl.workdir_root(args.workdir)
        rin = pl.check_in_workdir(args.reel_in, root, "--reel-in", must_exist=True)
        rout = pl.check_in_workdir(args.reel_out, root, "--reel-out", must_exist=True)
        pl.refuse_inner_symlinks(args.frames_dir, root, "--frames-dir")
        frames = pl.check_in_workdir(args.frames_dir, root, "--frames-dir", must_exist=False)
        if frames == root:
            raise pl.PlanError(["--frames-dir must be a folder below the work folder"])
        gate = os.path.join(os.path.dirname(rout), ".gate")
        stamp = os.path.join(gate, "premium.json")
        pl.refuse_inner_symlinks(stamp, root, ".gate/premium.json")
        pngs = [os.path.join(frames, "qa_%d.png" % pct) for pct in (10, 35, 60, 85)]
        for x in pngs:
            pl.refuse_inner_symlinks(x, root, "--frames-dir")
        if {os.path.realpath(x) for x in pngs + [stamp]} & {rin, rout}:
            raise pl.PlanError(["an output file is also an input file"])
        if os.path.exists(frames) and not os.path.isdir(frames):
            raise pl.PlanError(["--frames-dir exists and is not a folder"])
        d_in, d_out = pl.probe_duration(rin), pl.probe_duration(rout)
        t_in, t_out = pl.probe_video_timing(rin, "--reel-in"), pl.probe_video_timing(rout, "--reel-out")
        if t_in["frames"] != t_out["frames"] or t_in["fps"] != t_out["fps"]:
            probs.append("length changed: input %d frames at %s (%.3f s), output %d frames at %s (%.3f s) (the pass must not trim or extend)"
                         % (t_in["frames"], t_in["fps"], t_in["seconds"], t_out["frames"], t_out["fps"], t_out["seconds"]))
        if not pl.has_audio(rout):
            probs.append("the output has no audio stream")
        dec = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-protocol_whitelist", "file", "-i", rout, "-f", "null", "-"],
                             capture_output=True, text=True, check=False)
        if dec.returncode != 0 or dec.stderr.strip():
            probs.append("the output does not decode cleanly: %s" % dec.stderr.strip()[:300])
        if not probs and args.grade == "off":
            if not pl.is_num(args.max_shift) or not 0 <= args.max_shift <= 50:
                raise pl.PlanError(["--max-shift must be a number from 0 to 50"])
            size_in, size_out = pl.probe_media(rin, "--reel-in")["size"], pl.probe_media(rout, "--reel-out")["size"]
            colour_check = "ran"
            if size_in != size_out:
                probs.append("picture size changed: %s to %s" % (size_in, size_out))
            else:
                for pct in (10, 35, 60, 85):
                    a = frame_means(rin, d_in * pct / 100.0, size_in)
                    b = frame_means(rout, d_out * pct / 100.0, size_in)
                    worst = max(abs(x - y) for x, y in zip(a, b))
                    if worst > args.max_shift:
                        probs.append("colour shifted by %.2f levels at %d percent (limit %s) with no grade in the plan"
                                     % (worst, pct, args.max_shift))
        if not probs:
            pl.ensure_dir(frames, root, "--frames-dir")
            for pct, png in zip((10, 35, 60, 85), pngs):
                t = "%.2f" % (d_out * pct / 100.0)
                tmp = pl.temp_output(png, root, ".png", "--frames-dir")
                try:
                    r = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", t, "-protocol_whitelist", "file",
                                        "-i", rout, "-frames:v", "1", tmp], capture_output=True, text=True, check=False)
                    if r.returncode != 0 or os.path.getsize(tmp) == 0:
                        probs.append("could not save the frame at %d percent" % pct)
                    else:
                        pl.finish_temp(tmp, png, root, "--frames-dir")
                        tmp = None
                finally:
                    pl.drop_temp(tmp)
        if probs:
            raise pl.PlanError(probs)
    except FileNotFoundError as e:
        sys.stderr.write("qa.py: a required tool is missing: %s\n" % e)
        return 3
    pl.ensure_dir(gate, root, ".gate folder")
    pl.write_file(stamp, root, data=json.dumps({"applied": True, "captions": args.captions, "sfx": args.sfx,
                                                "grade": args.grade, "colour_check": colour_check,
                                                "by": "b-reel-premium"}).encode("utf-8"), what=".gate/premium.json")
    print("qa passed: %s (frames in %s, stamp %s)" % (os.path.relpath(rout, root), os.path.relpath(frames, root),
                                                    os.path.relpath(stamp, root)))
    return 0


if __name__ == "__main__":
    sys.exit(pl.run_main(main, "qa.py", sys.argv[1:]))
