# r-reels-spotlight

A template that teaches. Your bot reads it, understands the method, and builds its own version
for your brand. Nothing here runs for a brand by itself. Based on CFW Social's built-in spotlight reel recipe.

## 1. What it makes

One full-frame vertical reel (1080×1920, 30 fps, H.264 + AAC, 20 to 65 seconds) from one
talking-head clip. The speaker's voice is a single unbroken audio bed. Word-synced kinetic
captions, sound effects and a colour grade ride over the whole reel. Motion-graphics takeovers (and
optional b-roll cutaways you place) cover the picture at planned beats. A money-shot cover frame sits at
frame 0, and a branded end card closes the reel. It also writes the cover image and post text per
platform.

```text
audio:    ████████████████████████████████████████████  one voice bed, never cut
video:    [speaker][== GRAPHICS / B-ROLL ==][speaker][== GRAPHICS ==][speaker + END CARD]
captions: ▁▂▃ word-synced captions over everything ▃▂▁
frame 0:  money-shot cover (0.4 s freeze), then the full reel
```

**Your video stays on your machine.** The talking-head clip is read from disk and processed with
`ffmpeg`, a local speech-to-text tool and a local render. No step uploads it, and no step sends it,
its audio or its words to any service (see section 6 for the downloads that do happen).

## 2. What you need

| Tool | Version | Used for |
|---|---|---|
| Python | 3.10 or newer; standard library only | the recipe's scripts and the blocks' scripts |
| `ffmpeg` and `ffprobe` | 6 or newer, with libx264 and aac; run with 8.1 | bed, grade, mux, overlays, checks (`b-audio` and `b-qa-gate` use them too) |
| Node.js | 22 or newer (HyperFrames requires it); run with 25.9.0 | the renderer and the b-roll planner |
| `hyperframes` (npm) | `0.7.5`, pinned and installed inside the work folder by `b-hyperframes` | renders the takeover, caption and end-card pages |
| `gsap` (npm) | `3.14.2`, pinned and fetched by `b-hyperframes`. Third-party code under GreenSock's standard licence (gsap.com/standard-license); it is never copied into this repository | animation inside the pages |
| Chrome headless shell | exactly 131.0.6778.85, pinned by `b-hyperframes`, downloaded by its install into the work folder and checked at every render | rendering |
| whisper.cpp (`whisper-cli`) | your own setup (`STT_VERSION`); run with 1.8.4 | speech to text, through `b-audio` |
| A ggml model file | for example `ggml-base.en.bin`, your own setup (`STT_MODEL`); an order never supplies it | speech to text |
| Fonts Oswald, Inter, JetBrains Mono | installed on the machine that renders (SIL Open Font Licence); none is bundled | the card pages. Each is declared with a local `@font-face`; a missing one falls back to a generic family and the letter shapes differ |

**Provider accounts: none.** This recipe uses no paid voice, video or model provider and reads no
key. The talking-head clip is supplied by the order. (In CFW Social's order format an alternative
input can have a server write the script first; those server steps are not part of this template.)

## 3. Blocks it uses

Blocks live in `../../blocks/`. This recipe reaches them only by that relative path.

| Block | Why | Path |
|---|---|---|
| `b-audio` | Speech to text with word timings (step 02), also for b-roll cues | `../../blocks/b-audio/` |
| `b-hyperframes` | The one place that installs, checks and renders: pinned renderer, pinned GSAP, the local-only check, the render wrapper | `../../blocks/b-hyperframes/` |
| `b-reel-premium` | Plan check, kinetic caption page, grade and sound effects under the voice, QA frames; holds the eight sound effects | `../../blocks/b-reel-premium/` |
| `b-qa-gate` | The mechanical checks and the looks the bot answers, run over `acceptance.json` | `../../blocks/b-qa-gate/` |
| `b-broll-sync` | Checks the bot's scene plan and lays out the beat list (only when b-roll is supplied) | `../../blocks/b-broll-sync/` |
| `b-typing-ui` | The typed-prompt takeover scene, filled from a text file (only for a `tk-typing-ui` takeover) | `../../blocks/b-typing-ui/` |

The recipe carries no copy of the sound effects, no transcription script and no renderer steps.

## 4. The steps

