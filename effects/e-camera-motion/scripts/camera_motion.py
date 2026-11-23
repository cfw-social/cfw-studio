#!/usr/bin/env python3
"""camera_motion.py - add a camera move to a video clip with one ffmpeg command.

Pure ffmpeg, no browser, no GPU, no models. The ffmpeg and ffprobe programs are run with
argument lists (never a shell string). Every option is checked before it reaches an ffmpeg
filter. The input and the output must both be inside the work folder (the current folder).

Three ways of moving the camera:

  ZOOM   animated scale and crop, smooth at sub-pixel level
         push-in (alias focus)  pull-out  pan-left  pan-right  pan-up  pan-down
         ken-burns (diagonal zoom and drift)  drift (steady zoom with a slow diagonal drift)
  WARP   perspective corner-pinning that fakes a 3D lean, kept gap-free by a built-in inset
         tilt-back  tilt-forward  orbit (gentle left-right rock)  sway (slow idle float)
  CARD   the clip floats as a rounded, shadowed card on a flat colour (or transparent)
         canvas, and a virtual camera moves around it
         card-orbit  card-swoop  card-focus  card-glide

The WARP and CARD moves are 2D perspective approximations. They read well on flat footage.
They are not a true 3D orbit with depth, parallax, lighting and reflections.

Usage
  camera_motion.py INPUT --motion NAME --out OUTPUT [options]
  camera_motion.py --list

Exit codes
  0 done      1 the clip could not be read or ffmpeg failed
  2 bad arguments or a path outside the work folder (nothing was written)
  3 ffmpeg or ffprobe is not installed
"""
import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys

PI = math.pi
MAX_DIM = 16384
PRESETS = ("ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow")
OPAQUE_EXT = (".mp4", ".mov", ".mkv")
ALPHA_EXT = (".mov", ".webm")


class Usage(Exception):
    pass


class Failed(Exception):
    pass


class MissingTool(Exception):
    pass


# --------------------------------------------------------------------------- checks
def f(x):
    """A validated number written for an ffmpeg expression: plain decimal, no exponent."""
    return "%.6f" % x


def number(name, value, lo, hi):
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        raise Usage("%s must be a number from %s to %s" % (name, lo, hi))
    if not lo <= value <= hi:
        raise Usage("%s must be from %s to %s, got %s" % (name, lo, hi, value))
    return value


def colour(value):
    """'transparent' or a colour written as 0xRRGGBB or #RRGGBB; returns 'transparent' or '0xRRGGBB'."""
    v = value.strip()
    if v.lower() == "transparent":
        return "transparent"
    m = re.fullmatch(r"(?:0x|#)([0-9A-Fa-f]{6})", v)
    if not m:
        raise Usage("--background must be 0xRRGGBB, #RRGGBB or transparent")
    return "0x" + m.group(1).upper()


def canvas_size(value):
    m = re.fullmatch(r"(\d{2,4})x(\d{2,4})", value.strip().lower())
    if not m:
        raise Usage("--canvas must look like 1920x1080")
    w, h = int(m.group(1)), int(m.group(2))
    if not (16 <= w <= 4096 and 16 <= h <= 4096):
        raise Usage("--canvas sides must be from 16 to 4096")
    return w, h


def inside_work(path, what):
    work = os.path.realpath(os.getcwd())
    real = os.path.realpath(path)
    if real != work and not real.startswith(work + os.sep):
        raise Usage("%s %r must be inside the work folder (the current folder)" % (what, path))
    return real


