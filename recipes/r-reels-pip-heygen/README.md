# r-reels-pip-heygen

A recipe **template** for a talking-head reel with a picture-in-picture speaker who is a **generated
avatar**. It is [`r-reels-pip`](../r-reels-pip/) with one difference: the person does not supply a video.
Step 0 generates it from a script, an avatar id and a voice id with the `b-heygen` block, and steps 1 to 6
are the same. A bot reads it, builds its own recipe from it, and tries it. It teaches; it does not run for
any brand by itself. (Saving the result in a brand's recipe library in CFW Social is planned, not built.)

Based on CFW Social's built-in HeyGen picture-in-picture reel recipe.

**Read this first.** The narration text is **uploaded to the provider**. The avatar and the voice must be
the brand's own, of a person who agreed to be shown and heard. Each run makes **one paid render**; a rerun
resumes the render record and is not charged twice. **Not proven with a real account**: see section 10.

## 1. What it makes

One vertical video, 1080×1920, 30 fps, H.264 video and AAC audio, 20 to 60 seconds long plus a
0.4 second freeze of the best frame at the start. The generated avatar video sits as a rounded card
with a ring in the brand colour at the bottom centre. Behind it is a full-frame background that
follows the words: your b-roll where a clip fits, text cards everywhere else. The speaker's voice is
the one audio track (the avatar's voice), never cut. Kinetic captions, a light grade and sound effects sit on top. It
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

**One provider account:** HeyGen, with API credits, and the brand's own key. The bot takes the brand's own key
from the order's private input, for the one command of step 0 only; the recipe never reads a key from a
file or the brief, and ships no avatar id, voice id or name. Only step 0 uses a provider key. Everything after step 0 runs on the
machine that makes the reel.

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
| `b-heygen` | makes the talking-head video from the narration, an avatar id and a voice id, and downloads it (step 0) | `../../blocks/b-heygen/` |
| `b-audio` | speech to text with word timings, on this machine (step 2) | `../../blocks/b-audio/` |
| `b-broll-sync` | checks your scene plan and tiles the voice bed into card and b-roll beats (step 3) | `../../blocks/b-broll-sync/` |
| `b-typing-ui` | the typing card and the hook card, filled from a text file (step 4) | `../../blocks/b-typing-ui/` |
| `b-hyperframes` | installs the pinned renderer and browser, fetches the animation library, checks every page is local-only and renders it, always with `--quiet` (steps 4 and 5) | `../../blocks/b-hyperframes/` |
| `b-reel-premium` | kinetic captions (drawn as a transparent `.mov`), the grade and the eight sound effects, from one checked plan; the footage never goes through the renderer (step 5) | `../../blocks/b-reel-premium/` |
| `b-qa-gate` | the measured checks and the looks on the finished reel, plus two interim checks (steps 1, 4 and 6) | `../../blocks/b-qa-gate/` |

## 4. The steps

```text
script ─► 0 avatar video ─► 1 voice bed ─► 2 words ─► 3 beat list ─► 4 background ─┐
(+ b-roll, CTA, outro)                                                              ▼
                       voice bed ──────────────────────────────► 5 composite ─► 6 checks ─► reel + cover + captions
```

0. **Generate the avatar video**: `b-heygen` renders the narration with the brand's avatar and voice (paid, once).
1. **Prepare footage**: crop any baked-in bar pair, seal the voice bed near -14 LUFS, once.
2. **Transcribe**: word timestamps with `b-audio`; what each b-roll clip says, if anything.
3. **Plan the beats**: you write the scene plan (the last 3 seconds on a plain card, for the end card); `b-broll-sync` checks it and tiles the bed.
4. **Build the background**: one page per card, rendered by `b-hyperframes`; b-roll cut; one silent track.
5. **Composite**: the speaker card, one end card, captions, grade and sound effects, optional outro.
6. **Final checks**: cover freeze, the `b-qa-gate` checks and looks, post captions.

`SKILL.md` is the short guide; each file in `steps/` holds the commands.

## 5. Inputs and outputs

Inputs: `script` (required, the narration, 50 to 150 words of plain prose), `avatar_id` and `voice_id`
(text; each falls back to the brand's own setting in the brief; none is shipped here), `broll` (optional clips), `cta` (optional
text or `{text, brandName, handle}`), `outro` (optional portrait clip). Options (captions, sound
effects, grade, b-roll coverage, end card and ring) are in
`steps/_shared.md`; `scripts/options.py` checks them.

Outputs: `final_video` (MP4), `cover` (PNG), `captions` (JSON). Earlier steps also save
`talking_head` (the avatar render, kept as the provider returned it), `avatar_render` (the render record, no
key; keep it so a rerun resumes instead of paying twice), `voice_track`, `transcripts`, `beat_list`, `background` and `assembled_video`.

**What leaves the machine.** Step 0 sends the narration text, the avatar id and the voice id, with the key,
to HeyGen, and downloads the video from the host HeyGen names. Nothing else is uploaded: the b-roll, the
voice track and the reel never leave the machine in steps 1 to 6.

**Step 0 in detail.** It calls `b-heygen/scripts/render.py` as that block's README documents, with
`--aspect-ratio 9:16` and `--resolution 720p` (from its fixed lists: the speaker card is 364×504 and is
filled from a portrait frame; 720p is the block's default, and higher resolutions can depend on the provider
plan) and a plain solid background, the
brand's `palette.bg` or `#0F172A`, instead of the block's default green: the colour shows around the avatar
inside the card. The key goes from the order's private input into an unexported shell variable, without
being echoed or printed, and is passed only as a per-command prefix on that one render command (or piped with
`--key-stdin`); it is never typed into the command text and never written to a file. The render is paid, once
per run: after submitting, the block writes a render record; step 0 saves it as `avatar_render.json` before it
checks the video, and a rerun that restores it resumes the same render. A failed render is never resubmitted by the script.

## 6. Network use

Step 0 is the only step that contacts a provider. After it, none of this recipe's scripts opens a
connection, and none of the other blocks does at run time as written. ffmpeg runs with only the `file`
protocol allowed (`-protocol_whitelist file` before each input of every ffmpeg and ffprobe call in the steps
and scripts).

**Step 0, every run.** What `b-heygen` states:

| Host | When | What is sent |
|---|---|---|
| `api.heygen.com` | create the video and poll it | the key (in a header), the ids and the narration text. HTTPS only, no redirect followed |
| the host in HeyGen's `video_url` reply (HeyGen's own file host; the block does not name it) | download | nothing but the request; no key; HTTPS required, no redirect, a size cap |

**Setup, once per work folder.** Exactly what the blocks state:

| When | Host | What |
|---|---|---|
| `b-hyperframes` `hf_install.py` | `registry.npmjs.org` | `hyperframes` 0.7.5 and its dependencies, from a lockfile with integrity hashes, installed inside the work folder with install scripts off. About 150 MB downloaded, 450 MB on disk (observed on macOS, Apple silicon) |
| `hf_install.py` (by default) | `storage.googleapis.com` | the pinned Chrome headless shell 131.0.6778.85, an 88 MB zip, into the work folder's cache |
| `b-hyperframes` `fetch_gsap.py` | `registry.npmjs.org` | the `gsap` 3.14.2 tarball (1.7 MB), checked against a pinned hash before use |
| `b-audio`, only with `--allow-download` and a missing model | `huggingface.co` | one ggml model file, checked against a checksum you give. Without that flag nothing is downloaded |

**Run time after step 0.** None. `b-hyperframes` checks each page before it renders (no address, no remote
font, no script that builds a request), and the fillers refuse any text that holds a web address. That
block sampled renders with the pinned browser and saw no connection; an installed Chrome makes its own
background connections, which is why the pinned browser is the default. The renderer's telemetry and update checks are switched off by that block. Render on a
machine with no network when any text in the order is not yours.

## 7. How to run the tests

From the repository root, with the blocks present in `blocks/` and the base recipe beside this one:

```bash
python3 -B -I recipes/r-reels-pip-heygen/test/test_generate_step.py -v
python3 -B -I recipes/r-reels-pip-heygen/test/test_shared_files.py -v
python3 -B -I recipes/r-reels-pip-heygen/test/test_card_and_cta.py -v
python3 -B -I recipes/r-reels-pip-heygen/test/test_scripts.py -v
python3 -B -I recipes/r-reels-pip-heygen/test/test_recipe_files.py -v
bash recipes/r-reels-pip-heygen/scripts/verify-skill.sh
```

They need ffmpeg and Python only (a few tests also read the `b-hyperframes` and `b-typing-ui` blocks and are
skipped by name if those are missing). No network beyond 127.0.0.1, no account, no key, no private file, no
real footage, no render.

- `test_generate_step.py` runs step 00's own commands against a small local fake server standing in for the
  provider (the block's test-only `--base-url` option is added to the render command, nothing else). It
  checks the request (9:16, 720p, the brand's background colour, the ids and the text), one submit per run,
  that a rerun with the render record resumes instead of submitting again, that a missing key sends nothing,
  that missing or malformed inputs (including ids with shell characters) ask and send nothing and run nothing,
  that a render of the wrong length or without audio fails (it is never an ask), saves no `talking_head`, keeps the
  render record so a rerun resumes without a second charge, and that the key appears in no output and
  no file and is not sent to the file host.
- `test_shared_files.py` fails if any script, page template or script test shared with `../r-reels-pip`
  differs from the base recipe's copy, so the two cannot drift apart silently.
- `test_card_and_cta.py` and `test_scripts.py` are the base recipe's tests, unchanged. `test_recipe_files.py`
  is adapted (names, `b-heygen`) and also runs the real `blocks/b-qa-gate/check.py` on a generated reel with
  this recipe's `acceptance.json`, proving that no check kind is "not supported", and runs step 6's gate and
  finalize commands to show that a "no", a missing answer or a failed gate stops the step with nothing in `saves/`.

Results when written: 9 tests in `test_generate_step.py`, 3 in `test_shared_files.py`, 33 in
`test_card_and_cta.py`, 46 in `test_scripts.py` and 22 in `test_recipe_files.py` passed (113 in all, none
skipped), and 46 of 46 static checks of `verify-skill.sh` passed.

## 8. Sample

No sample is stored here. The one run of the shared steps made for the base recipe used stand-in media, not a
generated avatar, and its 4.8 MB reel is not stored. A sample of this recipe needs a HeyGen account with API
credits and the brand's own key, an avatar id and a voice id of a person who agreed, a narration of 50 to
150 words, the tools in section 2 and a few minutes of render time. It costs one paid render.

## 9. Terms used by CFW Social

You can ignore these outside CFW Social.

- **order**: one request to make a reel; **brief**: its `brief.json`; **step workdir**: the folder a
  step runs in.
- **`manifest.json`**: the recipe's description in today's CFW format: `steps`, `saves` (files a step
  must write), `checks` (tests a runner runs on them), `maxCheckRetries`, `canAsk` and
  `needs_input.json` (a step asking the person for a missing input), `neededAt`, `runsOn`, `weight`.
  `needs.os` says `macos`: the shared steps were run on macOS in the base recipe; this variant has not been run
  start to finish, and its first step has run only against a local fake server. The value says where the steps
  are expected to work; it is not a record of testing. The manifest's tool list does not name the browser,
  because `b-hyperframes` downloads its own pinned one at setup (section 6).
- **`order-brand-v2`**: how CFW Social hands a brand to a recipe, as `brief.json.brand`. Its optional
  `heygen.avatarId` and `heygen.voiceId` are what step 0 falls back to when the order has no avatar or voice id.
- **`acceptance.json`**: the checks `b-qa-gate` applies.

## 10. Limits and known gaps

- **Step 0 has not been run against a real HeyGen account.** The block and this recipe were tested only against
  a local fake server built from HeyGen's public v3 pages. Before the first paid run, check the request
  (`background`, `voice_settings`, `resolution`) against HeyGen's live page; whether 720p at 9:16 is allowed
  for a given avatar or plan is not known.
- The script text is uploaded to the provider. The avatar and the voice must be the brand's own, of a person
  who agreed; the recipe cannot check that.
- Each run makes one paid render. The render record (`avatar_render.json`) is what prevents a second charge on
  a rerun: lose it, and a rerun is a new render. A failed render is never resubmitted by the script, and
  deleting its record starts a new paid one.
- The video link is short-lived: download soon after completion.
- The narration cap of 150 words is this recipe's own, to land a 20 to 60 s video; the block's cap is 5000
  characters. The length of the avatar's speech is not known until the render is done, so a script can still
  produce a video outside 20 to 60 s: step 0 then fails (inputs missing or invalid before the render are asked
  for; a wrong-length video after it is a failure), keeps the render record so nothing is paid twice, saves no
  `talking_head`, and leaves the decision about a new script and a new render to the person.
- A solid background behind the avatar shows inside the speaker card. This recipe does not key it out.
- **A scorecard is a record, not proof.** Someone who edits it by hand can make it pass; `check_delivery.py`
  checks the recorded result against the file, not the pictures.
- The manifest's `needs.os` value says where the steps are expected to work; it is not a record of testing.
  This edition was run on macOS only, and this variant has not been run start to finish.
- Steps 1 to 6 are the base recipe's. They were run once end to end on macOS (Apple silicon) with stand-in
  media and real speech-to-text (see `../r-reels-pip/`); they were not run on a generated avatar video. Not
  exercised there: a real face and recorded speech, `--hint-file`, the outro, ring `0`, captions off, sound
  effects off, a planned `cta` beat, a brand font file, native Windows and Linux. No bot app is recorded as
  having run either recipe.
- The "face whole in the card" look cannot be judged on stand-in media.
- `b-reel-premium`'s caption render can print a few "overlapping tweens" lint warnings, and `b-typing-ui`'s
  typing card makes the validator print contrast warnings for its dim text; both renders finished. Check a
  frame before trusting a recipe.
- A caption phrase can still be split in a way the repair script does not catch. Reading the captions is your job.
- HyperFrames renders run page scripts, so scripts cannot be turned off. Safety rests on escaping every text,
  the local-only check, and the browser's own limits (HyperFrames starts it without its sandbox, as
  `b-hyperframes` says).
- Captions are Latin script only. The outro is joined after the polished reel and gets no captions, grade or
  sound effects; that is intended.
- No second AI agent is started by any step.
