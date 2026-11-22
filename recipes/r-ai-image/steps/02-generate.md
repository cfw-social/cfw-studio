# Generate the images

Make one Kie image per planned prompt with the block `b-kie-ai`, fit each result to the exact
canvas and write the batch plus a contact sheet. Every generation call spends the brand's own
Kie credits, so each image is made once and a call that fails is not repeated by this step.

## You receive

- `prior/prompts.json` — `count`, `aspect_ratio`, `model`, `has_reference`, `negative`, `images[]`.
- `inputs/reference_image/<file>` — optional. When present every call is image-to-image
  (`gpt-image-2-image-to-image`). `b-kie-ai` uploads the file to Kie's upload host and sends the
  hosted address, never the file's bytes in the request.
- `brief.json` — `intent`.
- The brand's own Kie key, held by the bot in the shell variable `KEY` (not exported). It is
  given to the one `generate.py` command as `KIE_AI_API_KEY="${KEY:-}"` and to no other command
  (see `_shared.md`, "Provider key"). It is never read from a file and never printed.

## You must produce

- `saves/image_1.png` — the first image at the exact canvas (the first preview).
- `saves/contact_sheet.png` — all images tiled in order (single image: identical to `image_1`).
- `saves/images.json` — `{ "width", "height", "count", "cols", "model", "images": [ { "n",
  "task_id", "sha256", "bytes", "attempts" } ] }`. Only these three saves are passed to the
  next step: the full batch travels inside `contact_sheet.png` (`cols` tiles across,
  row-major) and the QA step re-splits it from this geometry.

## How

### 0. Set up

```bash
mkdir -p work saves
: "${BLOCKS_DIR:?run the paths snippet in steps/_shared.md first}"
GEN="$BLOCKS_DIR/b-kie-ai/scripts/generate.py"
[ -f "$GEN" ] || { echo "blocks/b-kie-ai/scripts/generate.py is missing; the recipe needs that block"; exit 1; }
AR=$(python3 -c "import json;print(json.load(open('prior/prompts.json'))['aspect_ratio'])")
case "$AR" in
  9:16) W=1080; H=1920;; 16:9) W=1920; H=1080;; 1:1) W=1080; H=1080;;
  *) echo "aspect ratio $AR is not supported; use 1:1, 9:16 or 16:9"; exit 1;;     # never fall back to a square
esac
REF=$(ls inputs/reference_image/* 2>/dev/null | head -1)
MODEL=$(python3 -c "import json;print(json.load(open('prior/prompts.json'))['model'])")
COUNT=$(python3 -c "import json;print(json.load(open('prior/prompts.json'))['count'])")
if [ -n "${ONLY:-}" ]; then      # ONLY goes into arithmetic below: digits only, one image of the batch
  case "$ONLY" in 0*|*[!0-9]*) echo "ONLY must be an image number such as 2"; exit 1;; esac
  [ "$ONLY" -le "$COUNT" ] || { echo "ONLY=$ONLY is more than the $COUNT image(s) planned"; exit 1; }
fi
# Step 01 picks the model from the same input: image-to-image exactly when a reference exists.
if [ -n "$REF" ] && [ "$MODEL" != "gpt-image-2-image-to-image" ]; then
  echo "the plan did not choose the reference model although a reference image was supplied"; exit 1
fi
if [ -z "$REF" ] && [ "$MODEL" != "z-image" ]; then
  echo "the plan chose $MODEL; without a reference image the model is z-image"; exit 1
fi
```

### 1. Generate, one paid call per image

For each image the step writes the prompt to a file in `work/` (it is never a shell string), then runs
the block. The prompt is the planned prompt followed by `Avoid:` and the negative list, which
step 01 already checked against the model's length limit. The block's exit codes: `0` saved,
`1` Kie or network failure, `2` bad arguments (nothing sent), `3` no key (nothing sent, nothing
spent). The last stdout line is `IMAGE_FILE: ...` or `IMAGE_FAILED: ...`; `KIE_TASK: <id>` appears
once Kie accepts the task. Record `task_id` and `attempts` per image in `work/tasks.json`.