```text
 talking_head ─> 01 prepare ─> 02 transcribe ─> 03 plan edit ──┬─> 05 render ─> 06 assemble ─> 07 final
   (1 video)     voice_track     b-audio         edit_plan     │   b-hyperframes  b-reel-premium   cover, b-qa-gate,
                 b-qa-gate       b-qa-gate       plan_guard +  │   b-typing-ui    b-hyperframes    delivery gate,
                                                 check_plan    │   b-qa-gate      end card         post text
   broll (0..n) ───────────────────────────> 04 plan b-roll ───┘
                                              b-broll-sync (you pin clips to words)
```

Each step has a file in `steps/` with what it receives, what it must produce, how, and the checks
that gate it. `steps/_shared.md` holds the rules every step shares. The recipe's own guards for the
edit plan (`scripts/plan_guard.py`) and the b-roll beat list (`scripts/beats_guard.py`) are scripts the
steps run; they are not checks in `acceptance.json`, because the gate does not own them.

## 5. Inputs and outputs

| Input | Required | Notes |
|---|---|---|
| `talking_head` | yes | one video, 20 to 60 seconds, real face and voice; its audio is the voice bed |
| `broll` | no | any number of clips; when none, step 04 is skipped and the reel has graphics takeovers only |
| `cta` | no | end-card copy as `{"text","brandName","handle"}` or typed text; with no text there is no end card and no silent tail |
| `brief.json` | yes | intent, target platforms, brand (name, palette, optional `cta` and `handle`) and `options` |
| a whisper.cpp model file | yes | part of the bot's own setup, not of the order; a download only if the person says yes (section 6) |

Outputs: `final_video.mp4` (cover freeze + reel), `cover.png`, `captions.json` (post text per
platform). The options and their defaults are in `steps/_shared.md`.

## 6. Network use

| When | Host | What |
|---|---|---|
| Setup, `hf_install.py` | `registry.npmjs.org` | `hyperframes@0.7.5` and its dependencies from the block's lockfile, installed with scripts off. Observed by the block: 172 requests, about 150 MB downloaded, 450 MB on disk |
| Setup, `hf_install.py` | `storage.googleapis.com` (`chrome-for-testing-public`) | the pinned Chrome headless shell 131.0.6778.85, an 88 MB zip (about 172 MB unpacked), into the work folder's cache |
| Setup, `fetch_gsap.py` | `registry.npmjs.org` | the `gsap@3.14.2` version record and tarball (about 1.7 MB), checked against pinned hashes |
| Setup, only if the person says yes | `huggingface.co` | the whisper model, through `b-audio --allow-download`, checked against a checksum the person gives. Otherwise no download |
| Run time | none | the recipe's scripts and the blocks' scripts open no connection. `b-hyperframes` refuses a page that would load anything from the network and renders in its own pinned browser; its README says what was observed and what was not |

These are the hosts the blocks state; this recipe adds none. Nothing sends your video, its audio or
its words anywhere. No script reads a key, an env file or another brand's folder, and none writes
outside the work folder.

## 7. How to run the tests

```bash
cd recipes/r-reels-spotlight
for t in test/test_*.py; do python3 -I "$t" || break; done
```

They need `ffmpeg` and `ffprobe` and, for the page and gate tests, the blocks beside the recipe (the
repository layout). No network, no provider, no private file, no real footage (media is generated with
ffmpeg test sources). They check the helper scripts, the escaping of text into pages, that every
filled page passes `b-hyperframes`' local-only check (including hostile text), that every check in
`acceptance.json` runs in the real `b-qa-gate` and none comes back unsupported, the safety rules (no
`eval`, no shell string built from order text, no direct renderer call), and that the files agree with
each other. They do not render a reel.

## 8. Sample

No rendered reel is attached. The recipe was run end to end once in a scratch folder on stand-in media
(see section 10), and the 9.4 MB result is not stored here. A real sample needs a talking-head clip
with real speech, a whisper.cpp model, and the tools in section 2. It needs no paid provider.

## 9. Terms used by CFW Social

You can ignore these outside CFW Social.

