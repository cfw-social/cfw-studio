# Render and check every slide

Read the shared rules (they set `RECIPE_DIR` and `BLOCKS_DIR`), `prior/carousel_html.md`,
`prior/slide_copy.json` and `brief.json`. Every command below runs in the order's work
folder (the one with `saves/`, `work/` and `prior/`), and every path is relative to it.
Pass each path as its own argument. Never build a command from order or brand text.

Let N be the slide count from `prior/slide_copy.json`, and H the height: 1350 for
portrait (`4:5`) or 1080 for square (`1:1`). The width is always 1080.

## 1. Install the renderer, once

In the work folder:

```sh
npm install --save-exact playwright@1.64.1
npx playwright install chromium-headless-shell
```

Missing tools stop the step. Do not switch to another Playwright version if this fails;
report it.

## 2. Render

```sh
cp prior/carousel_html.md work/carousel.html
node "$RECIPE_DIR/render.mjs" work/carousel.html --width 1080 --height H --scale 2 --playwright-version 1.64.1
```

`render.mjs` needs the HTML file to be a regular file inside the work folder. It
captures at 2x, scales to the exact size with ffmpeg, and writes `slides/slide-1.png`
to `slides/slide-N.png`. It refuses an output folder or file that is a link. It runs
the page with scripts off and blocks every network request except the two font hosts.

## 3. Save the slides, cover, sheet and index

```sh
python3 "$RECIPE_DIR/finish.py" slides --count N --width 1080 --height H
```

This copies each `slides/slide-n.png` to `saves/slide_n.png` (checking it is a PNG of the
exact size), then writes `saves/cover.png` (slide 1, preview only),
`saves/slide_sheet.png` (the slides stacked, preview only, 1080 by N times H) and
`saves/slides.json` (width, height, count, and for each slide its file, SHA256 and
byte count). Only slides 1 to N are saved; the manifest's other slots stay empty.

## 4. Check every slide with `b-qa-gate`

`b-qa-gate` takes one image at a time (read `$BLOCKS_DIR/b-qa-gate/README.md`). The
helper runs it once per slide. First write the spec for this canvas, then run the checks:

```sh
python3 "$RECIPE_DIR/finish.py" spec --recipe-dir "$RECIPE_DIR" --width 1080 --height H
python3 "$RECIPE_DIR/finish.py" qa --count N --blocks-dir "$BLOCKS_DIR"
```

`spec` writes `work/acceptance.json`, a copy of this recipe's `acceptance.json` with the
size and the crop set to this canvas. `qa` runs the gate on `saves/slide_n.png` and writes
`work/qa/slide_n.json` for each slide. Each slide exits 0 or 4 (the mechanical checks,
size and not blank, passed). Any other exit stops the command: fix the HTML (step 2 of
the recipe), render again, and start this step from section 2.

## 5. Look at every slide, then record the answers

The five `perceptual` checks (clipped text, contrast, margins, on-brand palette, premium
hierarchy) are LOOK rows in each slide's scorecard. Open each `saves/slide_n.png` with
your own vision tool and answer every LOOK row for that slide. Also check UTF-8 text and
that the slides look like one set. Write `work/qa/answers_n.json`, one file per slide:

```json
{ "no_clipped_text":   { "answer": "yes", "note": "all text inside the card" },
  "legible_contrast":  { "answer": "yes", "note": "" },
  "consistent_margins": { "answer": "yes", "note": "" },
  "on_brand_palette":  { "answer": "yes", "note": "" },
  "premium_hierarchy": { "answer": "yes", "note": "" } }
```

Answer "no" if you did not really look or are unsure. Never edit a scorecard by hand and
never lower a threshold in the spec. Then finalize:

```sh
python3 "$RECIPE_DIR/finish.py" finalize --count N --blocks-dir "$BLOCKS_DIR"
```

A slide passes only when its `work/qa/final_n.json` verdict is PASS. A "no", a missing
answer, or a slide that changed after the check fails it.

## 6. Fix or finish

A failed slide needs an HTML fix, a new render, and a fresh check (new scorecards and
fresh answers) for every slide that changed. Stop after three rounds and report the
remaining concrete faults. A missing vision tool is a blocker; there is no mechanical-only
pass. When every slide passes, write the report (R is the number of rounds you ran):

```sh
python3 "$RECIPE_DIR/finish.py" report --count N --rounds R
```

This writes `saves/qa_report.json`: the rounds and, for each slide, its verdict, the path
of its final scorecard and the notes you gave. It fails unless every slide is a finalized
PASS. Record `slide_dims` and `slide_not_blank` from the `canvas_*` and `slide_not_blank`
rows, and `vision_qa_pass` from the final scorecards.

Do not deliver the cover or the sheet. Deliver slides 1 to N in order. This step cannot
ask for input. Report a tool or check failure with a plain reason.
