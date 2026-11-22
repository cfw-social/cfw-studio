# Render to PNG

Screenshot every card with headless Chromium, crop to the exact canvas, verify the dims, and
write the batch plus a contact sheet. Re-render anything that comes out blank.

## You receive

- `prior/cards_html.json`: `width`, `height`, `format`, `cards[]` (`n`, `html`).
- `brief.json`: `intent` (for the log line only).
- `$RECIPE_DIR/render.mjs`.

## You must produce

- `saves/image_1.png`: card 1 at the exact canvas (the preview).
- `saves/contact_sheet.png`: all cards tiled in order (a single card: identical to `image_1`).
- `saves/images.json`: `{ "width", "height", "count", "cols", "images": [ { "n", "sha256", "bytes" } ] }`. The full batch travels inside `contact_sheet.png` (`cols` tiles across, row-major); the QA step re-splits it from this geometry.

## How

```bash
mkdir -p work saves
read -r W H N < <(python3 -c "import json;d=json.load(open('prior/cards_html.json'));print(d['width'],d['height'],len(d['cards']))")
python3 - <<'PY'
import json
for c in json.load(open('prior/cards_html.json'))["cards"]:
    open(f"work/card-{c['n']}.html", "w", encoding="utf-8").write(c["html"])
PY
```

### 1. Render each card

`render.mjs` opens each card with the pinned Playwright, with JavaScript off, and allows only local files, inline data and the two font hosts. It takes a screenshot of exactly the canvas. The browser sandbox stays on: do not add `--no-sandbox` or any other switch that weakens the browser. If the browser will not start with its sandbox (for example in a container that forbids it), stop and report that as the blocker.

```bash
CARDS=()
for ((i = 1; i <= N; i++)); do CARDS+=( "work/card-$i.html" ); done
node "$RECIPE_DIR/render.mjs" --width "$W" --height "$H" --out-dir work --playwright-version 1.64.1 "${CARDS[@]}"
for ((i = 1; i <= N; i++)); do
  ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0 "work/img-$i.png"
done
```

Every `work/img-N.png` must report exactly `W,H`. Anything else is a failure.

### 2. Look at each render

Open each `work/img-N.png`: fonts loaded (no system-serif fallback), entities rendered
(`&rarr;` is an arrow, not literal text), nothing clipped, nothing blank. A blank or half-loaded card is fixed in its HTML and re-rendered; `render.mjs` already waits for the fonts. The scripted size, not-black and not-flat checks run in step 4 with `b-qa-gate`.

### 3. Write the saves

```bash
cp work/img-1.png saves/image_1.png
COLS=$(( N <= 1 ? 1 : 2 ))
# The sheet has no text, so it is tiled with plain appends that need no font. (`montage` always
# loads a font and exits 1, "unable to read font `'", where ImageMagick has no default font.)
SHEET=()
for ((r = 0; r * COLS < N; r++)); do
  SHEET+=( '(' )
  for ((c = 1; c <= COLS; c++)); do
    i=$(( r * COLS + c ))
    if [ "$i" -le "$N" ]; then SHEET+=( "work/img-$i.png" ); else SHEET+=( -size "${W}x${H}" xc:black ); fi
  done
  SHEET+=( +append ')' )
done
convert "${SHEET[@]}" -append saves/contact_sheet.png
python3 - "$W" "$H" "$COLS" <<'PY'
import glob, hashlib, json, os, re, sys
W, H, cols = map(int, sys.argv[1:4])
files = sorted(glob.glob('work/img-*.png'), key=lambda f: int(re.search(r'(\d+)\.png$', f).group(1)))
n = len(json.load(open('prior/cards_html.json'))["cards"])
assert len(files) == n, "image count"
imgs = [{"n": i+1, "sha256": hashlib.sha256(open(f,'rb').read()).hexdigest(), "bytes": os.path.getsize(f)} for i, f in enumerate(files)]
json.dump({"width": W, "height": H, "count": n, "cols": cols, "images": imgs}, open('saves/images.json','w'), indent=1)
print(f"[gfx] {n} image(s) rendered at {W}x{H}")
PY
```

## If you cannot proceed

This step has no `canAsk`. Never write `needs_input.json`. A missing Playwright or browser, a screenshot
that is not the exact canvas, or a card that renders blank twice is a
failure: exit non-zero with one plain line naming the card.

## Checks the order runs

- `image_dims` — `saves/image_1.png` is exactly `width`×`height` from `saves/images.json`;
  `saves/contact_sheet.png` is `cols`·`width` wide and `ceil(count/cols)`·`height` tall.
- `not_black` — luma floor ≥ 16 at five sample points on `saves/image_1.png` and on every
  tile of the contact sheet.