Without a reference the command is:

```text
KIE_AI_API_KEY="${KEY:-}" python3 "$GEN" --prompt-file work/prompt-N.txt --out work/raw-N.png --aspect "$AR" --timeout 240 --poll 5
```

With a reference it adds the reference model, the output size and the reference file (a copy of
the picture as a JPEG of at most 2048 pixels a side, made with ffmpeg, well under the block's 10 MB
limit):

```text
KIE_AI_API_KEY="${KEY:-}" python3 "$GEN" --prompt-file work/prompt-N.txt --out work/raw-N.png --aspect "$AR" --model gpt-image-2-image-to-image --resolution 2K --ref work/ref-in.jpg --timeout 240 --poll 5
```

The key is set only on the `generate.py` command, as a per-command prefix
`KIE_AI_API_KEY="${KEY:-}"`; no other command in this step has it in its environment. (If your tool
cannot do that, pipe the key on standard input with `--key-stdin` instead.) A failure fails the step with
the block's last line and is never repeated: a timeout or a failed task may still have been
charged. A regeneration after looking at a result (section 2) is a new, deliberate paid call: run
this block again with `ONLY=<image number>` (digits only; the set-up block refuses anything else), with the user's say-so. It counts one more attempt.

```bash
if [ -n "$REF" ]; then
  command -v ffmpeg >/dev/null 2>&1 || { echo "ffmpeg is not installed; it is needed to prepare the reference image"; exit 1; }
  # Any input format becomes a JPEG of at most 2048 px a side.
  ffmpeg -y -v error -protocol_whitelist file -i "$REF" -vf "scale='min(2048,iw)':'min(2048,ih)':force_original_aspect_ratio=decrease" \
    -frames:v 1 -q:v 2 work/ref-in.jpg \
    || { echo "the reference image could not be read; send a PNG, JPEG or WEBP picture"; exit 1; }
fi
for ((n = ${ONLY:-1}; n <= ${ONLY:-$COUNT}; n++)); do
  python3 - "$n" > "work/prompt-$n.txt" <<'PY'
import json, sys
p = json.load(open('prior/prompts.json'))
print(p["images"][int(sys.argv[1]) - 1]["prompt"].strip().rstrip(". ") + ". Avoid: " + p["negative"])
PY
  if [ -n "$REF" ]; then
    KIE_AI_API_KEY="${KEY:-}" python3 "$GEN" --prompt-file "work/prompt-$n.txt" --out "work/raw-$n.png" --aspect "$AR" \
      --model gpt-image-2-image-to-image --resolution 2K --ref work/ref-in.jpg \
      --timeout 240 --poll 5 > "work/gen-$n.log" 2>&1 && RC=0 || RC=$?
  else
    KIE_AI_API_KEY="${KEY:-}" python3 "$GEN" --prompt-file "work/prompt-$n.txt" --out "work/raw-$n.png" --aspect "$AR" \
      --timeout 240 --poll 5 > "work/gen-$n.log" 2>&1 && RC=0 || RC=$?
  fi
  tail -1 "work/gen-$n.log"
  if [ "$RC" -eq 3 ]; then echo "no Kie key was supplied for this brand"; exit 1; fi
  [ "$RC" -eq 0 ] || exit 1      # IMAGE_FAILED: the reason is on the last line; never repeat the call
  TASK=$(sed -n 's/^KIE_TASK: //p' "work/gen-$n.log" | tail -1)
  [ -n "$TASK" ] || { echo "Kie accepted image $n but no task id was recorded"; exit 1; }
  python3 - "$n" "$TASK" <<'PY'
import json, os, sys
n, task = sys.argv[1:3]
t = json.load(open('work/tasks.json')) if os.path.exists('work/tasks.json') else {}
e = t.setdefault(n, {"attempts": 0})
if e.get("task_id") and e["task_id"] != task:
    e.setdefault("earlier_task_ids", []).append(e["task_id"])
e["task_id"] = task; e["attempts"] += 1
json.dump(t, open('work/tasks.json', 'w'), indent=1)
print("[r-ai-image] image %s: paid attempt %d, Kie task %s" % (n, e["attempts"], task))
PY
done
```

