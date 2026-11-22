#!/usr/bin/env python3
"""b-qa-gate: mechanical quality checks for a reel or an image.

    check.py --kind reel|image --spec acceptance.json --input FILE --out scorecard.json [--step NAME]

Reads a recipe's acceptance.json, runs the check kinds this block owns, and
writes a scorecard. A check kind it does not know is a FAIL. Nothing is skipped.
Checks that need a person or a bot to look are copied into the scorecard as
"LOOK" rows with their question text.

Second mode: check.py --finalize scorecard.json --answers answers.json --out final.json
records yes/no answers for the LOOK rows. Exit 0 only if every row ends PASS.

Exit codes: 0 all mechanical checks passed, no looks owed
            1 at least one check failed (including an unknown kind or a missing tool)
            2 bad usage or bad input, nothing was checked
            4 all mechanical checks passed, but looks are still owed

Standard library only. Needs ffmpeg and ffprobe on PATH. No network.
"""
import argparse
import collections
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys

EXIT_OK, EXIT_FAIL, EXIT_USAGE, EXIT_LOOKS = 0, 1, 2, 4
TIMEOUT_S = 300
MAX_PIXELS = 100_000_000
CROP_RE = re.compile(r"^(\d{1,5}):(\d{1,5}):(\d{1,5}):(\d{1,5})$")
FORMATS = {
    "reel": (1080, 1920), "portrait": (1080, 1920),
    "vsl": (1920, 1080), "landscape": (1920, 1080),
    "square": (1080, 1080),
}
DEFAULT_SAMPLES = [0.05, 0.2, 0.4, 0.6, 0.8, 0.95]


class CheckFail(Exception):
    """A check failed. The message is the detail line."""


class ToolMissing(CheckFail):
    pass


# ---------------------------------------------------------------- numbers

def is_num(x):
    """A real, finite, sane number. Big integers are range-checked before any float work."""
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return False
    if isinstance(x, int):
        return -1e15 <= x <= 1e15
    return math.isfinite(x) and abs(x) <= 1e15


def num(spec, key, default=None, lo=None, hi=None, integer=False):
    """Read a number from a spec dict, validated before it reaches any argument."""
    if key not in spec:
        if default is None:
            raise CheckFail(f"missing number '{key}'")
        return default
    v = spec[key]
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise CheckFail(f"'{key}' must be a number")
    if not is_num(v):
        raise CheckFail(f"'{key}' must be a finite number of sane size")
    if integer and (v != int(v)):
        raise CheckFail(f"'{key}' must be a whole number")
    if lo is not None and v < lo or hi is not None and v > hi:
        raise CheckFail(f"'{key}' must be between {lo} and {hi}")
    return int(v) if integer else float(v)


def samples_of(spec):
    raw = spec.get("samples", DEFAULT_SAMPLES)
    if not isinstance(raw, list) or not raw or len(raw) > 50:
        raise CheckFail("'samples' must be a list of 1 to 50 numbers")
    out = []
    for p in raw:
        if not is_num(p) or not 0 <= p <= 1:
            raise CheckFail("every sample must be a number from 0 to 1")
        out.append(float(p))
    return out


def crop_of(spec):
    """Return a crop filter string, or None for the whole frame."""
    crop = spec.get("crop")
    if crop is None:
        return None
    m = CROP_RE.match(crop) if isinstance(crop, str) else None
    if not m or int(m.group(1)) == 0 or int(m.group(2)) == 0:
        raise CheckFail("'crop' must be W:H:X:Y with whole numbers, W and H above 0")
    return "crop=" + crop


# ---------------------------------------------------------------- tools

