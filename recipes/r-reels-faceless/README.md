# r-reels-faceless

Based on CFW Social's built-in faceless reel recipe.

## What it makes

A template for a narrated faceless reel. It makes one 9:16 video, 1080x1920 at 30 fps (H.264 with AAC 48 kHz stereo), 30 to 90 seconds long. The video has one brand voice, animated illustrative graphics for each beat, optional b-roll you supply, kinetic captions, sound effects and a branded closing card. It also makes a cover image, per-platform captions and a QA report.

This is a template to learn from and adapt. A brand's bot reads it, builds its own recipe, and saves that recipe in the brand's recipe library in CFW Social. The bot then runs its saved recipe. The CFW tools for saving a recipe are live, for a key made with the "Save its own recipes" permission (see [../../docs/DESIGN.md](../../docs/DESIGN.md)). You can also read the steps and follow them by hand or with your own agent.

## What you need

| Tool | Version |
| --- | --- |
| Python 3 | 3.10 or newer (standard library only) |
| Node.js and npm | Node 22 or newer (HyperFrames requires it). Observed: 25.9.0 |
| FFmpeg and ffprobe | 6 or newer, with libx264, AAC and the `loudnorm`, `concat`, `curves`, `unsharp` and `eq` filters. The blocks were tested on 8.1 |
| HyperFrames (npm `hyperframes`) | exactly 0.7.5, installed inside the run folder by `b-hyperframes` |
| GSAP (npm `gsap`) | exactly 3.14.2, fetched by `b-hyperframes` (third-party, GreenSock's standard licence, not included here) |
| A browser | Chrome headless shell exactly 131.0.6778.85, downloaded by `hf_install.py` into the run folder (about 88 MB). An installed Chrome is used only if the person asks (`--use-system-browser`) |
| whisper.cpp (`whisper-cli`) | You name the version. `b-audio` ran it once with 1.8.4. Its model file (for example `ggml-base.en.bin`) must already be on the machine |
| Fonts | The templates name Oswald, Inter and JetBrains Mono (or the brand's own display and body fonts) and use them only if they are installed on the machine. Nothing is shipped here; check each font's own licence |
| A vision-capable model | to look at the frames; there is no mechanical-only pass |

Provider account: ElevenLabs, for the narration only. The bot uses the brand's own key and hands it to `scripts/voiceover.py` as the `ELEVENLABS_API_KEY` environment variable of that one command, or on standard input with `--key-stdin`. Nothing here reads a key from a file. A voice is paid per use, so a person must allow that step. The template ships no voice id.

## Blocks it uses

Blocks live in `../../blocks/`. The steps call them by the relative path `../../blocks/b-<name>/`.

| Block | Why | Path |
| --- | --- | --- |
| `b-audio` | Speech to text with word timings, one named local tool, no download unless the person allows it (step 2) | `../../blocks/b-audio/` |
| `b-broll-sync` | Checks the bot's scene plan and turns it into a gapless beat list; never picks clips itself (step 3) | `../../blocks/b-broll-sync/` |
| `b-typing-ui` | Safe fillers for the hook card and the typing card (step 4) | `../../blocks/b-typing-ui/` |
| `b-hyperframes` | The one place that installs the renderer, fetches the animation library, checks a page is local-only and renders it (steps 4 and 5) | `../../blocks/b-hyperframes/` |
| `b-reel-premium` | Plan check, kinetic captions, colour grade and sound effects; the eight sound effects live only here (step 5) | `../../blocks/b-reel-premium/` |
| `b-qa-gate` | The mechanical floor and the "look at it" answers for the voice, the body and the final reel (steps 1, 4 and 6) | `../../blocks/b-qa-gate/` |

## The steps

```text
script
  |
  v
01 voice-over -> 02 transcribe -> 03 plan beats -> 04 render graphics
 (ElevenLabs)     (b-audio)       (b-broll-sync)    (card_fill, b-typing-ui,
 voice_bed        transcripts     scene_plan,        b-hyperframes)
                                  beat_list              |  body_video
                                                         v
                  06 final checks  <-  05 assemble (outro, b-reel-premium captions,
                  (b-qa-gate, looks)   sound effects, grade, loudness master)
                  final_video, cover,
                  captions, qa_report
```

Each step has its own file in `steps/`. `steps/_shared.md` holds the setup and the rules every step shares, including how the brand data in `brief.json` looks.

## Inputs and outputs

Inputs: `script` (required, about 80 to 230 words, hook first, call to action last); `voice_id` (an ElevenLabs voice id; empty means the brand's voice); `broll` (video clips, optional, inside `inputs/`); `cta` (the closing line and handle, optional); `outro` (one portrait clip of 1 to 8 seconds, optional); and `brief.json`, which holds the brand details and options (`target_seconds`, `captions`, `sfx`, `grade`, b-roll settings). A brand font file for the captions is optional.

Outputs, in `saves/`: `final_video.mp4`, `cover.png`, `captions.json` and `qa_report.json`. The earlier steps save `voice_bed.mp4`, `transcripts.json`, `scene_plan.json`, `beat_list.json`, `body_video.mp4` and `assembled_video.mp4`.

## Network use

At setup, once per run folder (declared by `b-hyperframes`, as that block's README states):

- `registry.npmjs.org`: `hf_install.py` installs HyperFrames 0.7.5 and its dependencies from a lockfile, with `npm ci --ignore-scripts` (no install script runs). The block observed 172 requests, about 150 MB in npm's cache, 171 packages and 450 MB on disk.
- `storage.googleapis.com` (`chrome-for-testing-public`): `hf_install.py` downloads the pinned Chrome headless shell 131.0.6778.85, one 88 MB zip (about 172 MB unpacked), into the run folder's cache. A new run folder downloads it again.
- `registry.npmjs.org`: `fetch_gsap.py` fetches the `gsap@3.14.2` version record and tarball (about 1.7 MB) and checks them against pinned hashes.
- `huggingface.co`: only if the person allows a speech model download in `b-audio` (`--allow-download`). Not used by default.

At run time:

- `api.elevenlabs.io`, in step 1 only, over https, to make the voice. Redirects are not followed.
- Nothing else is intended. `b-hyperframes` refuses any page that loads from the network and switches off the renderer's telemetry and update checks. The block sampled the pinned browser's sockets during renders and saw no connection; the page's own requests are blocked only by its text check, not by a sandbox or firewall, so for untrusted text render on a machine with no network. Speech to text is local.

Plainly: **the script text is uploaded to ElevenLabs**, and ElevenLabs' API documentation (https://elevenlabs.io/docs/api-reference/text-to-speech/convert, read 2026-11-22) describes request logging as on by default (`enable_logging` defaults to true; its zero-retention mode is for enterprise customers only). Do not put anything in a script that the brand may not share with the provider.

### The voice-over script

`scripts/voiceover.py` makes one MP3 and is held to the rules of the provider blocks.

| Item | Rule |
| --- | --- |
| Command | `voiceover.py --text-file F --voice-id ID --out F.mp3` plus optional `--model-id`, `--output-format` (mp3 only), `--stability`, `--similarity-boost`, `--style`, `--speed`, `--use-speaker-boost`, `--timeout` (1 to 600 s, default 120), `--max-bytes` (default 40 MiB), `--key-stdin` |
| Key | Environment variable `ELEVENLABS_API_KEY` set for that one command, or one line on standard input with `--key-stdin`. Never an argument, never read from disk, never printed or written: every printed line is scrubbed of it |
| Files | Text file and output must resolve inside the run folder. The output goes through an exclusive temporary file and `os.replace`; a symlinked target is refused; the voice id is checked (`[A-Za-z0-9_-]{8,64}`) before it enters the URL path |
| Network | `https://api.elevenlabs.io` only, no redirect followed, one call (never retried), an overall deadline, a size cap, and the body must start like an MP3 |
| Text limit | At most 10,000 characters per request (this recipe's own cap; the provider's API page states no per-model limit) |
| Output | Last line, printed once: `AUDIO_FILE: <relative path>` or `AUDIO_FAILED: <reason>`. Server messages are stripped of control characters, scrubbed and cut to 200 characters. No traceback |
| Exit | 0 saved, 1 provider or network failure, 2 bad arguments or paths, 3 no key (nothing was sent) |
| Tests only | `--base-url http://127.0.0.1:PORT` or `http://localhost:PORT`, parsed and compared exactly; any `@` is refused |

The request shape follows ElevenLabs' public documentation as read on 2026-11-22
(https://elevenlabs.io/docs/api-reference/text-to-speech/convert): `POST /v1/text-to-speech/{voice_id}`, header
`xi-api-key`, JSON body `{"text", "model_id"}` with optional `voice_settings`, query `output_format` (default
`mp3_44100_128`; some formats need a paid tier). The page gives no numeric ranges for the voice settings; the
script's ranges (0 to 1, speed 0.7 to 1.2) are this recipe's own. **Not proven with a real account.** It is tested
only against a local fake server.

## Run the tests

From the repository root. They need no network, no paid account, no browser and no speech model. Tests that make media need `ffmpeg` and `ffprobe`; without them they are skipped, by name.

```text
python3 -I recipes/r-reels-faceless/test/test_portable.py -v
python3 -I recipes/r-reels-faceless/test/test_scripts.py -v
python3 -I recipes/r-reels-faceless/test/test_voiceover.py -v
```

`test_portable.py` checks the contract helpers in `scripts/contracts.py`, the words and beats checks, the loudness master, the instruction files (every block and recipe path in them exists, no retired names), and the planner with a guard that fails if it starts another process. `test_voiceover.py` runs `voiceover.py` against a local fake server (success, 401, 402, 429, 404, a redirect, an oversized body, a slow body, a forged last line, a planted symlink, the key in no output). `test_scripts.py` checks the picture guards (including the PSNR proof on files with sound, and `av-span` on the real output of the loudness master and of the cover join), the caption-group rule (`check_captions.py`), the palette and call-to-action helpers, `card_fill.py` (every card type, hostile text, the local-only check from `b-hyperframes`), the block fillers as the steps call them, and runs the real `b-qa-gate` on `acceptance.json` to prove no check kind is unknown. The tests use the blocks beside this folder.

## Sample

There is no sample reel in this repository. The one real run recorded in "Limits" used generated stand-in media (colour patterns and a tone), and its 33-second output is too large to keep here. A real sample needs a paid ElevenLabs voice, a local whisper.cpp model, a full render and the tools above.

## Terms used by CFW Social

A few names in this folder belong to CFW Social's order format. If you use this template outside CFW Social, you can ignore them.

- **The order**: one request for one finished piece, with its inputs and a brand attached. Here the brand arrives frozen with the order, and `scripts/contracts.py` `private_brand()` checks it. Outside CFW Social, write `brief.json` by hand.
- **Claim and Reviews**: inside CFW Social a bot claims an order, reports each step and uploads the final files to the order's Reviews page. This recipe never approves, schedules or publishes.
- **`order-brand-v2`**: a feature name in `manifest.json` (`needs.features`) for how the brand details reach the steps.
- **`needs.engines`**: an order-format field naming the agent apps an order may be routed to. It is not a claim that this recipe was proven on them.
- **The `research` and `script` steps**: `runsOn: "server"` steps in `manifest.json` that run only when the person chose "research and write my script first". CFW Social runs them itself; they have no instruction files here. Outside CFW Social, supply `inputs/script/` yourself (or write `prior/approved_script.md`) and skip them.
- **`runsOn`, `saves`, `checks`, `canAsk`, `weight`, `neededAt`**: fields in `manifest.json`. Each step declares what it saves, which checks it must pass, whether it may ask for an input, and when an input is needed.
- **Check ids** such as `bed_has_audio`, `words_found`, `beats_cover_bed`, `body_dims`, `qa_gate` and `final_loudness`: the names under which `manifest.json` declares each check. The step file says what to measure. The id is a label.

## Limits and known gaps

- **One end-to-end run, on stand-in media, on one machine.** macOS on Apple silicon, Node 25.9.0, FFmpeg 8.1, a fresh `hf_install.py` with the pinned browser. It followed the steps in order: a generated tone as the voice (the `voiceover.py` call to ElevenLabs was not made), a hand-written `words.json` (speech to text was not run), one generated colour-pattern clip as one b-roll scene, six graphics beats, a generated closing card, captions and sound effects through `b-reel-premium`, the loudness master, and `b-qa-gate`. The output was 1080x1920, 30 fps, H.264 and AAC 48 kHz stereo, 33.0 s, 8.1 MB, at -14.0 LUFS. All mechanical checks passed, the 11 looks were answered "yes" from the frames, and the final verdict was PASS. Nothing else was proven: no real voice, no real speech-to-text run, no real footage, no Windows or Linux run. A later run by a separate agent, from the published files, found two of the recipe's own checks failing as written: the PSNR proof (it stopped the encoder early, so ffmpeg often printed no value) and the audio-length check after the loudness master and the cover join (the sound ended 15 to 24 ms after the picture). Both are fixed at the cause and covered by tests; the steps and the "Limits" below describe the fixed behaviour. The run's stand-in voice was macOS `say`.
- `manifest.json` `needs.os` lists Windows, macOS and Linux: it says where the steps are expected to work (they use no shell-specific commands, and a test checks that). It is not a record of testing. This edition was run on macOS only, and not by a stranger's bot.
- Not proven on Windows, macOS or Linux by any recorded run of a stranger's bot. The scripts use no shell and no OS-specific call, and that is all this repository can say.
- Speech to text is `b-audio` with whisper.cpp only. Word times are good to about 0.1 to 0.2 seconds, not frame accurate. The tool's version is whatever the bot records.
- The `overlay_beats` option is not supported. It must fail before any paid call.
- A run cannot switch scripts off, because the animation timeline must run. The guards are the local-only check in `b-hyperframes` (a text scan, not a sandbox) and a render machine with no network. For untrusted text, render without a network.
- Cards need Oswald, Inter and JetBrains Mono (or the brand's fonts) installed. A missing font silently falls back to a generic family in the render, so confirm the fonts before a run; the look and the widths change if they are missing. Captions use the generic sans-serif unless you supply a brand font file.
- The hook card and the typing card come from `b-typing-ui`, filled with the brand's background, text and accent colours (a pair under 3.0 contrast is refused). Both cards animate their text in from nothing (exempt from the first-frame check), and the hook card has no illustrative hero. In the run, the first line of the typing prompt was indented against the second line; the block's template does this, not the recipe.
- The footage is graded by ffmpeg and never goes through the renderer; the renderer draws only the captions, as a transparent video. `qa.py` (in `b-reel-premium`) guards colour when the grade is `off`. Caption overlay lint printed two warnings in the run (`overlapping_gsap_tweens` at one instant and `composition_file_too_large`); the render still completed.
- Text with a web address (`https:`, `//host`, `url(`) is refused in cards and in the block fillers, because the local-only check cannot tell a sentence from a link. Write `example.com`.
- `frame_qa.py band-scan` skips b-roll beats, so it cannot see a caption layer lost over moving footage; look at the b-roll windows.
- The headline of a `hook` or `typing` scene is not drawn (those cards show their own text).
- Two thresholds worth knowing: `frame_qa.py tail-luma` uses a floor of 26 (a dark brand canvas is lifted only to luma 24, so 30 failed a lit closing card; 26 still catches a black or faded end, and the gate's own not-black floor is 16), and `av-span` allows the sound to end one AAC frame (21.3 ms) after the picture, because an AAC encode is built from whole 1024-sample frames and cannot end inside one. Longer overhang fails, and the loudness master refuses sound more than 0.1 s longer than the picture instead of cutting it.
- A scorecard is a record, not proof: someone who edits it by hand can make it pass. `deliver_final.py` stops a skipped, unfinalized or stale gate, not a forged scorecard.
- The ghost-glyph and hero looks judge only the card types meant to have them (see step 6); a reel made only of hook and typing cards answers them "yes, not applicable".
- The tests prove the helper scripts, the filler's escaping and the page checks on small made-up clips. They do not prove how a card looks in a real render.

## Files

- `SKILL.md`: the overview an agent reads first.
- `manifest.json`: inputs, steps, saves and checks, in today's file format.
- `acceptance.json`: the thresholds and the quality rubric `b-qa-gate` runs in step 6.
- `steps/`: one file per step, plus `_shared.md`.
- `scripts/`: this recipe's own guards and helpers: `card_fill.py` (the card page filler), `check_words.py`, `check_beats.py`, `segments.py`, `deliver_final.py`, `proofs.py`, `master_loudness.py`, `voiceover.py`, `frame_qa.py`, `brand_palette.py`, `cta_copy.py`, `contracts.py`.
- `templates/card.html`: the motion-graphics card page that `card_fill.py` fills.
- `test/`: the tests.
- `LEARNINGS.md`: short quality rules from earlier runs.
