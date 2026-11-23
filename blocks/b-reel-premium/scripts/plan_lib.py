"""Shared code for the b-reel-premium scripts: plan checks, path checks, safe JSON for a page.

Standard library only. Nothing here starts a program except probe_duration (ffprobe, argument
list). Nothing here reads anything except the files the caller names.
"""
import html
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata

BLOCK_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SFX_DIR = os.path.join(BLOCK_DIR, "assets", "sfx")
TEMPLATE_DIR = os.path.join(BLOCK_DIR, "templates")

SFX_NAMES = ("whoosh-deep", "whoosh-air", "impact-sub", "impact-punch", "riser", "click", "pop", "swipe")
GRADES = {
    "warm-amber": "curves=r='0/0 0.5/0.55 1/1':b='0/0 0.5/0.46 1/0.95',eq=contrast=1.05:saturation=1.08,unsharp=5:5:0.5",
    "clean-bright": "eq=brightness=0.02:contrast=1.06:saturation=1.1,unsharp=5:5:0.5",
    "off": "null",
}
MUSIC_EXTENSIONS = (".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg")
INPUTS_DIR = "inputs"
FONT_EXTENSIONS = {".ttf": (b"\x00\x01\x00\x00", b"true"), ".otf": (b"OTTO",), ".woff": (b"wOFF",), ".woff2": (b"wOF2",)}
FONT_MAX_BYTES = 3 * 1024 * 1024
FONT_FAMILY_NAME = "CaptionFont"

MAX_DURATION = 600.0
MAX_GROUPS = 400
MAX_WORDS_PER_GROUP = 8
MAX_WORD_CHARS = 40
MAX_SFX = 12
MAX_SFX_GAIN = 0.6
MAX_MUSIC_GAIN = 0.3

_HEX = re.compile(r"#?([0-9A-Fa-f]{6})")


class PlanError(Exception):
    """One or more problems, each one plain line. Exit code 1 in every script."""

    def __init__(self, problems):
        super().__init__("; ".join(problems))
        self.problems = list(problems)


def is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _reject_constant(name):
    raise ValueError("JSON constant %s is not allowed" % name)


def load_json(path):
    """Read a JSON file. NaN and Infinity are refused. Raises OSError or ValueError."""
    with open(path, encoding="utf-8") as fh:
        return json.load(fh, parse_constant=_reject_constant)


def norm_color(value):
    """Return '#RRGGBB' (upper case) for a six-digit hex colour, with or without one '#'. Else None."""
    if not isinstance(value, str):
        return None
    m = _HEX.fullmatch(value)
    return "#" + m.group(1).upper() if m else None


# ---------------------------------------------------------------- paths

def workdir_root(workdir):
    return os.path.realpath(workdir or ".")


def inside(path, root):
    """True when the real path of `path` is `root` or below it. Works for paths that do not exist yet."""
    rp = os.path.realpath(path)
    return rp == root or rp.startswith(root + os.sep)


def check_in_workdir(path, root, what, must_exist):
    """Return the real path, or raise PlanError. `path` is a command-line value."""
    if not path or "\x00" in path:
        raise PlanError(["%s: path is empty or has a null byte" % what])
    if not inside(path, root):
        raise PlanError(["%s: %s is outside the work folder" % (what, path)])
    rp = os.path.realpath(path)
    if must_exist and not os.path.isfile(rp):
        raise PlanError(["%s: %s is not a file" % (what, path)])
    return rp


def check_music_path(value, root):
    """A music file is accepted only inside <work folder>/inputs. Returns the real path."""
    if not isinstance(value, str) or not value or "\x00" in value:
        raise PlanError(["music.file must be a path inside %s/" % INPUTS_DIR])
    if os.path.isabs(value):
        candidate = value
    else:
        candidate = os.path.join(root, value)
    inputs_root = os.path.realpath(os.path.join(root, INPUTS_DIR))
    if not inside(candidate, inputs_root) or os.path.realpath(candidate) == inputs_root:
        raise PlanError(["music.file %r is not inside the work folder's %s/ folder" % (value, INPUTS_DIR)])
    rp = os.path.realpath(candidate)
    if not os.path.isfile(rp):
        raise PlanError(["music.file %r does not exist" % value])
    if not rp.lower().endswith(MUSIC_EXTENSIONS):
        raise PlanError(["music.file %r must end in one of %s" % (value, " ".join(MUSIC_EXTENSIONS))])
    return rp


