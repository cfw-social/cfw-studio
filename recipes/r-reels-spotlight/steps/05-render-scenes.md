# Render scenes

Fill the shipped HyperFrames templates from the edit plan (never author new ones), render the
**silent** graphics-takeover composition over the bed picture, and pre-render any b-roll takeover
clips. Every creative value is already in the plan; this step is mechanical. Rendering is the
`b-hyperframes` block's job: this step does not repeat its install or call the renderer itself.

## You receive

- `prior/voice_track.mp4` — the sealed bed (picture + audio; audio is NOT used here).
- `prior/edit_plan.json` — `duration`, `brand`, `takeovers[]`.
- `prior/beat_list.json` — present only when b-roll was planned.
- `inputs/broll/` — the b-roll clips referenced by `beat_list.json` (only when present).

## You must produce

- `saves/rendered_scenes.mp4` — 1080×1920 30 fps **silent** video, full bed length: the bed
  picture with the graphics takeovers composited at their planned windows AND (when b-roll was
  planned) the trimmed b-roll takeover clips composited at their beat windows. Captions are NOT
  burned here; the premium pass does that later on the fully composited picture.

## How

```bash
mkdir -p work saves || exit 1
cp prior/edit_plan.json work/plan.json || exit 1
cp prior/voice_track.mp4 work/base.mp4 || exit 1
rm -rf work/comp work/takeover-text work/broll_takeovers || exit 1
python3 -c "import json; json.dump(json.load(open('prior/transcripts.json'))['words'], open('work/words.json','w'))" || exit 1
BED_DUR=$(ffprobe -v error -protocol_whitelist file -show_entries format=duration -of csv=p=0 prior/voice_track.mp4) || exit 1
# The plan this step is about to use is checked again here: a plan file can change after step 03, and
# `build_takeovers.py` only builds from the fixed templates and fill keys this guard also enforces.
python3 "$RECIPE_DIR/scripts/plan_guard.py" work/plan.json "$BED_DUR" work/words.json || exit 1
rm -f work/beat_list.json work/scenes.mp4 work/visuals.mp4 || exit 1   # nothing from an earlier run is reused
if [ -f prior/beat_list.json ]; then cp prior/beat_list.json work/beat_list.json || exit 1; fi
# Renderer setup, once per work folder (see _shared.md): skip what is already here.
[ -d hyperframes-runtime ] || python3 "$BLOCKS_DIR/b-hyperframes/scripts/hf_install.py" || exit 1
[ -s vendor/gsap.min.js ] || python3 "$BLOCKS_DIR/b-hyperframes/scripts/fetch_gsap.py" --outdir vendor || exit 1
```

Exit 3 from `hf_install.py` means Node 22+, npm, ffmpeg or ffprobe is missing: tell the person; do
not install anything outside the work folder.

### Part A — Pre-render b-roll takeover clips (only if `work/beat_list.json` exists)

Trim + FIT + blurred-fill composite, silent. The clip is shown whole; a heavily blurred zoomed copy
fills the frame edges (a no-op for true 9:16 clips). Never scale-to-cover a screen capture. The
helper refuses any clip that is not inside `inputs/broll/`.

```bash
if [ -f work/beat_list.json ]; then python3 "$RECIPE_DIR/scripts/broll_takeovers.py" || exit 1; fi
```

### Part B — Build the HyperFrames composition (graphics takeovers only)

`build_takeovers.py` fills `templates/tk-*.html` from `work/plan.json`, and for `tk-typing-ui` calls
the `b-typing-ui` block's `typing_fill.py --wrap template --slot tk<N>`. Every text value is
escaped before it enters a page; the only markup it lets through is one `<span class="accent">`
wrapper in `TITLE` and `QUOTE`. Placeholders are filled in a single pass, and a placeholder left
unfilled stops the build. GSAP comes from `vendor/gsap.min.js` (the pinned copy `fetch_gsap.py`
wrote); never load a CDN copy.

