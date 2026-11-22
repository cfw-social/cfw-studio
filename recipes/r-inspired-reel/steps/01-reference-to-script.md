# Read the reference's format and write a new script

Take the reference file the person supplied, transcribe it, measure its format, write a fresh script that has the same shape, check the script, then delete everything made from the reference. Read `_shared.md` first.

This step runs in one work folder from start to finish because the transcript must exist for two checks and must not be saved. The logical steps are numbered 1 to 4 below.

## You receive

- `inputs/reference_reel/`: exactly one video file (`.mp4 .mov .m4v .webm`), 15 to 90 s, with sound.
- `inputs/topic/topic.md`: what the new reel is about. `inputs/cta/cta.md`: the closing line, when given.
- `brief.json`: the brand's name and voice.
- Environment set by the bot: `WHISPER_VERSION` (the installed whisper.cpp version, read from the package manager) and `WHISPER_MODEL` (a model file the person named, inside the work folder or in `WHISPER_MODEL_DIR`). Optional: `WHISPER_BIN` (explicit path to `whisper-cli`). No speech model is downloaded unless the person says yes (see `b-audio`).

## You must produce

- `saves/format.json`: numbers and labels only. See "What format.json holds" below.
- `saves/script.md`: the new script, plain spoken text, one paragraph per beat.
- `saves/overlap.json`: `{check, limit, script_words, reference_words, longest_shared_run, verdict, runs}`. Numbers only.
- `saves/cleanup.json`: `{check, verdict, items_removed}`.

## How

```bash
set -eu   # every command in this step stops the step if it fails
mkdir -p ref work saves
case "${RECIPE_DIR:-}:${BLOCKS_DIR:-}" in /*:/*) ;; *) echo "RECIPE_DIR and BLOCKS_DIR must be set to absolute paths"; exit 1 ;; esac
RS="$RECIPE_DIR/scripts"
[ -f "$RS/measure_format.py" ] || { echo "the recipe scripts are missing under RECIPE_DIR"; exit 1; }
[ -f "$BLOCKS_DIR/b-audio/scripts/transcribe.py" ] || { echo "b-audio is missing under BLOCKS_DIR"; exit 1; }
command -v ffmpeg >/dev/null 2>&1 && command -v ffprobe >/dev/null 2>&1 || { echo "ffmpeg and ffprobe are needed"; exit 1; }
```

### 1. Take in the reference and transcribe it

`prepare_reference.py` checks the file (a picture, a sound track, 15 to 90 s) and extracts `ref/audio.wav`. It never changes the file. `b-audio` then writes `ref/words.json` (words with start and end times) and `ref/words.meta.json`, which holds the full text and is deleted with the rest. Exit 3 from `b-audio` means the tool or model is missing: tell the person what to install and stop. Do not try another tool. Keep the model file outside the work folder (`WHISPER_MODEL_DIR`): a model inside the work folder is a large binary file, and the clean-up scan in sub-step 4 fails on any file it cannot read as text.

```bash
python3 "$RS/prepare_reference.py" --input-dir inputs/reference_reel --outdir ref
ASR=(--tool whisper-cpp --tool-version "${WHISPER_VERSION:?set WHISPER_VERSION}" --model "${WHISPER_MODEL:?set WHISPER_MODEL}")
[ -z "${WHISPER_BIN:-}" ] || ASR+=(--tool-bin "$WHISPER_BIN")
[ -z "${WHISPER_MODEL_DIR:-}" ] || ASR+=(--allow-model-dir "$WHISPER_MODEL_DIR")
python3 "$BLOCKS_DIR/b-audio/scripts/transcribe.py" ref/audio.wav --out ref/words.json "${ASR[@]}"
```

An empty transcript or fewer than 15 words means the reel has no usable speech. Ask for another reference (`needs_input.json` for `reference_reel`).

### 2. Measure the format

```bash
python3 "$RS/measure_format.py" --input-dir inputs/reference_reel --words ref/words.json --out saves/format.json
```

It runs `ffprobe` for the length, ffmpeg scene detection for the cuts, and reads the word timings for pace and beats. The hook type (`question`, `claim`, `stat`, `story`) is a first guess from simple rules. If the person told you the type, add `--hook-type <type>`. Do not open the transcript to decide it.

#### What format.json holds

Numbers and labels, nothing else: `duration_s`, `width`, `height`, `orientation`, `fps`, `speech_span_s`, `first_word_at_s`, `word_count`, `wpm`, `speech_share`, `cut_count`, `cuts_per_10s`, `mean_shot_s`, `scene_threshold`, `cut_times_s` (a list of seconds), `hook` (`type`, `type_source`, `seconds`), `beats` (a list of `label` = `hook`, `point_N` or `cta`, with `start_s`, `end_s`, `share` of the speaking time, `words`) and `structure` (for example `hook, 3 points, cta`). Any other key, or any text value outside the fixed labels, is refused.

### 3. Write the new script, then check it

Write the script yourself, from `format.json`, the topic and the brand voice. Do not open `ref/words.json`.

- One paragraph per beat, in order, blank line between paragraphs: first the hook, then each point, then the call to action. The number of paragraphs equals the number of beats.
- Total words within 10 percent of `word_count`. Each paragraph holds about the share of the words that its beat holds of the time (within 12 points).
- The hook has the type in `hook.type` and takes about `hook.seconds` seconds to say. A `cta` input, when given, is the last paragraph's closing line.
- Plain spoken text: no brackets, tags, headings or bullet marks. The brand's own topic, in the brand's own voice, with the brand's own examples. Write numbers as you want them spoken.
- Write it to `work/script.txt` with your file-writing tool.

```bash
python3 "$RS/check_script_shape.py" --format saves/format.json --script work/script.txt
python3 "$RS/check_overlap.py" --script work/script.txt --reference ref/words.json --out saves/overlap.json
```

`check_script_shape.py` lists what to fix (paragraph count, word count, a beat that is too long or short). `check_overlap.py` exits 1 and prints the position of every run of six or more shared words, never the words. Rewrite those sentences in your own words and run both again. After three rewrites that still fail, stop and tell the person; do not weaken the check.

### 4. Delete the reference, then check it is gone

```bash
cp work/script.txt saves/script.md
python3 "$RS/cleanup_reference.py" --receipt saves/cleanup.json
python3 "$RS/cleanup_reference.py" --check-only
```

The first command remembers every run of six reference words, looks for them in every file that decodes as text, whatever its extension, in every folder outside `inputs/` and `ref/` (so in `saves/` and `work/`; a file over 2 MB is skipped and counted), deletes the whole `ref/` folder, then checks it is gone and that `format.json` still passes its fixed-keys check. It exits 1 if a run of reference words turns up in a file, if anything is left behind, or if `format.json` holds anything but numbers and labels. The second command repeats the check without deleting.

The reference video the person supplied stays in `inputs/`. It is theirs: this step never changes, moves or reuses it.

Done when `saves/format.json`, `saves/script.md`, `saves/overlap.json` and `saves/cleanup.json` exist and both cleanup commands printed PASS.
