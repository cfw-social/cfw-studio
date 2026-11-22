#!/usr/bin/env python3
"""Picture checks for r-reels-faceless. Python standard library + ffmpeg only.

Each subcommand prints what it measured and exits 1 when the picture fails (2 = bad input).

  av-target FILE              The frame-aligned end time (a multiple of 0.1 s) both streams are padded to.
  av-span FILE                FAIL when the caption pass would outlast the picture. It sizes its HyperFrames
                              composition from the FORMAT duration (audio included), rounded to 0.01 s, and
                              renders ceil(dur x 30) frames. HyperFrames shows a blank frame once the reel's
                              own frames run out before the composition ends (videoFrameExtractor.ts, 0.7.5:
                              "Mid-clip source exhaustion ... stays blank"), so the reel ended on black.
  first-frames VIDEO BEATS    Frame 1 of every card must be whole: its foreground (headline + hero) must be
                              at least --min-ratio of the same card's settled foreground. Writes each first
                              frame to --out for the vision pass.
  band-scan VIDEO             Scans the bottom band (y >= --top, default 1832) of EVERY frame for frames whose
                              band lost its top layers while the picture just above did not change.
                              --skip-broll leaves b-roll beats out (footage may move in the band).
  color-drift SRC DST         FAIL when DST shifts near-neutral surfaces of SRC toward green/magenta
                              (the premium pass must not tint the picture).
  cover-pick VIDEO BEATS      Prints a cover time whose frame passes the gate's frame-0 contrast rule:
                              the planner's cover_at when it passes, else the best graphics-beat frame.
  luma-floor VIDEO            Mean luma (full range) at sampled points must be >= --floor.
  tail-luma VIDEO             Mean luma of the last frame (-sseof -0.1) must be > --min.
"""
import argparse
import json
import math
import os
import subprocess
import sys

FPS = 30.0
W, H = 1080, 1920


class Bad(Exception):
    pass


# ---------------------------------------------------------------- ffmpeg helpers

def probe(path):
    if not os.path.isfile(path):
        raise Bad("%s is missing" % path)
    p = subprocess.run(["ffprobe", "-v", "error", "-protocol_whitelist", "file", "-show_entries",
                        "format=duration:stream=codec_type,start_time,duration,nb_frames",
                        "-of", "json", path], capture_output=True, text=True)
    if p.returncode != 0:
        raise Bad("ffprobe could not read %s" % path)
    return json.loads(p.stdout)


def stream_end(info, kind):
    for s in info.get("streams", []):
        if s.get("codec_type") == kind:
            start = float(s.get("start_time") or 0.0)
            dur = s.get("duration")
            if dur in (None, "N/A"):
                return None
            return start + float(dur)
    return None


def raw_frame(path, t, crop=None, size=(270, 480), pix="gray", sseof=None):
    """One frame as raw bytes, area-downscaled (gray: 1 byte/px, rgb24: 3)."""
    vf = []
    if crop:
        vf.append("crop=%s" % crop)
    vf.append("scale=%d:%d:flags=area" % size)
    vf.append("format=%s" % pix)
    args = ["ffmpeg", "-v", "error", "-protocol_whitelist", "file"]
    args += ["-sseof", str(sseof)] if sseof is not None else ["-ss", "%.3f" % max(0.0, t)]
    args += ["-i", path, "-frames:v", "1", "-vf", ",".join(vf), "-f", "rawvideo", "-"]
    out = subprocess.run(args, capture_output=True).stdout
    need = size[0] * size[1] * (3 if pix == "rgb24" else 1)
    if len(out) < need:
        raise Bad("could not read a frame of %s at %s" % (path, "end" if sseof is not None else "%.2fs" % t))
    return out[:need]


def all_frames(path, crop, size):
    """Every frame of a crop, area-downscaled to gray, as a list of bytes objects."""
    p = subprocess.run(["ffmpeg", "-v", "error", "-protocol_whitelist", "file", "-i", path, "-an", "-vf",
                        "crop=%s,scale=%d:%d:flags=area,format=gray" % (crop, size[0], size[1]),
                        "-f", "rawvideo", "-"], capture_output=True)
    n = size[0] * size[1]
    data = p.stdout
    if p.returncode != 0 or len(data) < n:
        raise Bad("could not decode the frames of %s" % path)
    return [data[i:i + n] for i in range(0, len(data) - n + 1, n)]


