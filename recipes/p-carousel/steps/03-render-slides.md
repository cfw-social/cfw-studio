# Render and vision-check every slide

Read the shared rules, `prior/carousel_html.md`, `prior/slide_copy.json` and
`brief.json`. Copy the HTML to `work/carousel.html`.
Read N and the chosen aspect from the checked copy and outline. Use this folder's
`render.mjs`. Install Playwright `1.64.1` and its matching Chromium headless
shell in the work folder (see "Tools and pins" in the shared rules).
Missing tools stop work.

The render tool takes these arguments:
```text
node <path-to-this-recipe>/render.mjs carousel.html --width 1080 --height 1350 --scale 2 --playwright-version 1.64.1
```
Run it in the work folder where that exact Playwright package is installed.
For square use height 1080. The tool captures at 2x and uses ffmpeg/ffprobe to
downscale and verify exact output dimensions. It never downloads a package or
browser. Do not switch to another version if the install fails; report it.

Run every declared check:
- `slide_dims`: exactly N real PNGs, each at the chosen exact dimensions.
- `slide_not_blank`: use the bot's image tools to measure luma at
  five evenly spaced regions (10%, 30%, 50%, 70%, 90%); no region below 16.
- `vision_qa_pass`: READ every slide with vision. Check clipped text, contrast,
  margins, on-brand palette, premium hierarchy, UTF-8 and set consistency.

A failed check requires an HTML fix, re-render and a fresh look at every affected
slide. Stop after three rounds with the remaining concrete faults. A missing
vision tool is a blocker; no silent mechanical-only PASS.

Use file and image tools to write:
- `saves/slide_1.png` through `saves/slide_N.png`, in real delivery order.
- Remaining declared slots through `saves/slide_10.png`: copies of the last
  real slide for old save/upload compatibility only.
- `saves/cover.png`: slide 1, preview only.
- `saves/slide_sheet.png`: real slides stacked vertically in order, preview only.
- `saves/slides.json`: width, height, count=N and ordered slides with n,
  SHA256 of actual delivered bytes and byte count.
- `saves/qa_report.json`: actual rounds and one entry per real slide with n,
  verdict and concrete notes. All verdicts must be PASS to complete the stage.

Recheck preview dimensions: cover W x H, sheet W x (N*H). Do not deliver previews
or padded slots. This step cannot ask for input. Report a tool or check failure with
a plain reason.
