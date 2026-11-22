#!/usr/bin/env python3
"""Delete everything made from the reference, then check that it is gone.

  python3 cleanup_reference.py [--ref-dir ref] [--format saves/format.json] [--receipt saves/cleanup.json]   delete, then check
  python3 cleanup_reference.py --check-only [--ref-dir ref] [--format saves/format.json]   check only

The reference transcript, its meta file and the extracted reference audio all live in the ref
folder. Before deleting, this script remembers every run of six reference words and looks for them
in every file elsewhere in the work folder that decodes as text, whatever its extension (the
person's own inputs folder and the ref folder are skipped). A file it cannot read as UTF-8 text
of 2 MB or less (UTF-16, compressed, binary, too big, or a link) and that is not a wav, mp4, mov,
png or jpg file with the right header makes the scan FAIL, with the file named: nothing is passed unseen. After deleting it checks that the
ref folder is gone or empty, and that format.json still passes its fixed-keys check.
Exit 0 clean, 1 a problem (a file left behind, a sentence found, format.json not clean), 2 bad input.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from format_schema import validate_format  # noqa: E402
from rs_common import Stop, main, read_json, rel, resolve, scan_text, variants, work_root, write_json  # noqa: E402

RUN = 6
REF_NAME = "ref"
MAX_FILE = 2_000_000


def run_sets(text):
    """Every 6-word run of a text, in both hyphen readings."""
    out = set()
    for toks in variants(text):
        out.update(tuple(toks[i:i + RUN]) for i in range(len(toks) - RUN + 1))
    return out


def reference_runs(refdir):
    """Set of 6-word runs from every file in the ref folder that decodes as text (kept in memory only)."""
    runs = set()
    for dirpath, _dirs, files in os.walk(refdir):
        for name in files:
            path = os.path.join(dirpath, name)
            if os.path.islink(path):
                continue
            try:
                runs |= run_sets(scan_text(path, MAX_FILE))
            except (Stop, ValueError):
                continue
    return runs


MEDIA_MAGIC = {".wav": lambda h: h[:4] == b"RIFF", ".mp4": lambda h: h[4:8] == b"ftyp",
               ".mov": lambda h: h[4:8] in (b"ftyp", b"moov", b"mdat", b"wide"),
               ".png": lambda h: h[:4] == b"\x89PNG", ".jpg": lambda h: h[:3] == b"\xff\xd8\xff"}


def known_media(path):
    """True for a file of a media type this recipe itself makes, by extension and file header."""
    check = MEDIA_MAGIC.get(os.path.splitext(path)[1].lower())
    try:
        with open(path, "rb") as fh:
            return bool(check and check(fh.read(16)))
    except OSError:
        return False


def leaks(root, runs):
    """(files holding a reference run, files the scan could not see, as (path, reason)).

    Every file outside the person's inputs folder and the ref folder is read as text, whatever its
    extension. A file that cannot be read that way (too big, not UTF-8 such as UTF-16 or a compressed
    file, binary, or a link) and is not a known media type is NOT passed over: it is listed."""
    found, unseen = [], []
    for dirpath, dirs, files in os.walk(root):
        if os.path.abspath(dirpath) == root:
            dirs[:] = [d for d in dirs if d not in ("inputs", REF_NAME)]
        for d in list(dirs):
            if os.path.islink(os.path.join(dirpath, d)):
                dirs.remove(d)
                unseen.append((rel(root, os.path.join(dirpath, d)), "a link to a folder, not followed"))
        for name in files:
            path = os.path.join(dirpath, name)
            if os.path.islink(path):
                unseen.append((rel(root, path), "a link, not followed"))
                continue
            if known_media(path):
                continue
            if os.path.getsize(path) > MAX_FILE:
                unseen.append((rel(root, path), "over %d MB" % (MAX_FILE // 1_000_000)))
                continue
            try:
                text = scan_text(path, MAX_FILE)
            except (Stop, ValueError):
                unseen.append((rel(root, path), "not readable as UTF-8 text"))
                continue
            if run_sets(text) & runs:
                found.append(rel(root, path))
    return found, unseen


def delete_tree(top):
    removed = 0
    for dirpath, dirs, files in os.walk(top, topdown=False):
        for name in files:
            os.remove(os.path.join(dirpath, name))
            removed += 1
        for name in dirs:
            p = os.path.join(dirpath, name)
            if os.path.islink(p):
                os.remove(p)  # the link only, never what it points at
                removed += 1
            else:
                os.rmdir(p)
    os.rmdir(top)
    return removed


def left_behind(refdir):
    if not os.path.lexists(refdir):
        return []
    if os.path.islink(refdir) or not os.path.isdir(refdir):
        return [refdir]
    return sorted(os.path.join(d, n) for d, ds, fs in os.walk(refdir) for n in ds + fs)  # an empty folder is fine


def run(argv):
    ap = argparse.ArgumentParser(prog="cleanup_reference.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--ref-dir", default=REF_NAME, help="only the folder named ref, directly inside the work folder")
    ap.add_argument("--format", default="saves/format.json")
    ap.add_argument("--receipt", help="on a pass, write a small numbers-only receipt here")
    ap.add_argument("--check-only", action="store_true")
    ap.add_argument("--workdir")
    a = ap.parse_args(argv)
    root = work_root(a.workdir)
    if a.ref_dir.strip("/\\") != REF_NAME:
        raise Stop("--ref-dir must be the folder named %s, directly inside the work folder" % REF_NAME)
    refdir = resolve(root, REF_NAME)
    if refdir == root or os.path.dirname(refdir) != root:
        raise Stop("refusing to touch anything but the ref folder")
    problems, removed = [], 0
    if not a.check_only and os.path.lexists(refdir):
        if not os.path.isdir(refdir):
            raise Stop("the ref path is not a folder")
        leaked, unseen = leaks(root, reference_runs(refdir))
        problems += ["a run of reference words is in %s" % f for f in leaked]
        problems += ["not scanned: %s (%s); delete it, move it outside the work folder, or fix it" % u for u in unseen]
        try:
            removed = delete_tree(refdir)
        except OSError:
            problems.append("could not delete everything in the ref folder")
    problems += ["still there: %s" % rel(root, p) for p in left_behind(refdir)]
    fmt = resolve(root, a.format)
    if os.path.exists(fmt):
        try:
            validate_format(read_json(root, a.format))
        except Stop as e:
            problems.append(e.msg)
    label = "CLEANUP CHECK" if a.check_only else "CLEANUP"
    if problems:
        print("%s: FAIL" % label)
        for p in problems:
            print("  " + p)
        return 1
    if a.receipt and not a.check_only:
        write_json(root, a.receipt, {"check": "cleanup", "verdict": "PASS", "items_removed": removed})
    print("%s: PASS (%s)" % (label, "nothing left of the reference" if a.check_only else "%d items removed" % removed))
    return 0


if __name__ == "__main__":
    main(run)