def save_frame(path, t, dest):
    subprocess.run(["ffmpeg", "-v", "error", "-protocol_whitelist", "file", "-y", "-ss", "%.3f" % max(0.0, t), "-i", path,
                    "-frames:v", "1", dest], check=False)


def mean(b):
    return sum(b) / float(len(b)) if b else 0.0


def median(vals):
    s = sorted(vals)
    n = len(s)
    if n == 0:
        return 0.0
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def load_beats(path):
    try:
        with open(path, encoding="utf-8") as fh:
            bl = json.load(fh)
    except (OSError, ValueError) as e:
        raise Bad("beat list %s could not be read: %s" % (path, e))
    beats = bl.get("beats") if isinstance(bl, dict) else None
    if not isinstance(beats, list) or not beats:
        raise Bad("beat list %s has no beats" % path)
    return sorted(beats, key=lambda b: float(b["start"]))


def beat_type(b):
    sc = b.get("scene") if isinstance(b.get("scene"), dict) else {}
    return str(sc.get("type") or b.get("type") or "").strip().lower()


def is_graphics(b):
    return str(b.get("kind", "")).startswith("graphic")


# ---------------------------------------------------------------- av-target / av-span

def av_numbers(path, fps=FPS):
    info = probe(path)
    fmt = float(info.get("format", {}).get("duration") or 0.0)
    v_end = stream_end(info, "video")
    a_end = stream_end(info, "audio")
    if v_end is None:
        raise Bad("%s has no video stream" % path)
    p2_dur = round(fmt, 2)                                   # caption pass: round(format duration, 2)
    p2_frames = int(math.ceil(p2_dur * fps - 1e-6))          # HyperFrames: ceil(duration x fps)
    video_frames = int(round(v_end * fps))                   # frames the reel can supply from t = 0
    return {"format_dur": round(fmt, 4), "video_end": round(v_end, 4),
            "audio_end": None if a_end is None else round(a_end, 4),
            "p2_dur": p2_dur, "p2_frames": p2_frames, "video_frames": video_frames,
            "blank_tail_frames": max(0, p2_frames - video_frames)}


def cmd_av_target(a):
    n = av_numbers(a.file)
    end = max(n["video_end"], n["audio_end"] or 0.0)
    print("%.1f" % (math.ceil(end * 10 - 1e-6) / 10.0))
    return 0


def cmd_av_span(a):
    n = av_numbers(a.file)
    print(json.dumps(n))
    bad = []
    if n["blank_tail_frames"] > 0:
        bad.append("the premium pass would render %d frame(s) past the picture (black tail): format %.3fs, "
                   "picture ends %.3fs" % (n["blank_tail_frames"], n["format_dur"], n["video_end"]))
    if n["audio_end"] is not None and n["audio_end"] > n["video_end"] + 1e-3:
        bad.append("audio ends %.3fs after the picture" % (n["audio_end"] - n["video_end"]))
    for b in bad:
        print("FAIL av-span: " + b)
    if not bad:
        print("PASS av-span: the picture covers the whole file")
    return 1 if bad else 0


# ---------------------------------------------------------------- first-frames

CARD_CROP = "1080:1380:0:0"   # the card area: above the caption band (captions ride at y 1450-1710)
CARD_SIZE = (270, 345)
FG_DELTA = 96                 # a pixel is foreground when it differs this much from the card's background


def foreground(frame):
    bg = median(frame[::7])
    return sum(1 for p in frame if abs(p - bg) > FG_DELTA) / float(len(frame))


