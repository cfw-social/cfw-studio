# b-qa-gate

The mechanical quality floor for a finished reel or a finished image.

It reads a recipe's `acceptance.json`, runs every check it can measure, and writes a
`scorecard.json`. Checks that only a person or a bot can judge (kind `perceptual`) are
copied into the scorecard as "needs a look", with their question text. Nothing is ever
skipped: a check kind it does not know is a FAIL, and a missing tool is a FAIL.

```text
acceptance.json + final.mp4 (or card.png)
        |
        v
  check.py --kind reel|image
        |
        |-- measures: size, frame rate, length, loudness, audio, not black, not flat
        '-- copies "look at it" questions as LOOK rows
        v
  scorecard.json   (+ frames to look at, for a reel)
        |
        v
  exit 0 pass | 4 pass, looks owed | 1 fail | 2 bad input
```

This block is a template. A recipe calls it as `../../blocks/b-qa-gate/check.py`.

## Interface

One entry point, plain Python, standard library only.

```sh
python3 ../../blocks/b-qa-gate/check.py --kind reel  --spec acceptance.json --input saves/final.mp4 --out work/scorecard.json
python3 ../../blocks/b-qa-gate/check.py --kind image --spec acceptance.json --input saves/card.png   --out work/scorecard.json
```

The first mode is described here. The second mode, `--finalize`, is described after the exit codes.

| Item | Detail |
|---|---|
| Entry point | `check.py` |
| `--kind reel\|image` | Required. Picks the set of check kinds it runs (tables below). |
| `--spec FILE` | Required. The recipe's `acceptance.json`, or a copy a step wrote with this order's sizes. Read only. May be anywhere. |
| `--input FILE` | Required. The file to check. Must resolve inside the current folder (the work folder). |
| `--out FILE` | Required. Where the scorecard goes. Must resolve inside the current folder. It must not be the input, the spec, or (with `--finalize`) the scorecard or answers file. In both modes it must be a new path or an old scorecard this tool wrote; any other existing file makes the run exit 2 and is left alone. With `--finalize` it may also not be the checked input or a file named like the recorded spec. An old scorecard at that path is removed once those checks pass, before anything else runs, so a stale PASS cannot survive a failed run. The frames folder may not be a link or point outside the work folder. A reel's look frames go in a folder beside it named `<scorecard name>-frames/`. |
| `--step NAME` | Optional. Run `steps.<NAME>.checks` from the spec instead of the top-level `checks`. |
| Reads | The three named files, and `ffmpeg` and `ffprobe` from `PATH`. Every `ffmpeg` and `ffprobe` call allows the `file` protocol only, so a crafted media file cannot open a network address. Nothing else. It never searches a folder and never runs a script it finds. |
| Writes | The scorecard and, for a reel with looks owed, seven PNG frames. Nothing else. |
| Stdout | One verdict line, one line per FAIL, the scorecard path. Text from the spec, answers or scorecard is flattened to one line first. |

Exit codes. This block adds code 4 so a bot can tell "passed, but you still owe looks"
from a clean pass.

| Code | Meaning |
|---|---|
| 0 | Every mechanical check passed and no look is owed. |
| 1 | At least one check failed. This includes an unknown check kind, a bad number in the spec, and a missing `ffmpeg` or `ffprobe`. A scorecard is written. |
| 2 | Bad usage or bad input (missing file, unreadable spec, path outside the work folder, no checks, unknown step). Nothing was checked and no scorecard is written. |
| 4 | Every mechanical check passed. One or more LOOK rows are owed. Answer them with `--finalize`. |

A failure always wins over a look. The looks are answered with the second mode,
`--finalize`, below.

### Recording the look answers (`--finalize`)

After the bot has looked at every LOOK row, it writes `answers.json` and finalizes:

```sh
python3 ../../blocks/b-qa-gate/check.py --finalize work/scorecard.json --answers work/answers.json --out work/final-scorecard.json
```

```json
{ "no_clipped_text": { "answer": "yes", "note": "all text inside the card" },
  "legible_contrast": { "answer": "no",  "note": "grey on dark in the footer" } }
```