- **Order**: one request to make something, with its inputs and a brief.
- **Step work folder**: the folder one step runs in (`inputs/`, `prior/`, `saves/`, `work/`, `brief.json`).
- **Saves / prior**: what a step writes (`saves/`) and what the next step reads (`prior/`).
- **Runner**: whatever runs the steps and their checks (the step files call it the runner).
- **`canAsk`**: an input a step may ask the owner for by writing `needs_input.json`.
- **`manifest.json`, `acceptance.json`**: CFW Social's order format: the inputs, steps and checks. Kept as it is. The `research` and `script` steps in the manifest run on a server there and are not part of this template.
- **`order-brand-v2`** (a manifest feature name): a flag in CFW Social's order format for how the brand reaches the recipe.
- **Reviews**: where a finished reel lands for the owner to look at.

## 10. Limits and known gaps

**What was run for real.** Once, on one Mac (Apple silicon, macOS), with Python 3.15.2, Node 25.9.0,
ffmpeg 8.1 and whisper.cpp 1.8.4 with `ggml-base.en.bin`: all seven steps in order, in one fresh scratch
folder with a fresh `hf_install.py`, following the step files. The talking head was a colour-bar picture
with a voice made by the Mac's built-in text-to-speech (so `b-audio` recognised real speech, 91 words,
with a short hint file and the script checked against it), and the b-roll was three generated clips. Four
takeovers (keyword, stat, list and typing card), three b-roll windows, transparent captions laid over the
graded footage, ten sound effects, the end card, the cover freeze and `b-qa-gate` with its looks answered
all ran. The final file was 1080×1920, 30 fps, 32.9 s, 9.4 MB, and the gate's final scorecard was PASS.
Not run: a real face, a real brand, Windows, Linux, any model other than `ggml-base.en.bin`, non-English
speech, the `letterbox` layout, `captions: off`, `sfx: off`, a music file, a brand font file, a reel with
no b-roll and the b-roll `even` order. Other claims in this folder rest on the blocks' own statements and
on the tests.

- **Look answers are the bot's word.** The gate records the answers; it cannot prove a bot looked. The
  scorecard is not signed. A scorecard is a record, not proof; someone who edits it by hand can make it pass.
  The delivery check refuses a card whose verdict alone was changed (it checks the counts, every row, the spec and the file's hash and size), and the video reaches `saves/` only after that check passes.
- **Render safety.** HyperFrames pages need scripts to run, so a render with scripts switched off is
  not possible. Text from the order, brand or transcript is escaped before it enters a page, and
  `b-hyperframes` refuses a page that loads from the network. That check is a text scan, not a sandbox,
  and the browser runs without its own sandbox: for text you do not trust, render on a machine with no
  network.
- **Fonts.** The takeover and end-card pages name Oswald, Inter and JetBrains Mono. If one is not
  installed the render falls back to a generic family and the look changes. The caption page uses the
  generic sans-serif unless you give it a font file.
- **Renderer warnings.** The takeover pages render with no lint warnings; the validate step still prints contrast warnings for the decorative text on the cards and for the captions, which are not changed here.
- **Speech hint.** The hint file is a short list of names and unusual words (the brand name and such words from the script), never the whole script. A hint holding the whole script made whisper.cpp repeat its last sentence in a test, so the recipe never sends one.
- **B-roll.** The bot decides which clip goes with which words by writing `broll` scenes. `as-given` and
  `even` only place clips by position. The graphic scenes in the scene plan only feed the planner; the
  takeover content comes from the edit plan.
- **Install and disk size.** Each fresh work folder installs about 450 MB of renderer and 170 MB of browser. The transparent caption render (`work/premium/captions.mov`) was about 160 MB for a 33 s reel and took about 1.5 minutes after a 1 minute takeover render; delete it when the reel is done.
- **Operating system.** The manifest value says where the steps are expected to work; it is not a record of
  testing. This edition was run on macOS only. The blocks say Linux and native Windows are not proven.
- **Language.** Captions and cards are Latin script only (non-Latin words are transliterated, never
  translated). The brand-name guard in `scripts/takeover_brand.py` uses an English word list.
- **Saving needs a permission:** the CFW Social tools that let a brand's bot save, try and lock in its own
  version of this recipe work only for a key made with the "Save its own recipes" permission. Post tags and a
  "Your recipes" page are planned, not built.