def cmd_first_frames(a):
    beats = load_beats(a.beats)
    exempt = {x.strip().lower() for x in (a.exempt or "").split(",") if x.strip()}
    cards = []
    for b in beats:
        if is_graphics(b):
            cards.append((b.get("slug") or "beat%s" % b.get("index"), beat_type(b),
                          float(b["start"]), float(b["end"])))
    if a.outro is not None:
        info = probe(a.video)
        end = stream_end(info, "video") or float(info["format"]["duration"])
        cards.append(("outro", "outro", float(a.outro) - a.offset, end - a.offset))
    if a.out:
        os.makedirs(a.out, exist_ok=True)
    fails, rows = [], []
    for slug, typ, s, e in cards:
        span = e - s
        t0 = a.offset + s + 0.5 / FPS                       # the card's first frame
        refs = [a.offset + s + span * f for f in (0.45, 0.65, 0.85)]
        c0 = foreground(raw_frame(a.video, t0, CARD_CROP, CARD_SIZE))
        cref = median([foreground(raw_frame(a.video, t, CARD_CROP, CARD_SIZE)) for t in refs])
        ratio = c0 / cref if cref > 0 else 0.0
        if a.out:
            save_frame(a.video, t0, os.path.join(a.out, "first-%s.png" % slug))
        status = "PASS"
        if cref < 0.003:
            status = "FAIL"
            why = "card has no foreground even when settled (%.2f%% of pixels)" % (cref * 100)
        elif ratio < a.min_ratio:
            status = "EXEMPT" if typ in exempt else "FAIL"
            why = "first frame shows %.0f%% of the settled card" % (ratio * 100)
        else:
            why = "first frame shows %.0f%% of the settled card" % (min(ratio, 9.99) * 100)
        rows.append("%-6s %-24s type=%-10s t=%.2fs  fg0=%.2f%% fgref=%.2f%%  %s"
                    % (status, slug, typ or "-", t0, c0 * 100, cref * 100, why))
        if status == "FAIL":
            fails.append(slug)
    for r in rows:
        print(r)
    if fails:
        print("FAIL first-frames: not whole on frame 1: %s (entrances must not fade the headline or hero in "
              "from opacity 0; re-author those cards)" % ", ".join(fails))
        return 1
    print("PASS first-frames: %d card(s) whole on frame 1" % len(cards))
    return 0


# ---------------------------------------------------------------- band-scan

STRIP = (120, 8)      # downscaled size of the bottom band (1080 x 88 -> 120 x 8)
ABOVE = (120, 8)      # the same size for the 88 px just above it
DIFF = 24             # a downscaled pixel "changed" when it moved this much
MIN_FRAC = 0.03       # a band "lost layers" when this share of its pixels changed ...
ABOVE_RATIO = 0.34    # ... and the region above changed less than a third as much


def segments_for(n_frames, beats, offset):
    """Frame-index segments (one per beat; anything outside the beats is its own segment)."""
    cuts = {0, n_frames}
    for b in beats or []:
        for key in ("start", "end"):
            k = int(round((offset + float(b[key])) * FPS))
            if 0 < k < n_frames:
                cuts.add(k)
    k0 = int(round(offset * FPS))
    if 0 < k0 < n_frames:
        cuts.add(k0)
    c = sorted(cuts)
    return list(zip(c, c[1:]))


def changed_frac(a, ref):
    return sum(1 for x, r in zip(a, ref) if abs(x - r) > DIFF) / float(len(a))


def per_pixel_median(frames):
    return bytes(int(median([f[i] for f in frames])) for i in range(len(frames[0])))


def cmd_band_scan(a):
    band_h = H - a.top
    strip = all_frames(a.video, "%d:%d:0:%d" % (W, band_h, a.top), STRIP)
    above = all_frames(a.video, "%d:%d:0:%d" % (W, band_h, a.top - band_h), ABOVE)
    n = min(len(strip), len(above))
    beats = load_beats(a.beats) if a.beats else None
    skip = []
    if a.skip_broll and beats:
        skip = [(int(round((a.offset + float(b["start"])) * FPS)), int(round((a.offset + float(b["end"])) * FPS)))
                for b in beats if not is_graphics(b)]
    bad = set()
    for s0, s1 in segments_for(n, beats, a.offset):
        if s1 - s0 < 3:
            continue
        if any(k0 <= s0 and s1 <= k1 for k0, k1 in skip):
            continue
        seg_s, seg_a = strip[s0:s1], above[s0:s1]
        # reference 1: the segment's own median band (catches runs up to half the segment)
        ref_s, ref_a = per_pixel_median(seg_s), per_pixel_median(seg_a)
        for i in range(s1 - s0):
            fs = changed_frac(seg_s[i], ref_s)
            if fs >= MIN_FRAC and changed_frac(seg_a[i], ref_a) < fs * ABOVE_RATIO:
                bad.add(s0 + i)
        # reference 2: a rolling median of +-7 frames (catches scattered frames in a moving band)
        for i in range(s1 - s0):
            lo, hi = max(0, i - 7), min(s1 - s0, i + 8)
            if hi - lo < 5:
                continue
            fs = changed_frac(seg_s[i], per_pixel_median(seg_s[lo:hi]))
            if fs >= MIN_FRAC and changed_frac(seg_a[i], per_pixel_median(seg_a[lo:hi])) < fs * ABOVE_RATIO:
                bad.add(s0 + i)
    bad = sorted(bad)
    if bad:
        shown = ", ".join("%d (%.2fs)" % (f, f / FPS) for f in bad[:30])
        print("FAIL band-scan: %d of %d frames lost the bottom %d px band: %s%s"
              % (len(bad), n, band_h, shown, " ..." if len(bad) > 30 else ""))
        return 1
    print("PASS band-scan: all %d frames keep the bottom %d px band" % (n, band_h))
    return 0


