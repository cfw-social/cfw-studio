---
name: r-ai-image
description: Make one AI image, or a small batch of 2 to 6, at an exact social canvas (1080x1080, 1080x1920 or 1920x1080) with Kie, from a text prompt or from a reference image, and check every image before delivery.
when-to-use: Use when the user wants one image or a small batch of generated images (a photo-style scene, an illustration, a product shot, a character). Not for HTML graphics and not for video.
version: 0.1.0
kind: pipeline
produces:
  format: image (single or batch)
  duration: n/a
inputs: [prompt, count, aspect_ratio, reference_image]
dependsOn: [b-kie-ai, b-qa-gate]
requires: python3, ffmpeg, a Kie key
---

# AI Image

This is a template. The plan is that a brand's bot reads it, adapts it into its own recipe and
runs that (the CFW tools for saving a brand's own recipe are live, for a key made with the "Save its own recipes" permission).

Read `steps/_shared.md` before any step. It holds the tool versions, the work-folder layout,
the key rule and the network list. The recipe spends the brand's own Kie credits, so run
it only with that brand's key and the user's go-ahead.

```text
prompt (+ count, shape, reference)
        |
        v
01 plan prompts --> 02 generate (b-kie-ai) --> 03 quality gate (b-qa-gate) + looks
  prompts.json      image_1.png                  final.png
                    contact_sheet.png            qa_report.json
                    images.json
```

1. `steps/01-plan-prompts.md`: one concrete prompt per image, a negative list, the model.
2. `steps/02-generate.md`: write each prompt to a file, make one image with
   `../../blocks/b-kie-ai/scripts/generate.py` (text-to-image with `z-image`, or image-to-image
   with `gpt-image-2-image-to-image` and `--ref`), fit it to the exact canvas, write the batch
   and a contact sheet. The Kie key is set only on that one command (a per-command
   `KIE_AI_API_KEY=` prefix), or goes on standard input; never on a command line.
3. `steps/03-qa-gate.md`: re-split the batch, run `../../blocks/b-qa-gate/check.py --kind image`
   on every image with `acceptance.json`, answer each look question by looking at the image
   yourself, record the answers with `--finalize`, pick the final.

Inputs: `prompt` (required), `count` (1, 2, 3, 4 or 6, default 1), `aspect_ratio` (`1:1`,
`9:16`, `16:9`, default `1:1`), `reference_image` (optional).

Only Kie is supported, with the two models `b-kie-ai` confirms. Other image providers are not
part of this recipe.

## Quality gate (run on every produced image before delivery)

Run it per image, from the work folder, with `BLOCKS_DIR` set as in `steps/_shared.md` (`$RECIPE_DIR/../../blocks`). Step 03 writes the spec copy for the order's canvas first.

```bash
python3 "$BLOCKS_DIR/b-qa-gate/check.py" --kind image --spec work/acceptance.json \
  --input work/img-1.png --out work/scorecard-1.json
```

- Exit `0`: every check passed and no look is owed.
- Exit `4`: the mechanical checks passed. Look at the image, answer each LOOK row in
  `work/answers-1.json`, then run `check.py --finalize work/scorecard-1.json --answers
  work/answers-1.json --out work/final-scorecard-1.json`. Deliver only on a final PASS.
- Exit `1`: a check failed (wrong size, black or flat frame). Regenerate with the user's say-so; do not deliver.
- Exit `2`: the command was wrong; nothing was checked.
