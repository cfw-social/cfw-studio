# QA gate and final checks

Run `b-qa-gate` on every rendered card, READ each card with vision and answer its look questions, record the answers with `--finalize`, and pick the final. An image that fails is a fix-and-re-render job for the
previous steps, not something to deliver.

## You receive

- `prior/images.json` — `width`, `height`, `count`, `cols`, `images[]` (`n`, `sha256`).
- `prior/image_1.png` — card 1 at the exact canvas.
- `prior/contact_sheet.png` — all cards tiled `cols` across in order.
- `prior/plan.json` — what each card must say (`headline`, `items`, `layout`).
- `brief.json` — `brand` (slug, palette), `intent`.
- `$RECIPE_DIR/acceptance.json` and `$BLOCKS_DIR/b-qa-gate/check.py` (read `$BLOCKS_DIR/b-qa-gate/README.md`).

## You must produce

- `saves/final.png`: a selected preview, exact canvas. For a single card it is card 1.
  It is not delivery of a multi-image set. The manifest does not yet define ordered
  delivery of several images, so neither this preview nor `contact_sheet` delivers a set.
  Deliver every passing full-resolution card in plan order (section 6).
- `saves/qa_report.json` — `{ "final_n": 1, "images": [ { "n", "verdict": "PASS",
  "scores": { "no_text_clipping": "PASS", "legible_contrast": "PASS", "consistent_margins":
  "PASS", "on_brand_palette": "PASS", "premium_hierarchy": "PASS" }, "notes": [] } ] }`.

## How

```bash
mkdir -p work saves
read -r W H N COLS < <(python3 -c "import json;d=json.load(open('prior/images.json'));print(d['width'],d['height'],d['count'],d['cols'])")
```

### 1. Re-split the set from the contact sheet

```bash
cp prior/image_1.png work/img-1.png
# Count up with shell arithmetic, not `seq 2 "$N"`: macOS seq prints "2 1" for one card.
for ((i = 2; i <= N; i++)); do
  r=$(( (i-1) / COLS )); c=$(( (i-1) % COLS ))
  convert prior/contact_sheet.png -crop "${W}x${H}+$((c*W))+$((r*H))" +repage "work/img-$i.png"
done
python3 - <<'PY'
import hashlib, json
d = json.load(open('prior/images.json'))
assert hashlib.sha256(open('work/img-1.png','rb').read()).hexdigest() == d["images"][0]["sha256"], "image_1 changed in transit"
PY
```

### 2. Write the spec for this canvas

The shipped `acceptance.json` checks a 1080x1080 canvas. For `portrait` or `banner`, write a copy for the chosen canvas first. For `square` the copy is the same file.

```bash
python3 - "$W" "$H" "$RECIPE_DIR/acceptance.json" <<'PY'
import json, sys
W, H = int(sys.argv[1]), int(sys.argv[2])
spec = json.load(open(sys.argv[3]))
for c in spec["checks"]:
    if c["id"] == "canvas_1080x1080": c.update(id=f"canvas_{W}x{H}", w=W, h=H)
    if c.get("crop"): c["crop"] = f"{W}:{H}:0:0"
json.dump(spec, open('work/acceptance.json', 'w'), indent=1)
PY
```

### 3. Run `b-qa-gate` on each card

`b-qa-gate` measures the exact size, that the card is not black and not a single flat colour. It copies the five look questions of `acceptance.json` into a scorecard as `LOOK` rows. Run it from the work folder, with paths as separate arguments (never build the command from order or brand text):

```bash
for ((i = 1; i <= N; i++)); do
  rc=0
  python3 "$BLOCKS_DIR/b-qa-gate/check.py" --kind image --spec work/acceptance.json \
    --input "work/img-$i.png" --out "work/scorecard-$i.json" || rc=$?
  case "$rc" in
    0|4) ;;                              # passed (4: looks are owed, next section)
    *) echo "card $i failed the gate (exit $rc); see work/scorecard-$i.json" >&2; exit 1;;
  esac
done
```

Exit 1 blocks: fix the card's HTML and re-render. Exit 2 means the command was wrong; nothing was checked. A check kind the block does not know is a failure, never a skip. Do not edit the spec or lower a threshold to pass.

### 4. Look at each card, answer, finalize

READ each `work/img-N.png` next to its plan entry with your own vision tool. For each `LOOK` row in `work/scorecard-N.json` (no clipped text, legible contrast, on-brand palette against `brief.json.brand`, premium hierarchy, consistent margins; for a set, also check consistency across cards), answer `yes` or `no` with a short note in `work/answers-N.json`:

```json
{ "no_text_clipping": { "answer": "yes", "note": "all text inside the card" },
  "legible_contrast": { "answer": "no",  "note": "grey on dark in the footer" } }
```

Every `LOOK` row needs an answer. Answer `no` if you did not really look or are unsure. Then record the answers:

```bash
for ((i = 1; i <= N; i++)); do
  python3 "$BLOCKS_DIR/b-qa-gate/check.py" --finalize "work/scorecard-$i.json" \
    --answers "work/answers-$i.json" --out "work/final-scorecard-$i.json" || echo "card $i: final FAIL" >&2
done
```

A missing answer or a `no` makes that card FAIL. A card that fails is a fix-and-re-render job for the previous steps. If the card file changes, run section 3 again: `--finalize` fails on a changed input. A scorecard is a record, not proof. Never edit one by hand.

### 5. Pick the final and write the saves

Write `work/qa_report.json` from the final scorecards, then check it. `scores` maps each look id to `PASS` or `FAIL`.

```bash
python3 - <<'PY'
import json, shutil
d = json.load(open('prior/images.json'))
images = []
for n in range(1, d["count"] + 1):
    sc = json.load(open(f'work/final-scorecard-{n}.json'))
    looks = [c for c in sc["checks"] if c["type"] == "perceptual"]
    images.append({"n": n, "verdict": sc["verdict"],
                   "scores": {c["id"]: c["status"] for c in looks},
                   "notes": [c["note"] for c in looks if c.get("note")]})
qa = {"final_n": 1, "images": images}   # change final_n to the best passing card when there is a choice
json.dump(qa, open('work/qa_report.json', 'w'), indent=1)
assert len(qa["images"]) == d["count"], "one entry per card"
fin = int(qa["final_n"]); entry = next(i for i in qa["images"] if i["n"] == fin)
assert entry["verdict"] == "PASS" and all(v == "PASS" for v in entry["scores"].values()), f"card {fin} did not pass"
shutil.copy(f"work/img-{fin}.png", "saves/final.png")
json.dump(qa, open('saves/qa_report.json', 'w'), indent=1)
print(f"[gfx] final = card {fin}; {sum(i['verdict']=='PASS' for i in qa['images'])}/{d['count']} passed")
PY
ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0 saves/final.png
```

### 6. Deliver the set

The preview is `saves/final.png`. When the person asked for more than one image, hand over every card that passed, full size and in plan order, as separate files:

```bash
mkdir -p work/out
for ((i = 1; i <= N; i++)); do cp "work/img-$i.png" "work/out/image-$i.png"; done
```

## If you cannot proceed

This step has no `canAsk`. Never write `needs_input.json`. A card that fails `b-qa-gate` or a look is a failure: exit non-zero with one plain line naming the card and the defect so
the authoring step can fix the HTML.

## Checks the order runs

- `vision_qa_pass` — `saves/qa_report.json` has one entry per card; the `final_n` entry is
  `verdict: "PASS"` with every score PASS.
- `final_dims` — `saves/final.png` is exactly `width`×`height` from `prior/images.json` and
  its luma floor is ≥ 16.
