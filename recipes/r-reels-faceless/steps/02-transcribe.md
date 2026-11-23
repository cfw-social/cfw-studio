# Transcribe

Read `_shared.md` first. Receive `prior/voice_bed.mp4` and the exact script. Produce
`saves/transcripts.json` with `duration` and `words`. Word timestamps are ground truth for scenes,
b-roll and captions; never invent, scale or move them to fit a picture. Speech to text is local
and belongs to the `b-audio` block. No hosted speech-to-text, no key lookup and no silent switch to
another tool. This step makes no network call.

## Run b-audio

Pick the one installed tool, whisper.cpp (`whisper-cli`), and read its version from your package
manager. Its model file must already be on the machine: inside the run folder, or in a folder the
person named (pass that folder as `--allow-model-dir`). Do not download a model or install a
missing tool. A download needs the person's yes, then `--allow-download --model-name NAME
--model-sha256 HEX`; read `"$BLOCKS_DIR/b-audio/README.md"` for that case.

```text
python3 "$BLOCKS_DIR/b-audio/scripts/transcribe.py" prior/voice_bed.mp4 --out work/words.json --tool whisper-cpp --tool-version <version> --model <model file>
```

It writes `work/words.json` (`[{"text","start","end"}]`, seconds) and `work/words.meta.json` (tool,
version, model checksum). Exit 3 means something is missing: tell the person what to install and stop.
Exit 1 is a failed run: report it safely and stop. Never turn a failure into empty words or retry
another model or provider without the person's say-so. An empty list means no speech was found: a
silent bed is a failed step.

## Check the words

Compare the words with the exact script and correct recognised brand or product tokens by editing the
text only; keep every timestamp and the token count. Hyphenated words can stay split: the scene validator
matches phrases across hyphens. Then run the recipe's `words_found` check, which also writes the save:

```text
python3 "$RECIPE_DIR/scripts/check_words.py" --words work/words.json --bed-duration <seconds> --out saves/transcripts.json
```

`<seconds>` is the bed length from ffprobe JSON (not shell text). It requires at least 20 timed words,
finite and monotonic times, and every word inside the bed (0.5 s codec slack). Exit 1 prints each problem.
Record the tool, its version and the model from `words.meta.json`. A check on made-up JSON does not prove
a real run of the tool. This step has no `canAsk`.
