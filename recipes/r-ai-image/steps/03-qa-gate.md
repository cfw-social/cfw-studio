# Quality gate and look answers

Run the block `b-qa-gate` on every generated image, answer the look questions it lists by
looking at each image yourself, record the answers, and pick the final. Only an image that
passes leaves this step. An image that fails is a regeneration job for the previous step, not
something to deliver.

## You receive

- `prior/images.json` — `width`, `height`, `count`, `cols`, `images[]` (`n`, `task_id`, `sha256`).
- `prior/image_1.png` — the first image at the exact canvas.
- `prior/contact_sheet.png` — all images tiled `cols` across in order.
- `prior/prompts.json` — the prompt each image was generated from (what the subject must be).
- `brief.json` — `brand` (palette), `intent`.
- `$RECIPE_DIR/acceptance.json` and `../../blocks/b-qa-gate/`.

## You must produce

- `saves/final.png` — a selected preview (with a batch of 1 it is `image_1`), exact
  canvas. It does not deliver the batch. The manifest declares no ordered
  individual-image final outputs, so a batch is not delivered by this save alone: keep every
  passing full-resolution image (`work/img-N.png`) in prompt order, never only this preview
  or the contact sheet.
- `saves/qa_report.json` — `{ "final_n": 1, "images": [ { "n", "verdict": "PASS" | "FAIL",
  "input_sha256", "checks": [ { "id", "status", "detail" } ] } ] }`, built from the finalized
  scorecards.

## How

```bash
mkdir -p work saves
: "${RECIPE_DIR:?run the paths snippet in steps/_shared.md first}" "${BLOCKS_DIR:?run the paths snippet in steps/_shared.md first}"
[ -f "$BLOCKS_DIR/b-qa-gate/check.py" ] || { echo "blocks/b-qa-gate/check.py is missing; the recipe needs that block"; exit 1; }
read -r W H N COLS < <(python3 -c "import json;d=json.load(open('prior/images.json'));print(d['width'],d['height'],d['count'],d['cols'])")
```

### 1. Re-split the batch from the contact sheet

```bash
cp prior/image_1.png work/img-1.png
# Count up with shell arithmetic, not `seq 2 "$N"`: macOS seq prints "2 1" for one image.
for ((i = 2; i <= N; i++)); do
  r=$(( (i-1) / COLS )); c=$(( (i-1) % COLS ))
  ffmpeg -y -v error -protocol_whitelist file -i prior/contact_sheet.png -vf "crop=${W}:${H}:$((c*W)):$((r*H))" -frames:v 1 "work/img-$i.png"
done
python3 - <<'PY'
import hashlib, json
d = json.load(open('prior/images.json'))
assert hashlib.sha256(open('work/img-1.png','rb').read()).hexdigest() == d["images"][0]["sha256"], "image_1 changed in transit"
PY
```

### 2. Mechanical checks with `b-qa-gate`

`acceptance.json` names the square canvas. The first command writes a copy for this order's own
canvas (`W` by `H`) into `work/`, so a `9:16` or `16:9` order is checked against its own size.
Then `check.py` runs once per image. Every check kind in `acceptance.json` is one `b-qa-gate`
owns or is `perceptual`; a kind the block does not know would be a FAIL, never a skip, so do not
edit the spec to make a row go away.

```bash
python3 - "$W" "$H" "$RECIPE_DIR/acceptance.json" <<'PY'
import json, sys
w, h, src = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
spec = json.load(open(src))
for c in spec["checks"]:
    if c["type"] == "dims":
        c["w"], c["h"] = w, h
    if c["type"] in ("luma_floor", "not_flat"):
        c["crop"] = "%d:%d:0:0" % (w, h)
json.dump(spec, open("work/acceptance.json", "w"), indent=1)
PY
: > work/gate-status.txt
for ((i = 1; i <= N; i++)); do
  python3 "$BLOCKS_DIR/b-qa-gate/check.py" --kind image --spec work/acceptance.json \
    --input "work/img-$i.png" --out "work/scorecard-$i.json" && RC=0 || RC=$?
  echo "$i $RC" >> work/gate-status.txt
  [ "$RC" -ne 2 ] || { echo "check.py was run wrongly for image $i; nothing was checked"; exit 1; }
done
```

