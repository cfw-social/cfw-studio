---
name: r-carousel
description: Make a branded HTML carousel as ordered slide PNGs and per-platform captions. Uses a pinned Chromium renderer and a per-slide check with the `b-qa-gate` block and a mandatory look at every slide.
disable-model-invocation: true
argument-hint: "[topic] [slide count] [shape]"
kind: pipeline
visibility: catalog
produces:
  format: image carousel
inputs: [topic]
dependsOn: []
requires: node, chromium, ffmpeg, python3
---

# Carousel — 2026.11.2

This is a template. The plan is that a brand's bot reads it, adapts it into its own recipe and runs that (the CFW tools for saving a brand's own recipe are planned, not built).
Read `steps/_shared.md` before any step. It holds the tool pins, the brief format,
the file layout and the safety rules. Missing tools are blockers, not reasons to
guess.

```text
brief + topic -> outline -> (optional outline review)
                               |
                  copy + HTML -> PNG slides + b-qa-gate check -> captions
```

Run the steps in order, using these files:

1. `steps/01-outline.md`: required topic, bounded slide count, checked outline.
2. `steps/02-author-slides.md`: checked copy and HTML from `template.html`.
3. `steps/03-render-slides.md`: exact dimensions, non-blank images, `b-qa-gate` once per slide, then the looks.
4. `steps/04-captions.md`: one caption per target platform plus a default.

The optional outline review stops after step 1 until a person approves the
outline. Never approve it yourself, and never treat a check as human approval.

`contracts/carousel-plan.json` lists the typed inputs and outputs of each step.
Only the topic, CTA, slide count, slide shape and outline review may vary.
Keep brand facts and order text in the order's own work folder. Never save them
into this template.

Use rich HTML layouts, a real type hierarchy, the brand's fonts, generous margins
and depth. `template.html` is a quality floor. Look at every slide with vision
and fix defects before delivery. The checks run through `b-qa-gate`. Deliver the real slides in order plus the
captions. The cover copy and the contact sheet are previews, not deliverables. This recipe does not publish anything and calls no paid provider.

Network use is declared in `steps/_shared.md`: setup downloads the pinned
Playwright package and its browser, and the render itself contacts only the
two Google Fonts hosts.

Windows, macOS and Linux are targets. Only a run you actually did on a host is
evidence that it works there.