class Tools:
    def __init__(self):
        self.ffmpeg = shutil.which("ffmpeg")
        self.ffprobe = shutil.which("ffprobe")

    def missing(self):
        return [n for n, p in (("ffmpeg", self.ffmpeg), ("ffprobe", self.ffprobe)) if not p]

    def run(self, tool, args, binary=False):
        path = getattr(self, tool)
        if not path:
            raise ToolMissing(f"{tool} not found on PATH")
        try:
            safe = []
            for x in args:                      # only the file protocol may open an input
                if x == "-i":
                    safe += ["-protocol_whitelist", "file"]
                safe.append(x)
            p = subprocess.run([path, *safe], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               timeout=TIMEOUT_S, shell=False, stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            raise CheckFail(f"{tool} timed out")
        return p.returncode, p.stdout, p.stderr.decode("utf-8", "replace")

    def version(self, tool):
        try:
            _, out, _ = self.run(tool, ["-version"])
        except CheckFail:
            return None
        first = out.decode("utf-8", "replace").splitlines()
        return first[0].strip() if first else None

    def probe(self, path):
        rc, out, err = self.run("ffprobe", [
            "-v", "error", "-show_entries",
            "stream=index,codec_type,codec_name,width,height,r_frame_rate:format=duration",
            "-of", "json", "-i", path])
        if rc != 0:
            raise CheckFail("ffprobe could not read the file")
        try:
            return json.loads(out)
        except ValueError:
            raise CheckFail("ffprobe gave unreadable output")

    def luma(self, path, crop, t):
        """Full-range 0-255 luma stats of one frame: (mean, min, max, bright_fraction)."""
        vf = ((crop + ",") if crop else "") + "format=gray"
        args = ["-v", "error"]
        if t:
            args += ["-ss", f"{t:.3f}"]
        args += ["-i", path, "-vf", vf, "-frames:v", "1", "-f", "rawvideo", "-"]
        rc, out, err = self.run("ffmpeg", args)
        if rc != 0 or not out:
            raise CheckFail(f"no frame at t={t:.2f}" + (f" ({err.strip().splitlines()[-1]})" if err.strip() else ""))
        if len(out) > MAX_PIXELS:
            raise CheckFail("frame is too large to measure")
        hist = collections.Counter(out)
        n = len(out)
        mean = sum(k * v for k, v in hist.items()) / n
        bright = sum(v for k, v in hist.items() if k >= 128) / n
        return mean, min(hist), max(hist), bright

    def loudness(self, path):
        rc, _, err = self.run("ffmpeg", ["-hide_banner", "-nostats", "-i", path,
                                         "-af", "ebur128", "-f", "null", "-"])
        m = re.search(r"Integrated loudness:\s*\n\s*I:\s+(-?\d+(?:\.\d+)?|-inf)\s+LUFS", err)
        if rc != 0 or not m or m.group(1) == "-inf":
            raise CheckFail("no loudness reading (no audio, or silent)")
        return float(m.group(1))

    def mean_volume(self, path):
        rc, _, err = self.run("ffmpeg", ["-hide_banner", "-nostats", "-i", path,
                                         "-af", "volumedetect", "-f", "null", "-"])
        m = re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?|-inf)\s*dB", err)
        if rc != 0 or not m or m.group(1) == "-inf":
            raise CheckFail("no mean volume reading (no audio, or silent)")
        return float(m.group(1))

    def frame_to(self, path, t, dest):
        args = ["-v", "error", "-y"]
        if t:
            args += ["-ss", f"{t:.3f}"]
        rc, _, _ = self.run("ffmpeg", args + ["-i", path, "-frames:v", "1", dest])
        return rc == 0 and os.path.isfile(dest)


def duration_of(tools, path):
    d = tools.probe(path).get("format", {}).get("duration")
    try:
        v = float(d)
    except (TypeError, ValueError):
        raise CheckFail("no duration")
    if not math.isfinite(v) or v <= 0:
        raise CheckFail("no duration")
    return v


def video_stream(tools, path):
    for s in tools.probe(path).get("streams", []):
        if s.get("codec_type") == "video":
            return s
    raise CheckFail("no decodable video stream")


def fps_of(stream):
    try:
        a, _, b = str(stream.get("r_frame_rate", "")).partition("/")
        return float(a) / float(b or 1)
    except (ValueError, ZeroDivisionError):
        raise CheckFail("no frame rate")


def has_audio(tools, path):
    return any(s.get("codec_type") == "audio" for s in tools.probe(path).get("streams", []))


# ---------------------------------------------------------------- checks
# Each check: fn(ctx, spec) -> (value, detail) or raises CheckFail.
# Return value is a short measured value; a failed check raises CheckFail(detail).

def c_dims(ctx, c):
    w, h = num(c, "w", integer=True, lo=1, hi=100000), num(c, "h", integer=True, lo=1, hi=100000)
    s = video_stream(ctx.tools, ctx.input)
    got = (s.get("width"), s.get("height"))
    if got != (w, h):
        raise CheckFail(f"size {got[0]}x{got[1]}, expected {w}x{h}")
    return f"{w}x{h}"


def c_aspect_ratio(ctx, c):
    w, h = num(c, "w", integer=True, lo=1, hi=100000), num(c, "h", integer=True, lo=1, hi=100000)
    tol = num(c, "tol", 0.01, lo=0, hi=0.5)
    s = video_stream(ctx.tools, ctx.input)
    gw, gh = s.get("width"), s.get("height")
    if not gw or not gh:
        raise CheckFail("no size")
    ratio, want = gw / gh, w / h
    if abs(ratio / want - 1) > tol:
        raise CheckFail(f"ratio {ratio:.4f} for {gw}x{gh}, expected {want:.4f} within {tol}")
    if "min_w" in c and gw < num(c, "min_w", integer=True, lo=1, hi=100000):
        raise CheckFail(f"width {gw} is under the minimum {c['min_w']}")
    return f"{gw}x{gh}"