| Rule | Result |
|---|---|
| Every LOOK row has an answer of `"yes"` or `"no"` | Required. A missing or malformed answer is a FAIL on that row. |
| Any `"no"` | FAIL on that row. |
| An answer for an id that is not a LOOK row (including a mechanical row) | FAIL, a row named `answer:<id>` is added. |
| The input scorecard already has a FAIL row | The final scorecard is FAIL. It can never become PASS. |
| All answers `"yes"` and every mechanical row PASS | Verdict `PASS`, exit 0. |
| The checked input changed, is missing, or the scorecard records no hash | FAIL, with a row named `input_unchanged`. |
| The scorecard was already finalized | Exit 2. Run the check again instead. |

- `--finalize`, `--answers` and `--out` must all resolve inside the current folder. No other option may be used with `--finalize`.
- Notes are stored as plain text: control characters become spaces and each note is cut to 500 characters. Notes are never rendered as HTML or run.
- The final scorecard keeps every row and adds `answer` and `note` to the LOOK rows, `"finalized": true` and `finalized_from`. LOOK rows become PASS or FAIL, so `counts.look` is 0.
- Exit codes: 0 final PASS, 1 final FAIL, 2 bad usage or bad input (a path outside the work folder, an unreadable file, not a scorecard from this block). The final scorecard is written for 0 and 1 only.
- **A scorecard is a record, not proof.** This does not prove the bot looked. It records what the bot says. The scorecard file is not signed. Anyone who edits the file by hand (for example, turning a FAIL row into PASS or into LOOK) defeats the gate, and `--finalize` will accept it. The hash only catches the checked file being swapped. Run the check yourself if the result matters.

### Scorecard

```json
{
  "scorecard_version": 1,
  "recipe": "r-example",
  "kind": "reel",
  "spec": "acceptance.json",
  "step": "final",
  "input": "saves/final.mp4",
  "input_sha256": "9f2c...",
  "input_bytes": 4821377,
  "tools": {"ffmpeg": "ffmpeg version 8.1 ...", "ffprobe": "ffprobe version 8.1 ..."},
  "verdict": "PASS_WITH_LOOKS",
  "counts": {"pass": 9, "fail": 0, "look": 3},
  "checks": [
    {"id": "canvas", "type": "dims", "status": "PASS", "value": "1080x1920", "detail": ""},
    {"id": "gate.loudness", "type": "qa_gate", "status": "FAIL", "value": "", "detail": "-18.2 LUFS, expected -14 within 1.5"},
    {"id": "no_clipped_text", "type": "perceptual", "status": "LOOK", "value": "", "detail": "", "question": "(a) No text is clipped."}
  ],
  "frames": ["work/scorecard-frames/frame-00.png"]
}
```

- `verdict` is `PASS`, `PASS_WITH_LOOKS` or `FAIL`.
- `status` is `PASS`, `FAIL` or `LOOK`. There is no skip status.
- `input_sha256` and `input_bytes` describe the file that was checked. `--finalize` re-hashes it and fails if it changed or is missing.
- Every path in the scorecard is relative to the work folder. `spec` is the file name only.
- `frames` is filled for a reel only, and only when a LOOK row exists (frames at 0, 5, 20, 40, 60, 80 and 95 percent).
- A `qa_gate` check becomes seven rows named `<id>.video`, `.audio`, `.size`, `.fps`, `.duration`, `.loudness`, `.cover`.

## Check kinds

All numbers come from the spec and are checked as numbers (whole, finite, in range)
before they reach `ffmpeg` or `ffprobe`. Tools run as argument lists, never through a
shell. A crop must be four whole numbers, `W:H:X:Y`.

Luma is full-range 0 to 255, measured from the decoded frame. A "not black" check on
a crop compares the crop's mean luma to `floor`.

