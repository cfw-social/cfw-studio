---
name: r-ai-character
description: Make a character-consistent set of 3 to 6 portrait scene images (1080x1920) that tell a short visual story. One locked character reference anchors every scene, and every scene is checked for drift.
disable-model-invocation: true
argument-hint: "[story concept] [character description] [human|plush] [scene count]"
kind: pipeline
visibility: catalog
providers: kie
produces:
  format: ordered 9:16 scene images
  count: 3-6
inputs: [story_concept, character_description]
dependsOn: [b-kie-ai, b-qa-gate]
requires: python3, ffmpeg, imagemagick
---

# AI Character Scenes

This is a template. The plan is that a brand's bot reads it, adapts it into its own recipe and runs that (the CFW tools for saving a brand's own recipe are planned, not built).
Read `steps/_shared.md` before any step. It holds the file layout, the safety rules and the
provider notes.

The method has one idea: **lock the character first, then never let a scene drift from the lock.**

```text
story + character text
        |
 01 lock + story arc --> 02 reference image --> 03 scene images (one at a time) --> 04 quality gate
 (character_lock.json,   (char_ref.png)         (scene_1..N, scene_sheet.png)       (final.png = cover,
  story_arc.json)                                                                     qa_report.json)
```

## What this recipe produces today

A set of 3 to 6 still images at 1080x1920, in story order, with scene 1 as the cover. No
dialogue, no text in frame. The manifest delivers images (`deliverable.kind: image`).

It does **not** produce a video. An older version of this method animated each scene with an
image-to-video model, joined the clips with crossfades and added a music bed. Those steps are
not in `steps/` or `manifest.json`, have no tests, and are not part of this template. The
character lock, the story arc and the drift check below carry over to a video version, but the
animation, assembly and music steps would have to be written and tested from scratch.

## Arguments

| Input | Required | Default | Meaning |
|---|---|---|---|
| `story_concept` | yes | none | One paragraph: who the character is, what they want, the payoff |
| `character_description` | yes | none | The character, visually, in all six attributes |
| `character_type` | no | `human` | `human` or `plush` (toy or mascot) |
| `num_scenes` | no | `5` | 3, 4, 5 or 6 |
| `reference_image` | no | none | An existing picture of the character to keep |

## The six-attribute character lock (hard gate)

Before anything is generated, the description must cover all six attributes. Each must be
specific and visual. Vague means fail: stop and ask for the missing detail.

| # | `human` | `plush` |
|---|---|---|
| 1 | Face shape | Body type and material |
| 2 | Hair: colour, length, style | Face: eye shape, eye colour, nose and mouth |
| 3 | Eyes: colour, shape, expression | Ear or head shape |
| 4 | Clothing: colour, pattern, texture | Outfit: colour, pattern, texture |
| 5 | Distinctive feature (scar, glasses, accessory) | Accessories or distinctive feature |
| 6 | Colour palette (primary and accent) | Colour palette (primary and accent) |

**Divergence rule:** after every generated image, compare it with the reference attribute by
attribute. A change in face, outfit or distinctive feature means regenerate at once. A diverged
image never moves on.

## Story arc

One scene per act. Acts in order: establish, desire, (attempt), obstacle, climax, resolution.
Three scenes use establish, climax, resolution. Four add desire. Six add attempt. Each scene
has a visual, one emotion word, a camera framing and a gentle motion cue. For `plush`, keep the
register toylike and playful.

## Steps

Run in order. Each step file says what it reads, what it saves and which checks apply.

1. `steps/01-character-lock.md`: the six-attribute audit and the story arc. Nothing is generated.
2. `steps/02-character-ref.md`: one reference image, audited against the lock.
3. `steps/03-scene-images.md`: one image-to-image call per scene, anchored on the reference, with a drift check after each.
4. `steps/04-qa-gate.md`: the `b-qa-gate` checks on each scene, then you look at each scene and answer its look questions, then `--finalize`.

## Blocks

- `../../blocks/b-kie-ai/`: `scripts/generate.py` makes each image (upload reference, create once, poll, download). The prompt goes in a file.
- `../../blocks/b-qa-gate/`: `check.py --kind image` runs the checks in `acceptance.json`; `check.py --finalize` records the look answers.

## Paid provider, key and likeness

Image generation uses Kie with the brand's own key, taken from the order. The key goes in the
environment of the one generation command (or on standard input with `--key-stdin`). A step
must never put it on a command line, read it from a file, write it to a file or print it.
Each image is one paid call.

The optional `reference_image`, and the generated reference that anchors every scene, are
uploaded to Kie. Use only a reference picture the brand has the right to use, of a person who
agreed. This template ships no reference image, no person's name and no id. Details are in
`steps/02-character-ref.md`.

## Safety rules for the steps

- Put order text (story, description, brand style) into a prompt file with a quoted heredoc or
  your file-writing tool, and pass the file with `--prompt-file`. Never paste it into a command
  line, and never evaluate it.
- Write only inside the order's work folder.
- The create call to the provider is made once and never retried; the generation script enforces this.

## Feedback loop

`LEARNINGS.md` holds lessons from earlier runs. Read it before the first step.
