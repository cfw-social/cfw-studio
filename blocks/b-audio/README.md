# b-audio

Speech to text with word timings. One Python script runs one local speech-to-text tool, named by the caller, and writes a JSON list of words with start and end times.

## What it does

```text
audio or video file --(ffmpeg, only if needed)--> 16 kHz mono WAV --> one named local tool --> words.json
                                                                                          \--> words.meta.json
```

- One tool per run. No chain of fallbacks. If the named tool is missing, the script stops and says what to install.
- The model file is always named by the caller. The script never searches home folders or package-manager folders.
- It never downloads a model unless the caller passes `--allow-download`, and then only with `--model-sha256`. The download goes to a temporary file in the work folder and is checked against that checksum before it is moved into place. A mismatch deletes it.
- It writes only inside the work folder (the folder it is run from), including a downloaded model. A model that already exists in an `--allow-model-dir` folder outside the work folder may be read, never written; a download to a path outside the work folder is refused.
- Every file it writes (words, meta, model) goes through a random temporary name in the target folder, is refused if the target is a symbolic link, and is checked to be inside the work folder afterwards.

## Interface

One entry point: `scripts/transcribe.py` (Python 3.10 or newer, standard library only).

```text
python3 blocks/b-audio/scripts/transcribe.py INPUT --out words.json \
  --tool whisper-cpp --tool-version 1.8.4 --model models/ggml-base.en.bin
```

| Argument | Required | Meaning |
|---|---|---|
| `INPUT` | yes | Audio or video file, inside the work folder. |
| `--out PATH` | yes | Words file to write, inside the work folder. The meta file is written beside it. |
| `--tool NAME` | yes | The one tool to use. Only `whisper-cpp` exists (program `whisper-cli`). |
| `--tool-version TEXT` | yes | The installed version, as you read it from your package manager. Recorded beside the output. `whisper-cli` cannot report it itself. |
| `--tool-bin PATH` | no | Explicit path to the program. Default: found on `PATH`. |
| `--model PATH` | yes | Model file. **It must be inside the work folder or in a folder named with `--allow-model-dir`**; any other place is refused (symlinks are resolved first). |
| `--allow-model-dir DIR` | no | Extra folder the model may be in. Repeatable. |
| `--model-sha256 HEX` | with download | Expected checksum of the model (64 hex characters). A mismatch fails. Required with `--allow-download`. |
| `--hint-file FILE` | no | UTF-8 text inside the work folder, up to 2000 characters (newline and tab allowed, other control characters refused). Passed to whisper.cpp as `--prompt` (its initial prompt, listed in `whisper-cli --help` for 1.8.4) in the argument list, so names and product words are spelled right. It biases the tool; it does not guarantee spelling. Keep the hint to a short list of names and unusual words, never the whole script. Reason: a hint holding a whole script (about 74 words of full sentences) made the transcriber stop after 4 words, while a short list of the script's names and unusual words gave all 74 words (seen once, with whisper.cpp 1.8.4 and the base English model). The meta file records only that a hint was used, its length and its sha256, never its text. |
| `--language CODE` | no | Default `en`. A `.en.bin` model with another language is refused. |
| `--allow-download` | no | Allow fetching a missing model into the work folder. Needs `--model-name` and `--model-sha256`. |
| `--model-name NAME` | with download | For example `base.en`. Fetched as `ggml-<NAME>.bin`. |
| `--max-model-bytes N` | no | Download cap. Default 4 GiB. |
| `--timeout SECONDS` | no | Stops the tool. Default 1800. |
| `--download-timeout SECONDS` | no | Overall time allowed for a model download. Default 1800. |

No environment variable is read. No key is used.

Exit codes: `0` done (a recording with no speech gives an empty list and a warning on stderr) | `1` failed (tool error, timeout, bad checksum, download failure) | `2` bad usage or bad input (path outside the work folder, unknown option, model outside allowed places) | `3` something required is missing (tool, ffmpeg, model without `--allow-download`).

## Word-timing format (the one agreed format)

`words.json` is a bare JSON array, times in seconds, three decimals, never decreasing:

```json
[ {"text": "Hello", "start": 0.07, "end": 0.59}, {"text": "world.", "start": 0.59, "end": 0.78} ]
```

