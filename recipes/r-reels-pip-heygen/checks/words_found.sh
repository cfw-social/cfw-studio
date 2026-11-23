#!/usr/bin/env bash
# words_found: transcribe check. Run it as `bash checks/words_found.sh <step workdir>`:
# exit 0 = pass, anything else = fail, and the output is the reason.
# saves/transcripts.json parses and `words` is a non-empty array of {text,start,end} with number
# times and non-decreasing starts. Each entry is ONE spoken word: an entry of more than 3 words, or
# under 1 entry per spoken second (the entries' lengths summed), is a Whisper sentence segment,
# which this check refuses. A real reel has about 3.5 entries per spoken second; segments about 0.3.
set -u
WORK="${1:-.}"
exec python3 - "$WORK/saves/transcripts.json" <<'PY'
import json, sys
path = sys.argv[1]
try:
    words = json.load(open(path, encoding="utf-8"))["words"]
except (OSError, ValueError, KeyError, TypeError) as exc:
    sys.exit("saves/transcripts.json is missing or has no words array: %s" % exc)
if not isinstance(words, list) or not words:
    sys.exit("saves/transcripts.json: words is empty")
for i, w in enumerate(words):
    ok = isinstance(w, dict) and isinstance(w.get("text"), str) and w["text"].strip()
    ok = ok and all(isinstance(w.get(k), (int, float)) and not isinstance(w.get(k), bool) for k in ("start", "end"))
    if not ok:
        sys.exit("words[%d] is not {text, start, end}: %r" % (i, w))
starts = [w["start"] for w in words]
if any(b < a for a, b in zip(starts, starts[1:])):
    sys.exit("word starts go backwards")
spoken = sum(max(w["end"] - w["start"], 0.0) for w in words)
longest = max(len(w["text"].split()) for w in words)
rate = len(words) / spoken if spoken > 0 else float("inf")
if longest > 3 or rate < 1.0:
    sys.exit("transcript entries look like sentences, not words (%d entries, %.2f per spoken second, "
             "longest %d words): transcribe again with word timestamps" % (len(words), rate, longest))
print("words_found: %d words, %.2f per spoken second" % (len(words), rate))
PY
