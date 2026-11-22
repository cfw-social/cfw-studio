# p-carousel

A template for a branded image carousel. It makes ordered slide PNGs (3, 5, 7 or 10) at 1080x1350 or 1080x1080, plus one caption for each platform.

This is a template to learn from and adapt. The plan is that a brand's bot reads it, builds its own recipe, and saves that recipe in the brand's recipe library in CFW Social, which then runs it. Those CFW tools are planned, not built (see [../../docs/DESIGN.md](../../docs/DESIGN.md)). Today you can read the steps and follow them by hand or with your own agent.

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

Network use, in two parts:

- **Setup** downloads the pinned Playwright package from npm and its Chromium browser (`npm install`, then `npx playwright install`). This is the only time the work folder needs more than the two font hosts.
- **Rendering** contacts only `fonts.googleapis.com` and `fonts.gstatic.com`, for the fonts in `template.html`. `render.mjs` turns JavaScript off in the page and blocks every other network request. If the font hosts cannot be reached, the render still finishes with fallback system fonts.

No keys, no paid providers.

A vision-capable model must look at every slide. There is no mechanical-only pass.

## Run the tests

From this folder. They need no network and no browser.

```sh
node --test test/test_render.mjs
python3 -I test/test_brand_check.py -v
```

The first checks that `render.mjs` refuses bad sizes and wrong Playwright versions. The second checks the authoring check in step 2: the brand-colour check, and the refusal of script, event handlers, embeds and remote content.

Two more tests in the first file open a real browser. They check that the renderer runs no script and loads no remote resource. They are skipped unless you point `CAROUSEL_TEST_PLAYWRIGHT_DIR` at a folder where Playwright 1.64.1 and its browser are installed (it must contain `node_modules/playwright`), and ffmpeg must be on the path.

## Terms used by CFW Social

A few names in this folder belong to CFW Social's order format. If you use this template outside CFW Social, you can ignore them.

- **CFW Social's bot guide**: the instructions a brand's bot follows to claim an order, report each step and hand in results. It is part of CFW Social. This recipe does not change that protocol.
- **`order-brand-v2`**: a feature name in `manifest.json` (`needs.features`). It is part of CFW Social's order format. In this recipe the brand's details reach the steps as `brief.json`.
- **Check ids** such as `outline_shape`, `html_has_slides`, `brand_vars_set`, `slide_dims`, `vision_qa_pass` and `captions_per_target`: the names under which `manifest.json` declares each step's checks, so an order can record a result for each. Each step file says what to check. For example, `outline_shape` is the outline check in step 1 and `captions_per_target` is the caption check in step 4. Run the check the step describes; the id is just its label.

## Files

- `SKILL.md`: the overview an agent reads first.
- `manifest.json`: inputs, steps, saves and checks, in today's file format.
- `contracts/carousel-plan.json`: the typed files each step reads and writes.
- `acceptance.json`: the quality rubric for the slides.
- `template.html`: the slide template and CSS tokens.
- `render.mjs`: turns the HTML into PNGs.
- `LEARNINGS.md`: short lessons from earlier runs.
- `examples/`: a sample run (five slides for a made-up brand).