def c_fps(ctx, c):
    expect = num(c, "expect", lo=1, hi=240)
    tol = num(c, "tol", 1.5, lo=0, hi=60)
    got = fps_of(video_stream(ctx.tools, ctx.input))
    if abs(got - expect) > tol:
        raise CheckFail(f"{got:.2f} fps, expected {expect:g} within {tol:g}")
    return f"{got:.2f} fps"


def c_duration_window(ctx, c):
    lo, hi = num(c, "min_s", 0, lo=0, hi=1e6), num(c, "max_s", 1e6, lo=0, hi=1e6)
    d = duration_of(ctx.tools, ctx.input)
    if not lo <= d <= hi:
        raise CheckFail(f"{d:.2f}s, expected {lo:g} to {hi:g}s")
    return f"{d:.2f}s"


def c_spoken_duration_window(ctx, c):
    lo, hi = num(c, "min_s", lo=0, hi=1e6), num(c, "max_s", lo=0, hi=1e6)
    wpm = num(c, "wpm", 150, lo=50, hi=400)
    try:
        with open(ctx.input, "rb") as fh:
            raw = fh.read(2_000_001)
        if len(raw) > 2_000_000:
            raise CheckFail("script is larger than 2 MB")
        text = raw.decode("utf-8")
    except (OSError, UnicodeDecodeError):
        raise CheckFail("input is not a readable UTF-8 text file")
    words = sum(1 for t in text.split() if any(ch.isalnum() for ch in t))
    secs = words / wpm * 60
    if not lo <= secs <= hi:
        raise CheckFail(f"{words} words at {wpm:g} wpm is {secs:.1f}s, expected {lo:g} to {hi:g}s")
    return f"{words} words, {secs:.1f}s"


def c_json_array_nonempty(ctx, c):
    n = num(c, "min_items", 1, lo=0, hi=1_000_000, integer=True)
    data = load_json_in_work(ctx, ctx.input)
    if not isinstance(data, list):
        raise CheckFail("the JSON is not an array")
    if len(data) < max(n, 1):
        raise CheckFail(f"{len(data)} items, needs at least {max(n, 1)}")
    keys = c.get("item_keys", [])
    if not isinstance(keys, list) or any(not isinstance(k, str) for k in keys):
        raise CheckFail("'item_keys' must be a list of names")
    for i, it in enumerate(data):
        if keys and (not isinstance(it, dict) or any(not isinstance(it.get(k), str) or not it[k].strip() for k in keys)):
            raise CheckFail(f"item {i} needs non-empty text for {keys}")
    return f"{len(data)} items"


def c_json_words_nonempty(ctx, c):
    n = num(c, "min_items", 1, lo=1, hi=10_000_000, integer=True)
    path = c.get("path", "words")
    if not isinstance(path, str) or not WF_KEY.match(path):
        raise CheckFail("'path' must be a top-level name")
    data = load_json_in_work(ctx, ctx.input)
    # Two shapes are accepted: a bare array of words (what b-audio writes),
    # or an object that holds the list under 'path'.
    words = data if isinstance(data, list) else (data.get(path) if isinstance(data, dict) else None)
    if not isinstance(words, list) or len(words) < n:
        raise CheckFail(f"the JSON is not a list of at least {n} words (a bare array, or an object with '{path}')")
    prev = 0.0
    for i, w in enumerate(words):
        s, e = (w.get("start"), w.get("end")) if isinstance(w, dict) else (None, None)
        if not (is_num(s) and is_num(e)):
            raise CheckFail(f"word {i} needs numeric start and end")
        if not isinstance(w.get("text"), str) or not w["text"].strip():
            raise CheckFail(f"word {i} needs text")
        if s < prev or e < s:
            raise CheckFail(f"word {i} starts before the one before it, or ends before it starts")
        prev = s
    last = float(words[-1]["end"])
    if "expected_duration_s" in c:
        exp, tol = num(c, "expected_duration_s", lo=0, hi=1e6), num(c, "tail_tolerance_s", 0.5, lo=0, hi=1e6)
        if exp - last > tol or last - exp > 0.5:
            raise CheckFail(f"last word ends at {last:.2f}s, expected near {exp:g}s (tail up to {tol:g}s)")
    elif "tail_tolerance_s" in c:
        raise CheckFail("'tail_tolerance_s' needs 'expected_duration_s' written into the spec")
    return f"{len(words)} words, last ends {last:.2f}s"


def c_audio_present(ctx, c):
    if not has_audio(ctx.tools, ctx.input):
        raise CheckFail("no audio track")
    return "audio present"


def c_loudness(ctx, c):
    target, tol = num(c, "target", -14, lo=-70, hi=0), num(c, "tol", 1.5, lo=0, hi=30)
    i = ctx.tools.loudness(ctx.input)
    if abs(i - target) > tol:
        raise CheckFail(f"{i} LUFS, expected {target:g} within {tol:g}")
    return f"{i} LUFS"