This is the shape the reel recipes and `b-broll-sync` read (`text`, `start`, `end`). A recipe that used `w` for the word reads `text` instead.

`words.meta.json` sits beside it: `tool`, `tool_version`, `model_file`, `model_sha256`, `model_downloaded`, `hint_used`, `hint_chars`, `hint_sha256`, `tool_bin_as_given`, `tool_sha256`, `ffmpeg_version` (null when ffmpeg was not needed), `language`, `input` (relative), `duration`, `word_count`, `text`, `wpm`. The input is a relative path. `tool_version` is whatever the caller typed and the script cannot check it; `tool_bin_as_given` and `tool_sha256` (a checksum of the program file) identify the binary that actually ran.

Word times come from the tool's token times. They are good to about 0.1 to 0.2 seconds, not frame accurate. Sound-only tokens such as `[MUSIC]` are dropped. A word the tool invents over digital silence is dropped.

## Tools and versions

| Tool | Version | Needed for |
|---|---|---|
| Python | 3.10 or newer; run with 3.15 only | the script |
| whisper.cpp (`whisper-cli`) | You name the version. Run with whisper.cpp 1.8.4 and the `ggml-base.en.bin` model on macOS (see Limits) | the transcription |
| ffmpeg | 6 or newer, run with `-protocol_whitelist file`, so it reads local files only | only when the input is not already a 16 kHz mono 16-bit WAV |
| A ggml model file | You choose, for example `ggml-base.en.bin`. Its checksum is recorded each run | the transcription |

## Network

None by default. With `--allow-download` and a missing model file, one host: `huggingface.co` (path `/ggerganov/whisper.cpp/resolve/main/ggml-<NAME>.bin`). Redirects are followed only to `huggingface.co` or `hf.co` hosts over https. That host list is not verified against Hugging Face's current serving setup. No key is sent.

## Used by

`r-reels-faceless`, `r-reels-pip`, `r-reels-spotlight` and the two HeyGen variants (`r-reels-pip-heygen`, `r-reels-spotlight-heygen`), and `r-inspired-reel` transcribe through this block. Nothing else calls it (recipe templates live under `recipes/` and are added separately).

## Proof

A short summary of the limits below. Where this README does not say, it reads "not recorded".

| What | Status | Detail |
|---|---|---|
| Automated tests | 33 tests, as of 2026-11-22 | `python3 -m unittest discover -s blocks/b-audio/test`, from the repository root. They use a small fake tool and a local fake server. |
| Run on which operating systems | macOS (Apple silicon) only; Linux and Windows not run | Python 3.15.2, Node 25.9.0, ffmpeg 8.1 on one Apple-silicon Mac. |
| Run with a real provider account | no provider | A local tool; no account or key is used. |
| Used in a real start-to-finish recipe run | yes, in recipe template runs with stand-in media on macOS, 2026-11-22 | Real whisper.cpp 1.8.4 with the base English model in three of the four runs, on generated speech. |

## Tests

```text
cd blocks/b-audio && python3 -m unittest discover -s test -v
```

They use a small fake tool and a local fake server. No speech model, no paid account, no private file.

## Limits and what is not proven

- Only whisper.cpp is supported. Another tool needs its own output reader.
- What was run: one real run inside a reel recipe on macOS, with whisper.cpp 1.8.4 and the base English model (`ggml-base.en.bin`), on generated speech (90 words). It worked. An earlier check used a short synthetic voice clip on the same setup. Untested on Windows and Linux, on long audio and on other languages. A hint file that held a whole script cut the output to 4 words in one run (see `--hint-file`): keep it to a short list of names and unusual words. The `--hint-file` option is covered by tests with the fake tool. It was also run with a real model: on 2026-11-22, with whisper.cpp 1.8.4 and the base English model on macOS, a short hint (a brand name plus names and unusual words, under 300 characters) was used in a recipe run and 91 words were recognised. A hint holding a whole script made the transcriber stop early or repeat itself in two separate runs. Keep the hint to a short list of names and unusual words, never the whole script.
- The model download path is tested only against a local fake server, not the real host.
- The tool can mishear. The recipe decides what to do with the text.