# ---------------------------------------------------------------- color-drift

def cmd_color_drift(a):
    info = probe(a.src)
    dur = float(info["format"]["duration"])
    times = [float(x) for x in a.times.split(",")] if a.times else [dur * f for f in (0.15, 0.35, 0.55, 0.75, 0.9)]
    crop = "1080:1380:0:0"
    shifts = []
    for t in times:
        s = raw_frame(a.src, t, crop, (180, 230), "rgb24")
        d = raw_frame(a.dst, t, crop, (180, 230), "rgb24")
        acc, n = 0.0, 0
        for i in range(0, len(s), 3):
            r, g, b = s[i], s[i + 1], s[i + 2]
            if max(r, g, b) - min(r, g, b) > 14 or max(r, g, b) < 40:
                continue                                    # only near-neutral, not near-black surfaces
            r2, g2, b2 = d[i], d[i + 1], d[i + 2]
            acc += (g2 - (r2 + b2) / 2.0) - (g - (r + b) / 2.0)
            n += 1
        if n >= 50:
            shifts.append((t, acc / n, n))
    if not shifts:
        print("SKIP color-drift: no near-neutral surface found to compare")
        return 0
    for t, v, n in shifts:
        print("t=%.2fs green-shift=%+.2f levels over %d near-neutral px" % (t, v, n))
    worst = max(abs(v) for _, v, _ in shifts)
    if worst > a.max:
        print("FAIL color-drift: neutral surfaces moved %.2f levels toward %s (max %.1f)"
              % (worst, "green" if max(shifts, key=lambda x: abs(x[1]))[1] > 0 else "magenta", a.max))
        return 1
    print("PASS color-drift: worst %.2f levels (max %.1f)" % (worst, a.max))
    return 0


# ---------------------------------------------------------------- cover-pick / luma

def contrast_stats(path, t):
    """The cover contrast rule for frame 0 (acceptance.json cover_has_contrast), full range."""
    fr = raw_frame(path, t, None, (270, 480), "gray")
    m = mean(fr)
    rng = max(fr) - min(fr)
    bright = sum(1 for p in fr if p >= 128) / float(len(fr))
    ok = m > 48 or (m >= 8 and rng >= 128 and bright >= 0.02)
    return ok, m, rng, bright


def cmd_cover_pick(a):
    beats = load_beats(a.beats)
    cands = [("planner", a.cover_at)]
    for b in beats:
        if is_graphics(b) and beat_type(b) not in ("hook", "typing-ui") and float(b["start"]) >= 1.0:
            s, e = float(b["start"]), float(b["end"])
            for f in (0.5, 0.75):
                cands.append((b.get("slug") or "beat%s" % b.get("index"), s + (e - s) * f))
    best = None
    for name, t in cands:
        ok, m, rng, bright = contrast_stats(a.video, a.offset + t)
        sys.stderr.write("cover candidate %-24s t=%.2fs mean=%.0f range=%d bright=%.1f%% %s\n"
                         % (name, t, m, rng, bright * 100, "ok" if ok else "fails"))
        if ok and name == "planner":
            print("%.3f" % t)
            return 0
        if ok and (best is None or bright > best[1]):
            best = (t, bright, name)
    if best is None:
        sys.stderr.write("FAIL cover-pick: no card frame passes the cover contrast rule "
                         "(mean > 48, or mean >= 8 + range >= 128 + >= 2%% bright pixels)\n")
        return 1
    sys.stderr.write("cover-pick: planner's cover_at fails the contrast rule; using %s at %.2fs\n" % (best[2], best[0]))
    print("%.3f" % best[0])
    return 0


