# p-carousel

A template for a branded image carousel. It makes ordered slide PNGs (3, 5, 7 or 10) at 1080x1350 or 1080x1080, plus one caption for each platform.

This is a template to learn from and adapt. A brand's bot reads it, builds its own recipe and runs that.

## The steps

```text
topic + brief.json
      |
      v
01 outline --> 02 copy + HTML --> 03 render PNGs + vision check --> 04 captions
 (outline.json)  (template.html)    (slide_1.png ... slide_N.png)     (captions.json)
```

Each step has its own file in `steps/`. `steps/_shared.md` holds the rules every step shares.

## What it needs

| Tool | Version |
| --- | --- |
| Node.js | 22 or newer (tested on 25.9.0) |
| Playwright | exactly 1.64.1, installed in the work folder |
| Chromium headless shell | revision 1248 (what Playwright 1.64.1 asks for) |
| ffmpeg and ffprobe | 6 or newer (tested on 8.1) |
| ImageMagick | 7 or newer |
| Python 3 | 3.10 or newer |

Network: while rendering, `template.html` loads fonts from Google Fonts. Nothing else uses the network. No keys, no paid providers.

A vision-capable model must look at every slide. There is no mechanical-only pass.

## Run the tests

From this folder. They need no network and no browser.

```sh
node --test test/test_render.mjs
python3 -I test/test_brand_check.py -v
```

The first checks that `render.mjs` refuses bad sizes and wrong Playwright versions. The second checks the brand-colour check in step 2.

## Files

- `SKILL.md`: the overview an agent reads first.
- `manifest.json`: inputs, steps, saves and checks, in today's file format.
- `contracts/carousel-plan.json`: the typed files each step reads and writes.
- `acceptance.json`: the quality rubric for the slides.
- `template.html`: the slide template and CSS tokens.
- `render.mjs`: turns the HTML into PNGs.
- `LEARNINGS.md`: short lessons from earlier runs.
