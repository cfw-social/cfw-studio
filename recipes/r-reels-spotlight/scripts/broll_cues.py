#!/usr/bin/env python3
"""usage (from the step work folder):
  python3 scripts/broll_cues.py              write work/broll_cues.json
  python3 scripts/broll_cues.py --list-audio print the clips that have an audio stream, one per line

Builds the b-roll cues file that b-broll-sync reads: one entry per clip in inputs/broll/ with its
duration and its speech cues. Cues come from work/broll_words/<clip file name>.json when that file
exists: the words.json that b-audio's transcribe.py wrote for that clip (see step 02). A clip with
no such file has `cues: []`; the clip is still usable, the bot just matches it by looking at it.

Nothing here transcribes: this script starts only ffprobe, with an argument list.
"""
import glob
import json
import os
import re
import subprocess
import sys

CLIP_DIR = "inputs/broll"
WORDS_DIR = "work/broll_words"


def probe(args, clip):
    return subprocess.run(["ffprobe", "-v", "error", "-protocol_whitelist", "file", *args, "-i", clip],
                          capture_output=True, text=True)


def duration(clip):
    try:
        return float(probe(["-show_entries", "format=duration", "-of", "csv=p=0"], clip).stdout.strip())
    except ValueError:
        return 0.0


def has_audio(clip):
    r = probe(["-select_streams", "a", "-show_entries", "stream=codec_type", "-of", "csv=p=0"], clip)
    return r.returncode == 0 and "audio" in r.stdout


def clips():
    out = []
    for clip in sorted(glob.glob(os.path.join(CLIP_DIR, "*"))):
        if re.search(r"[\x00-\x1f\x7f]", clip):
            print("[spotlight] broll_cues: skipped a clip whose name holds a control character", file=sys.stderr)
            continue
        if os.path.isfile(clip) and not os.path.islink(clip) and duration(clip) > 0:
            out.append(clip)
        else:
            print("[spotlight] broll_cues: skipped %s (not a plain readable video)" % clip, file=sys.stderr)
    return out


def cues_for(clip):
    path = os.path.join(WORDS_DIR, os.path.basename(clip) + ".json")
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as fh:
        words = json.load(fh)
    return [{"start": float(w["start"]), "end": float(w["end"]), "text": str(w["text"])} for w in words]


def main(argv):
    if argv[1:] == ["--list-audio"]:
        for clip in clips():
            if has_audio(clip):
                print(clip)
        return 0
    if argv[1:]:
        sys.exit(__doc__)
    result = [{"clip": c, "duration": round(duration(c), 3), "cues": cues_for(c)} for c in clips()]
    os.makedirs("work", exist_ok=True)
    with open("work/broll_cues.json", "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)
    print("[spotlight] broll_cues: %d clips, %d with speech cues" % (len(result), sum(1 for r in result if r["cues"])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
