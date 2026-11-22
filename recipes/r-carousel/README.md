# r-carousel

Based on CFW Social's built-in carousel recipe.

## What it makes

A branded image carousel: ordered slide PNGs (3, 5, 7 or 10) at 1080x1350 (portrait) or 1080x1080 (square), plus one caption for each target platform.

This is a template to learn from and adapt. The plan is that a brand's bot reads it, builds its own recipe, and saves that recipe in the brand's recipe library in CFW Social, which then runs it. The CFW tools for saving a recipe are live, for a key made with the "Save its own recipes" permission (see [../../docs/DESIGN.md](../../docs/DESIGN.md)). You can also read the steps and follow them by hand or with your own agent.

## What you need

| Tool | Version this edition was run with |
| --- | --- |
| Node.js | 25.9.0 |
| Playwright | exactly 1.64.1, installed in the work folder |
| Chromium headless shell | revision 1248 (what Playwright 1.64.1 asks for) |
| ffmpeg and ffprobe | 8.1 |
| Python 3 | 3.15.2 |

All of this was run on macOS. Other versions and other systems are untested.

No provider account and no key. A vision-capable model must look at every slide. There is no mechanical-only pass.

## Blocks it uses

| Block | Why | Path |
| --- | --- | --- |
| `b-qa-gate` | Checks every slide: exact size, not blank, and the "look at it" questions the bot must answer. | `../../blocks/b-qa-gate/` |

## The steps

```text
topic + brief.json
      |
      v
01 outline --> 02 copy + HTML --> 03 render PNGs, then b-qa-gate --> 04 captions
 (outline.json)  (template.html)   one scorecard per slide             (captions.json)
                                   + looks answered per slide
```

Each step has its own file in `steps/`. `steps/_shared.md` holds the rules every step shares.
In step 3 the gate takes one image at a time, so the step runs it once per slide, answers that slide's looks, and finalizes each slide's scorecard. A slide is done only when its final scorecard passes.

Files:

- `SKILL.md`: the overview an agent reads first.
- `manifest.json`: inputs, steps, saves and checks, in today's file format.
- `contracts/carousel-plan.json`: the typed files each step reads and writes.
- `acceptance.json`: the quality rubric `b-qa-gate` reads.
- `template.html`: the slide template and CSS tokens.
- `render.mjs`: turns the HTML into PNGs. It refuses an HTML file outside the work folder and any output folder or file that is a link.
- `finish.py`: step 3's helper: saves the slides, cover, sheet and index, writes the spec for the canvas, runs `b-qa-gate` per slide, and writes the report.
- `LEARNINGS.md`: short lessons from earlier runs.

## Inputs and outputs

| Input | Required | Notes |
| --- | --- | --- |
| `topic` | yes | One or two sentences: the hook, the insight, the audience. |
| `num_slides` | no | 3, 5, 7 or 10. Default 5. |
| `aspect_ratio` | no | `portrait_4_5` (default) or `square_1_1`. |
| `cta` | no | Call to action. Default: the brand's. |
| `brief.json` | yes | Brand palette, fonts, CTA, handle, target platforms (format in `steps/_shared.md`). |

Outputs: `saves/slide_1.png` to `saves/slide_N.png` in order, `saves/slides.json` (size, count, hashes), `saves/qa_report.json` (one entry per slide, with its final scorecard), and `saves/captions.json`. Cover and contact sheet are previews, not deliverables.

## Network use

Three parts.

- **Setup** downloads the pinned Playwright package from npm and its Chromium browser (`npm install`, then `npx playwright install`). This is the only time the work folder needs more than the two font hosts.
- **Rendering** contacts only `fonts.googleapis.com` and `fonts.gstatic.com`, for the fonts in `template.html`. `render.mjs` turns JavaScript off in the page and blocks every other network request. If the font hosts cannot be reached, the render still finishes with fallback system fonts.
- **Checking** with `b-qa-gate` contacts no host.

No keys, no paid providers.

## Run the tests

From this folder. These need no network and no account. The browser tests are skipped without Playwright (see below).

```sh
node --test test/test_render.mjs
python3 -I test/test_brand_check.py -v
python3 -I test/test_qa_gate.py -v
python3 -I test/test_finish.py -v
```

- `test_render.mjs` checks that `render.mjs` refuses bad sizes, wrong Playwright versions, an HTML file outside the work folder and any output folder that is a link, with no browser. Four more tests in it open a real browser (scripts off, remote requests blocked, an output file that is a link, no temporary files left). They are skipped unless you set `CAROUSEL_TEST_PLAYWRIGHT_DIR` to a folder where Playwright 1.64.1 and its browser are installed (it must contain `node_modules/playwright`), and ffmpeg must be on the path.
- `test_brand_check.py` checks the authoring check in step 2: the brand-colour check, and the refusal of script, event handlers, embeds and remote content.
- `test_finish.py` runs the whole of step 3's helper in a throwaway work folder: copying the slides, the sheet, the spec for both canvases, the gate and the report, and the refusal of links and wrong sizes.
- `test_qa_gate.py` runs the real `b-qa-gate` on a sample slide with this recipe's `acceptance.json`, answers the looks, and finalizes. It needs ffmpeg and ffprobe.

## Sample

`examples/` holds five slides for a made-up brand and topic, shown at 540 pixels wide (rendered at 1080x1350). The brand is invented.

## Terms used by CFW Social

A few names in this folder belong to CFW Social's order format. If you use this template outside CFW Social, you can ignore them.

- **CFW Social's bot guide**: the instructions a brand's bot follows to claim an order, report each step and hand in results. It is part of CFW Social. This recipe does not change that protocol.
- **`order-brand-v2`**: a feature name in `manifest.json` (`needs.features`). In this recipe the brand's details reach the steps as `brief.json`.
- **Check ids** such as `outline_shape`, `html_has_slides`, `brand_vars_set`, `slide_dims`, `vision_qa_pass` and `captions_per_target`: the names under which `manifest.json` declares each step's checks, so an order can record a result for each. Each step file says what to check. Run the check the step describes; the id is just its label.

## Limits and known gaps

- `b-qa-gate` measures size and blankness. Everything else (clipped text, contrast, margins, palette, hierarchy) is a look the bot answers. The scorecard records what the bot says; it does not prove the bot looked.
- The gate checks one image per run, so a carousel needs N runs. There is no whole-set check; the bot checks set consistency by eye in step 3.
- Fonts come from Google Fonts at render time. Without them the text uses system fonts.
- This edition was run only on macOS, with the versions in the table. `manifest.json` lists Windows and Linux as targets (that is today's order format), but no run on them is recorded here. No run on any bot app is claimed.
- Saving a brand's own version needs a key made with the "Save its own recipes" permission. The tags that show a post's recipe and template, and a "Your recipes" page in CFW Social, are planned, not built.