def check_font_path(value, root):
    """A caption font file: inside <work folder>/inputs, a known font extension and header, at most 3 MB."""
    if not isinstance(value, str) or not value or "\x00" in value:
        raise PlanError(["brand.font_file must be a path inside %s/" % INPUTS_DIR])
    candidate = value if os.path.isabs(value) else os.path.join(root, value)
    inputs_root = os.path.realpath(os.path.join(root, INPUTS_DIR))
    rp = os.path.realpath(candidate)
    if rp == inputs_root or not inside(candidate, inputs_root):
        raise PlanError(["brand.font_file %r is not inside the work folder's %s/ folder" % (value, INPUTS_DIR)])
    if not os.path.isfile(rp):
        raise PlanError(["brand.font_file %r does not exist" % value])
    ext = os.path.splitext(rp)[1].lower()
    if ext not in FONT_EXTENSIONS:
        raise PlanError(["brand.font_file must end in %s" % " ".join(sorted(FONT_EXTENSIONS))])
    if os.path.getsize(rp) > FONT_MAX_BYTES:
        raise PlanError(["brand.font_file is larger than %d MB" % (FONT_MAX_BYTES // (1024 * 1024))])
    with open(rp, "rb") as fh:
        head = fh.read(4)
    if head not in FONT_EXTENSIONS[ext]:
        raise PlanError(["brand.font_file does not look like a %s font file" % ext])
    return rp, ext


def refuse_inner_symlinks(path, root, what):
    """Refuse a path that passes through, or ends at, a symbolic link below the work folder.

    A link that leads to the work folder itself or to a folder above it (for example /tmp on some
    systems) is the user's own setting and is allowed. Any other link is refused, whether it points
    outside or back inside.
    """
    cur = os.sep
    for comp in os.path.abspath(path).split(os.sep):
        if not comp:
            continue
        cur = os.path.join(cur, comp)
        if os.path.islink(cur):
            real = os.path.realpath(cur)
            if not (real == root or root.startswith(real + os.sep)):
                raise PlanError(["%s: %s is a symbolic link; links are not followed for output" % (what, cur)])


def ensure_dir(path, root, what="output folder"):
    """Make `path` (inside the work folder) one component at a time, refusing a link at any level below the root."""
    rp = os.path.abspath(path)
    rel = os.path.relpath(rp, root) if (rp == root or rp.startswith(root + os.sep)) else None
    if rel is None:
        rel = os.path.relpath(os.path.realpath(rp), root)
    if rel == os.pardir or rel.startswith(os.pardir + os.sep):
        raise PlanError(["%s: %s is outside the work folder" % (what, path)])
    cur = root
    for comp in [c for c in rel.split(os.sep) if c and c != "."]:
        cur = os.path.join(cur, comp)
        if os.path.islink(cur):
            raise PlanError(["%s: %s is a symbolic link; links are not followed for output" % (what, cur)])
        if os.path.exists(cur):
            if not os.path.isdir(cur):
                raise PlanError(["%s: %s exists and is not a folder" % (what, cur)])
        else:
            os.mkdir(cur)
    return cur


def preflight_target(target, root, what):
    """Check a file target without creating anything: no link at any level below the root, no folder in its place."""
    rp = os.path.abspath(target)
    if not (rp == root or rp.startswith(root + os.sep)):
        rp = os.path.join(os.path.realpath(os.path.dirname(rp)), os.path.basename(rp))
    rel = os.path.relpath(rp, root)
    if rel == os.pardir or rel.startswith(os.pardir + os.sep):
        raise PlanError(["%s: %s is outside the work folder" % (what, target)])
    parts = [c for c in rel.split(os.sep) if c and c != "."]
    cur = root
    for i, comp in enumerate(parts):
        cur = os.path.join(cur, comp)
        if os.path.islink(cur):
            raise PlanError(["%s: %s is a symbolic link; links are not followed for output" % (what, cur)])
        if os.path.lexists(cur) and i < len(parts) - 1 and not os.path.isdir(cur):
            raise PlanError(["%s: %s exists and is not a folder" % (what, cur)])
    if os.path.isdir(rp):
        raise PlanError(["%s: %s is a folder" % (what, target)])


def _check_target(target, root, what):
    if os.path.islink(target):
        raise PlanError(["%s: %s is a symbolic link; refusing to write through it" % (what, target)])
    if os.path.isdir(target):
        raise PlanError(["%s: %s is a folder" % (what, target)])


def _finish(tmp, target, root, what):
    """Move a finished temporary file into place and confirm where it landed."""
    os.chmod(tmp, 0o644)
    os.replace(tmp, target)
    if not inside(target, root) or os.path.islink(target):
        try:
            os.unlink(target)
        finally:
            raise PlanError(["%s: %s ended up outside the work folder" % (what, target)])


def write_file(target, root, data=None, copy_from=None, what="output"):
    """Write `target` through a temporary file in its own folder, then os.replace. Temp file removed on any failure."""
    ensure_dir(os.path.dirname(target), root, what)
    _check_target(target, root, what)
    if copy_from is not None and os.path.realpath(copy_from) == os.path.realpath(target):
        raise PlanError(["%s: %s is also an input file" % (what, target)])
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(target), prefix=".tmp-", suffix=".part")
    try:
        with os.fdopen(fd, "wb") as fh:
            if copy_from is not None:
                with open(copy_from, "rb") as src:
                    shutil.copyfileobj(src, fh)
            else:
                fh.write(data)
        _finish(tmp, target, root, what)
        tmp = None
    finally:
        if tmp is not None and os.path.lexists(tmp):
            os.unlink(tmp)


def temp_output(target, root, suffix, what="output"):
    """Reserve a fresh temporary file name beside `target` for a program to write; returns its path.

    The caller must call `finish_temp(tmp, target, ...)` on success and `drop_temp(tmp)` otherwise.
    """
    ensure_dir(os.path.dirname(target), root, what)
    _check_target(target, root, what)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(target), prefix=".tmp-", suffix=suffix)
    os.close(fd)
    return tmp


def finish_temp(tmp, target, root, what="output"):
    if os.path.islink(tmp) or not os.path.isfile(tmp):
        raise PlanError(["%s: the temporary file is not a plain file" % what])
    _check_target(target, root, what)
    _finish(tmp, target, root, what)


def drop_temp(tmp):
    if tmp and os.path.lexists(tmp):
        os.unlink(tmp)


def run_main(main, name, argv):
    """Run main(argv). Problems become a list on stderr and exit 1. Anything unexpected prints one fixed line, exit 1."""
    try:
        return main(argv)
    except SystemExit:
        raise
    except PlanError as e:
        sys.stderr.write("%s: %d problem(s)\n" % (name, len(e.problems)))
        for p in e.problems:
            sys.stderr.write("  - %s\n" % p)
        return 1
    except Exception:
        sys.stderr.write("%s: failed unexpectedly; nothing further was written\n" % name)
        return 1


def check_output_path(path, root, what, suffixes):
    refuse_inner_symlinks(path, root, what)
    rp = check_in_workdir(path, root, what, must_exist=False)
    if not rp.lower().endswith(suffixes):
        raise PlanError(["%s must end in %s" % (what, " or ".join(suffixes))])
    if os.path.isdir(rp):
        raise PlanError(["%s is a folder" % what])
    return rp


# ---------------------------------------------------------------- tools

def probe_duration(path):
    """Duration in seconds of a media file, from ffprobe (argument list). Raises FileNotFoundError, PlanError."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-protocol_whitelist", "file", "-show_entries", "format=duration", "-of", "csv=p=0", "-i", path],
        capture_output=True, text=True, check=False,
    )
    try:
        d = float(out.stdout.strip())
    except ValueError:
        raise PlanError(["ffprobe could not read a duration from %s" % path])
    if not math.isfinite(d) or d <= 0:
        raise PlanError(["%s has no usable duration" % path])
    return d


MIN_FPS, MAX_FPS = 1.0, 120.0


def probe_video_timing(path, what="--reel"):
    """The reel's own picture timing: {"fps": "30/1", "frames": int, "seconds": float}.

    The frame count is the number of video packets (one per frame); the rate is the stream's average rate
    (its base rate when the average is not given). The output is made to match these exactly, so anything odd
    is refused: a rate that cannot be read or is outside 1 to 120 frames a second, no frames, or a frame count
    that does not fit the picture's own length.
    """
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-protocol_whitelist", "file", "-select_streams", "v:0", "-count_packets", "-show_entries",
         "stream=avg_frame_rate,r_frame_rate,nb_read_packets,duration", "-of", "json", "-i", path],
        capture_output=True, text=True, check=False,
    )
    try:
        st = (json.loads(out.stdout).get("streams") or [{}])[0]
    except (ValueError, AttributeError, IndexError):
        st = {}
    try:
        frames = int(st.get("nb_read_packets"))
    except (ValueError, TypeError):
        raise PlanError(["%s has no countable video frames" % what])
    if frames < 1:
        raise PlanError(["%s has no video frames" % what])
    raw = str(st.get("avg_frame_rate", ""))
    if raw in ("", "0/0", "N/A"):
        raw = str(st.get("r_frame_rate", ""))
    m = re.fullmatch(r"(\d{1,9})/(\d{1,9})", raw)
    if not m or int(m.group(1)) == 0 or int(m.group(2)) == 0:
        raise PlanError(["%s has a frame rate that cannot be read (%r)" % (what, raw)])
    num, den = int(m.group(1)), int(m.group(2))
    if not MIN_FPS <= num / den <= MAX_FPS:
        raise PlanError(["%s has a frame rate of %.3g frames a second; only %d to %d are accepted" % (what, num / den, MIN_FPS, MAX_FPS)])
    seconds = frames * den / num
    try:
        length = float(st.get("duration"))
    except (ValueError, TypeError):
        length = None
    if length is not None and (not math.isfinite(length) or abs(length - seconds) > max(0.25, 3.0 * den / num)):
        raise PlanError(["%s holds %d frames at %d/%d (%.2f s) but its picture is %.2f s long" % (what, frames, num, den, seconds, length)])
    return {"fps": "%d/%d" % (num, den), "frames": frames, "seconds": seconds}


MUSIC_FORMATS = ("wav", "mp3", "aac", "flac", "ogg", "mp4")


def probe_media(path, what=None):
    """What ffprobe says a file holds: {"video": bool, "audio": bool, "formats": set of container names}.

    A cover picture inside an audio file (attached picture) is not counted as video.
    """
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-protocol_whitelist", "file", "-show_entries",
         "stream=codec_type,width,height,pix_fmt:stream_disposition=attached_pic:format=format_name", "-of", "json", "-i", path],
        capture_output=True, text=True, check=False,
    )
    if out.returncode != 0:
        raise PlanError(["%s is not a readable media file" % (what or os.path.basename(path))])
    try:
        info = json.loads(out.stdout)
    except ValueError:
        raise PlanError(["%s is not a readable media file" % (what or os.path.basename(path))])
    streams = info.get("streams") or []
    vids = [st for st in streams if st.get("codec_type") == "video" and not (st.get("disposition") or {}).get("attached_pic")]
    return {
        "video": bool(vids),
        "size": (vids[0].get("width"), vids[0].get("height")) if vids else None,
        "pix_fmt": str(vids[0].get("pix_fmt", "")) if vids else "",
        "audio": any(st.get("codec_type") == "audio" for st in streams),
        "formats": set(str((info.get("format") or {}).get("format_name", "")).split(",")),
        "format_list": str((info.get("format") or {}).get("format_name", "")).split(","),
    }


_DEMUXERS = ("mov", "matroska", "wav", "mp3", "flac", "ogg", "aac")


def input_format_args(path, what=None):
    """["-f", NAME] naming the file's real format, which must be one of the short list.

    mp4, m4a and mov all report a list that starts with mov. A format outside the list (a playlist,
    a concat text file, anything else) is refused, so ffmpeg never has to guess.
    """
    first = probe_media(path, what)["format_list"][0]
    if first not in _DEMUXERS:
        raise PlanError(["%s is in the format %r, which is not accepted; use mp4 or mov video, or wav, mp3, m4a/aac, flac or ogg audio"
                         % (what or os.path.basename(path), first or "unknown")])
    return ["-f", first]


def require_video(path, what):
    if not probe_media(path, what)["video"]:
        raise PlanError(["%s holds no video stream" % what])


def require_overlay(path, reel, what):
    """The caption render: a video with an alpha channel, the same picture size as the reel."""
    m, r = probe_media(path, what), probe_media(reel, "--reel")
    if not m["video"]:
        raise PlanError(["%s holds no video stream" % what])
    if not any(tag in m["pix_fmt"] for tag in ("yuva", "rgba", "bgra", "argb", "abgr", "gbrap", "ya")):
        raise PlanError(["%s has no alpha channel (pixel format %r); render the captions with hf_render.py --format mov" % (what, m["pix_fmt"])])
    if m["size"] != r["size"]:
        raise PlanError(["%s is %sx%s but the reel is %sx%s; both must be the same size" % ((what,) + tuple(m["size"]) + tuple(r["size"]))])


def require_audio_file(path, what):
    """A plain audio file in one of the named formats: no video stream, at least one audio stream."""
    m = probe_media(path, what)
    if not m["audio"] or m["video"]:
        raise PlanError(["%s must be a plain audio file (it holds %s)" % (what, "a video stream" if m["video"] else "no audio")])
    if not m["formats"] & set(MUSIC_FORMATS):
        raise PlanError(["%s is in the container format %s; accepted: wav, mp3, m4a/aac, flac, ogg" % (what, ",".join(sorted(m["formats"])) or "unknown")])


def has_audio(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-protocol_whitelist", "file", "-select_streams", "a", "-show_entries", "stream=codec_type", "-of", "csv=p=0", "-i", path],
        capture_output=True, text=True, check=False,
    )
    return out.returncode == 0 and "audio" in out.stdout


def check_tolerance(value):
    if not is_num(value) or not 0 <= value <= 30:
        raise PlanError(["--cover-tolerance must be a number from 0 to 30"])
    return float(value)


def check_duration(value):
    if not is_num(value) or not 0 < value <= MAX_DURATION:
        raise PlanError(["duration must be a number above 0 and at most %d seconds" % MAX_DURATION])
    return float(value)


# ---------------------------------------------------------------- plan check

_ADDRESS_RULES = (
    (re.compile(r"(?i)[a-z][a-z0-9+.-]*\s*:\s*//"), "a web address with ://", "write example.com, not https://example.com"),
    (re.compile(r"(?i)(?<![a-z0-9+.-])(?:https?|wss?|ftp)\s*:"), "a web address scheme", "write example.com, not https://example.com"),
    (re.compile(r"//"), "a protocol-relative address", "write example.com, not //example.com"),
    (re.compile(r"(?i)(?:javascript|vbscript)\s*:"), "a script address", "leave the script address out"),
    (re.compile(r"(?i)(?<![a-z0-9])data\s*:\s*\S"), "a data: address", "leave the data address out"),
    (re.compile(r"(?i)\burl\("), "a CSS url(", "write the words without url("),
    (re.compile(r"(?i)@import"), "a CSS @import", "write import without the @"),
    (re.compile(r"(?i)image-set\s*\("), "a CSS image-set(", "write the words without image-set("),
)
_CSS_ESCAPE = re.compile(r"\\([0-9a-fA-F]{1,6})[ \t\n]?|\\u([0-9a-fA-F]{4})|\\(.)", re.S)


def _undo_escapes(text):
    """HTML entities, CSS escapes and \\uXXXX escapes undone, so a disguised address shows up. Applied twice."""
    def one(m):
        h = m.group(1) or m.group(2)
        if h:
            n = int(h, 16)
            return chr(n) if 0 < n <= 0x10FFFF else ""
        return m.group(3)
    for _ in range(2):
        text = _CSS_ESCAPE.sub(one, html.unescape(text))
    return text


def address_problem(text):
    """None, or (what, what to write instead) when the text holds a web address, script address or CSS link form.

    Both the text and its escape-undone form are tested, to match what b-hyperframes' check_local.py refuses.
    """
    for body in (text, _undo_escapes(text)):
        for rx, what, advice in _ADDRESS_RULES:
            if rx.search(body):
                return what, advice
    return None


def _latin_only(text):
    return all(not c.isalpha() or unicodedata.name(c, "").startswith("LATIN") for c in text)


def plan_problems(plan, duration, root, captions=True, sfx=True, cover_tolerance=3.0, any_script=False):
    """Return a list of problem lines. Empty list means the plan is sound.

    `root` is the work folder (a real path); it is used to check a music file.
    """
    probs = []
    if not isinstance(plan, dict):
        return ["the plan must be a JSON object"]

    grade = plan.get("grade")
    if grade not in GRADES:
        probs.append("grade must be one of %s (got %r)" % (", ".join(GRADES), grade))

    brand = plan.get("brand")
    if not isinstance(brand, dict):
        probs.append("brand must be an object with accent and fg")
    else:
        for key in ("accent", "fg"):
            if norm_color(brand.get(key)) is None:
                probs.append("brand.%s must be a six-digit hex colour such as #F97316 (got %r)" % (key, brand.get(key)))
        if brand.get("font_file") is not None:
            try:
                check_font_path(brand["font_file"], root)
            except PlanError as e:
                probs.extend(e.problems)

    groups = plan.get("caption_groups")
    if captions:
        if not isinstance(groups, list) or not groups:
            probs.append("caption_groups must be a non-empty list (or run with captions off)")
        elif len(groups) > MAX_GROUPS:
            probs.append("caption_groups has %d groups; the limit is %d" % (len(groups), MAX_GROUPS))
        else:
            probs.extend(_group_problems(groups, duration, cover_tolerance, any_script))

    cues = plan.get("sfx", [])
    if cues is None:
        cues = []
    if not isinstance(cues, list):
        probs.append("sfx must be a list")
    elif sfx:
        probs.extend(_sfx_problems(cues, duration))

    if "music" in plan and plan["music"] is not None:
        probs.extend(_music_problems(plan["music"], root))
    return probs


def _group_problems(groups, duration, tolerance, any_script):
    probs = []
    prev_end = 0.0
    for i, g in enumerate(groups):
        tag = "caption group %d" % i
        if not isinstance(g, dict):
            probs.append("%s must be an object" % tag)
            continue
        s, e = g.get("start"), g.get("end")
        if not is_num(s) or not is_num(e):
            probs.append("%s needs numeric start and end" % tag)
            continue
        if s < 0 or e <= s:
            probs.append("%s: times must satisfy 0 <= start < end (got %s, %s)" % (tag, s, e))
        if e > duration + tolerance:
            probs.append("%s ends at %s, after the end of the reel (%.2f s)" % (tag, e, duration))
        if s < prev_end - 0.001:
            probs.append("%s starts at %s, before the previous group ends (%s): groups must be in order and not overlap" % (tag, s, prev_end))
        prev_end = max(prev_end, e)
        style = g.get("style")
        if isinstance(style, bool) or style not in (0, 1, 2):
            probs.append("%s: style must be 0, 1 or 2" % tag)
        words = g.get("words")
        if not isinstance(words, list) or not words:
            probs.append("%s needs a words list" % tag)
            continue
        if len(words) > MAX_WORDS_PER_GROUP:
            probs.append("%s has %d words; the limit is %d" % (tag, len(words), MAX_WORDS_PER_GROUP))
        emphasis = 0
        prev_s = -1.0
        for j, w in enumerate(words):
            wt = "%s word %d" % (tag, j)
            if not isinstance(w, dict):
                probs.append("%s must be an object" % wt)
                continue
            text = w.get("w")
            if not isinstance(text, str) or not text.strip():
                probs.append("%s: w must be non-empty text" % wt)
            else:
                if len(text) > MAX_WORD_CHARS:
                    probs.append("%s: w is longer than %d characters" % (wt, MAX_WORD_CHARS))
                if any(unicodedata.category(c) in ("Cc", "Cf", "Cs", "Co", "Cn") for c in text):
                    probs.append("%s: w holds a control or unassigned character" % wt)
                bad = address_problem(text)
                if bad:
                    probs.append("%s: w %r holds %s, which the render check refuses; %s" % (wt, text[:40], bad[0], bad[1]))
                if not any_script and not _latin_only(text):
                    probs.append("%s: w is not Latin script; transliterate it, never translate" % wt)
            ws, we = w.get("s"), w.get("e")
            if not is_num(ws) or not is_num(we):
                probs.append("%s: s and e must be numbers" % wt)
            else:
                if we < ws:
                    probs.append("%s: e is before s" % wt)
                if ws < prev_s - 0.001:
                    probs.append("%s: words must be in time order" % wt)
                prev_s = max(prev_s, ws)
                if ws < s - 0.05 or ws > e + 0.05:
                    probs.append("%s: s=%s is outside its group (%s to %s)" % (wt, ws, s, e))
            em = w.get("em", False)
            if not isinstance(em, bool):
                probs.append("%s: em must be true or false" % wt)
            elif em:
                emphasis += 1
        if emphasis > 1:
            probs.append("%s has %d emphasis words; at most one" % (tag, emphasis))
    if groups and isinstance(groups[-1], dict) and is_num(groups[-1].get("end")):
        if abs(groups[-1]["end"] - duration) >= tolerance:
            probs.append("the captions end at %s, more than %s s from the end of the reel (%.2f s)" % (groups[-1]["end"], tolerance, duration))
    return probs


def _sfx_problems(cues, duration):
    probs = []
    if len(cues) > MAX_SFX:
        probs.append("sfx has %d cues; the limit is %d" % (len(cues), MAX_SFX))
    prev_t = -1.0
    for j, c in enumerate(cues):
        tag = "sfx cue %d" % j
        if not isinstance(c, dict):
            probs.append("%s must be an object" % tag)
            continue
        name = c.get("name")
        if not isinstance(name, str) or name not in SFX_NAMES:
            probs.append("%s: name %r is not one of %s" % (tag, name, ", ".join(SFX_NAMES)))
        t = c.get("t")
        if not is_num(t) or not 0 <= t <= duration:
            probs.append("%s: t must be a number from 0 to the reel length (%.2f s), got %r" % (tag, duration, t))
        else:
            if t < prev_t:
                probs.append("%s: cues must be in time order (t=%s is before %s)" % (tag, t, prev_t))
            prev_t = max(prev_t, t)
        gain = c.get("gain", 0.5)
        if not is_num(gain) or not 0 <= gain <= MAX_SFX_GAIN:
            probs.append("%s: gain must be a number from 0 to %s, got %r" % (tag, MAX_SFX_GAIN, gain))
    return probs


def _music_problems(music, root):
    if not isinstance(music, dict):
        return ["music must be an object with file and gain"]
    probs = []
    try:
        check_music_path(music.get("file"), root)
    except PlanError as e:
        probs.extend(e.problems)
    gain = music.get("gain", 0.15)
    if not is_num(gain) or not 0 <= gain <= MAX_MUSIC_GAIN:
        probs.append("music.gain must be a number from 0 to %s, got %r" % (MAX_MUSIC_GAIN, gain))
    return probs


def require_sound_plan(plan, duration, root, **kw):
    probs = plan_problems(plan, duration, root, **kw)
    if probs:
        raise PlanError(probs)


# ---------------------------------------------------------------- safe values for a page

def _enc_str(s, hide_words=False):
    """A JSON string with everything but ASCII letters, digits and spaces written as \\uXXXX.

    With hide_words, the first letter of every run of ASCII letters is escaped too, so no word (innerHTML,
    WebSocket, fetch and the like) appears intact in the page file, whatever the render check refuses.
    The browser reads the same text back.
    """
    out = ['"']
    prev_letter = False
    for ch in s:
        letter = ch.isascii() and ch.isalpha()
        if ch == " " or (ch.isascii() and ch.isalnum() and not (hide_words and letter and not prev_letter)):
            out.append(ch)
        else:
            cp = ord(ch)
            if cp > 0xFFFF:
                cp -= 0x10000
                out.append("\\u%04x\\u%04x" % (0xD800 + (cp >> 10), 0xDC00 + (cp & 0x3FF)))
            else:
                out.append("\\u%04x" % cp)
        prev_letter = letter
    out.append('"')
    return "".join(out)


def script_json(value):
    """JSON for a script tag. Inside strings, everything except ASCII letters, digits and space is a \\uXXXX escape.

    So the output holds no angle bracket, quote, slash, colon, backslash-letter or other
    punctuation from the text: it cannot close a script, open a tag, or look like a web address.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise PlanError(["a non-finite number cannot go into a page"])
        return repr(round(value, 4))
    if isinstance(value, str):
        return _enc_str(value, hide_words=True)
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(script_json(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{" + ",".join(_enc_str(str(k)) + ":" + script_json(v) for k, v in value.items()) + "}"
    raise PlanError(["cannot put a %s into a page" % type(value).__name__])


def timeline_js(groups):
    """The caption tween calls as plain statements, from checked numbers only. Contains no caption text."""
    n = num_text
    out = []
    for gi, g in enumerate(groups):
        sel = '"#cg-%d"' % gi
        start, end, style = g["start"], g["end"], g["style"] % 3
        if style == 0:
            out.append('tl.fromTo(%s, { opacity: 0, scale: 0.9, y: 26 }, { opacity: 1, scale: 1, y: 0, duration: 0.3, ease: "back.out(1.7)" }, %s);' % (sel, n(start)))
        elif style == 1:
            out.append('tl.fromTo(%s, { opacity: 0, x: -44 }, { opacity: 1, x: 0, duration: 0.28, ease: "power3.out" }, %s);' % (sel, n(start)))
        else:
            out.append('tl.fromTo(%s, { opacity: 0, y: 54 }, { opacity: 1, y: 0, duration: 0.32, ease: "power4.out" }, %s);' % (sel, n(start)))
        for wi, w in enumerate(g["words"]):
            wsel = '"#cw-%d-%d"' % (gi, wi)
            at = max(w["s"], start + 0.02)
            if w["em"]:
                out.append('tl.fromTo(%s, { "--pop": 1, opacity: 0.42, color: FG }, { "--pop": POP_TO, opacity: 1, color: ACCENT, duration: 0.26, ease: POP_EASE }, %s);' % (wsel, n(at)))
                out.append('tl.to(%s, { textShadow: "0 0 26px " + ACCENT + "AA, 0 4px 24px rgba(0,0,0,0.75)", duration: 0.2, ease: "power2.out" }, %s);' % (wsel, n(at)))
                out.append('tl.to(%s, { "--pop": POP_SETTLE, duration: 0.18, ease: "power2.inOut" }, %s);' % (wsel, n(at + 0.26)))
            else:
                out.append('tl.to(%s, { opacity: 1, duration: 0.14, ease: "power1.out" }, %s);' % (wsel, n(at)))
        out.append('tl.to(%s, { opacity: 0, scale: 0.95, duration: 0.12, ease: "power2.in" }, %s);' % (sel, n(max(start + 0.12, end - 0.12))))
        out.append('tl.set(%s, { opacity: 0, visibility: "hidden" }, %s);' % (sel, n(end)))
    return "\n      ".join(out)


def clean_groups(groups):
    """Copy only the known fields, so nothing else in the plan reaches the page."""
    out = []
    for g in groups:
        out.append({
            "start": float(g["start"]), "end": float(g["end"]), "style": int(g["style"]),
            "words": [{"w": w["w"], "s": float(w["s"]), "e": float(w["e"]), "em": bool(w.get("em", False))} for w in g["words"]],
        })
    return out


_TOKEN = re.compile(r"\{\{([A-Z_]+)\}\}")


def fill_template(text, values):
    """Fill every {{NAME}} in one pass from `values`. An unknown name is an error. Inserted text is never re-scanned."""
    def pick(m):
        name = m.group(1)
        if name not in values:
            raise PlanError(["template placeholder %s has no value" % name])
        return str(values[name])
    out = _TOKEN.sub(pick, text)
    if "{{" in out and _TOKEN.search(out):
        raise PlanError(["a placeholder is left unfilled"])
    return out


def read_template(name):
    with open(os.path.join(TEMPLATE_DIR, name), encoding="utf-8") as fh:
        return fh.read()


def num_text(x):
    """A finite number as plain digits for HTML and CSS."""
    if isinstance(x, int):
        return str(x)
    return repr(round(float(x), 4))