| Kind | Entry | Fields (defaults) | Passes when |
|---|---|---|---|
| `dims` | reel, image | `w`, `h` | Size is exactly `w` by `h`. |
| `aspect_ratio` | image | `w`, `h`, `tol` (0.01), `min_w` | Ratio matches within `tol`. 2x renders pass. `min_w` is a hard minimum width if given. |
| `fps` | reel | `expect`, `tol` (1.5) | Frame rate is within `tol` of `expect`. |
| `duration_window` | reel | `min_s` (0), `max_s` | Length is inside the window. |
| `spoken_duration_window` | reel | `min_s`, `max_s`, `wpm` (150) | The input is a UTF-8 script. Its word count at `wpm` lands inside the window. Run it with the script as `--input`. |
| `audio_present` | reel | none | An audio stream exists. |
| `loudness` | reel | `target` (-14), `tol` (1.5) | Integrated loudness (ebur128) is within `tol` of `target`. Silence fails. |
| `mean_volume` | reel | `min_db` (-90), `max_db` (0) | Mean volume is in the range. Silence fails. |
| `luma_floor` | reel, image | `crop`, `floor` (16), `samples` (0.05 to 0.95) | The crop's mean luma is at least `floor` at every sample. `samples` are fractions of the length. An image is sampled once. Add `0` to sample frame 0. |
| `luma_floor_windows` | reel | `windows`, `windows_from`, `crop`, `floor`, `samples`, `expected_duration_s`, `duration_tolerance_s` (0.5) | Same, at each sample and at the start, middle and end of every window. Windows come from `windows` (a list of `[start, end]` pairs or `{"start", "end"}` objects), from `windows_from`, or both. See below. |
| `json_array_nonempty` | reel | `min_items` (1), `item_keys` | The input is a JSON array with at least `min_items` items. With `item_keys`, every item is an object whose named keys hold non-empty text. |
| `json_words_nonempty` | reel | `path` ("words"), `min_items` (1), `expected_duration_s`, `tail_tolerance_s` | The input is either a bare JSON array of words (what `b-audio` writes) or a JSON object whose `path` list holds them. Both shapes are checked the same way. Each word is an object with non-empty `text` and numeric `start` and `end`. Starts do not go backwards, and no end is before its start. With `expected_duration_s` written into the spec, the last end is within `tail_tolerance_s` before it (and not more than 0.5 s after). `tail_tolerance_s` alone is a FAIL. |
| `contrast_floor` | reel, image | `crop`, `samples` ([0]), `bright_mean` (48), `min_mean` (8), `min_range` (128), `min_bright_pct` (2) | Cover rule. A bright frame, or a dark card with a bright element. A flat dark or black frame fails. |
| `not_flat` | image | `crop`, `min_range` (32) | The luma range (max minus min) is above `min_range`. A single colour fails. A mostly blank card with real content passes. |
| `qa_gate` | reel | `format` (reel), `expect_fps` (30), `lufs_target` (-14), `lufs_tol` (1.5) | The reel floor in one check: video stream, audio, size for the format (`reel` 1080x1920, `landscape` 1920x1080, `square` 1080x1080), frame rate, length above 0, loudness, and the frame 0 cover rule. |
| `perceptual` | reel, image | `desc` | Never passes or fails here. It becomes a LOOK row with `desc` as the question. |

### `windows_from`

A list of entries like `"edit_plan.takeovers"` and `"beat_list.broll"`. Each is
`<name>.<key>`: the file is `<name>.json`, looked for in the work folder, then in `saves/`,
`prior/` and `work/` inside it (first match wins). Nothing else is searched.

- `<key>` names a top-level list in the file. Each item is `{"start": s, "end": e}` or `[s, e]` with numbers in seconds. A takeovers list (`edit_plan.takeovers`) has that shape.
- Special case: for `<key>` `broll`, when the file has no list of that name but has a `beats` list, the items with `"kind": "broll"` are used. This is the shape of `beat_list.json`.
- `<name>` may hold only letters, digits, `-` and `_`. `<key>` the same, without `-`. At most 10 entries and 200 windows in all.
- The file must resolve inside the work folder after symlinks. Anything outside, a missing file, a missing list, a non-number or a window outside the video is a FAIL.
- An empty list is fine (an order with no b-roll). The samples still run.
- `expected_duration_s` still has to be written into the spec by the recipe, since the bed length is not in those files.

Any other `type` is a FAIL that names it, as is a known kind used with the wrong `--kind`.

### Check kinds used by the recipe templates

Checked against the `acceptance.json` of `r-carousel`, `r-gfx-image`, `r-ai-image`,
`r-ai-character`, `r-reels-faceless`, `r-reels-pip` and `r-reels-spotlight`. Those
templates are published separately.

