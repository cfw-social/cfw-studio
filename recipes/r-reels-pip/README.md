# r-reels-pip

A recipe **template** for a talking-head reel with a picture-in-picture speaker. A bot reads it,
builds its own recipe from it, and tries it. It teaches; it does not run for any brand by itself.
(Saving the result in a brand's recipe library in CFW Social is planned, not built.)

Based on CFW Social's built-in picture-in-picture reel recipe.

## 1. What it makes

One vertical video, 1080×1920, 30 fps, H.264 video and AAC audio, 20 to 60 seconds long plus a
0.4 second freeze of the best frame at the start. The speaker's own clip sits as a rounded card
with a ring in the brand colour at the bottom centre. Behind it is a full-frame background that
follows the words: your b-roll where a clip fits, text cards everywhere else. The speaker's voice is
the one audio track, never cut. Kinetic captions, a light grade and sound effects sit on top. It
also saves the cover frame (1080×1920 PNG) and a `captions.json` with post text per platform.

```text
┌──────────────────────────┐
│ background: cards, b-roll│   graphics stay above y≈1040
│ captions (band y 980-1240)│
│      ┌────────────┐      │   364×504 rounded card, ring in the brand colour,
│      │ the speaker│      │   110 px above the bottom edge
│      └────────────┘      │
└──────────────────────────┘
```

## 2. What you need

No provider account and no provider key. Everything runs on the machine that makes the reel.

| Tool | Version | Used for |
|---|---|---|
| ffmpeg and ffprobe | 6 or newer (run on 8.1) | all video and audio work, and `b-audio`'s conversion |
| Node.js | 22 or newer (run on 25.9.0) | the beat planner, and the renderer HyperFrames needs |
| Python 3 | 3.10 or newer, standard library only (run on 3.15.2) | every script and test |
| `whisper-cli` (whisper.cpp) and one ggml model file | the version you name; `b-audio` and this recipe were run with 1.8.4 and `ggml-base.en.bin` | speech to text. The model file and the version are facts of the bot's own machine setup (`STT_MODEL`, `STT_VERSION`); an order never supplies them |
| `hyperframes` (npm) | 0.7.5, pinned and installed inside the work folder by `b-hyperframes` | renders the cards, captions and end card |
| `gsap` (npm) | 3.14.2, fetched by `b-hyperframes`; third-party code under GreenSock's standard licence, never copied into this repository | the animation timeline of every page |
| Chrome headless shell | exactly 131.0.6778.85, downloaded by `hf_install.py` into the work folder (88 MB); an installed Chrome is not used unless the person chooses it | the browser HyperFrames renders in |

Fonts Oswald, Inter and JetBrains Mono (SIL Open Font Licence) should be installed on the machine
that renders; each page declares them with a local `@font-face` and nothing is fetched. Without them
the renderer falls back to a generic font and the letter shapes and widths differ. The sound effects
are the eight files in `../../blocks/b-reel-premium/assets/sfx/`; the repository owner supplies
them. Captions use the generic sans-serif unless the plan names a font file (then its licence goes here).

The brand comes in `brief.json.brand` (name, optional handle and call to action, accent colour). A bot
running for a brand uses that brand's own settings; nothing here holds a brand.

## 3. Blocks it uses

| Block | Why | Path |
|---|---|---|
| `b-audio` | speech to text with word timings, on this machine (step 2) | `../../blocks/b-audio/` |
| `b-broll-sync` | checks your scene plan and tiles the voice bed into card and b-roll beats (step 3) | `../../blocks/b-broll-sync/` |
| `b-typing-ui` | the typing card and the hook card, filled from a text file (step 4) | `../../blocks/b-typing-ui/` |
| `b-hyperframes` | installs the pinned renderer and browser, fetches the animation library, checks every page is local-only and renders it, always with `--quiet` (steps 4 and 5) | `../../blocks/b-hyperframes/` |
| `b-reel-premium` | kinetic captions (drawn as a transparent `.mov`), the grade and the eight sound effects, from one checked plan; the footage never goes through the renderer (step 5) | `../../blocks/b-reel-premium/` |
| `b-qa-gate` | the measured checks and the looks on the finished reel, plus two interim checks (steps 1, 4 and 6) | `../../blocks/b-qa-gate/` |

## 4. The steps

```text
talking head ─► 1 voice bed ─► 2 words ─► 3 beat list ─► 4 background ─┐
(+ b-roll, CTA, outro)                                                  ▼
                       voice bed ──────────────────────────────► 5 composite ─► 6 checks ─► reel + cover + captions
```

1. **Prepare footage**: crop any baked-in bar pair, seal the voice bed near -14 LUFS, once.
2. **Transcribe**: word timestamps with `b-audio`; what each b-roll clip says, if anything.
3. **Plan the beats**: you write the scene plan (the last 3 seconds on a plain card, for the end card); `b-broll-sync` checks it and tiles the bed.
4. **Build the background**: one page per card, rendered by `b-hyperframes`; b-roll cut; one silent track.
5. **Composite**: the speaker card, one end card, captions, grade and sound effects, optional outro.
6. **Final checks**: cover freeze, the `b-qa-gate` checks and looks, post captions.

`SKILL.md` is the short guide; each file in `steps/` holds the commands.

## 5. Inputs and outputs

Inputs: `talking_head` (required, one video, 20 to 60 s), `broll` (optional clips), `cta` (optional
text or `{text, brandName, handle}`), `outro` (optional portrait clip). Options (captions, sound
effects, grade, b-roll coverage, end card and ring) are in
`steps/_shared.md`; `scripts/options.py` checks them.

Outputs: `final_video` (MP4), `cover` (PNG), `captions` (JSON). Earlier steps also save
`voice_track`, `transcripts`, `beat_list`, `background` and `assembled_video`.

**The talking head stays on the machine.** Every step reads and writes local files. No step uploads
the video, the voice, the b-roll or the reel, and no step uses a provider. Only setup downloads
(below) leave the machine.

## 6. Network use

None of this recipe's own scripts opens a connection, and none of the blocks it calls does at run
time as written. Every ffmpeg and ffprobe call in the steps and scripts allows only the `file` protocol
(`-protocol_whitelist file` before each input).

**Setup, once per work folder.** Exactly what the blocks state:

| When | Host | What |
|---|---|---|
| `b-hyperframes` `hf_install.py` | `registry.npmjs.org` | `hyperframes` 0.7.5 and its dependencies, from a lockfile with integrity hashes, installed inside the work folder with install scripts off. About 150 MB downloaded, 450 MB on disk (observed on macOS, Apple silicon) |
| `hf_install.py` (by default) | `storage.googleapis.com` | the pinned Chrome headless shell 131.0.6778.85, an 88 MB zip, into the work folder's cache |
| `b-hyperframes` `fetch_gsap.py` | `registry.npmjs.org` | the `gsap` 3.14.2 tarball (1.7 MB), checked against a pinned hash before use |
| `b-audio`, only with `--allow-download` and a missing model | `huggingface.co` | one ggml model file, checked against a checksum you give. Without that flag nothing is downloaded |

**Run time.** None. `b-hyperframes` checks each page before it renders (no address, no remote
font, no script that builds a request), and the fillers refuse any text that holds a web address. That
block sampled renders with the pinned browser and saw no connection; an installed Chrome makes its own
background connections, which is why the pinned browser is the default. The renderer's telemetry and update checks are switched off by that block. Render on a
machine with no network when any text in the order is not yours.

## 7. How to run the tests

From the repository root, with the blocks present in `blocks/`:

```bash
python3 -B -I recipes/r-reels-pip/test/test_card_and_cta.py -v
python3 -B -I recipes/r-reels-pip/test/test_scripts.py -v
python3 -B -I recipes/r-reels-pip/test/test_recipe_files.py -v
bash recipes/r-reels-pip/scripts/verify-skill.sh
```

They need ffmpeg and Python only (a few tests also read the `b-hyperframes` and `b-typing-ui`
blocks and are skipped by name if those are missing). No network, no paid account, no private file,
no real footage, no render: the media is generated with ffmpeg, the animation library is a one-line
stand-in, and the local-only check of `b-hyperframes` is run on every filled page. `test_recipe_files.py`
also runs the real `blocks/b-qa-gate/check.py` on a generated reel with this recipe's `acceptance.json`
and proves that no check kind is "not supported"; it also runs step 6's own gate and finalize commands and checks
that a "no", a missing answer or a failed gate stops the step with nothing in `saves/`. Results when written: 33 tests in `test_card_and_cta.py`,
46 in `test_scripts.py` and 22 in `test_recipe_files.py` passed (101 in all, none skipped), and 42 of 42 static
checks of `verify-skill.sh` passed.

## 8. Sample

No sample video is stored here. The one reel made while writing this edition is 4.8 MB, over the size
a repository should carry, and it was made from stand-in media (see "Limits"). To make a sample you
need a talking-head clip with clear speech (20 to 60 s), the tools in section 2, a whisper.cpp model
file and a few minutes of render time (plus the browser download on a new work folder). It needs no paid account.

## 9. Terms used by CFW Social

You can ignore these outside CFW Social.

- **order**: one request to make a reel; **brief**: its `brief.json`; **step workdir**: the folder a
  step runs in.
- **`manifest.json`**: the recipe's description in today's CFW format: `steps`, `saves` (files a step
  must write), `checks` (tests a runner runs on them), `maxCheckRetries`, `canAsk` and
  `needs_input.json` (a step asking the person for a missing input), `neededAt`, `runsOn`, `weight`.
  `needs.os` says `macos`: it says where the steps are expected to work. It is not a record of testing;
  this edition was run on macOS only. The manifest's tool list does not name the browser, because
  `b-hyperframes` downloads its own pinned one at setup (section 6).
- **`order-brand-v2`**: how CFW Social hands a brand to a recipe, as `brief.json.brand`.
- **`acceptance.json`**: the checks `b-qa-gate` applies.

## 10. Limits and known gaps

- Planned, not built: CFW Social's recipe library for a brand, and the tools to save a recipe in it.
- **A scorecard is a record, not proof.** Someone who edits it by hand can make it pass; `check_delivery.py`
  checks the recorded result against the file, not the pictures.
- The manifest's `needs.os` value says where the steps are expected to work; it is not a record of testing.
  This edition was run on macOS only.
- **One end-to-end run was made on macOS (Apple silicon), with a fresh `hf_install.py`.** The talking head
  was a generated colour-bar picture carrying real speech made with the macOS `say` command; the speech
  went through `b-audio` with whisper.cpp 1.8.4 and `ggml-base.en.bin` (73 words, all picked up). The b-roll
  was two flat colour clips. The cards, end card, captions, grade and sound effects were rendered for
  real, and the reel (a 24 s, 1080×1920 file) finished with `b-qa-gate` and `--finalize`. Not exercised: a
  real face and real recorded speech, `--hint-file`, the outro, ring `0`, captions off, sound effects off,
  a planned `cta` beat, a hook `sub` or typing `bottom_tag` (left empty on purpose), a brand font file,
  native Windows and Linux. No bot app is recorded as having run it.
- The "face whole in the card" look cannot be judged on a colour-bar picture. It was answered with a note
  that says so.
- `b-reel-premium`'s caption render can still print a few "overlapping tweens" lint warnings at the
  boundary between two caption groups (four in the run); the render finished and the captions looked
  right. `b-typing-ui`'s typing card makes the validator print contrast warnings for its dim text.
  Check a frame before trusting a recipe.
- A phrase can still be split in a way the repair script does not catch (it knows prepositions,
  articles, conjunctions and auxiliaries only). Reading the captions is your job.
- HyperFrames renders run page scripts, so scripts cannot be turned off. Safety rests on escaping
  every text, the local-only check, and the browser's own limits (HyperFrames starts it without its
  sandbox, as `b-hyperframes` says).
- Captions are Latin script only (transliterate, never translate); `b-reel-premium` refuses others.
- The outro is joined after the polished reel, so it gets neither captions, grade nor sound effects. That is intended.
- No second AI agent is started by any step.
- `whisper-cli` cannot report its own version; you read it from your package manager and it is recorded
  beside the words. Word times are good to about 0.1 to 0.2 s.