def c_mean_volume(ctx, c):
    lo, hi = num(c, "min_db", -90, lo=-200, hi=10), num(c, "max_db", 0, lo=-200, hi=10)
    mv = ctx.tools.mean_volume(ctx.input)
    if not lo <= mv <= hi:
        raise CheckFail(f"{mv} dB, expected {lo:g} to {hi:g} dB")
    return f"{mv} dB"


def times_for(ctx, samples):
    """Seconds to sample. A still image has one moment, time 0."""
    if ctx.kind == "image":
        return [0.0]
    d = duration_of(ctx.tools, ctx.input)
    return [0.0 if p == 0 else max(0.0, min(round(d * p, 3), d - 0.05)) for p in samples]


def c_luma_floor(ctx, c):
    floor = num(c, "floor", 16, lo=0, hi=255)
    crop = crop_of(c)
    low = []
    worst = 255.0
    times = times_for(ctx, samples_of(c))
    for t in times:
        mean = ctx.tools.luma(ctx.input, crop, t)[0]
        worst = min(worst, mean)
        if mean < floor:
            low.append(t)
    if low:
        raise CheckFail(f"{len(low)} of {len(times)} samples under luma {floor:g} (lowest {worst:.1f}), at t={low}")
    return f"lowest mean luma {worst:.1f}"


def c_luma_floor_windows(ctx, c):
    if ctx.kind == "image":
        raise CheckFail("windows need a video")
    if "windows" not in c and "windows_from" not in c:
        raise CheckFail("needs 'windows' or 'windows_from' in the spec")
    wins = []
    if "windows" in c:
        wins = c["windows"]
        if not isinstance(wins, list) or len(wins) > 200:
            raise CheckFail("'windows' must be a list of at most 200 [start, end] pairs")
        wins = list(wins)
    if "windows_from" in c:
        wins += windows_from(ctx, c["windows_from"])
    if len(wins) > 200:
        raise CheckFail("more than 200 windows")
    floor = num(c, "floor", 16, lo=0, hi=255)
    crop = crop_of(c)
    d = duration_of(ctx.tools, ctx.input)
    if "expected_duration_s" in c:
        exp, tol = num(c, "expected_duration_s", lo=0, hi=1e6), num(c, "duration_tolerance_s", 0.5, lo=0, hi=1e6)
        if abs(d - exp) > tol:
            raise CheckFail(f"duration {d:.2f}s, expected {exp:g}s within {tol:g}s")
    elif "duration_tolerance_s" in c:
        raise CheckFail("'duration_tolerance_s' needs 'expected_duration_s' written into the spec")
    pts = [min(round(d * p, 3), d - 0.05) for p in samples_of(c)]
    for w in wins:
        w = as_pair(w)
        if (not isinstance(w, list) or len(w) != 2 or not all(is_num(x) for x in w)
                or not 0 <= w[0] < w[1] <= d + 0.5):
            raise CheckFail("each window must be [start, end] in seconds inside the video")
        a, b = float(w[0]), min(float(w[1]), d)
        pts += [max(0.0, a + 0.02), max(0.0, (a + b) / 2), max(0.0, b - 0.1)]
    dark = []
    worst = 255.0
    for t in pts:
        mean = ctx.tools.luma(ctx.input, crop, t)[0]
        worst = min(worst, mean)
        if mean < floor:
            dark.append(round(t, 2))
    if dark:
        raise CheckFail(f"{len(dark)} of {len(pts)} samples under luma {floor:g} (lowest {worst:.1f}), at t={dark}")
    return f"{len(pts)} samples, lowest mean luma {worst:.1f}"


WF_NAME = re.compile(r"^[A-Za-z0-9_-]{1,60}$")
WF_KEY = re.compile(r"^[A-Za-z0-9_]{1,40}$")
WF_FOLDERS = ("", "saves", "prior", "work")
MAX_JSON = 2_000_000


def load_json_in_work(ctx, path):
    """Read a JSON file that must resolve inside the work folder."""
    real = os.path.realpath(path)
    if not inside(real, ctx.work):
        raise CheckFail("a file the spec names is outside the work folder")
    try:
        with open(real, "rb") as fh:
            raw = fh.read(MAX_JSON + 1)
        if len(raw) > MAX_JSON:
            raise CheckFail("a JSON file is larger than 2 MB")
        return json.loads(raw.decode("utf-8"))
    except (OSError, ValueError, RecursionError):
        raise CheckFail("a JSON file is missing or unreadable")


def as_pair(w):
    """A window is [start, end] or an object with numeric start and end."""
    if isinstance(w, dict):
        return [w.get("start"), w.get("end")]
    return w


