# Transcribe

Produce the word-timed transcript of the sealed bed, and when b-roll was supplied a short list of
what each clip says. The words feed the beat planner, the card copy and the captions. Speech
recognition runs on this machine through `b-audio`; no audio is uploaded.

## You receive

- `prior/voice_track.mp4`: the sealed bed. Read only.
- `inputs/broll/`: zero or more clips (folder absent means none). Only their speech, if any, is read.
- `brief.json`: nothing used here. The speech model file and the tool version are **not** in the
  order: they come from your own machine setup (below).

## You must produce

- `saves/transcripts.json`:

```json
{ "words": [ {"text": "...", "start": 0.00, "end": 0.42} ],
  "broll_cues": [ {"clip": "inputs/broll/<file>", "duration": 12.3, "label": "<file name without extension>",
                   "cues": [ {"start": 0.0, "end": 0.5, "text": "..."} ]} ] }
```

`words` is one entry per spoken word, in time order. `broll_cues` is `[]` when there is no b-roll.

## How

```bash
mkdir -p work saves
RECIPE_DIR=${RECIPE_DIR:?set RECIPE_DIR to the absolute path of this recipe folder}
case "$RECIPE_DIR" in /*) ;; *) echo "RECIPE_DIR must be an absolute path"; exit 1 ;; esac
BLOCKS_DIR="$(cd "$RECIPE_DIR/../../blocks" && pwd)" || exit 1
# From YOUR machine's setup, never from the order or the brief:
#   STT_MODEL   the whisper.cpp model file you installed (for example models/ggml-base.en.bin)
#   STT_VERSION the whisper-cli version your package manager reports (whisper-cli cannot say it itself)
STT_MODEL=${STT_MODEL:?set STT_MODEL to the speech model file on this machine}
STT_VERSION=${STT_VERSION:?set STT_VERSION to the installed whisper-cli version}
```

### 1. Transcribe the bed

One tool, named by you: `whisper-cpp` (program `whisper-cli`). The model file and the version are
facts of the machine this bot runs on, so you set `STT_MODEL` and `STT_VERSION` yourself; an order
never supplies them, and `b-audio` is never pointed at a path the order names. If `whisper-cli` or the model is
missing, `transcribe.py` exits 3: tell the person what to install and stop; do not try another tool
and do not download a model unless the person said yes (then add `--allow-download --model-name
<name> --model-sha256 <checksum>`; see `b-audio`). A model file outside the work folder needs
`--allow-model-dir <its folder>` (a folder you chose, not one from the order). The default language is English; for another language use a
multilingual model (not `.en.bin`) and add `--language <code>`.

```bash
python3 "$BLOCKS_DIR/b-audio/scripts/transcribe.py" prior/voice_track.mp4 --out work/words.json \
  --tool whisper-cpp --tool-version "$STT_VERSION" --model "$STT_MODEL"
```

`work/words.json` is `[{"text","start","end"}]` in seconds; `work/words.meta.json` records the tool,
version and model checksum. Word times are good to about 0.1 to 0.2 s. An empty list means no speech
was found: stop and report it.

Names and unusual words are often misheard. If you know some (the brand name, a product), write a short list of
them, never the whole script, one per line, to `work/hint.txt` and add `--hint-file work/hint.txt` to the command:
it biases the recogniser and does not guarantee spelling. Read the words. If one is plainly misheard, correct its `text` in `work/words.json`; never change a
time. The text is burned into the captions.

### 2. B-roll cues (only when `inputs/broll/` exists)

Cues only help you decide which clip goes with which words. For each clip that has an audio track
and speech worth matching, run the same transcription into `work/cues/<name without extension>.json`;
skip silent clips. Then list the clips:

```bash
if [ -d inputs/broll ]; then
  mkdir -p work/cues
  for f in inputs/broll/*; do
    ffprobe -v error -protocol_whitelist file -select_streams a:0 -show_entries stream=codec_type -of csv=p=0 "$f" | grep -q audio || continue
    python3 "$BLOCKS_DIR/b-audio/scripts/transcribe.py" "$f" --out "work/cues/$(basename "${f%.*}").json" \
      --tool whisper-cpp --tool-version "$STT_VERSION" --model "$STT_MODEL" || exit 1
  done
fi
python3 "$RECIPE_DIR/scripts/broll_cues.py"      # "0 cue words" is normal for a clip with no speech
```

`broll_cues.py` reads each clip's length, labels it with its file name and attaches the cues; with no
folder it writes `[]`. A file that is not a readable video stops it, named.

### 3. Write the save and check it

```bash
python3 - <<'PY'
import json
words = json.load(open('work/words.json'))
cues = json.load(open('work/broll_cues.json'))
json.dump({"words": words, "broll_cues": cues}, open('saves/transcripts.json', 'w'), indent=1)
PY
bash "$RECIPE_DIR/checks/words_found.sh" .
```

`words_found.sh` fails when an entry is a sentence instead of a word (more than 3 words in an
entry, or under one entry per spoken second), so a recogniser that gave sentence segments cannot
pass. The end of the last word should be within about 3 s of the bed's length; if not, say so.

## If you cannot proceed

This step has no `canAsk`. Never write `needs_input.json`. A missing tool or model, or zero words,
is a failure: exit non-zero with one plain line.

## Checks (declared in `manifest.json`)

- `words_found`: `saves/transcripts.json` parses, `words` is a non-empty list of `{text,start,end}`
  with non-decreasing starts, one spoken word per entry (`checks/words_found.sh`).
