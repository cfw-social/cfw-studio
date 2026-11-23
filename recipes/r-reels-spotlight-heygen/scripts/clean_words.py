#!/usr/bin/env python3
"""usage: python3 scripts/clean_words.py WORDS.json

Strip non-word entries, canonicalise the key (`word` -> `text`) and refuse sentence-like entries.
Rewrites WORDS.json in place.
"""
import json
import re
import sys

path = sys.argv[1]
words = json.load(open(path, encoding="utf-8"))
out = []
for w in words:
    t = (w.get("text") or w.get("word") or "").strip()
    if not t or t in ("♪", "[Music]", "(music)") or not re.search(r"\w", t):
        continue
    out.append({"text": t, "start": float(w["start"]), "end": float(w["end"])})
if not out:
    sys.exit("clean_words: no words transcribed")
# One entry per spoken word. Whisper sentence segments (no word timestamps) must not pass here.
# A word entry holds at most 3 words, and words come at least 1 per spoken second
# (a real reel: about 3.5; sentence segments: about 0.3).
spoken = sum(max(w["end"] - w["start"], 0.0) for w in out)
longest = max(len(w["text"].split()) for w in out)
rate = len(out) / spoken if spoken > 0 else float("inf")
if not (longest <= 3 and rate >= 1.0):
    sys.exit("clean_words: transcript entries look like sentences, not words (%d entries, %.2f per spoken second, longest "
             "%d words): transcribe again with word timestamps" % (len(out), rate, longest))
json.dump(out, open(path, "w", encoding="utf-8"))
print(f"[spotlight] {len(out)} words, {out[0]['start']:.2f}s -> {out[-1]['end']:.2f}s")