def windows_from(ctx, refs):
    """Resolve entries like "edit_plan.takeovers" and "beat_list.broll".

    "<name>.<key>" reads <name>.json, looked for in the work folder, then saves/,
    prior/ and work/ inside it, first match wins. <key> names a top-level list of
    objects with numeric start and end. For key "broll" in a file with a "beats"
    list, the beats with kind "broll" are used. A missing file is a FAIL.
    """
    if not isinstance(refs, list) or not refs or len(refs) > 10:
        raise CheckFail("'windows_from' must be a list of 1 to 10 entries like \"edit_plan.takeovers\"")
    out = []
    for ref in refs:
        name, _, key = ref.partition(".") if isinstance(ref, str) else ("", "", "")
        if not WF_NAME.match(name) or not WF_KEY.match(key):
            raise CheckFail("a 'windows_from' entry must look like name.key, with letters, digits, - and _ only")
        found = None
        for folder in WF_FOLDERS:
            cand = os.path.join(ctx.work, folder, name + ".json")
            if os.path.isfile(cand):
                found = cand
                break
        if not found:
            raise CheckFail(f"'windows_from' file {name}.json was not found in the work folder")
        data = load_json_in_work(ctx, found)
        items = data.get(key) if isinstance(data, dict) else None
        if items is None and key == "broll" and isinstance(data, dict) and isinstance(data.get("beats"), list):
            items = [b for b in data["beats"] if isinstance(b, dict) and b.get("kind") == "broll"]
        if not isinstance(items, list):
            raise CheckFail(f"{name}.json has no list named '{key}'")
        out += items
    return out


def cover_ok(mean, rng, bright, c):
    bright_mean = num(c, "bright_mean", 48, lo=0, hi=255)
    min_mean = num(c, "min_mean", 8, lo=0, hi=255)
    min_range = num(c, "min_range", 128, lo=0, hi=255)
    min_bright = num(c, "min_bright_pct", 2.0, lo=0, hi=100) / 100
    return mean > bright_mean or (mean >= min_mean and rng >= min_range and bright >= min_bright), \
        f"need mean>{bright_mean:g}, or mean>={min_mean:g} with range>={min_range:g} and >={min_bright * 100:g}% bright pixels"


def c_contrast_floor(ctx, c):
    crop = crop_of(c)
    bad, vals = [], []
    times = times_for(ctx, samples_of({"samples": c.get("samples", [0.0])}))
    for t in times:
        mean, lo, hi, bright = ctx.tools.luma(ctx.input, crop, t)
        ok, rule = cover_ok(mean, hi - lo, bright, c)
        vals.append(f"t={t:g}: mean {mean:.0f}, range {hi - lo}, bright {bright * 100:.1f}%")
        if not ok:
            bad.append(t)
    if bad:
        raise CheckFail("flat, dark or blank at t=" + str(bad) + "; " + rule + " (" + "; ".join(vals) + ")")
    return "; ".join(vals)


def c_not_flat(ctx, c):
    min_range = num(c, "min_range", 32, lo=0, hi=255)
    mean, lo, hi, _ = ctx.tools.luma(ctx.input, crop_of(c), 0.0)
    if hi - lo <= min_range:
        raise CheckFail(f"flat or blank: luma range {hi - lo}, needs more than {min_range:g}")
    return f"luma range {hi - lo}"


def c_qa_gate(ctx, c):
    """The reel floor in one kind. Returns one row per part."""
    fmt = c.get("format", "reel")
    if fmt not in FORMATS:
        raise CheckFail(f"unknown format '{fmt}', expected one of {sorted(FORMATS)}")
    w, h = FORMATS[fmt]
    fps = num(c, "expect_fps", 30, lo=1, hi=240)
    target, tol = num(c, "lufs_target", -14, lo=-70, hi=0), num(c, "lufs_tol", 1.5, lo=0, hi=30)
    parts = [
        ("video", lambda: (video_stream(ctx.tools, ctx.input), "decodable video stream")[1]),
        ("audio", lambda: c_audio_present(ctx, {})),
        ("size", lambda: c_dims(ctx, {"w": w, "h": h})),
        ("fps", lambda: c_fps(ctx, {"expect": fps})),
        ("duration", lambda: c_duration_window(ctx, {"min_s": 0.001})),
        ("loudness", lambda: c_loudness(ctx, {"target": target, "tol": tol})),
        ("cover", lambda: c_contrast_floor(ctx, {"samples": [0.0]})),
    ]
    rows = []
    for name, fn in parts:
        try:
            rows.append((name, "PASS", fn(), ""))
        except CheckFail as e:
            rows.append((name, "FAIL", "", str(e)))
    return rows


KINDS = {
    "reel": {
        "dims": c_dims, "fps": c_fps, "duration_window": c_duration_window,
        "spoken_duration_window": c_spoken_duration_window, "audio_present": c_audio_present,
        "loudness": c_loudness, "mean_volume": c_mean_volume, "luma_floor": c_luma_floor,
        "luma_floor_windows": c_luma_floor_windows, "contrast_floor": c_contrast_floor,
        "qa_gate": c_qa_gate, "json_array_nonempty": c_json_array_nonempty,
        "json_words_nonempty": c_json_words_nonempty,
    },
    "image": {
        "dims": c_dims, "aspect_ratio": c_aspect_ratio, "luma_floor": c_luma_floor,
        "contrast_floor": c_contrast_floor, "not_flat": c_not_flat,
    },
}


