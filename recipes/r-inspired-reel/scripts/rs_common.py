"""Shared helpers for the r-inspired-reel scripts (standard library only).

Path safety, safe writes, tool runs and word handling. Every recipe script imports this file.
Nothing here opens a network connection, reads a key or starts a shell.
"""
import json
import math
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unicodedata


class Stop(Exception):
    """A planned stop: a plain message and an exit code (1 failed, 2 bad input, 3 tool missing)."""

    def __init__(self, msg, code=2):
        super().__init__(msg)
        self.msg = msg
        self.code = code


def main(fn):
    """Run fn(argv) and turn every stop into one plain line. A traceback is never printed."""
    try:
        code = fn(sys.argv[1:])
    except Stop as e:
        print("error: %s" % e.msg, file=sys.stderr)
        code = e.code
    except KeyboardInterrupt:
        code = 130
    except Exception:  # noqa: BLE001 - one fixed line, never a traceback
        print("error: unexpected failure", file=sys.stderr)
        code = 1
    sys.exit(code or 0)


# ---- paths -------------------------------------------------------------------------------------

def work_root(arg=None):
    root = os.path.realpath(arg or ".")
    if not os.path.isdir(root):
        raise Stop("work folder not found")
    return root


def resolve(root, rel, must_exist=False, kind=None):
    """Absolute path of `rel` inside the work folder `root`.

    Refused: an empty or odd value, '..', a path outside the folder, and any link on the way
    (the work folder itself may be a link; it was resolved once already)."""
    if not isinstance(rel, str) or not rel or "\0" in rel:
        raise Stop("bad path argument")
    parts = [p for p in re.split(r"[\\/]+", rel) if p not in ("", ".")]
    if ".." in parts:
        raise Stop("path leaves the work folder: %s" % rel)
    full = os.path.normpath(os.path.join(root, rel))
    try:
        inside = os.path.commonpath([root, full]) == root
    except ValueError:
        inside = False
    if not inside:
        raise Stop("path leaves the work folder: %s" % rel)
    cur = root
    for part in os.path.relpath(full, root).split(os.sep):
        if part in (".", ""):
            continue
        cur = os.path.join(cur, part)
        if os.path.islink(cur):
            raise Stop("a link is refused: %s" % os.path.relpath(cur, root))
    if must_exist and not os.path.exists(full):
        raise Stop("not found: %s" % rel)
    if kind == "file" and os.path.exists(full) and not os.path.isfile(full):
        raise Stop("not a file: %s" % rel)
    if kind == "dir" and os.path.exists(full) and not os.path.isdir(full):
        raise Stop("not a folder: %s" % rel)
    return full


def rel(root, path):
    return os.path.relpath(path, root).replace(os.sep, "/")


def read_bytes(path, limit):
    """Read a regular file (never through a link) up to `limit` bytes."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError:
        raise Stop("cannot read %s" % os.path.basename(path))
    with os.fdopen(fd, "rb") as fh:
        if not stat.S_ISREG(os.fstat(fh.fileno()).st_mode):
            raise Stop("not a regular file: %s" % os.path.basename(path))
        data = fh.read(limit + 1)
    if len(data) > limit:
        raise Stop("file too large: %s" % os.path.basename(path))
    return data


def read_text(root, relpath, limit=2_000_000):
    data = read_bytes(resolve(root, relpath, must_exist=True, kind="file"), limit)
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise Stop("not UTF-8 text: %s" % relpath)


def read_json(root, relpath, limit=5_000_000):
    try:
        return json.loads(read_text(root, relpath, limit))
    except ValueError:
        raise Stop("not valid JSON: %s" % relpath)


def write_atomic(root, relpath, data):
    """Write bytes inside the work folder: exclusive temporary file, then rename into place."""
    target = resolve(root, relpath)
    if os.path.isdir(target):
        raise Stop("target is a folder: %s" % relpath)
    parent = os.path.dirname(target)
    os.makedirs(parent, exist_ok=True)
    resolve(root, rel(root, parent), kind="dir")  # re-check after creating folders
    fd, tmp = tempfile.mkstemp(dir=parent, prefix=".tmp-", suffix=".part")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, target)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    resolve(root, relpath, must_exist=True)
    return target


def write_json(root, relpath, obj):
    return write_atomic(root, relpath, (json.dumps(obj, indent=2) + "\n").encode("utf-8"))


def temp_in(root, relpath, suffix):
    """A fresh exclusive temporary file in the target's folder (for a tool to overwrite)."""
    target = resolve(root, relpath)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(target), prefix=".tmp-", suffix=suffix)
    os.close(fd)
    return target, tmp


# ---- tools -------------------------------------------------------------------------------------

def need_tools(*names):
    for n in names:
        if not shutil.which(n):
            raise Stop("%s is not installed" % n, 3)


