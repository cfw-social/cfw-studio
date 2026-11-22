# Plan the background beats

Write the scene plan and turn it into the **beat list** that tiles the whole voice bed: every
second of the background is a `graphics` beat (a card that restates what is said) or, when b-roll
was supplied, a `broll` beat. `b-broll-sync` checks and tiles; it plans only and renders nothing.
With no b-roll the result is all cards, which is a valid reel.

## You receive

- `prior/voice_track.mp4`: probe it for the bed length.
- `prior/transcripts.json`: `words` and `broll_cues`.
- `inputs/broll/`: the clips, when supplied.
- `brief.json`: `brand` and the `broll_*` options.

## You must produce

- `saves/beat_list.json`: the `b-broll-sync` output `{bed_duration, achieved_broll_pct, cover_at,
  shortfall_note, beats[]}`. Beats run from 0 to the bed length with no gap. A graphics beat has
  `scene` (`title_html`, `eyebrow`, `ghost`, `sub`, `type`, and any other key you put in the scene);
  a b-roll beat has `broll {clip, in, out}` with `clip` a file in `inputs/broll/`. `cover_at` is the
  second of the money-shot frame the final step freezes.

## How

```bash
mkdir -p work saves
RECIPE_DIR=${RECIPE_DIR:?set RECIPE_DIR to the absolute path of this recipe folder}
case "$RECIPE_DIR" in /*) ;; *) echo "RECIPE_DIR must be an absolute path"; exit 1 ;; esac
BLOCKS_DIR="$(cd "$RECIPE_DIR/../../blocks" && pwd)" || exit 1
python3 "$RECIPE_DIR/scripts/options.py" || exit 1
opt () { python3 -c 'import json,sys; v=json.load(open("work/options.json")).get(sys.argv[1]); print("" if v is None else v)' "$1"; }
BED_DUR=$(ffprobe -v error -protocol_whitelist file -show_entries format=duration -of csv=p=0 prior/voice_track.mp4)
python3 - <<'PY'
import json
t = json.load(open('prior/transcripts.json')); b = json.load(open('brief.json'))
json.dump(t['words'], open('work/words.json', 'w'))
json.dump(t.get('broll_cues') or [], open('work/broll_cues.json', 'w'))
json.dump(b.get('brand') or {}, open('work/brand.json', 'w'))
PY
```

### 1. Write `work/scene_plan.json`

The full format is `"$BLOCKS_DIR/b-broll-sync/SCENE-PLAN.md"`; read it. You write the plan; the block never
chooses a clip for you, and no other AI agent is started. A complete minimal plan for a 30 s bed with one
b-roll clip (`"version": 1` is required; scenes are sorted, with no gap, from 0 to the end of the bed):

```json
{ "version": 1,
  "scenes": [
    { "id": "hook", "kind": "graphic", "start": 0, "end": 5, "type": "hook", "eyebrow": "THE TRICK",
      "headline": "MOST PEOPLE WASTE HOURS", "lines": ["MOST PEOPLE", "WASTE HOURS"] },
    { "id": "idea", "kind": "graphic", "start": 5, "end": 13, "type": "standard", "eyebrow": "STEP ONE",
      "headline": "START WITH <span class=\"accent\">ONE</span> IDEA", "cover": true },
    { "id": "clip", "kind": "broll", "start": 13, "end": 19, "asset": "clip_a", "in": 1 },
    { "id": "result", "kind": "graphic", "start": 19, "end": 27, "type": "standard", "eyebrow": "THE RESULT",
      "headline": "A REEL THEY <span class=\"accent\">FINISH</span>" },
    { "id": "tail", "kind": "graphic", "start": 27, "end": 30, "type": "plain", "headline": "end card here" }
  ] }
```

`kind` is `graphic` or `broll`; `start` and `end` are seconds (or `start_phrase` words from the transcript);
`asset` names a clip in `work/broll_cues.json`. A `plain` scene still needs a `headline` for the validator, but
the card draws no text.

- One `graphic` scene per idea of 4 to 6 s, with a `headline` that restates what is said in that
  window, a short `eyebrow` and `ghost` if they help, and `type`. A headline holds plain text plus
  `<span class="accent">...</span>` and `<br>` only; the validator rejects any other markup.