class Ctx:
    def __init__(self, kind, tools, input_path, work):
        self.kind, self.tools, self.input, self.work = kind, tools, input_path, work


# ---------------------------------------------------------------- run

def run_checks(ctx, checks, tools):
    rows = []
    if tools.missing():
        rows.append({"id": "tools", "type": "tools", "status": "FAIL", "value": "",
                     "detail": " and ".join(tools.missing()) + " not found on PATH"})
    for n, c in enumerate(checks, 1):
        if not isinstance(c, dict):
            rows.append({"id": f"check-{n}", "type": "?", "status": "FAIL", "value": "", "detail": "check is not an object"})
            continue
        cid = c.get("id") if isinstance(c.get("id"), str) else f"check-{n}"
        typ = c.get("type")
        row = {"id": cid, "type": typ if isinstance(typ, str) else "?", "status": "FAIL", "value": "", "detail": ""}
        if typ == "perceptual":
            desc = c.get("desc")
            row.update(status="LOOK", question=desc if isinstance(desc, str) and desc else "(no question text in the spec)")
        elif not isinstance(typ, str) or not typ:
            row["detail"] = "check has no type"
        elif typ not in KINDS[ctx.kind]:
            known = typ in KINDS["reel"] or typ in KINDS["image"]
            row["detail"] = (f"check kind '{typ}' is not supported with --kind {ctx.kind}" if known
                             else f"check kind '{typ}' is not known to b-qa-gate")
        else:
            try:
                res = KINDS[ctx.kind][typ](ctx, c)
                if typ == "qa_gate":
                    for name, st, val, det in res:
                        rows.append({"id": f"{cid}.{name}", "type": typ, "status": st, "value": val, "detail": det})
                    continue
                row.update(status="PASS", value=res)
            except CheckFail as e:
                row["detail"] = str(e)
            except Exception as e:             # never a traceback: a clean FAIL row
                row["detail"] = f"unexpected error ({type(e).__name__}) while running this check"
        rows.append(row)
    return rows


def sha256_of(path):
    h, size = hashlib.sha256(), 0
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
            size += len(chunk)
    return h.hexdigest(), size


FLAT = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]")


def flat(x, limit=200):
    """Text from a spec, answers or scorecard, made safe to print on one line."""
    return FLAT.sub(" ", str(x))[:limit]


def old_scorecard_or_absent(path):
    """True if nothing is at path, or the file is a JSON scorecard this tool wrote."""
    if not os.path.lexists(path):
        return True
    try:
        if os.path.islink(path) or not os.path.isfile(path) or os.path.getsize(path) > MAX_JSON:
            return False
        with open(path, "rb") as fh:
            data = json.loads(fh.read().decode("utf-8"))
        return isinstance(data, dict) and "scorecard_version" in data
    except (OSError, ValueError, RecursionError):
        return False


def clear_old(path):
    """Remove an old scorecard so a stale PASS cannot survive a crash."""
    if os.path.lexists(path) and not os.path.isdir(path):
        os.unlink(path)


def inside(path, root):
    return path == root or path.startswith(root + os.sep)


NOTE_MAX = 500
CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def input_row(card, work):
    """Re-hash the checked input. It must be unchanged since the check ran."""
    row = {"id": "input_unchanged", "type": "input", "status": "FAIL", "value": "", "detail": ""}
    rel, want = card.get("input"), card.get("input_sha256")
    if not isinstance(rel, str) or not isinstance(want, str) or not isinstance(card.get("input_bytes"), int):
        row["detail"] = "the scorecard does not record the input's hash"
        return row
    path = os.path.realpath(os.path.join(work, rel))
    if os.path.isabs(rel) or not inside(path, work) or not os.path.isfile(path):
        row["detail"] = f"the checked input {rel[:120]} is missing or outside the work folder"
        return row
    try:
        got, size = sha256_of(path)
    except OSError:
        row["detail"] = "the checked input cannot be read"
        return row
    if got != want or size != card["input_bytes"]:
        row["detail"] = "the input changed after the check ran; run the check again"
        return row
    row.update(status="PASS", value=got[:12])
    return row