| Kind in the spec | Status in this block | Used by |
|---|---|---|
| `dims` | Owned and implemented | all seven |
| `luma_floor` | Owned and implemented | all seven |
| `perceptual` | Needs a look (LOOK row) | all seven |
| `not_flat` | Owned and implemented | gfx-image, ai-image, ai-character |
| `qa_gate` | Owned and implemented | reels-faceless, reels-pip, reels-spotlight |
| `duration_window` | Owned and implemented | reels-faceless, reels-pip, reels-spotlight |
| `contrast_floor` | Owned and implemented | reels-faceless |
| `loudness` | Owned and implemented | reels-faceless, reels-pip |
| `mean_volume` | Owned and implemented | reels-faceless, reels-pip |
| `spoken_duration_window` | Owned and implemented | reels-spotlight |
| `luma_floor_windows` | Owned and implemented, including `windows_from`. The recipe writes `expected_duration_s` into a copy of the spec. | reels-spotlight |
| `json_array_nonempty` | Owned and implemented | reels-spotlight |
| `json_words_nonempty` | Owned and implemented. The recipe writes `expected_duration_s` into a copy of the spec to get the tail rule. | reels-spotlight |
| `spotlight_plan_guard` | Not supported. FAIL, named. Recipe-specific guard, stays in the recipe. | reels-spotlight |
| `spotlight_beats_guard` | Not supported. FAIL, named. Recipe-specific guard, stays in the recipe. | reels-spotlight |

Kinds added by this block that no recipe uses yet: `aspect_ratio`, `fps`, `audio_present`.

## Tools

| Tool | Version | Notes |
|---|---|---|
| Python | 3.10 or newer; run with 3.15 only | Standard library only. |
| ffmpeg and ffprobe | 8.1 | Tested with ffmpeg 8.1 only. Older versions are untested. Needs `libx264` and `aac` only to run the tests. Checks use `ebur128`, `volumedetect` and raw frame output. The version is not enforced at run time; it is recorded in the scorecard. |

## Network use

None. No host is contacted, at setup or at run time. No key is read.

## Recipes that use it

Every recipe: the image recipes `r-carousel`, `r-gfx-image`, `r-ai-image` and `r-ai-character` (`--kind image`), and the reel recipes (`--kind reel`): `r-reels-faceless`, `r-reels-pip`, `r-reels-spotlight` and the two HeyGen variants (`r-reels-pip-heygen`, `r-reels-spotlight-heygen`), and `r-inspired-reel` (recipe templates live under `recipes/` and are added separately). A recipe's last
step runs the check, answers each LOOK row with its own vision tool, then records the
answers with `--finalize`. The recipe gates delivery on the final scorecard.

## Proof

A short summary of the limits below. Where this README does not say, it reads "not recorded".

| What | Status | Detail |
|---|---|---|
| Automated tests | 55 tests, as of 2026-11-22 | `python3 -m unittest discover -s blocks/b-qa-gate/test`, from the repository root. They build small media with `ffmpeg`. |
| Run on which operating systems | macOS (Apple silicon) only; Linux and Windows not run | Python 3.15.2, Node 25.9.0, ffmpeg 8.1 on one Apple-silicon Mac. |
| Run with a real provider account | no provider | No network, no key. |
| Used in a real start-to-finish recipe run | yes, in recipe template runs with stand-in media on macOS, 2026-11-22 | Recipe runs used generated clips and generated speech, not a real reel from a provider. |

## Tests

No account, no private file. The tests build small media with `ffmpeg`.

```sh
python3 -m unittest discover -s blocks/b-qa-gate/test -v
```

Run from the repository root. Needs `ffmpeg` and `ffprobe` on `PATH`.

## Limits and known gaps

- A spec with an unexpected value never ends in a traceback: a check that cannot run becomes a FAIL row and the scorecard is still written. A spec nested too deeply to read is exit 2.
- It measures; it does not judge. A reel can pass every check and still look wrong. The LOOK rows exist for that.
- `loudness` and `mean_volume` read the whole file. A silent reel fails both.
- `luma_floor` and `contrast_floor` use the mean luma of a crop at a few moments. A brief black flash between samples is not seen. Use `luma_floor_windows` or more `samples` to look closer.
- `luma_floor_windows` reads window files only by the `windows_from` rules above.
- `json_words_nonempty` checks the shape and order of the words, not that they are right. The spotlight recipe's own check on words per second stays in the recipe.
- There is no green-screen residual check.
- Frame extraction for looks needs a video input. A step that checks a text file and holds a LOOK row will report a frames failure.
- Tests use synthetic media. They are not proof of a real reel from any provider.
