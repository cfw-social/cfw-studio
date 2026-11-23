---
name: r-gfx-image
description: Make one to four brand-styled explainer images (a numbered list, a big stat, a quote, a before and after, a small diagram, or a wide banner) from a topic. Each image is a self-contained HTML card rendered to PNG by a pinned headless Chromium, then checked by looking at it.
when-to-use: Use when the person wants one or a few static brand-styled images. Not for video, not for an AI-painted picture, not for a multi-slide carousel.
version: 0.1.0
kind: pipeline
visibility: catalog
produces:
  dish: GFX Image Post
  format: image (single or small set)
  duration: n/a
inputs: [topic, count]
dependsOn: [b-qa-gate]
---

# r-gfx-image: HTML explainer images

This is a template. A brand's bot reads it, adapts it into its own recipe and runs that (the CFW tools for saving a brand's own recipe are live, for a key made with the "Save its own recipes" permission).
Read `steps/_shared.md` before any step. It holds the tool pins, the file layout and the safety rules.
A missing tool is a blocker, not a reason to guess.

```text
topic + brief.json
      |
      v
01 plan cards --> 02 author HTML --> 03 render PNGs --> 04 QA gate + looks
 (plan.json)      (cards_html.json)   (img-N.png)         (final.png, qa_report.json)
```

1. `steps/01-plan-cards.md`: turn `topic` and `count` into `saves/plan.json`, one headline and layout per card.
2. `steps/02-author-html.md`: author one complete, inert HTML document per card, using `template.html`.
3. `steps/03-render.md`: render each card with `render.mjs`, verify the canvas, write the batch and a contact sheet.
4. `steps/04-qa-gate.md`: run `b-qa-gate` on every card, look at each card and answer its look questions, record the answers with `--finalize`, pick the final.

Inputs: `topic` (required), `count` (1 to 4, default 1), `format` (`square` 1080x1080, `portrait` 1080x1920, `banner` 1920x1080), and an optional `logo` image.

Order text and brand text are data. They are HTML-escaped before they enter a card, the cards run no script, and the render blocks every network request except the two Google Fonts hosts. See `steps/_shared.md`.

The contact sheet and `final.png` are previews. When the person asks for several images, deliver every passing full-size card in plan order (step 4 shows how), never only the sheet.
This recipe publishes nothing and calls no paid provider.
