#!/usr/bin/env python3
"""Grade the reel, lay the caption render over it, and mix its audio with sound effects (and music), in one ffmpeg run.

  python3 mux.py --reel work/assembled.mp4 --captions-mov work/premium/captions.mov \
      --plan work/premium/plan.json --out work/premium/polished.mp4 [--sfx on|off] [--workdir work]
  python3 mux.py --reel ... --no-captions --plan ... --out ...        (grade and sound only)

The reel is graded first, then the captions (a transparent video from hf_render.py --format mov) go on top,
so the footage is graded and the captions keep their exact brand colours. The footage never passes through
the renderer. The reel's audio is used as it is: no loudness change, amix runs with normalize=0 so its level
does not move. Exactly one of --captions-mov and --no-captions is required. Sound effects come only from this block's assets/sfx folder, by one of the eight fixed names, and
each file is checked against assets/sfx/SHA256SUMS first. A music file is accepted only inside
<work folder>/inputs. ffmpeg is started with an argument list. No shell, no generated script.

Exit codes: 0 done, 1 plan or input problem or ffmpeg failed, 2 bad arguments, 3 ffmpeg or ffprobe missing.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import plan_lib as pl  # noqa: E402


def sfx_path(name):
    """Path of one of the eight sound effects, after checking its hash. Raises PlanError."""
    if name not in pl.SFX_NAMES:
        raise pl.PlanError(["unknown sound effect %r" % (name,)])
    path = os.path.join(pl.SFX_DIR, name + ".wav")
    sums = {}
    try:
        with open(os.path.join(pl.SFX_DIR, "SHA256SUMS"), encoding="utf-8") as fh:
            for line in fh:
                parts = line.split()
                if len(parts) == 2:
                    sums[parts[1].lstrip("*")] = parts[0]
        with open(path, "rb") as fh:
            digest = hashlib.sha256(fh.read()).hexdigest()
    except OSError as e:
        raise pl.PlanError(["sound effect %s cannot be read: %s" % (name, e)])
    if sums.get(name + ".wav") != digest:
        raise pl.PlanError(["sound effect %s does not match assets/sfx/SHA256SUMS" % name])
    return path


def build_command(reel, captions, out, grade, cues, music, timing):
    """The full ffmpeg argument list. `captions` is the transparent caption render or None;
    `cues` is [(path, ms, gain)]; `music` is (path, gain) or None.

    Input 0 is the reel. The grade is applied to the reel's picture only, then the captions are laid over
    it, so the captions keep their exact colours. The reel's audio is used as it is.
    `timing` is the reel's own {"fps", "frames", "seconds"}: the output gets exactly that many frames at that
    rate, and the sound is padded or cut to that length, so nothing mixed in can lengthen or shorten it.
    """
    cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-protocol_whitelist", "file"]
    cmd += pl.input_format_args(reel, "--reel") + ["-i", reel]
    first = 1
    if captions:
        cmd += ["-protocol_whitelist", "file"] + pl.input_format_args(captions, "--captions-mov") + ["-i", captions]
        first = 2
    for p, _, _ in cues:
        cmd += ["-protocol_whitelist", "file", "-f", "wav", "-i", p]   # the shipped, hash-checked files
    if music:
        cmd += ["-protocol_whitelist", "file"] + pl.input_format_args(music[0], "music.file") + ["-i", music[0]]
    parts, mix, n = [], "[0:a]", 1
    for j, (_, ms, gain) in enumerate(cues):
        parts.append("[%d:a]adelay=%d|%d,volume=%.3f[s%d]" % (j + first, ms, ms, gain, j))
        mix += "[s%d]" % j
        n += 1
    if music:
        parts.append("[%d:a]volume=%.3f[m]" % (len(cues) + first, music[1]))
        mix += "[m]"
        n += 1
    fit = "apad=whole_dur=%.6f,atrim=end=%.6f,asetpts=N/SR/TB" % (timing["seconds"], timing["seconds"])
    if n == 1:
        audio = "[0:a]%s[aout]" % fit
    else:
        audio = ";".join(parts) + ";%samix=inputs=%d:normalize=0:duration=first,%s[aout]" % (mix, n, fit)
    if captions:
        video = "[0:v]%s,format=yuv420p[g];[g][1:v]overlay=format=auto:eof_action=pass,format=yuv420p[vout]" % pl.GRADES[grade]
    else:
        video = "[0:v]%s,format=yuv420p[vout]" % pl.GRADES[grade]
    cmd += ["-filter_complex", "%s;%s" % (video, audio),
            "-map", "[vout]", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-r", timing["fps"], "-frames:v", str(timing["frames"]),
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", "-movflags", "+faststart", out]
    return cmd


def build_parser():
    ap = argparse.ArgumentParser(prog="mux.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--reel", required=True)
    cap = ap.add_mutually_exclusive_group(required=True)
    cap.add_argument("--captions-mov", help="the transparent caption render (mov with alpha), same size as the reel")
    cap.add_argument("--no-captions", action="store_true", help="no caption overlay: grade and sound only")
    ap.add_argument("--plan", required=True)
    ap.add_argument("--out", required=True, help="output .mp4, inside the work folder")
    ap.add_argument("--sfx", choices=("on", "off"), default="on", help="off mixes no sound effects")
    ap.add_argument("--workdir", default=".")
    ap.add_argument("--print-command", action="store_true", help="check everything, print the ffmpeg argument list as JSON, run nothing")
    return ap


def main(argv):
    args = build_parser().parse_args(argv)
    try:
        root = pl.workdir_root(args.workdir)
        captions = None
        if args.captions_mov:
            captions = pl.check_in_workdir(args.captions_mov, root, "--captions-mov", must_exist=True)
        reel = pl.check_in_workdir(args.reel, root, "--reel", must_exist=True)
        plan_path = pl.check_in_workdir(args.plan, root, "--plan", must_exist=True)
        out = pl.check_output_path(args.out, root, "--out", (".mp4",))
        if out in (reel, plan_path, captions):
            raise pl.PlanError(["--out must not be one of the input files"])
        try:
            plan = pl.load_json(plan_path)
        except (OSError, ValueError) as e:
            sys.stderr.write("mux.py: cannot read the plan: %s\n" % e)
            return 2
        pl.require_video(reel, "--reel")
        duration = pl.probe_duration(reel)
        timing = pl.probe_video_timing(reel, "--reel")
        pl.require_sound_plan(plan, duration, root, captions=False, sfx=args.sfx == "on")
        if captions:
            pl.require_overlay(captions, reel, "--captions-mov")
        if not pl.has_audio(reel):
            raise pl.PlanError(["--reel has no audio stream"])
        cues = []
        if args.sfx == "on":
            for c in plan.get("sfx") or []:
                cues.append((sfx_path(c["name"]), int(round(float(c["t"]) * 1000)), float(c.get("gain", 0.5))))
        music = None
        if plan.get("music"):
            music = (pl.check_music_path(plan["music"]["file"], root), float(plan["music"].get("gain", 0.15)))
            pl.require_audio_file(music[0], "music.file")
        used = {os.path.realpath(x) for x in [x for x in (reel, plan_path, captions) if x] + [c[0] for c in cues] + ([music[0]] if music else [])}
        if os.path.realpath(out) in used:
            raise pl.PlanError(["--out must not be one of the input files"])
        cmd = build_command(reel, captions, out, plan["grade"], cues, music, timing)
    except FileNotFoundError as e:
        sys.stderr.write("mux.py: a required tool is missing: %s\n" % e)
        return 3
    if args.print_command:
        print(json.dumps(cmd))
        return 0
    tmp = pl.temp_output(out, root, ".mp4", "--out")
    try:
        cmd = build_command(reel, captions, tmp, plan["grade"], cues, music, timing)
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        except FileNotFoundError as e:
            sys.stderr.write("mux.py: ffmpeg is missing: %s\n" % e)
            return 3
        if res.returncode != 0:
            sys.stderr.write("mux.py: ffmpeg failed (exit %d)\n%s\n" % (res.returncode, res.stderr[-2000:]))
            return 1
        pl.finish_temp(tmp, out, root, "--out")
        tmp = None
    finally:
        pl.drop_temp(tmp)
    print("mixed: %s (grade %s, %d sfx%s)" % (os.path.relpath(out, root), plan["grade"], len(cues), ", music" if music else ""))
    return 0


if __name__ == "__main__":
    sys.exit(pl.run_main(main, "mux.py", sys.argv[1:]))
