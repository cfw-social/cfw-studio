# Captions, sound, quality gate and final check

Add word-timed captions, a light grade and sound effects with `b-reel-premium`, render the captions with `b-hyperframes`, run the `b-qa-gate` checks, answer the look questions, and confirm nothing of the reference remains. Read `_shared.md` first.

## You receive

- `prior/base_reel.mp4`, `prior/format.json`, `prior/script.md`.
- `brief.json`: the brand's palette (an accent colour and a light foreground colour, six hex digits each) and, when the brand has one, a font file already inside `inputs/` (a third-party font: name its licence in your report; none is shipped here).
- Environment set by the bot: `WHISPER_VERSION`, `WHISPER_MODEL` (and optionally `WHISPER_BIN`, `WHISPER_MODEL_DIR`), as in step 1.

## You must produce

- `saves/final.mp4`: the finished reel, 1080x1920, 30 fps.
- `saves/qa_report.json`: the final scorecard from `b-qa-gate`, after the looks are answered.

## How

```bash
set -eu   # every command in this step stops the step if it fails
mkdir -p premium work saves
case "${RECIPE_DIR:-}:${BLOCKS_DIR:-}" in /*:/*) ;; *) echo "RECIPE_DIR and BLOCKS_DIR must be set to absolute paths"; exit 1 ;; esac
RS="$RECIPE_DIR/scripts"
BP="$BLOCKS_DIR/b-reel-premium/scripts"
BH="$BLOCKS_DIR/b-hyperframes/scripts"
QG="$BLOCKS_DIR/b-qa-gate/check.py"
for f in "$RS/make_spec.py" "$BP/check_plan.py" "$BH/hf_render.py" "$QG" "$BLOCKS_DIR/b-audio/scripts/transcribe.py"; do
  [ -f "$f" ] || { echo "missing under the recipe or blocks folder: $f"; exit 1; }
done
for f in prior/base_reel.mp4 prior/format.json prior/script.md; do
  [ -s "$f" ] || { echo "$f is missing or empty"; exit 1; }
done
REEL=prior/base_reel.mp4
```

### 1. Transcribe the new narration

The caption timing comes from the new reel's own words, never from the reference. The script's longer words are passed to `b-audio` as a hint (`--hint-file`) so names and product words are spelled right; the shape check writes them to `work/hint.txt` as a short list (at most 30 words). Keep it a word list: tried on a real model, a hint made of whole sentences stopped whisper.cpp after four words. A hint is used only here, never for the reference. It biases the tool and does not guarantee spelling.

```bash
ASR=(--tool whisper-cpp --tool-version "${WHISPER_VERSION:?set WHISPER_VERSION}" --model "${WHISPER_MODEL:?set WHISPER_MODEL}")
[ -z "${WHISPER_BIN:-}" ] || ASR+=(--tool-bin "$WHISPER_BIN")
[ -z "${WHISPER_MODEL_DIR:-}" ] || ASR+=(--allow-model-dir "$WHISPER_MODEL_DIR")
python3 "$RS/check_script_shape.py" --format prior/format.json --script prior/script.md --hint-out work/hint.txt
python3 "$BLOCKS_DIR/b-audio/scripts/transcribe.py" "$REEL" --out premium/words.json --hint-file work/hint.txt "${ASR[@]}"
```

### 2. Write the caption plan, then check it

Write `premium/plan.json` yourself from `premium/words.json`, following the plan format in `$BLOCKS_DIR/b-reel-premium/README.md`. No other model, no nested agent. Use `prior/format.json` to set the pace:

- Caption groups of 2 to 4 words (up to 6 to keep a phrase whole), in time order, words as spoken, the caption style shows them in upper case. About one group per `mean_shot_s` seconds of the reference is a good rhythm; use shorter groups when `cuts_per_10s` is high.
- `sfx`: 4 to 10 cues, none in the first second. Put a cue at the start of each beat in `format.json` (`beats[].start_s`, scaled to the new reel by the beat's `share`) and fill up to a number near `cut_count`, using the names `whoosh-deep whoosh-air impact-sub impact-punch riser click pop swipe`, `gain` 0.6 at most.
- `grade`: `clean-bright`, `warm-amber` or `off`. `brand.accent` and `brand.fg` from the brief. One `em` word at most per group.

```bash
python3 "$BP/check_plan.py" --plan premium/plan.json --reel "$REEL"
```

Fix every listed problem and run it again. Do not go on until it exits 0.

### 3. Build and render the captions

Rendering goes only through `b-hyperframes`. It installs HyperFrames and a pinned headless browser (about 88 MB) inside the work folder, fetches the pinned animation library, refuses any page that loads from the network, and renders. See its README for the hosts it contacts at setup. The renderer draws only the captions, as a transparent `.mov`; the footage never goes through it. Always pass `--quiet`.

```bash
python3 "$BH/hf_install.py"
python3 "$BH/fetch_gsap.py" --outdir vendor
python3 "$BP/build_comp.py" --plan premium/plan.json --reel "$REEL" --cap-top 1180 --outdir premium/comp
python3 "$BH/hf_render.py" --comp premium/comp --out premium/captions.mov --format mov --quiet
```

The renderer prints warnings. You may ignore three kinds: WCAG contrast notes from validate (the captions sit over moving footage), `overlapping_gsap_tweens` notes from lint, and the `composition_file_too_large` note about the caption file's length. An error is never ignored: a failed lint, validate or render, or a non-zero exit, stops the step. `--cap-top 1180` is a starting point for a full-frame speaker, not a computed value. If the avatar's face reaches that band, look at a frame and move it. Exit 3 from `hf_install.py` means Node 22 or newer, npm, ffmpeg or ffprobe is missing: tell the person and stop. If the person wants no captions, run `check_plan.py --captions off`, skip `build_comp.py` and the render, and set `NO_CAPTIONS=1` in the next block.

### 4. Grade and mix

```bash
GRADE="$(python3 -c 'import json; print(json.load(open("premium/plan.json"))["grade"])')"
if [ "${NO_CAPTIONS:-}" = 1 ]; then MUXCAP=(--no-captions); QACAP=(--captions off); else MUXCAP=(--captions-mov premium/captions.mov); QACAP=(--captions on); fi
python3 "$BP/mux.py" --reel "$REEL" "${MUXCAP[@]}" --plan premium/plan.json --out premium/polished.mp4
python3 "$BP/qa.py" --reel-in "$REEL" --reel-out premium/polished.mp4 --frames-dir premium/qa --grade "$GRADE" "${QACAP[@]}"
```

`mux.py` grades the footage, then lays the captions over it, so the captions keep their exact colours. `qa.py` checks the output decodes, keeps the reel's length and, with grade `off`, that the colour did not shift. Look at the four frames in `premium/qa/`: captions legible and clear of the face, accent on the emphasis words, grade subtle.

### 5. Run the quality gate

`make_spec.py` writes a version of `acceptance.json` for this order, with the duration window set to the reference length, plus or minus 15 percent. The gate then measures the reel.

```bash
python3 "$RS/make_spec.py" --format prior/format.json --spec "$RECIPE_DIR/acceptance.json" --out work/acceptance.order.json
RC=0
python3 "$QG" --kind reel --spec work/acceptance.order.json --input premium/polished.mp4 --out work/scorecard.json || RC=$?
[ "$RC" -eq 0 ] || [ "$RC" -eq 4 ] || { echo "the quality gate failed; read the FAIL lines above"; exit 1; }
```

Exit 4 means every measured check passed and some looks are owed. Exit 1 is a real failure: fix the reel (a wrong length usually means a new narration), never the spec.

### 6. Answer the looks and record them

Open each frame listed under `frames` in `work/scorecard.json` and the reel itself, and answer every LOOK row with your own vision tool. Answer "no" if you did not really look or are unsure. In particular, for `nothing_of_the_reference`, compare the new reel with what you know of the brief: the topic, voice and avatar are the brand's own. Write `work/answers.json`:

```json
{ "<check id>": { "answer": "yes", "note": "short reason" } }
```

```bash
python3 "$QG" --finalize work/scorecard.json --answers work/answers.json --out work/final-scorecard.json
```

Exit 1 is a final FAIL (a "no", or an answer missing) and stops the step. Fix the reel and run steps 5 and 6 again. Nothing is saved yet: the reel and the report are written only in step 7, and only for a finalized PASS.

### 7. Confirm nothing of the reference remains, then deliver

```bash
python3 "$RS/cleanup_reference.py" --check-only --format prior/format.json
python3 "$RS/verify_final.py" --scorecard work/final-scorecard.json --input premium/polished.mp4 \
  --spec "$RECIPE_DIR/acceptance.json" --final saves/final.mp4 --report saves/qa_report.json
```

The first command must print PASS: no `ref/` folder with files in it, and `format.json` still holds only numbers and labels. If it fails, delete the named files, tell the person what was found, and run it again. (The six-word scan of other files ran in step 1, before the transcript was deleted; here the reference is gone, so this can only check that it stays gone.)

`verify_final.py` is the last command and the only thing that writes `saves/final.mp4` and `saves/qa_report.json`. It exits non-zero unless the scorecard is finalized, its verdict is PASS, every check in `acceptance.json` has a PASS row, and the checked file's sha-256 and size still match `premium/polished.mp4`. A failed check, a missing answer or a swapped file stops here with nothing saved.

Done when `verify_final.py` printed `DELIVERY: PASS`.
