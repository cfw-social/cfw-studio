#!/usr/bin/env python3
"""List the b-roll clips for the beat planner: path, length, label and, when known, what is said.

  python3 broll_cues.py [--inputs inputs/broll] [--cues-dir work/cues] [--out work/broll_cues.json]

For each file in the inputs folder (sorted by name; names starting with a dot are skipped) it
reads the length with ffprobe. If work/cues/<label>.json exists (the words file b-audio wrote
for that clip) its words become the clip's cues. <label> is the file name without its
extension. A clip with no cues file, or with no speech, has cues: [] (that is fine; cues only
help the bot decide which clip fits which words). The output is the list b-broll-sync reads:

  [ {"clip": "inputs/broll/demo.mp4", "duration": 12.4, "label": "demo", "cues": [{"start","end","text"}]} ]

Prints one line per clip. A file ffprobe cannot read as video stops the run (exit 1), so a
broken clip is named, not skipped. No folder: writes [] (exit 0). Exit 2 for bad arguments.
"""
import argparse
import json
import os
import subprocess
import sys


def probe(path):
    p = subprocess.run(["ffprobe", "-v", "error", "-protocol_whitelist", "file", "-select_streams", "v:0",
                        "-show_entries", "stream=codec_type:format=duration", "-of", "json", path],
                       capture_output=True, text=True)
    try:
        data = json.loads(p.stdout or "{}")
        if not data.get("streams"):
            return None
        return round(float(data["format"]["duration"]), 3)
    except (ValueError, KeyError, TypeError):
        return None


def read_cues(path):
    try:
        with open(path, encoding="utf-8") as fh:
            words = json.load(fh)
        return [{"start": float(w["start"]), "end": float(w["end"]), "text": str(w["text"])} for w in words]
    except (OSError, ValueError, KeyError, TypeError):
        raise SystemExit("cues file %s is not a b-audio words list" % path)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--inputs", default="inputs/broll")
    p.add_argument("--cues-dir", default="work/cues")
    p.add_argument("--out", default="work/broll_cues.json")
    a = p.parse_args(argv)
    clips = []
    try:
        names = sorted(n for n in os.listdir(a.inputs) if not n.startswith(".")) if os.path.isdir(a.inputs) else []
        for name in names:
            path = os.path.join(a.inputs, name)
            if not os.path.isfile(path) or os.path.islink(path):
                continue
            duration = probe(path)
            if duration is None:
                sys.stderr.write("broll_cues.py: FAILED - %s is not a video ffprobe can read\n" % path)
                return 1
            label = os.path.splitext(name)[0]
            cues_path = os.path.join(a.cues_dir, label + ".json")
            cues = read_cues(cues_path) if os.path.isfile(cues_path) else []
            clips.append({"clip": path.replace(os.sep, "/"), "duration": duration, "label": label, "cues": cues})
    except SystemExit as e:
        sys.stderr.write("broll_cues.py: FAILED - %s\n" % e)
        return 1
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(clips, fh, indent=1)
    for c in clips:
        print("%s  %.1fs  %d cue words" % (c["clip"], c["duration"], len(c["cues"])))
    if not clips:
        print("no b-roll clips")
    return 0


if __name__ == "__main__":
    sys.exit(main())
