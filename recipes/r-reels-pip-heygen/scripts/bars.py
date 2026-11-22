#!/usr/bin/env python3
"""Find a matched pair of flat bars baked into a video and print an ffmpeg crop. Needs ffmpeg and ffprobe.

  python3 bars.py VIDEO        prints "crop=W:H:X:Y," (with its comma) or an empty line, then exits 0
  python3 bars.py --help       prints this text

It samples three frames. It crops only top+bottom (or left+right) bars of about the same size and the
same flat colour, and only when what is left is within 5% of 16:9 or 9:16. Anything else (a speaker on a
plain backdrop, a one-sided margin): no crop, so a head is never cut. Frames are read as ffmpeg shows
them, rotation applied. A file that cannot be read as a video stops it with one line on stderr (exit 1);
wrong arguments exit 2.
"""
import subprocess, sys
if sys.argv[1:] in (["-h"], ["--help"]):
    print(__doc__.strip()); sys.exit(0)
if len(sys.argv) != 2:
    sys.stderr.write("usage: bars.py VIDEO   (bars.py --help for more)\n"); sys.exit(2)
def _fail(kind, err, tb):
    sys.stderr.write("bars.py: FAILED - %s cannot be read as a video (%s)\n" % (sys.argv[1], kind.__name__)); sys.exit(1)
sys.excepthook = _fail
SRC, TOL, MIN_BAR, ASPECT_TOL, SEAM, SEAM_TOL = sys.argv[1], 12, 8, 0.05, 6, 32
def grab(t):
    # One frame as PPM. Its header gives the size ffmpeg shows after autorotation, so a
    # rotated phone clip is measured on the same axes the later -vf crop sees.
    out = subprocess.run(["ffmpeg", "-v", "error", "-protocol_whitelist", "file", "-ss", "%.2f" % t, "-i", SRC, "-frames:v", "1",
        "-f", "image2pipe", "-c:v", "ppm", "-"], capture_output=True, check=True).stdout
    if not out.startswith(b"P6"):
        return None
    head, pos = [], 2
    while len(head) < 3:
        while out[pos:pos + 1].isspace():
            pos += 1
        end = pos
        while out[end:end + 1] and not out[end:end + 1].isspace():
            end += 1
        head.append(int(out[pos:end])); pos = end
    w, h, data = head[0], head[1], out[pos + 1:]
    return (w, h, data) if len(data) >= w * h * 3 else None
def duration():
    r = subprocess.run(["ffprobe", "-v", "error", "-protocol_whitelist", "file", "-show_entries", "format=duration", "-of", "csv=p=0", SRC],
        capture_output=True, text=True, check=True).stdout.strip()
    try:
        return float(r)
    except ValueError:
        return 1.0
def close(a, b, tol=TOL):
    return max(abs(a[k] - b[k]) for k in range(3)) <= tol
def run(fr, w, lines, pts, tol=TOL):
    # how many lines from this edge inwards are one flat colour -> (count, colour)
    ref, n = None, 0
    for ln in lines:
        row = [fr[(y * w + x) * 3:(y * w + x) * 3 + 3] for x, y in pts(ln)]
        ref = ref or sorted(row)[len(row) // 2]    # median pixel: robust to a noisy first pixel
        if not all(close(c, ref, tol) for c in row):
            break
        n += 1
    return n, ref
def bar(fr, w, lines, pts):
    # A bar run also swallows ONE short flat seam (SEAM rows or fewer, another flat
    # colour, within SEAM_TOL because video compression speckles it) right next to its inner edge, so no flat seam row stays at the picture's edge.
    lines = list(lines)
    n, ref = run(fr, w, lines, pts)
    if n >= MIN_BAR:
        m, _ = run(fr, w, lines[n:], pts, SEAM_TOL)   # a compressed seam is a bit noisy
        if 1 <= m <= SEAM and n + m < len(lines):
            n += m
    return n, ref
D = duration()
frames = [f for f in (grab(D * p) for p in (0.2, 0.5, 0.8)) if f]
if not frames or len({(f[0], f[1]) for f in frames}) != 1:
    print(""); sys.exit(0)
W, H = frames[0][0], frames[0][1]
sides = [(bar(fr, W, range(H // 2), lambda y: [(x, y) for x in range(0, W, 4)]),
          bar(fr, W, range(H - 1, H // 2, -1), lambda y: [(x, y) for x in range(0, W, 4)]),
          bar(fr, W, range(W // 2), lambda x: [(x, y) for y in range(0, H, 4)]),
          bar(fr, W, range(W - 1, W // 2, -1), lambda x: [(x, y) for y in range(0, H, 4)]))
         for _, _, fr in frames]
def edge(i):
    # bar size = the smallest run over the sampled frames; its colour must hold in every frame
    n, cols = min(s[i][0] for s in sides), [s[i][1] for s in sides]
    if n < MIN_BAR or not all(close(c, cols[0]) for c in cols):
        return 0, None
    return n, cols[0]
(top, ct), (bot, cb), (left, cl), (right, cr) = (edge(i) for i in range(4))
def pair(a, ca, b, cb_, side):
    # a matched pair: both bars present, the same flat colour, sizes within 2% of the side
    return bool(a and b and close(ca, cb_) and abs(a - b) <= max(4, side * 0.02))
def aspect_ok(w, h):
    return any(abs((w / h) / r - 1) <= ASPECT_TOL for r in (16 / 9, 9 / 16))
tb, lr = pair(top, ct, bot, cb, H), pair(left, cl, right, cr, W)
cands = ([(top, bot, left, right)] if tb and lr else []) + ([(top, bot, 0, 0)] if tb else []) \
    + ([(0, 0, left, right)] if lr else [])
for t, b, l, r in cands:
    t, l = t + t % 2, l + l % 2          # even x/y (yuv420p); never keeps a bar row
    cw, ch = W - l - r, H - t - b
    cw, ch = cw - cw % 2, ch - ch % 2    # even w/h
    if cw >= W // 4 and ch >= H // 4 and aspect_ok(cw, ch):
        print("crop=%d:%d:%d:%d," % (cw, ch, l, t)); sys.exit(0)
print("")