### 2. Fit to the canvas

Run this without the key, for every image or (with `ONLY`) for the one regenerated. The blocks in
this step share the variables from section 0. If you run them in separate shells, run section 0
first in each; it is safe to repeat.

```bash
for ((n = ${ONLY:-1}; n <= ${ONLY:-$COUNT}; n++)); do
  ffmpeg -y -v error -protocol_whitelist file -i "work/raw-$n.png" -vf "scale=${W}:${H}:force_original_aspect_ratio=increase,crop=${W}:${H}" -frames:v 1 "work/img-$n.png"
  ffprobe -v error -protocol_whitelist file -select_streams v:0 -show_entries stream=width,height -of csv=p=0 "work/img-$n.png"
done
```

Then look at each `work/img-N.png`. A black or blank frame, an obvious generation failure
(distorted anatomy, duplicate limbs, a watermark) or a subject missing from the prompt can be
regenerated now, with the user's say-so (a new paid call; counted in `attempts`). Step 03 runs the
mechanical checks and the look questions on every image.

### 3. Write the saves

```bash
cp work/img-1.png saves/image_1.png
N=$COUNT
COLS=$(( N <= 1 ? 1 : (N <= 4 ? 2 : 3) ))
# The sheet is tiled with ffmpeg's xstack filter (already required): one tile per image, row by
# row, `COLS` across. A short last row leaves black tiles. One image is just copied.
if [ "$N" -eq 1 ]; then
  cp work/img-1.png saves/contact_sheet.png
else
  INPUTS=(); LAYOUT=""
  for ((i = 1; i <= N; i++)); do
    INPUTS+=( -protocol_whitelist file -i "work/img-$i.png" )
    LAYOUT="${LAYOUT:+$LAYOUT|}$(( (i - 1) % COLS * W ))_$(( (i - 1) / COLS * H ))"
  done
  ffmpeg -y -v error "${INPUTS[@]}" -filter_complex "xstack=inputs=${N}:layout=${LAYOUT}" -frames:v 1 saves/contact_sheet.png
fi
python3 - "$W" "$H" "$COLS" <<'PY'
import glob, hashlib, json, os, re, sys
W, H, cols = map(int, sys.argv[1:4])
p = json.load(open('prior/prompts.json')); tasks = json.load(open('work/tasks.json'))
files = sorted(glob.glob('work/img-*.png'), key=lambda f: int(re.search(r'(\d+)\.png$', f).group(1)))
assert len(files) == int(p["count"]), "image count"
imgs = [{"n": i+1, "task_id": tasks[str(i+1)]["task_id"], "attempts": tasks[str(i+1)].get("attempts", 1),
         "sha256": hashlib.sha256(open(f,'rb').read()).hexdigest(), "bytes": os.path.getsize(f)} for i, f in enumerate(files)]
json.dump({"width": W, "height": H, "count": len(files), "cols": cols, "model": p["model"], "images": imgs},
          open('saves/images.json','w'), indent=1)
print(f"[r-ai-image] {len(files)} image(s) {W}x{H}, model {p['model']}")
PY
```

## If you cannot proceed

This step has no `canAsk` (`count`, `aspect_ratio` default; `reference_image` is optional).
Never write `needs_input.json`. A missing Kie key, exhausted credits, a reference image that
cannot be read or that Kie refuses, or a generation that fails (an `IMAGE_FAILED` line from the
block) is a failure: exit non-zero with one plain line. Do not repeat a paid call on your own.

## Checks for this step

- `image_dims` — `saves/image_1.png` is exactly `width`×`height` from `saves/images.json`;
  `saves/contact_sheet.png` is `cols`·`width` wide and `ceil(count/cols)`·`height` tall.
- `not_black` — luma floor ≥ 16 at the centre of `saves/image_1.png` and of every tile of
  the contact sheet.