def run(args, timeout=900):
    """Run a program from an argument list. No shell."""
    try:
        return subprocess.run(args, capture_output=True, text=True, errors="replace",
                              timeout=timeout, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise Stop("%s timed out" % os.path.basename(args[0]), 1)


def probe(path):
    """ffprobe facts about a local media file: duration, size, frame rate, stream kinds."""
    p = run(["ffprobe", "-v", "error", "-protocol_whitelist", "file", "-show_entries",
             "format=duration:stream=codec_type,width,height,avg_frame_rate", "-of", "json", "-i", path], 120)
    if p.returncode != 0:
        raise Stop("could not read the media file", 1)
    try:
        info = json.loads(p.stdout)
        streams = info.get("streams") or []
        video = next((s for s in streams if s.get("codec_type") == "video"), None)
        audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
        duration = float(info["format"]["duration"])
    except (ValueError, KeyError, TypeError):
        raise Stop("could not read the media file", 1)
    if not math.isfinite(duration) or duration <= 0:
        raise Stop("the media file has no usable length", 1)
    out = {"duration": duration, "has_audio": audio is not None, "has_video": video is not None,
           "width": 0, "height": 0, "fps": 0.0}
    if video:
        out["width"], out["height"] = int(video.get("width") or 0), int(video.get("height") or 0)
        try:
            n, d = str(video.get("avg_frame_rate", "0/1")).split("/")
            out["fps"] = float(n) / float(d) if float(d) else 0.0
        except ValueError:
            out["fps"] = 0.0
    return out


# ---- numbers -----------------------------------------------------------------------------------

def number(value, name, lo, hi):
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise Stop("%s must be a number" % name)
    if not math.isfinite(v) or not lo <= v <= hi:
        raise Stop("%s must be from %s to %s" % (name, lo, hi))
    return v


def hex6(value, name):
    v = str(value).lstrip("#")
    if not re.fullmatch(r"[0-9A-Fa-f]{6}", v):
        raise Stop("%s must be six hex digits" % name)
    return v.upper()


# ---- words -------------------------------------------------------------------------------------

HYPHENS = "-\u2010\u2011\u2012\u2013\u2014\u2015\u2212\ufe63\uff0d"


def _clean(text):
    """NFKD, then drop combining marks and every format character (zero-width, joiners, soft hyphen)."""
    t = unicodedata.normalize("NFKD", str(text))
    return "".join(c for c in t if unicodedata.category(c) not in ("Mn", "Me", "Cf")).casefold()


def normalize(text, joined=False):
    """Lower-case words. Apostrophes are ignored.

    Punctuation between letters (a hyphen, a dot, a slash: 'well-known', 'peo.ple') splits the word;
    with joined=True it is removed instead ('wellknown', 'people'). The overlap check runs both, so
    punctuation inside a word cannot hide a run."""
    t = re.sub(r"['\u2018\u2019\u02bc`]", "", _clean(text))
    if joined:
        t = re.sub(r"(?<=[^\W_])(?:[^\w\s]|_)+(?=[^\W_])", "", t)
    return "".join(c if c.isalnum() else " " for c in t).split()


def variants(text):
    """Both word lists (hyphen splits, hyphen joins) for a text."""
    return [normalize(text), normalize(text, joined=True)]


def require_latin(text, what="the script"):
    """Refuse any letter that is not plain a to z once accents are removed, and odd invisible or
    control characters. Look-alike letters (Cyrillic, Greek, small capitals, dotless i, and the
    like) would otherwise slip past a word comparison. The message names the character."""
    for c in str(text):
        cat = unicodedata.category(c)
        if (cat == "Cc" and c not in "\n\r\t") or cat in ("Co", "Cn", "Cs") or c == "\u2800":
            raise Stop("%s holds a control or unassigned character (U+%04X)" % (what, ord(c)))
    for c in str(text):
        for d in _clean(c):
            if d.isalpha() and not ("a" <= d <= "z"):
                raise Stop("%s holds a letter outside the Latin script a to z: %s (U+%04X, %s); "
                           "write it in plain letters" % (what, c, ord(c), unicodedata.name(c, "unnamed")))


def strings_in(obj, depth=0):
    """Every string value in a JSON structure, in order (keys are not included)."""
    if depth > 20:
        return []
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        return [s for v in obj.values() for s in strings_in(v, depth + 1)]
    if isinstance(obj, list):
        return [s for v in obj for s in strings_in(v, depth + 1)]
    return []


def file_text(root, relpath):
    """Text of a file for comparing words: JSON gives its string values, anything else its text."""
    text = read_text(root, relpath)
    if relpath.lower().endswith(".json"):
        try:
            return " ".join(strings_in(json.loads(text)))
        except ValueError:
            raise Stop("not valid JSON: %s" % relpath)
    return text


def words_of_file(root, relpath):
    return normalize(file_text(root, relpath))


def timed_words(root, relpath):
    """The b-audio words file: a list of {text, start, end}. Checked and returned."""
    data = read_json(root, relpath)
    if not isinstance(data, list):
        raise Stop("%s is not a words list" % relpath)
    out, last = [], 0.0
    for w in data:
        try:
            t, s, e = str(w["text"]), float(w["start"]), float(w["end"])
        except (KeyError, TypeError, ValueError):
            raise Stop("%s has a bad word entry" % relpath)
        if not (math.isfinite(s) and math.isfinite(e)) or s < 0 or e < s or s < last - 1e-6:
            raise Stop("%s has word times out of order" % relpath)
        last = s
        out.append({"text": t, "start": s, "end": e})
    return out


def scan_text(path, limit=2_000_000):
    """All the text a file holds, for comparing words: its decoded text, plus the string values when it
    parses as JSON. Raises Stop or ValueError when the file is too large or does not decode as UTF-8."""
    text = read_bytes(path, limit).decode("utf-8")
    if "\0" in text:
        raise ValueError("binary")
    try:
        text += " " + " ".join(strings_in(json.loads(text)))
    except ValueError:
        pass
    return text


VIDEO_EXTENSIONS = (".mp4", ".mov", ".m4v", ".webm")


def single_video(root, folder_rel):
    """The one video file in an input folder (inside the work folder), as an absolute path."""
    folder = resolve(root, folder_rel, must_exist=True, kind="dir")
    found = sorted(n for n in os.listdir(folder) if n.lower().endswith(VIDEO_EXTENSIONS))
    if len(found) != 1:
        raise Stop("put exactly one reference video in %s (found %d)" % (folder_rel, len(found)))
    return resolve(root, rel(root, os.path.join(folder, found[0])), must_exist=True, kind="file")