- `type` picks the card: `typing-ui` is a typed-prompt card and needs a `prompt` key in the scene
  (optional `label`, `card_label`; short, and no web address in any text, the render check refuses one); `hook` is a title card (optional `lines`, a list of
  at most three lines of at most 40 characters; otherwise the headline split at `<br>`; optional `eyebrow`); every
  other type (`standard`, `stat`, `chips`, and so on) is this recipe's motion card: the headline, its
  eyebrow and an accent rule on the brand background. Cards are text only; they draw no icon,
  chart or image. Leave a hook's `sub` and a typing card's `bottom_tag` empty: they sit near
  y 1000 to 1100, which is where step 5 puts the captions.
- A `broll` scene for each window where a clip fits the words, with `asset` a name from
  `work/broll_cues.json` (its path, file name or `label`) and `in` the second to start. Keep b-roll
  clear of the first 2 s.
- **Keep the last `cta_duration` seconds (3 by default, the end-card window) on a plain card.** Step 5
  lays the end card, a translucent scrim with the call to action, over those seconds, and any text card
  under it prints through and tangles with it. Make the last scene `type: "plain"` (the card background, no
  text) or a b-roll clip, and end every text card before the window opens. `check_scene_plan.py` below
  refuses a plan that puts a text card there. To end on a call to action inside the background instead, make
  the last scene `type: "cta"`; step 5 then draws no second end card.
- `cover: true` on the scene that is the money shot (a content scene about 40 % in, not the
  opening and not the end card).
- Content must stay in the top of the frame: short lines. Latin script only.

Check it. Exit 1 lists what to fix; fix and run again:

```bash
node "$BLOCKS_DIR/b-broll-sync/scripts/validate-scene-plan.js" work/scene_plan.json \
  --bed-dur "$BED_DUR" --transcript work/words.json || exit 1
python3 "$RECIPE_DIR/scripts/check_scene_plan.py" --plan work/scene_plan.json --bed-dur "$BED_DUR" || exit 1
```

`check_scene_plan.py` exits 1 and names the scene when an end card will be drawn (the option `cta_card` is on and
there is call-to-action copy) and a text card reaches into its window.

### 2. Build the beat list

```bash
BROLL_ARGS=(); [ -d inputs/broll ] && BROLL_ARGS=(--broll work/broll_cues.json)
node "$BLOCKS_DIR/b-broll-sync/scripts/plan.js" \
  --transcript work/words.json "${BROLL_ARGS[@]}" \
  --coverage "$(opt broll_coverage_pct)" --clip-secs "$(opt broll_clip_seconds)" \
  --min-secs "$(opt broll_min_seconds)" --max-secs "$(opt broll_max_seconds)" \
  --order "$(opt broll_order)" --reuse "$(opt broll_reuse)" --bed-dur "$BED_DUR" \
  --brand work/brand.json --scene-plan work/scene_plan.json --out work/beat_list.json
cp work/beat_list.json saves/beat_list.json
python3 - <<'PY'
import json
bl = json.load(open('saves/beat_list.json')); beats = sorted(bl['beats'], key=lambda b: b['start'])
print("beats:", len(beats), "b-roll:", sum(1 for b in beats if b['kind'] == 'broll'), "cover_at:", bl.get('cover_at'))
if bl.get('shortfall_note'): print("note:", bl['shortfall_note'])
for w in bl.get('warnings') or []: print("warning:", w)
PY
```

`BROLL_ARGS` is an array (empty or two words); quote it as `"${BROLL_ARGS[@]}"`, which works in bash and zsh. Read every warning the planner prints (`beat_list.json` has a `warnings` list): a b-roll clip shorter than its scene shortens the beat and stretches the next card; fix the plan if that is not what you want. The orderings are `as-given` and `even`. You place b-roll yourself with
`broll` scenes; when the plan has `broll` scenes they are the placements and `--order` is ignored.
If the plan has no `cover: true` scene, `cover_at` is whatever the block chose; read it and move
it to a content frame if it is not one.

## If you cannot proceed

This step may ask for **`broll` only**, and only when b-roll WAS supplied but is unusable: every
clip fails `ffprobe`, or every clip is shorter than `broll_min_seconds`, so no window can be placed.
Write `needs_input.json` and stop:

```json
{ "inputId": "broll", "reason": "The b-roll clips could not be used. Please add a few more clips of at least 2 seconds each.", "count": 2 }
```

No b-roll is not an ask. A shortfall that still yields one window is not an ask. A missing `node`
or a planner error is a failure.

## Checks (declared in `manifest.json`)

- `beats_cover_bed`: `saves/beat_list.json` parses; beats are contiguous from 0 to the bed length
  (within 0.1 s); every `broll` beat's clip exists inside `inputs/`; `cover_at` lies inside the bed.
