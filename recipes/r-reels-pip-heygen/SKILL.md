---
name: r-reels-pip-heygen
description: Generate a talking-head video from a script with the brand's own avatar and voice (HeyGen, through b-heygen), then turn it into a 9:16 reel where the speaker sits as a rounded, ringed card at the bottom centre over a full-frame background that follows the words (b-roll where a clip fits, text cards elsewhere). The avatar's voice is the single audio bed, never cut and never replaced. The same as r-reels-pip after its first step. A recipe template: a bot reads it and builds its own recipe from it.
when-to-use: Use when there is no recording of the speaker but there is a script, and the brand has its own avatar and voice at the provider (of a person who agreed). Use r-reels-pip when the person has their own recording.
kind: pipeline
produces:
  dish: Talking-Head PIP Reel
  format: 9:16 vertical video, 1080x1920, 30 fps
  duration: 20-60 s (+0.4 s cover frame)
inputs: [script, avatar_id, voice_id, broll, cta, outro]
blocks: [b-heygen, b-audio, b-broll-sync, b-typing-ui, b-reel-premium, b-hyperframes, b-qa-gate]
---

# r-reels-pip-heygen: bottom picture-in-picture reel from a generated avatar video

A template. Read `README.md` first for what it needs, what it downloads and what is not proven.
This file tells a bot how the six steps fit together; each file in `steps/` holds the commands and
is the only place they are written.

## What it makes

One 1080×1920 H.264/AAC MP4: the generated avatar video as a rounded, ringed card at the bottom centre
(364×504, 110 px above the bottom edge) over a background that restates what is said. The voice is
one unbroken bed, normalised once. The reel opens on a 0.4 s freeze of the best content frame and
ends on one call to action.

```text
┌──────────────────────────┐ 1080×1920
│ background: cards, b-roll│ graphics stay above y≈1040
│ captions (band y 980-1240)│
│      ┌────────────┐      │ card, ring in the brand colour
│      │ TALKING HEAD│     │ 110 px above the bottom edge
│      └────────────┘      │
└──────────────────────────┘
```

## Where things live

```text
RECIPE_DIR=<this folder>                 # recipes/r-reels-pip-heygen
BLOCKS_DIR="$RECIPE_DIR/../../blocks"    # the building blocks (b-*)
```

`steps/_shared.md` holds the workdir layout, the brand rules, the options and the safety rules.
Read it before any step.

## The steps

| # | Step | File | Saves | Blocks it calls |
|---|---|---|---|---|
| 0 | Generate the avatar video | `steps/00-generate-avatar.md` | `talking_head`, `avatar_render` | `b-heygen` |
| 1 | Prepare footage | `steps/01-prepare-footage.md` | `voice_track` | `b-qa-gate` (interim check) |
| 2 | Transcribe | `steps/02-transcribe.md` | `transcripts` | `b-audio` |
| 3 | Plan the background beats | `steps/03-plan-beats.md` | `beat_list` | `b-broll-sync` |
| 4 | Build the background | `steps/04-build-background.md` | `background` | `b-hyperframes`, `b-typing-ui`, `b-qa-gate` |
| 5 | Composite | `steps/05-composite.md` | `assembled_video` | `b-hyperframes`, `b-reel-premium` |
| 6 | Final checks and captions | `steps/06-final-checks.md` | `final_video`, `cover`, `captions` | `b-qa-gate` |

```text
script ─► 0 avatar video ─► 1 voice bed ─► 2 words ─► 3 beat list ─► 4 background ─┐
(+ b-roll, CTA, outro)                                                              ▼
                       voice bed ──────────────────────────────► 5 composite ─► 6 checks ─► reel + cover + captions
```

## Rules that make it work (each is enforced in a step)

- **Step 0 is the only step that calls a provider, and it costs money.** The key comes from your own
  connection for that one command; the avatar and voice are the brand's own; a rerun resumes the render
  record instead of paying twice; no id is ever invented.
- **The talking head is the audio and the length master.** Loudness is normalised once (step 1).
  Nothing later normalises it. Effects are mixed under it with `amix` `normalize=0`.
- **The card is filled, not fitted:** scale to cover, then a top-biased crop. Its mask and ring come
  from `scripts/pip_card.py` (standard library only).
- **Nothing enters the card's zone.** Graphics stay above y≈1040; captions sit in a 260 px band at
  y 980 to 1240.
- **One call to action.** A planned `cta` scene wins; otherwise one end card (a `.mov` with alpha so
  the scrim stays translucent) covers the last seconds. No copy means no card; no handle means no
  handle line. Never invent either.
- **The bot plans; no second agent runs.** Card copy, b-roll placement and the caption plan are
  written by you. `b-broll-sync` has no ordering that asks a model.
- **Order text is data.** It reaches a page only through a filler that escapes it, and never a shell
  command. Every page is checked local-only by `b-hyperframes` before it renders.
- **Verify every stage.** Probe each output, look at frames, and never deliver a reel that fails a
  check. A check kind `b-qa-gate` does not know is a failure, not a skip.

## Gotchas

- Render only through `b-hyperframes`' `hf_render.py`; never `npx hyperframes` directly.
- Fonts Oswald, Inter and JetBrains Mono must be installed where the render runs; pages declare them
  with a local `@font-face` and fetch nothing. Without them a generic font is used and widths differ.
- The end card needs `--format mov`; an MP4 card has no alpha. Step 5 checks the pixel format.
- Leave a hook's `sub` and a typing card's `bottom_tag` empty: they sit where the captions go.
- With no b-roll the background is all cards. That is valid, not degraded.

## Inputs and options

Inputs: `script`, `avatar_id`, `voice_id` (required), `broll` (optional), `cta` (optional text), `outro` (optional
clip). Options live in `brief.json.options`; `scripts/options.py` checks them and `steps/_shared.md`
lists the defaults.