```bash
python3 "$RECIPE_DIR/scripts/build_takeovers.py" work "$RECIPE_DIR" "$BLOCKS_DIR" vendor/gsap.min.js || exit 1
python3 "$BLOCKS_DIR/b-hyperframes/scripts/check_local.py" --comp work/comp || exit 1   # prints LOCAL_ONLY: PASS
```

Every page here passes `check_local.py`: nothing is loaded from the network, and each named font
(Oswald, Inter, JetBrains Mono) is declared with a local `@font-face`, so they must be installed on
the machine that renders (SIL Open Font Licence; none is bundled). A missing font falls back to the
generic family and the letter shapes differ. If it prints `LOCAL_ONLY: FAIL`, fix the named
`file:line`; never edit the check.

### Part C — Render (60–600 s; run it in the background if your engine can)

`hf_render.py` runs the local-only check again, then lint, validate and the render with one worker, in a pinned headless browser that `hf_install.py` downloaded into the work folder. Always pass `--quiet` (without it the renderer prints one line per frame); the full log is in `.hf-cache/logs/`.
A failed render stops the step with the printed error in the reason. There is no still-image
fallback: never compose the takeovers from PNG renders of the filled templates, because that hides a
total render failure.

```bash
python3 "$BLOCKS_DIR/b-hyperframes/scripts/hf_render.py" --comp work/comp --out work/visuals.mp4 --fps 30 --quality high --quiet \
  > work/render.log 2>&1 && [ -s work/visuals.mp4 ] \
  || { echo "takeovers: render of work/comp failed: $(tail -n 5 work/render.log 2>/dev/null | tr '\n' ' ')" >&2; exit 1; }
ffprobe -v error -protocol_whitelist file -select_streams v:0 -show_entries stream=width,height,duration -of csv=p=0 work/visuals.mp4 || exit 1
```

### Part D — Composite b-roll takeovers onto the visuals (only if beat_list present)

```bash
if [ -f work/beat_list.json ]; then python3 "$RECIPE_DIR/scripts/broll_overlay.py" || exit 1; else cp work/visuals.mp4 work/scenes.mp4 || exit 1; fi
cp work/scenes.mp4 saves/rendered_scenes.mp4 || exit 1
```

## If you cannot proceed

This step has no `canAsk`. Never write `needs_input.json`. A missing template, a failed GSAP fetch, a
`LOCAL_ONLY: FAIL` or a failed render is a failure: exit non-zero with one plain line that carries the
printed error. There is no still-card fallback.

## Checks

The `scenes_not_blank` check re-derives from the saved video that the render happened, so a skipped
render cannot pass: `saves/rendered_scenes.mp4` is 1080×1920, its duration matches the bed within
0.5 s, and frames sampled inside every planned takeover window (graphics and b-roll) and at
10/50/90 % are not black (mean luma above 16/255). With no b-roll, add `--no-broll` to the spec
copy, because there is no `beat_list.json` to read windows from.

```bash
BED_DUR=$(ffprobe -v error -protocol_whitelist file -show_entries format=duration -of csv=p=0 prior/voice_track.mp4) || exit 1
GATE_ARGS=()
if [ ! -f prior/beat_list.json ]; then GATE_ARGS=(--no-broll); fi
python3 "$RECIPE_DIR/scripts/gate_spec.py" --spec "$RECIPE_DIR/acceptance.json" --bed-duration "$BED_DUR" --out work/acceptance.run.json "${GATE_ARGS[@]}" || exit 1
python3 "$BLOCKS_DIR/b-qa-gate/check.py" --kind reel --spec work/acceptance.run.json \
  --step render_scenes --input saves/rendered_scenes.mp4 --out work/check-render.json || exit 1
```

`GATE_ARGS` is an array: empty, or the one flag `--no-broll`. Expand it as `"${GATE_ARGS[@]}"` (an array works the same in zsh and bash; a text string used unquoted would reach the script as one merged argument in zsh).
