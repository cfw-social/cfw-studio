# r-gfx-image

Based on CFW Social's built-in graphic image recipe.

## What it makes

A template for brand-styled explainer images. It makes one to four static PNG cards from a topic: a numbered list, a big stat, a quote, a before and after, a small diagram, or a wide banner. Sizes: 1080x1080 (square, default), 1080x1920 (portrait) or 1920x1080 (banner). Not a video, not an AI-painted picture, not a multi-slide carousel.

This is a template to learn from and adapt. A brand's bot reads it, builds its own recipe, and saves that recipe in the brand's recipe library in CFW Social. The bot then runs its saved recipe. The CFW tools for saving a recipe are live, for a key made with the "Save its own recipes" permission (see [../../docs/DESIGN.md](../../docs/DESIGN.md)). You can also read the steps and follow them by hand or with your own agent.

## What you need

| Tool | Version |
| --- | --- |
| Node.js | 25.9.0 (the version run) |
| Playwright (npm package) | exactly `1.64.1`, installed in the work folder |
| Chromium headless shell | revision 1248 (what Playwright 1.64.1 asks for) |
| ffmpeg and ffprobe | 8.1 (the version run; `b-qa-gate` was also tested with 8.1 only) |
| ImageMagick | 7.1.2 (the version run) |
| Python 3 | 3.15.2 (the version run) |
| bash | 3.2.57 (macOS system bash, the version run) |

No provider account, no paid service, no keys. A vision-capable model must look at every card and answer its look questions; there is no mechanical-only pass.

## Blocks it uses

| Block | Why | Path |
| --- | --- | --- |
| `b-qa-gate` | `check.py --kind image` checks the exact canvas, not black and not flat, and lists the look questions from `acceptance.json`; `--finalize` records the bot's answers | `../../blocks/b-qa-gate/` |

No other block is called. The HTML conventions live in this folder's `template.html`.

## The steps

```text
topic + brief.json
      |
      v
01 plan cards --> 02 author HTML --> 03 render PNGs --> 04 b-qa-gate + looks
 plan.json        cards_html.json     img-N.png          scorecards, final.png
                  (escaped, inert)    contact_sheet.png  qa_report.json
```

Each step has its own file in `steps/`. `steps/_shared.md` holds the rules every step shares.

## Inputs and outputs

Inputs (in `inputs/<id>/`): `topic` (required text), `count` (1 to 4, default 1), `format` (`square`, `portrait` or `banner`), `logo` (optional image). `brief.json` holds the brand: `name`, optional `palette` (six-digit hex colours) and `fonts`.

Outputs: `saves/image_1.png`, `saves/contact_sheet.png`, `saves/images.json` (step 3); `saves/final.png`, `saves/qa_report.json` (step 4; the per-card scorecards from `b-qa-gate` stay in `work/`). For a set, the deliverable is every passing full-size card in plan order (`work/out/image-N.png`, written at the end of step 4). The contact sheet and `final.png` are previews.

## Network use

- **Setup:** `npm install` fetches the pinned Playwright package; `npx playwright install` fetches its browser.
- **Rendering:** only `fonts.googleapis.com` and `fonts.gstatic.com`, for the web fonts named in the cards. `render.mjs` runs the page with JavaScript off and blocks every other request. If the font hosts cannot be reached, the render still finishes with fallback system fonts.
- `b-qa-gate` makes no network call and reads no key.
- Nothing else. The cards also carry a content-security-policy line that allows only those two hosts and inline images.

## Run the tests

From this folder:

```sh
python3 -I -B -m unittest discover -s test -v
```

`test/test_image_steps.py` needs Python 3, bash and ImageMagick (`convert`), and node for the `render.mjs` argument tests. No network, no keys. They run each step's own code block in a throwaway work folder: the brand-colour check, the refusal of script, handlers, embeds, remote content and unescaped text, the contact sheet with one to four cards, and the re-split in step 4.

Six tests open a real browser to check that a card runs no script, loads no remote resource, shows escaped order text as plain text, renders at the exact size, and refuses to write through a linked output folder, parent or file. They are skipped unless `GFX_TEST_PLAYWRIGHT_DIR` names a folder with Playwright 1.64.1 and its browser installed (it must contain `node_modules/playwright`) and `ffprobe` is on the path.

One test runs the real `../../blocks/b-qa-gate/check.py` (needs ffmpeg and ffprobe, and the block folder beside this recipe) on a card this recipe renders with ImageMagick. The block's own tests are in `../../blocks/b-qa-gate/test/`.

## Sample

`examples/` holds two small cards made with a made-up brand ("Example Plants") by following the steps with Playwright 1.64.1; see `examples/README.md`. It needed no paid account.

## Terms used by CFW Social

A few names in this folder belong to CFW Social's order format. If you use this template outside CFW Social, you can ignore them.

- **Order**: one request for this recipe, with its inputs. The "order's work folder" is the folder you run in.
- **`needs_input.json`** and **`canAsk`**: how a step asks the person for a missing input. Only the plan step may ask, and only for `topic`.
- **Check ids** such as `plan_shape`, `html_per_card`, `image_dims`, `not_black`, `vision_qa_pass` and `final_dims`: the names under which `manifest.json` declares each step's checks. Each step file says what to check. Run the check the step describes; the id is just its label.
- **Saves**: the files a step writes to `saves/`, named in `manifest.json`.
- **`manifest.json`**, **`acceptance.json`**, **`examples.json`**: today's CFW file format for the recipe's steps, quality rubric and sample list. `examples.json` is empty here; the sample is in `examples/`.

## Limits and known gaps

- Run and tested on macOS (Apple silicon) only, with the versions in the table above. Windows and Linux were not run: the steps use bash and ImageMagick `convert`.
- The vision pass is done by the model that runs the recipe. Only the mechanical checks (size, not blank, not flat) are scripted.
- `b-qa-gate` measures size, brightness and flatness. It does not judge the design: the five look questions are answered by the bot, and a scorecard is a record, not proof (see the block's README).
- The manifest does not yet define ordered delivery of several images (see step 4, section 6).
- `banner` here means a 1920x1080 card. Real platform banner sizes (for example 2560x1440 or 1584x396) are not covered.
- The web fonts come from Google Fonts. To avoid that, name fonts already installed on the machine; the render then uses them without a network request.
- Never run the cards with scripts on, with the browser sandbox off, or with the network open.