def finalize(a, usage):
    """Record the look answers on a scorecard and write the final scorecard."""
    if a.kind or a.spec or a.input or a.step:
        return usage("--finalize takes only --answers and --out")
    if not a.answers or not a.out:
        return usage("--finalize needs --answers and --out")
    work = os.path.realpath(os.getcwd())
    paths = [os.path.realpath(p) for p in (a.finalize, a.answers, a.out)]
    if any(not inside(p, work) for p in paths) or paths[2] == work or os.path.isdir(paths[2]):
        return usage("--finalize, --answers and --out must be files inside the current (work) folder")
    if paths[2] in paths[:2]:
        return usage("--out must not be the scorecard or the answers file")
    if not old_scorecard_or_absent(paths[2]):
        return usage("--out is an existing file that is not a scorecard from this tool; it was left alone")
    docs = []
    for p in paths[:2]:
        try:
            with open(p, "rb") as fh:
                raw = fh.read(MAX_JSON + 1)
            if len(raw) > MAX_JSON:
                clear_old(paths[2])
                return usage("a JSON file is larger than 2 MB")
            docs.append(json.loads(raw.decode("utf-8")))
        except (OSError, ValueError, RecursionError):
            clear_old(paths[2])
            return usage("the scorecard or the answers file is not a readable JSON file")
    c0 = docs[0]
    if isinstance(c0, dict):
        rel, spec_name = c0.get("input"), c0.get("spec")
        if isinstance(rel, str) and not os.path.isabs(rel) and os.path.realpath(os.path.join(work, rel)) == paths[2]:
            return usage("--out must not be the checked input")
        if isinstance(spec_name, str) and spec_name and os.path.basename(paths[2]) == os.path.basename(spec_name):
            return usage("--out must not have the name of the spec the scorecard records")
    clear_old(paths[2])
    card, answers = docs
    if (not isinstance(card, dict) or card.get("scorecard_version") != 1 or not isinstance(card.get("checks"), list)
            or any(not isinstance(r, dict) for r in card["checks"])):
        return usage("--finalize is not a b-qa-gate scorecard")
    if card.get("finalized"):
        return usage("that scorecard is already finalized")
    if not isinstance(answers, dict):
        return usage("--answers must hold a JSON object")

    rows = []
    look_ids = set()
    for r in card["checks"]:
        r = dict(r)
        if r.get("status") == "LOOK":
            look_ids.add(r.get("id"))
            ans = answers.get(r.get("id"))
            note = ""
            if ans is None:
                r.update(status="FAIL", detail="no answer was given for this look")
            elif not isinstance(ans, dict) or ans.get("answer") not in ("yes", "no"):
                r.update(status="FAIL", detail="answer must be an object with \"answer\": \"yes\" or \"no\"")
            else:
                raw_note = ans.get("note", "")
                note = CTRL.sub(" ", raw_note)[:NOTE_MAX] if isinstance(raw_note, str) else ""
                if not isinstance(raw_note, str):
                    r.update(status="FAIL", detail="note must be text")
                elif ans["answer"] == "yes":
                    r.update(status="PASS", value="yes", detail=note)
                else:
                    r.update(status="FAIL", value="no", detail="answered no" + (": " + note if note else ""))
                r["answer"], r["note"] = ans["answer"], note
        rows.append(r)
    for k in answers:
        if k not in look_ids:
            rows.append({"id": "answer:" + CTRL.sub(" ", str(k))[:80], "type": "answer", "status": "FAIL", "value": "",
                         "detail": "an answer was given for an id that is not a look row"})
    rows.append(input_row(card, work))
    fails = [r for r in rows if r.get("status") == "FAIL"]
    card.update(
        checks=rows, finalized=True, finalized_from=os.path.relpath(paths[0], work),
        verdict="FAIL" if fails else "PASS",
        counts={"pass": sum(r.get("status") == "PASS" for r in rows), "fail": len(fails), "look": 0},
    )
    os.makedirs(os.path.dirname(paths[2]), exist_ok=True)
    with open(paths[2], "w", encoding="utf-8") as fh:
        json.dump(card, fh, indent=2)
        fh.write("\n")
    print(f"verdict: {card['verdict']}  pass={card['counts']['pass']} fail={card['counts']['fail']}")
    for r in fails:
        print(f"FAIL {flat(r.get('id'), 100)}: {flat(r.get('detail'))}")
    print(f"scorecard: {flat(os.path.relpath(paths[2], work))}")
    return EXIT_FAIL if fails else EXIT_OK