The exit codes, per image: `0` every check passed and no look is owed; `4` the mechanical checks
passed and the look rows are owed; `1` a check failed (the output names it). An image with exit `1`
is a FAIL: it cannot become a PASS, so do not answer looks for it. Exit `2` is a bad command.

### 3. Answer the looks

For each image with exit `4`, open `work/img-N.png` next to its prompt from `prior/prompts.json`
and answer each LOOK row in `work/scorecard-N.json` (`status` `LOOK`, the question in `question`) with
your own vision tool. The five rows from `acceptance.json` are: (a) the subject is rendered as
prompted, no generation failures; (b) no AI artifacts, watermarks or seams; (c) any text is legible
and spelled right; (d) the palette reads as premium and on-brand; (e) the composition is strong,
with a clear focal point. Write `work/answers-N.json`, one entry per LOOK row id:

```json
{ "subject_rendered": { "answer": "yes", "note": "short reason" },
  "no_artifacts": { "answer": "yes", "note": "short reason" } }
```

Answer `"no"` if you did not really look or are not sure. A `"no"` fails that image.
Then record the answers. This is the second mode of the block, `--finalize`:

```bash
for ((i = 1; i <= N; i++)); do
  RC=$(awk -v n="$i" '$1 == n {print $2}' work/gate-status.txt)
  case "$RC" in
    0) cp "work/scorecard-$i.json" "work/final-scorecard-$i.json";;
    4) python3 "$BLOCKS_DIR/b-qa-gate/check.py" --finalize "work/scorecard-$i.json" \
         --answers "work/answers-$i.json" --out "work/final-scorecard-$i.json" && FRC=0 || FRC=$?
       # 0 final PASS, 1 final FAIL (both write the scorecard); 2 is a bad command and writes nothing
       [ "$FRC" -le 1 ] || { echo "--finalize was run wrongly for image $i"; exit 1; };;
    *) cp "work/scorecard-$i.json" "work/final-scorecard-$i.json";;
  esac
done
```

### 4. Pick the final and write the saves

The final is an image whose finalized scorecard has verdict `PASS`. With a batch, choose the
strongest composition among the passing images by setting `FINAL_N`; without it the first passing
image is used. If the chosen image (or the only image) did not pass, this step fails and names the
failed rows. A scorecard is a record of what the checks and you reported, not proof.

```bash
python3 - "$N" <<'PY'
import json, os, shutil, sys
n = int(sys.argv[1])
cards = {i: json.load(open("work/final-scorecard-%d.json" % i)) for i in range(1, n + 1)}
images = []
for i, c in cards.items():
    images.append({"n": i, "verdict": "PASS" if c["verdict"] == "PASS" else "FAIL",
                   "input_sha256": c.get("input_sha256"),
                   "checks": [{"id": r["id"], "status": r["status"], "detail": r.get("detail", "")} for r in c["checks"]]})
passing = [x["n"] for x in images if x["verdict"] == "PASS"]
fin = int(os.environ.get("FINAL_N") or (passing[0] if passing else 1))
entry = next(x for x in images if x["n"] == fin)
if entry["verdict"] != "PASS":
    bad = ", ".join(r["id"] for r in entry["checks"] if r["status"] != "PASS") or "no row passed"
    sys.exit("image %d did not pass the quality gate (%s)" % (fin, bad))
shutil.copy("work/img-%d.png" % fin, "saves/final.png")
json.dump({"final_n": fin, "images": images}, open("saves/qa_report.json", "w"), indent=1)
print("[r-ai-image] final = image %d; %d/%d passed" % (fin, len(passing), n))
PY
ffprobe -v error -protocol_whitelist file -select_streams v:0 -show_entries stream=width,height -of csv=p=0 saves/final.png
```

## If you cannot proceed

This step has no `canAsk`. Never write `needs_input.json`. A final that fails the gate or a
missing `b-qa-gate` is a failure: exit non-zero with one plain line naming the defect, so the
previous step can regenerate.

## Checks for this step

- `vision_qa_pass` — `saves/qa_report.json` has one entry per image; the `final_n` entry is
  `verdict: "PASS"` and every row of it is PASS.
- `final_dims` — `saves/final.png` is exactly `width`×`height` from `prior/images.json` and
  its centre luma is ≥ 16.
