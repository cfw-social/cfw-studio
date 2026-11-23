# Blocks

Building block **templates**. Each block is a `b-*` folder of instructions (`SKILL.md`), a `README.md`, supporting scripts and tests. A template teaches. A brand's bot reads it and builds its own recipe. It does not run for a brand from here.

Visual and audio treatments (transitions, caption styles, overlays, and the like) do **not** belong here; they live in [`../effects/`](../effects/).

Start a new block from [`_template/`](_template/). See [../docs/DESIGN.md](../docs/DESIGN.md) for the model and [../CONTRIBUTING.md](../CONTRIBUTING.md) for the vetting checklist.

## The eight blocks

| Block | What it does | Entry points | What it needs |
|---|---|---|---|
| [`b-audio`](b-audio/) | Speech to text with word timings (`words.json`) | `scripts/transcribe.py` | Python, whisper.cpp (`whisper-cli`), a ggml model file, ffmpeg when the input is not already 16 kHz mono WAV. No account |
| [`b-broll-sync`](b-broll-sync/) | Checks a reel's scene plan and makes a gapless beat list of cards and b-roll | `scripts/validate-scene-plan.js`, `scripts/plan.js` | Node.js 22 or newer. No packages, no network |
| [`b-heygen`](b-heygen/) | Makes an avatar narration video through the HeyGen API | `scripts/render.py` | Python, a HeyGen account with API credits |
| [`b-hyperframes`](b-hyperframes/) | Installs the pinned HyperFrames renderer, checks a page is local-only, renders it to video | `scripts/hf_install.py`, `scripts/fetch_gsap.py`, `scripts/check_local.py`, `scripts/hf_render.py` | Python, Node.js 22 or newer, npm, ffmpeg and ffprobe. Network at setup only (npm registry, a pinned browser). No account |
| [`b-kie-ai`](b-kie-ai/) | Makes one AI still image through the Kie API | `scripts/generate.py` | Python, a Kie account with credits, ffmpeg for JPEG or WEBP results |
| [`b-qa-gate`](b-qa-gate/) | Runs the mechanical checks in a recipe's `acceptance.json` and writes a scorecard | `check.py` | Python, ffmpeg and ffprobe. No network |
| [`b-reel-premium`](b-reel-premium/) | Kinetic captions, a light colour grade and sound effects for a finished 9:16 reel | `scripts/check_plan.py`, `scripts/build_comp.py`, `scripts/mux.py`, `scripts/qa.py` | Python, ffmpeg and ffprobe, and `b-hyperframes` to render the captions. No account |
| [`b-typing-ui`](b-typing-ui/) | A typing card and a hook card as page templates, with a safe filler for each | `scripts/typing_fill.py`, `scripts/hook_fill.py` | Python, `b-hyperframes` to render. Fonts installed locally |

## How a recipe refers to a block

By the relative path `../../blocks/b-<name>/`, from the recipe's own folder. For example, a recipe calls the quality gate as `../../blocks/b-qa-gate/check.py`. Recipe templates live under `recipes/` and are added separately.

## Exit codes

All blocks use the same codes:

| Code | Meaning |
|---|---|
| 0 | Done. |
| 1 | Failed. |
| 2 | Bad usage, or an unsafe path. |
| 3 | Something is missing: a tool, a key, a model. |

Two exceptions:

- `b-qa-gate` adds `4`: every check passed, but a "look at it" question is still owed. It reports a missing `ffmpeg` or `ffprobe` as `1` (a FAIL row), not `3`.
- `b-typing-ui` uses `3` only when the block's own page template is missing or has been changed.

## Words used in these docs

- An **order** is one request for one piece of content in CFW Social.
- The **work folder** is the folder a bot works in for that order.

Both can be ignored outside CFW Social. A work folder is then just the folder you run in. Every block reads and writes only inside it.

## About `block.yaml`

`block.yaml` is a later format and is optional today. Only `b-kie-ai` has one, and it is marked as not final. The `README.md` and `SKILL.md` of each block are what to read.
