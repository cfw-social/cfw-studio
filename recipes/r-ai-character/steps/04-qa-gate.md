# Vision QA and final checks

Run the `b-qa-gate` checks on every scene, look at each scene against the reference and answer
the look questions, then record the answers. Only a set where every scene passes leaves
this step.

## You receive

- `prior/scenes.json`: `width`, `height`, `count`, `scenes[]` (`n`, `sha256`, `attempts`).
- `prior/scene_1.png`: the cover scene.
- `prior/scene_sheet.png`: all scenes in one row, in order.
- `prior/char_ref.png`: the locked reference.
- `prior/character_lock.json`: `attributes` (what to compare against).
- `prior/story_arc.json`: what each scene must show.
- `brief.json`: `brand` (slug), `intent`.
- `$RECIPE_DIR/acceptance.json` and the `$BLOCKS_DIR/b-qa-gate` block (see `_shared.md`: `BLOCKS_DIR` is `$RECIPE_DIR/../../blocks`).

## You must produce

- `saves/final.png`: the cover scene (scene 1), exact canvas, confirmed as the cover.
  This is not the whole scene set. The manifest saves only the cover and the contact sheet,
  not one output per scene in order. Keep every passing full-resolution scene in story order
  yourself. Neither the cover nor `scene_sheet` replaces the complete set.
- `saves/qa_report.json`: `{ "final_n": 1, "scenes": [ { "n", "verdict": "PASS", "counts",
  "checks": [ { "id", "status", "answer", "note" } ] } ] }`, built from the final scorecards
  by the script in section 5. It is not written by hand.

## How

The blocks below share the variables `N` and `BLOCKS_DIR`. Run them in one shell, or run the
first block again before a later one.

```bash
mkdir -p work saves
[ -n "${RECIPE_DIR:-}" ] || { echo "RECIPE_DIR is not set; point it at this recipe folder"; exit 1; }
BLOCKS_DIR="$RECIPE_DIR/../../blocks"
[ -f "$BLOCKS_DIR/b-qa-gate/check.py" ] || { echo "the b-qa-gate check.py is missing under the blocks folder"; exit 1; }
N=$(python3 -c "import json;print(json.load(open('prior/scenes.json'))['count'])")
```

### 1. Re-split the set from the sheet

```bash
cp prior/scene_1.png work/scene-1.png
for ((i = 2; i <= N; i++)); do
  convert prior/scene_sheet.png -crop "1080x1920+$(( (i-1)*1080 ))+0" +repage "work/scene-$i.png"
done
python3 - <<'PY'
import hashlib, json
d = json.load(open('prior/scenes.json'))
assert hashlib.sha256(open('work/scene-1.png','rb').read()).hexdigest() == d["scenes"][0]["sha256"], "scene_1 changed in transit"
PY
```

### 2. Run the gate on each scene

`check.py --kind image` runs the mechanical checks (size, centre brightness, not flat) and
turns each perceptual line of `acceptance.json` into a look the bot must answer. Scene 1 runs
with `--step cover`, which adds the cover question. Exit 0 or 4 continues; exit 1 means a
mechanical check failed (the scene is regenerated); exit 2 means the command was wrong.
A check kind the gate does not know is a failure, never a skip. Do not edit the spec to make
a failure go away.

```bash
for ((i = 1; i <= N; i++)); do
  RC=0
  if [ "$i" -eq 1 ]; then
    python3 "$BLOCKS_DIR/b-qa-gate/check.py" --kind image --spec "$RECIPE_DIR/acceptance.json" --step cover \
      --input "work/scene-$i.png" --out "work/scorecard-$i.json" || RC=$?
  else
    python3 "$BLOCKS_DIR/b-qa-gate/check.py" --kind image --spec "$RECIPE_DIR/acceptance.json" \
      --input "work/scene-$i.png" --out "work/scorecard-$i.json" || RC=$?
  fi
  if [ "$RC" -ne 0 ] && [ "$RC" -ne 4 ]; then
    echo "scene $i failed the mechanical checks (exit $RC); see work/scorecard-$i.json"; exit 1
  fi
done
```

### 3. Look, then answer

For each scene, READ `prior/char_ref.png` and then `work/scene-N.png` (and its arc entry in
`prior/story_arc.json`) with your own vision tool. List the questions to answer:

```bash
python3 - <<'PY'
import json, glob
for f in sorted(glob.glob('work/scorecard-*.json')):
    for c in json.load(open(f))["checks"]:
        if c["status"] == "LOOK":
            print(f, c["id"], "-", c["question"])
PY
```

Write `work/answers-N.json` for each scene, one entry per look id, `yes` or `no` and a short
reason in plain words:

```json
{ "character_consistency": { "answer": "yes", "note": "same hair, outfit and glasses" } }
```

Answer `no` if you did not really look or are unsure. Never answer `yes` for a look you did
not make. The gate records what you say; it does not prove you looked.

### 4. Record the answers

```bash
for ((i = 1; i <= N; i++)); do
  RC=0
  python3 "$BLOCKS_DIR/b-qa-gate/check.py" --finalize "work/scorecard-$i.json" \
    --answers "work/answers-$i.json" --out "work/final-scorecard-$i.json" || RC=$?
  [ "$RC" -eq 0 ] || { echo "scene $i did not pass the final scorecard (exit $RC); regenerate it"; exit 1; }
done
```

Exit 0 is a final PASS. Exit 1 is a final FAIL (a `no`, a missing answer or a mechanical
failure): the scene goes back to the scene step. Exit 2 is a bad command.

### 5. Write the saves

```bash
python3 - <<'PY'
import json, shutil
d = json.load(open('prior/scenes.json'))
report = {"final_n": 1, "scenes": []}
for n in range(1, int(d["count"]) + 1):
    s = json.load(open(f'work/final-scorecard-{n}.json'))
    assert s["verdict"] == "PASS" and s.get("finalized"), f"scene {n} did not pass"
    assert not any(c["status"] != "PASS" for c in s["checks"]), f"scene {n} has a check that is not PASS"
    report["scenes"].append({"n": n, "verdict": "PASS", "counts": s["counts"],
        "checks": [{k: c.get(k, "") for k in ("id", "status", "answer", "note")} for c in s["checks"]]})
assert len(report["scenes"]) == d["count"], "one entry per scene"
assert any(c["id"] == "cover_is_moneyshot" and c["status"] == "PASS" for c in report["scenes"][0]["checks"]), "cover is not confirmed"
shutil.copy('work/scene-1.png', 'saves/final.png')
json.dump(report, open('saves/qa_report.json', 'w'), indent=1)
print(f"[character] {d['count']}/{d['count']} scenes passed; cover confirmed")
PY
ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0 saves/final.png
```

## If you cannot proceed

This step has no `canAsk`. Never write `needs_input.json`. A scene that fails the gate or has a
`no` answer is a failure: exit non-zero with one plain line naming the scene and the defect
so the scene step can regenerate it.

## Checks declared in the manifest

- `vision_qa_pass`: `saves/qa_report.json` has one entry per scene, every `verdict: "PASS"`,
  and `cover_is_moneyshot` passed on scene 1.
- `final_dims`: `saves/final.png` is exactly 1080x1920 and its centre zone luma is 16 or more.