# --------------------------------------------------------------------------- probe
def probe(path):
    """(width, height, duration seconds, fps, frames) of the first video stream."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise MissingTool("ffprobe is not installed")
    r = subprocess.run([ffprobe, "-v", "error", "-protocol_whitelist", "file", "-select_streams", "v:0",
                        "-show_entries", "stream=width,height,avg_frame_rate,nb_frames",
                        "-show_entries", "format=duration", "-of", "json", path],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if r.returncode != 0:
        raise Failed("ffprobe could not read the input as a video")
    try:
        d = json.loads(r.stdout)
        st = d["streams"][0]
        w, h = int(st["width"]), int(st["height"])
        dur = float(d["format"]["duration"])
    except (ValueError, KeyError, IndexError, TypeError):
        raise Failed("the input has no readable video stream or duration")
    if not (2 <= w <= MAX_DIM and 2 <= h <= MAX_DIM) or not (0 < dur < 36000):
        raise Failed("the input size or duration is outside what this tool accepts")
    fps = 30.0
    try:
        num, den = str(st.get("avg_frame_rate", "30/1")).split("/")
        if float(den):
            fps = float(num) / float(den)
    except (ValueError, ZeroDivisionError):
        pass
    if not 1 <= fps <= 240:
        fps = 30.0
    nb = st.get("nb_frames")
    n = int(nb) if (isinstance(nb, str) and nb.isdigit() and int(nb) > 0) else max(1, round(dur * fps))
    return w, h, dur, fps, n


# --------------------------------------------------------------------------- shared expressions
def _p_time(dur):
    return "min(t/%s,1)" % f(dur)


def _ss(p):
    return "((%s)*(%s)*(3-2*(%s)))" % (p, p, p)


def _p_frame(n):
    return "min(on/%d,1)" % max(n - 1, 1)


# --------------------------------------------------------------------------- ZOOM
ZOOM = {
    "push-in":   dict(z_in=True,  amount=0.18, drift_x=0.06, drift_y=0.0),
    "focus":     dict(z_in=True,  amount=0.18, drift_x=0.06, drift_y=0.0),
    "pull-out":  dict(z_in=False, amount=0.18, drift_x=0.0,  drift_y=0.0),
    "ken-burns": dict(z_in=True,  amount=0.20, drift_x=0.10, drift_y=0.08),
    "drift":     dict(z_in=None,  amount=0.10, drift_x=0.30, drift_y=0.15, linear=True),
    "pan-left":  dict(z_in=None,  amount=0.14, pan="left"),
    "pan-right": dict(z_in=None,  amount=0.14, pan="right"),
    "pan-up":    dict(z_in=None,  amount=0.14, pan="up"),
    "pan-down":  dict(z_in=None,  amount=0.14, pan="down"),
}
WARP = ("tilt-back", "tilt-forward", "orbit", "sway")
CARD = ("card-orbit", "card-swoop", "card-focus", "card-glide")


def _zoom(w, h, dur, amount, z_in, drift_x, drift_y, pan, linear=False):
    p = _p_time(dur)
    ss = _ss(p)
    a = f(amount)
    if z_in is True:
        z = "(1+%s*%s)" % (a, ss)
    elif z_in is False:
        z = "(1+%s*(1-%s))" % (a, ss)
    else:
        z = "(1+%s)" % a
    scale = "scale=w='2*round(iw*%s/2)':h='2*round(ih*%s/2)':eval=frame:flags=lanczos" % (z, z)
    if pan == "left":
        px, py = "(1-%s)" % ss, "0.5"
    elif pan == "right":
        px, py = ss, "0.5"
    elif pan == "up":
        px, py = "0.5", "(1-%s)" % ss
    elif pan == "down":
        px, py = "0.5", ss
    else:
        px = "(0.5+%s*(2*%s-1))" % (f(drift_x), p)
        py = "(0.5+%s*(2*%s-1))" % (f(drift_y), p)
    crop = "crop=w=%d:h=%d:x='(in_w-%d)*%s':y='(in_h-%d)*%s'" % (w, h, w, px, h, py)
    return "%s,%s,setsar=1" % (scale, crop)


# --------------------------------------------------------------------------- WARP
def _persp(w, h, c):
    return ("perspective=" + ":".join("%s='%s'" % (k, c[k]) for k in
                                      ("x0", "y0", "x1", "y1", "x2", "y2", "x3", "y3"))
            + ":interpolation=cubic:eval=frame,scale=%d:%d,setsar=1" % (w, h))


def _warp(w, h, n, motion, intensity):
    p = _p_frame(n)
    e = _ss(p)
    bw, bh = 0.07 * w, 0.07 * h
    i = intensity
    L, R, T, B = f(bw), f(w - bw), f(bh), f(h - bh)
    if motion in ("tilt-back", "tilt-forward"):
        aw, ah = f(0.10 * w * i), f(0.06 * h * i)
        if motion == "tilt-back":
            c = dict(x0="%s+%s*%s" % (L, aw, e), y0="%s+%s*%s" % (T, ah, e),
                     x1="%s-%s*%s" % (R, aw, e), y1="%s+%s*%s" % (T, ah, e),
                     x2=L, y2=B, x3=R, y3=B)
        else:
            c = dict(x0=L, y0=T, x1=R, y1=T,
                     x2="%s+%s*%s" % (L, aw, e), y2="%s-%s*%s" % (B, ah, e),
                     x3="%s-%s*%s" % (R, aw, e), y3="%s-%s*%s" % (B, ah, e))
    elif motion == "orbit":
        s = "sin(%s*2*%s)" % (p, f(PI))
        av, ah = f(0.05 * h * i), f(0.05 * w * i)
        c = dict(x0="%s+%s*%s" % (L, ah, s), y0="%s-%s*%s" % (T, av, s),
                 x1="%s+%s*%s" % (R, ah, s), y1="%s+%s*%s" % (T, av, s),
                 x2="%s+%s*%s" % (L, ah, s), y2="%s+%s*%s" % (B, av, s),
                 x3="%s+%s*%s" % (R, ah, s), y3="%s-%s*%s" % (B, av, s))
    else:  # sway
        s1 = "sin(%s*2*%s)" % (p, f(PI))
        s2 = "sin(%s*2*%s+%s)" % (p, f(PI), f(PI / 2))
        ah, av = f(0.035 * w * i), f(0.035 * h * i)
        c = dict(x0="%s+%s*%s" % (L, ah, s1), y0="%s+%s*%s" % (T, av, s2),
                 x1="%s+%s*%s" % (R, ah, s1), y1="%s+%s*%s" % (T, av, s2),
                 x2="%s+%s*%s" % (L, ah, s1), y2="%s+%s*%s" % (B, av, s2),
                 x3="%s+%s*%s" % (R, ah, s1), y3="%s+%s*%s" % (B, av, s2))
    return _persp(w, h, c)


# --------------------------------------------------------------------------- CARD
def _even(x):
    return int(round(x / 2.0)) * 2


def _card_graph(sw, sh, dur, fps, n, motion, intensity, canvas, card_scale, bg, corner_radius, shadow):
    cw, ch = canvas
    i = intensity
    aspect = sw / float(sh)
    card_h = max(2, _even(card_scale * ch))
    card_w = max(2, _even(card_h * aspect))
    if card_w > 0.94 * cw:
        card_w = max(2, _even(0.94 * cw))
        card_h = max(2, _even(card_w / aspect))
    padx, pady = (cw - card_w) // 2, (ch - card_h) // 2
    cx, cy = cw / 2.0, ch / 2.0
    p = "(on/%d)" % max(n - 1, 1)
    ss = "(%s*%s*(3-2*%s))" % (p, p, p)
    ix = [0, cw, 0, cw]
    iy = [0, 0, ch, ch]
    dx = ["0"] * 4
    dy = ["0"] * 4
    sgn = [1, -1, -1, 1]

    if motion == "card-orbit":
        s = "sin(%s*%s)" % (p, f(2 * PI * 0.75))
        ah, av = f(0.07 * cw * i), f(0.085 * ch * i)
        dx = ["%s*%s" % (ah, s)] * 4
        dy = ["-%s*%s" % (av, s), "%s*%s" % (av, s), "%s*%s" % (av, s), "-%s*%s" % (av, s)]
    elif motion == "card-swoop":
        grow = "(%s*%s)" % (f(0.26 * i), ss)
        tlt = "(%s*(1-%s))" % (f(0.09 * ch * i), ss)
        arc = "(-%s*sin(%s*%s))" % (f(0.05 * ch * i), p, f(PI))
        for k in range(4):
            dx[k] = "(%s)*%s" % (f(ix[k] - cx), grow)
            dy[k] = "(%s)*%s+(%d)*%s+%s" % (f(iy[k] - cy), grow, sgn[k], tlt, arc)
    elif motion == "card-focus":
        grow = "(%s*%s)" % (f(0.17 * i), ss)
        tlt = f(0.018 * ch * i)
        for k in range(4):
            dx[k] = "(%s)*%s" % (f(ix[k] - cx), grow)
            dy[k] = "(%s)*%s+(%d)*%s" % (f(iy[k] - cy), grow, sgn[k], tlt)
    else:  # card-glide
        tx = "(%s)*(2*%s-1)" % (f(0.15 * cw * i), p)
        tlt = f(0.035 * ch * i)
        dx = [tx] * 4
        dy = [tlt, "-" + tlt, "-" + tlt, tlt]

    persp = ("perspective=" + ":".join("x%d='%d+(%s)':y%d='%d+(%s)'" % (k, ix[k], dx[k], k, iy[k], dy[k])
                                       for k in range(4))
             + ":sense=destination:eval=frame:interpolation=cubic")

    r = int(round(corner_radius * min(card_w, card_h)))
    if r > 0:
        a = ("255*clip((%d-sqrt(pow(max(abs(X-W/2)-(W/2-%d)\\,0)\\,2)+pow(max(abs(Y-H/2)-(H/2-%d)\\,0)\\,2)))+0.5\\,0\\,1)"
             % (r, r, r))
        rounded = "format=rgba,geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='%s'" % a
    else:
        rounded = "format=rgba"

    core = ("[0:v]scale=%d:%d,%s,pad=%d:%d:%d:%d:color=0x00000000,%s"
            % (card_w, card_h, rounded, cw, ch, padx, pady, persp))
    bgcolor = "0x00000000" if bg == "transparent" else bg
    base = "color=c=%s:s=%dx%d:r=%s:d=%s,format=rgba[bg]" % (bgcolor, cw, ch, f(fps), f(dur))
    if shadow:
        sx, sy = int(round(0.006 * cw)), int(round(0.018 * ch))
        sig = f(0.018 * ch)
        sh = "[cs]colorchannelmixer=rr=0:gg=0:bb=0:aa=0.5,gblur=sigma=%s[sh]" % sig
        comp = ("[bg][sh]overlay=%d:%d:format=auto[b2];[b2][cf]overlay=0:0:format=auto:shortest=1[out]" % (sx, sy))
        return "%s;%s,split[cs][cf];%s;%s" % (base, core, sh, comp)
    return "%s;%s[cf];[bg][cf]overlay=0:0:format=auto:shortest=1[out]" % (base, core)


# --------------------------------------------------------------------------- command line
ALL = list(ZOOM) + list(WARP) + list(CARD)


def parse_args(argv):
    ap = argparse.ArgumentParser(description="Add a camera move to a clip with ffmpeg.")
    ap.add_argument("input", nargs="?", help="input clip, inside the work folder")
    ap.add_argument("--motion", "-m", default="push-in", help="motion name (see --list), default push-in")
    ap.add_argument("--out", help="output file inside the work folder; .mp4 (or .mov, .mkv); "
                                  "transparent card output needs .mov or .webm")
    ap.add_argument("--amount", type=float, help="ZOOM: travel fraction 0..0.5 (0.18 = zoom to 118%%)")
    ap.add_argument("--drift-x", type=float, help="ZOOM: horizontal focal sweep -0.5..0.5")
    ap.add_argument("--drift-y", type=float, help="ZOOM: vertical focal sweep -0.5..0.5")
    ap.add_argument("--intensity", type=float, help="WARP and CARD: strength 0..1.5 (default 1.0)")
    ap.add_argument("--background", "--bg", help="CARD: canvas colour 0xRRGGBB, #RRGGBB or transparent (default 0x101018)")
    ap.add_argument("--canvas", help="CARD: output canvas WxH, 16 to 4096 each (default 1920x1080)")
    ap.add_argument("--card-scale", type=float, help="CARD: card height as a fraction of the canvas, 0.1..1 (default 0.76)")
    ap.add_argument("--corner-radius", type=float, help="CARD: rounded corners, 0..0.5 of the short side (default 0.05)")
    ap.add_argument("--shadow", dest="shadow", action="store_true", default=None, help="CARD: drop shadow (default on)")
    ap.add_argument("--no-shadow", dest="shadow", action="store_false", help="CARD: no drop shadow")
    ap.add_argument("--crf", type=int, default=18, help="x264 quality 0..51 (default 18)")
    ap.add_argument("--preset", default="medium", help="x264 speed preset (default medium)")
    ap.add_argument("--print-filter", action="store_true", help="print the ffmpeg filter and exit; renders nothing")
    ap.add_argument("--list", action="store_true", help="list the motions and exit")
    return ap.parse_args(argv)


def check(args):
    """Validate every option. Returns a dict of clean values."""
    if args.motion not in ALL:
        raise Usage("unknown motion %r; run --list" % args.motion)
    kind = "zoom" if args.motion in ZOOM else "warp" if args.motion in WARP else "card"
    given = {
        "zoom": [("--amount", args.amount), ("--drift-x", args.drift_x), ("--drift-y", args.drift_y)],
        "warp": [("--intensity", args.intensity)],
        "card": [("--intensity", args.intensity), ("--background", args.background), ("--canvas", args.canvas),
                 ("--card-scale", args.card_scale), ("--corner-radius", args.corner_radius),
                 ("--shadow/--no-shadow", args.shadow)],
    }
    every = [("--amount", args.amount), ("--drift-x", args.drift_x), ("--drift-y", args.drift_y),
             ("--intensity", args.intensity), ("--background", args.background), ("--canvas", args.canvas),
             ("--card-scale", args.card_scale), ("--corner-radius", args.corner_radius),
             ("--shadow/--no-shadow", args.shadow)]
    for name, value in every:
        if value is not None and (name, value) not in given[kind]:
            raise Usage("%s does not apply to the %s motion %s" % (name, kind, args.motion))
    if not 0 <= args.crf <= 51:
        raise Usage("--crf must be 0..51")
    if args.preset not in PRESETS:
        raise Usage("--preset must be one of: " + ", ".join(PRESETS))
    c = dict(
        kind=kind,
        amount=number("--amount", args.amount, 0.0, 0.5),
        drift_x=number("--drift-x", args.drift_x, -0.5, 0.5),
        drift_y=number("--drift-y", args.drift_y, -0.5, 0.5),
        intensity=number("--intensity", 1.0 if args.intensity is None else args.intensity, 0.0, 1.5),
        card_scale=number("--card-scale", 0.76 if args.card_scale is None else args.card_scale, 0.1, 1.0),
        corner_radius=number("--corner-radius", 0.05 if args.corner_radius is None else args.corner_radius, 0.0, 0.5),
        background=colour(args.background or "0x101018"),
        canvas=canvas_size(args.canvas or "1920x1080"),
        shadow=True if args.shadow is None else args.shadow,
    )
    return c


def main(argv):
    args = parse_args(argv)
    if args.list:
        print("ZOOM  (scale and crop): " + ", ".join(k for k in ZOOM if k != "focus") + "   [focus = push-in]")
        print("WARP  (3D-ish lean):    " + ", ".join(WARP))
        print("CARD  (card on a canvas): " + ", ".join(CARD))
        return 0
    if not args.input:
        raise Usage("INPUT is required (or use --list)")
    c = check(args)
    if not args.print_filter and not args.out:
        raise Usage("--out is required")

    src = inside_work(args.input, "INPUT")
    if not os.path.isfile(src):
        raise Usage("INPUT %r is not a file" % args.input)
    out = None
    if args.out:
        out = inside_work(args.out, "--out")
        ext = os.path.splitext(out)[1].lower()
        transparent = c["kind"] == "card" and c["background"] == "transparent"
        if os.path.isdir(out) or out == src:
            raise Usage("--out must be a new file name, not the input or a folder")
        if transparent and ext not in ALPHA_EXT:
            raise Usage("a transparent background needs --out ending in .mov or .webm")
        if not transparent and ext not in OPAQUE_EXT:
            raise Usage("--out must end in .mp4, .mov or .mkv")

    w, h, dur, fps, n = probe(src)
    if c["kind"] == "zoom":
        cfg = dict(ZOOM[args.motion])
        graph = _zoom(w, h, dur, c["amount"] if c["amount"] is not None else cfg["amount"], cfg.get("z_in", True),
                      c["drift_x"] if c["drift_x"] is not None else cfg.get("drift_x", 0.0),
                      c["drift_y"] if c["drift_y"] is not None else cfg.get("drift_y", 0.0), cfg.get("pan"),
                      cfg.get("linear", False))
        flag, label = "-vf", graph
    elif c["kind"] == "warp":
        graph = _warp(w, h, n, args.motion, c["intensity"])
        flag, label = "-vf", graph
    else:
        graph = _card_graph(w, h, dur, fps, n, args.motion, c["intensity"], c["canvas"], c["card_scale"],
                            c["background"], c["corner_radius"], c["shadow"])
        flag, label = "-filter_complex", graph
    if args.print_filter:
        print(graph)
        return 0

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise MissingTool("ffmpeg is not installed")
    cmd = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-protocol_whitelist", "file",
           "-i", src, flag, graph]
    if c["kind"] == "card":
        cmd += ["-map", "[out]", "-map", "0:a?"]
    ext = os.path.splitext(out)[1].lower()
    if c["kind"] == "card" and c["background"] == "transparent":
        if ext == ".mov":
            cmd += ["-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le", "-c:a", "copy"]
        else:
            cmd += ["-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "0", "-crf", "24", "-an"]
    else:
        cmd += ["-c:v", "libx264", "-crf", str(args.crf), "-preset", args.preset, "-pix_fmt", "yuv420p",
                "-c:a", "copy"]
        if ext in (".mp4", ".mov"):
            cmd += ["-movflags", "+faststart"]
    cmd.append(out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    sys.stderr.write("camera_motion: %s (%s) %dx%d %.2fs -> %s\n" % (args.motion, c["kind"], w, h, dur, args.out))
    r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if r.returncode != 0 or not os.path.isfile(out) or os.path.getsize(out) == 0:
        if os.path.isfile(out):
            os.remove(out)
        tail = " ".join(r.stderr.strip().splitlines()[-2:])[:300]
        raise Failed("ffmpeg could not render the clip: %s" % (tail or "no message"))
    print("OUTPUT_FILE: " + args.out)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Usage as e:
        sys.stderr.write("camera_motion.py: %s\n" % e)
        sys.exit(2)
    except MissingTool as e:
        sys.stderr.write("camera_motion.py: %s\n" % e)
        sys.exit(3)
    except Failed as e:
        sys.stderr.write("camera_motion.py: %s\n" % e)
        sys.exit(1)