def main(argv=None):
    ap = argparse.ArgumentParser(description="Mechanical checks for a reel or an image.", add_help=True)
    ap.add_argument("--kind", choices=["reel", "image"])
    ap.add_argument("--spec", help="the recipe's acceptance.json")
    ap.add_argument("--input", help="the file to check (inside the work folder)")
    ap.add_argument("--out", help="scorecard path (inside the work folder)")
    ap.add_argument("--step", help="check the named step in the spec's 'steps' instead of the final checks")
    ap.add_argument("--finalize", help="a scorecard whose looks have been answered; needs --answers and --out")
    ap.add_argument("--answers", help="with --finalize: JSON of {id: {answer: yes|no, note}}")
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return EXIT_USAGE if e.code not in (0, None) else EXIT_OK

    def usage(msg):
        print(f"b-qa-gate: {flat(msg)}", file=sys.stderr)
        return EXIT_USAGE

    if a.finalize:
        return finalize(a, usage)
    if a.answers or not (a.kind and a.spec and a.input and a.out):
        return usage("needs --kind, --spec, --input and --out (or --finalize with --answers and --out)")
    work = os.path.realpath(os.getcwd())
    inp = os.path.realpath(a.input)
    out = os.path.realpath(a.out)
    if not inside(inp, work):
        return usage("--input must be inside the current (work) folder")
    if not os.path.isfile(inp):
        return usage("--input is not a file")
    if not inside(out, work) or out == work or os.path.isdir(out):
        return usage("--out must be a file path inside the current (work) folder")
    if out in (inp, os.path.realpath(a.spec)):
        return usage("--out must not be the input or the spec")
    if not old_scorecard_or_absent(out):
        return usage("--out is an existing file that is not a scorecard from this tool; it was left alone")
    clear_old(out)
    try:
        with open(a.spec, "rb") as fh:
            raw = fh.read(1_000_001)
        if len(raw) > 1_000_000:
            return usage("--spec is larger than 1 MB")
        spec = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError, RecursionError):
        return usage("--spec is not a readable JSON file")
    if not isinstance(spec, dict):
        return usage("--spec must hold a JSON object")
    if a.step:
        step = spec.get("steps", {}).get(a.step) if isinstance(spec.get("steps"), dict) else None
        checks = step.get("checks") if isinstance(step, dict) else None
        if checks is None:
            return usage(f"no step '{a.step}' in the spec")
    else:
        checks = spec.get("checks")
    if not isinstance(checks, list) or not checks:
        return usage("the spec has no checks to run")

    try:
        digest, nbytes = sha256_of(inp)
    except OSError:
        return usage("--input cannot be read")
    tools = Tools()
    ctx = Ctx(a.kind, tools, inp, work)
    rows = run_checks(ctx, checks, tools)

    out_dir = os.path.dirname(out)
    os.makedirs(out_dir, exist_ok=True)
    frames = []
    looks = [r for r in rows if r["status"] == "LOOK"]
    if looks and a.kind == "reel" and not tools.missing():
        try:
            d = duration_of(tools, inp)
            fdir = os.path.join(out_dir, os.path.splitext(os.path.basename(out))[0] + "-frames")
            if os.path.islink(fdir) or (os.path.lexists(fdir) and not os.path.isdir(fdir)):
                raise CheckFail("the frames folder is a link or not a folder; remove it")
            os.makedirs(fdir, exist_ok=True)
            if not inside(os.path.realpath(fdir), work):
                raise CheckFail("the frames folder is outside the work folder")
            for p in (0, 0.05, 0.2, 0.4, 0.6, 0.8, 0.95):
                dest = os.path.join(fdir, f"frame-{int(p * 100):02d}.png")
                if os.path.lexists(dest):
                    if os.path.isdir(dest) and not os.path.islink(dest):
                        raise CheckFail("a frame path is a folder")
                    os.unlink(dest)
                if not tools.frame_to(inp, 0.0 if p == 0 else min(round(d * p, 3), d - 0.05), dest):
                    raise CheckFail("could not extract a frame")
                frames.append(os.path.relpath(dest, work))
        except (CheckFail, OSError) as e:
            frames = []
            rows.append({"id": "frames", "type": "frames", "status": "FAIL", "value": "",
                         "detail": f"frames for the looks could not be made: {e}"})

    fails = [r for r in rows if r["status"] == "FAIL"]
    verdict = "FAIL" if fails else ("PASS_WITH_LOOKS" if looks else "PASS")
    card = {
        "scorecard_version": 1,
        "recipe": spec.get("recipe") if isinstance(spec.get("recipe"), str) else None,
        "kind": a.kind,
        "spec": os.path.basename(a.spec),
        "step": a.step or "final",
        "input": os.path.relpath(inp, work),
        "input_sha256": digest,
        "input_bytes": nbytes,
        "tools": {"ffmpeg": tools.version("ffmpeg"), "ffprobe": tools.version("ffprobe")},
        "verdict": verdict,
        "counts": {"pass": sum(r["status"] == "PASS" for r in rows), "fail": len(fails), "look": len(looks)},
        "checks": rows,
        "frames": frames,
    }
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(card, fh, indent=2)
        fh.write("\n")
    print(f"verdict: {verdict}  pass={card['counts']['pass']} fail={card['counts']['fail']} look={card['counts']['look']}")
    for r in fails:
        print(f"FAIL {flat(r['id'], 100)}: {flat(r['detail'])}")
    print(f"scorecard: {flat(os.path.relpath(out, work))}")
    return EXIT_FAIL if fails else (EXIT_LOOKS if looks else EXIT_OK)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:                   # last resort: one line, no traceback
        print(f"b-qa-gate: unexpected error ({type(exc).__name__})", file=sys.stderr)
        sys.exit(EXIT_FAIL)