def full_range(yavg):
    return max(0.0, (yavg - 16.0) * 255.0 / 219.0)


def yavg_at(path, t=None, sseof=None):
    args = ["ffmpeg", "-hide_banner", "-protocol_whitelist", "file"]
    args += ["-sseof", str(sseof)] if sseof is not None else ["-ss", "%.3f" % t]
    args += ["-i", path, "-frames:v", "1", "-vf", "signalstats,metadata=print:key=lavfi.signalstats.YAVG",
             "-f", "null", "-"]
    err = subprocess.run(args, capture_output=True, text=True).stderr
    for line in err.splitlines():
        if "lavfi.signalstats.YAVG=" in line:
            return full_range(float(line.split("YAVG=")[1].strip()))
    raise Bad("could not measure luma of %s" % path)


def cmd_luma_floor(a):
    dur = float(probe(a.video)["format"]["duration"])
    bad = []
    for f in [float(x) for x in a.samples.split(",")]:
        y = yavg_at(a.video, t=dur * f)
        print("t=%.2fs (%.0f%%) mean luma %.1f" % (dur * f, f * 100, y))
        if y < a.floor:
            bad.append("%.0f%%" % (f * 100))
    if bad:
        print("FAIL luma-floor: below %.0f at %s" % (a.floor, ", ".join(bad)))
        return 1
    print("PASS luma-floor: every sample >= %.0f" % a.floor)
    return 0


def cmd_tail_luma(a):
    y = yavg_at(a.video, sseof=-0.1)
    if y <= a.min:
        print("FAIL tail-luma: last frame mean luma %.1f <= %.0f" % (y, a.min))
        return 1
    print("PASS tail-luma: last frame mean luma %.1f > %.0f" % (y, a.min))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("av-target"); s.add_argument("file"); s.set_defaults(fn=cmd_av_target)
    s = sub.add_parser("av-span"); s.add_argument("file"); s.set_defaults(fn=cmd_av_span)
    s = sub.add_parser("first-frames"); s.add_argument("video"); s.add_argument("beats")
    s.add_argument("--offset", type=float, default=0.0, help="where beat 0 starts in VIDEO (0.4 after the cover)")
    s.add_argument("--outro", type=float, default=None, help="outro card start time in VIDEO (checked too)")
    s.add_argument("--out", default="", help="write first-<slug>.png here for the vision pass")
    s.add_argument("--min-ratio", type=float, default=0.5)
    s.add_argument("--exempt", default="hook,typing",
                   help="card types reported but not failed (the b-typing-ui hook and typing cards animate their text in by design)")
    s.set_defaults(fn=cmd_first_frames)
    s = sub.add_parser("band-scan"); s.add_argument("video")
    s.add_argument("--beats", default="", help="beat list: scan each beat as its own segment")
    s.add_argument("--offset", type=float, default=0.0)
    s.add_argument("--top", type=int, default=1832, help="top edge of the scanned bottom band (px)")
    s.add_argument("--skip-broll", action="store_true",
                   help="do not scan b-roll beats (use on the body video, where footage may move in the band)")
    s.set_defaults(fn=cmd_band_scan)
    s = sub.add_parser("color-drift"); s.add_argument("src"); s.add_argument("dst")
    s.add_argument("--times", default="")
    s.add_argument("--max", type=float, default=2.5)
    s.set_defaults(fn=cmd_color_drift)
    s = sub.add_parser("cover-pick"); s.add_argument("video"); s.add_argument("beats")
    s.add_argument("--cover-at", type=float, required=True)
    s.add_argument("--offset", type=float, default=0.0)
    s.set_defaults(fn=cmd_cover_pick)
    s = sub.add_parser("luma-floor"); s.add_argument("video")
    s.add_argument("--floor", type=float, default=16.0)
    s.add_argument("--samples", default="0.1,0.3,0.5,0.7,0.9")
    s.set_defaults(fn=cmd_luma_floor)
    s = sub.add_parser("tail-luma"); s.add_argument("video")
    s.add_argument("--min", type=float, default=30.0)
    s.set_defaults(fn=cmd_tail_luma)
    a = p.parse_args(argv)
    try:
        return a.fn(a)
    except Bad as e:
        sys.stderr.write("frame_qa.py %s: FAILED - %s\n" % (a.cmd, e))
        return 2


if __name__ == "__main__":
    sys.exit(main())
