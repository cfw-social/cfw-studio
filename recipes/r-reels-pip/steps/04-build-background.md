# Build the background track

Render every beat into a silent 1080×1920 clip and join them into the one background the speaker's
card is laid over. Cards are filled from the scene plan by scripts that escape every text, then
rendered by `b-hyperframes`. Nothing here uploads anything; setup downloads are listed in the README.

## You receive

- `prior/beat_list.json`, `prior/voice_track.mp4` (probed for its length only; never re-encoded),
  `inputs/broll/` and `brief.json` (`brand`).

## You must produce

- `saves/background.mp4`: 1080×1920, 30 fps, H.264, **no audio**, as long as the bed (within
  0.15 s), no black frame. Card content stays above y≈1040.

## How

```bash
mkdir -p work/bg_beats saves
RECIPE_DIR=${RECIPE_DIR:?set RECIPE_DIR to the absolute path of this recipe folder}
case "$RECIPE_DIR" in /*) ;; *) echo "RECIPE_DIR must be an absolute path"; exit 1 ;; esac
BLOCKS_DIR="$(cd "$RECIPE_DIR/../../blocks" && pwd)" || exit 1
python3 -c "import json; json.dump(json.load(open('brief.json')).get('brand') or {}, open('work/brand.json','w'))"
```

### 1. Once per work folder: the renderer and the animation library

`b-hyperframes` owns both. `hf_install.py` also downloads its pinned headless browser (about 88 MB)
into the work folder's cache, so a new work folder needs a few minutes the first time. Exit 3 means Node 22 or newer, npm, ffmpeg or ffprobe is missing: tell
the person and stop; install nothing outside the work folder.

```bash
python3 "$BLOCKS_DIR/b-hyperframes/scripts/hf_install.py"
python3 "$BLOCKS_DIR/b-hyperframes/scripts/fetch_gsap.py" --outdir vendor
```

### 2. Fill one page per graphics beat

```bash
python3 "$RECIPE_DIR/scripts/build_cards.py" --beats prior/beat_list.json --brand work/brand.json
```

For each graphics beat this writes `work/gfx_<N>/index.html` with `gsap.min.js` beside it, using
`b-typing-ui` (typing and hook cards, pip-safe variant) or this recipe's motion card. A typing scene
with no `prompt` stops it, named. The script prints each page; `work/cards.json` lists them.

### 3. Render each page with `b-hyperframes`

`hf_render.py` checks the page is local-only, lints, validates and renders. A failure names the
rule; fix the scene plan (not the check) and rebuild that card.

```bash
python3 -c 'import json; [print(c["dir"], c["out"]) for c in json.load(open("work/cards.json"))]' > work/render_list.txt
while read -r DIR OUT; do
  python3 "$BLOCKS_DIR/b-hyperframes/scripts/hf_render.py" --comp "$DIR" --out "$OUT" --fps 30 --quality high --quiet < /dev/null \
    || { echo "card $DIR did not render"; exit 1; }
done < work/render_list.txt
```

`$DIR` and `$OUT` are names the script made (`work/gfx_<number>`), never order text. `--quiet` prints only the stages,
warnings and errors; the full log is in `.hf-cache/logs/`.

### 4. Cut b-roll, join, check

```bash
python3 "$RECIPE_DIR/scripts/assemble_background.py" --beats prior/beat_list.json --voice prior/voice_track.mp4 --out saves/background.mp4
python3 "$RECIPE_DIR/scripts/check_reel.py" frames --video saves/background.mp4
python3 "$RECIPE_DIR/scripts/check_reel.py" duration --video saves/background.mp4 \
  --expect "$(ffprobe -v error -protocol_whitelist file -show_entries format=duration -of csv=p=0 prior/voice_track.mp4)"
python3 "$BLOCKS_DIR/b-qa-gate/check.py" --kind reel --spec "$RECIPE_DIR/acceptance.json" --step background \
  --input saves/background.mp4 --out work/scorecard-bg.json
```

b-roll beats are cut from their clip and scaled to cover. A black frame means a beat rendered
black: find its `work/bg_beats/bg_beat<N>.mp4`, fix its card and rebuild; do not composite over it.

## If you cannot proceed

No `canAsk`; never write `needs_input.json`. A card that will not render after one fix, a missing
renderer, or a length mismatch is a failure: exit non-zero with one plain line naming the beat.

## Checks (declared in `manifest.json`)

- `bg_not_black`: `check_reel.py frames` passes on `saves/background.mp4`.
- `bg_matches_bed`: 1080×1920, within 0.15 s of the bed, no audio stream (the `background` gate rows
  and `check_reel.py duration`).
