# Plan b-roll

Runs only when `broll` was supplied. Computes the b-roll takeover **beat list** with the
`b-broll-sync` block (`../../blocks/b-broll-sync/`). Its beats are **merged** with the graphics
takeovers from the edit plan: b-roll beats become additional full-frame picture takeovers; they
never replace the planned graphics and never touch the voice bed.

## You receive

- `inputs/broll/` — the b-roll clips (one or more video files).
- `prior/voice_track.mp4` — probe for `BED_DUR`.
- `prior/transcripts.json` — `.words` for matching, `.broll_cues` per clip.
- `prior/edit_plan.json` — `brand`, `takeovers` (so b-roll beats avoid them), `cover_at`.
- `brief.json` — `options.broll_coverage_pct` (30), `broll_clip_seconds` (4), `broll_min_seconds`
  (2), `broll_max_seconds` (6), `broll_order` (`as-given`), `broll_reuse` (`false`).

## You must produce

- `saves/beat_list.json` — the planner output: `{ beats: [ {index, kind: "broll"|"graphics"|
  "avatar", start, end, broll?: {clip, in, out}, scene?, slug?} ], achieved_broll_pct, shortfall_note? }`.
  `broll.clip` paths are work-folder-relative `inputs/broll/...`.

## How the matching is done (read this first)

**You are the matcher.** You read the transcript and each clip's cues (or look at the clip) and
decide which clip covers which moment. You write those decisions as `broll` scenes in
`work/scene_plan.json` (below). The block's `plan.js` then turns the scene plan into a gapless beat
list **mechanically**. No agent is started and nothing is matched from transcript text by the block.

When the scene plan pins at least one `broll` scene, `plan.js` ignores `--order` and uses your
placements. `--order` only matters when you pin none: `as-given` takes the first clips in the order
listed; `even` takes clips spread across the whole list.

## How

```bash
mkdir -p work saves || exit 1
BED_DUR=$(ffprobe -v error -protocol_whitelist file -show_entries format=duration -of csv=p=0 prior/voice_track.mp4) || exit 1
python3 - <<'PY' || exit 1
import json
t = json.load(open('prior/transcripts.json')); p = json.load(open('prior/edit_plan.json'))
json.dump(t['words'], open('work/words.json','w'))
json.dump(t.get('broll_cues') or [], open('work/broll_cues.json','w'))
json.dump(p['brand'], open('work/brand.json','w'))
PY
```

If `work/broll_cues.json` is `[]` but clips exist in `inputs/broll/`, rebuild it with
`python3 "$RECIPE_DIR/scripts/broll_cues.py"` (one entry per clip with its duration and empty cues)
so placement still works.

### 1. Author `scene_plan.json` (mandatory)

`plan.js` exits 1 rather than hand a blank graphics card downstream, so write
`work/scene_plan.json` first (format: `../../blocks/b-broll-sync/SCENE-PLAN.md`): one `graphic`
scene per 4–6 s idea with `headline` / `eyebrow` / `ghost` / `type` (restating what is said in that
window; mirror the edit plan's takeovers), `avatar` scenes for talking-head windows, `broll` scenes
that pin a clip to a window, and `cover: true` on the scene containing `cover_at`. Scenes must be
gapless and cover 0 to the bed length. Keep b-roll windows clear of the graphics takeovers in
`prior/edit_plan.json`, of the first 2 s, and of the final `cta_duration` (default 3) seconds. A
`broll` scene's `asset` must name a clip in `work/broll_cues.json`, by its exact path or its file name
*with* the extension (for example `broll_a.mp4`), and the clip must be a file inside `inputs/`.

A **complete minimal** scene plan, for a 12-second bed with one b-roll clip. `"version": 1` is required, the
scenes are in order, the first starts at 0, there is no gap, the last has no `end` (it runs to the end of the bed),
and each graphic scene has a headline of plain text plus at most one `<span class="accent">` and `<br>`:

```json
{
  "version": 1,
  "scenes": [
    { "id": "open", "kind": "avatar", "start": 0, "end": 3 },
    { "id": "kw", "kind": "graphic", "start": 3, "end": 6.5, "eyebrow": "THE HABIT",
      "headline": "ASKING <span class=\"accent\">BEATS</span> WAITING" },
    { "id": "clip1", "kind": "broll", "start": 6.5, "end": 9, "asset": "inputs/broll/clip1.mp4", "in": 0 },
    { "id": "end", "kind": "avatar", "start": 9, "cover": true }
  ]
}
```

Validate:

```bash
node "$BLOCKS_DIR/b-broll-sync/scripts/validate-scene-plan.js" work/scene_plan.json \
  --bed-dur "$BED_DUR" --transcript work/words.json || exit 1
```

Exit 1 lists what to fix; fix the plan and run again.

### 2. Run the planner (mechanical, no AI)

`broll_options.py` reads the six `broll_*` options from `brief.json`, checks them and prints them as
one line; any order other than `as-given` or `even` is refused.

```bash
read -r COVERAGE CLIP_SECS MIN_SECS MAX_SECS ORDER REUSE <<EOF || exit 1
$(python3 "$RECIPE_DIR/scripts/broll_options.py")
EOF
node "$BLOCKS_DIR/b-broll-sync/scripts/plan.js" --transcript work/words.json --broll work/broll_cues.json \
  --scene-plan work/scene_plan.json --brand work/brand.json --bed-dur "$BED_DUR" \
  --coverage "$COVERAGE" --clip-secs "$CLIP_SECS" --min-secs "$MIN_SECS" --max-secs "$MAX_SECS" \
  --order "$ORDER" --reuse "$REUSE" --out saves/beat_list.json || exit 1
python3 "$RECIPE_DIR/scripts/beats_guard.py" saves/beat_list.json prior/edit_plan.json "$BED_DUR" || exit 1
```

If a b-roll beat overlaps a graphics takeover, pin the b-roll elsewhere in `scene_plan.json` (or
shorten it) and rerun: the graphics takeovers from the edit plan are fixed.

## If you cannot proceed

This step may ask for **`broll` only**. Write `needs_input.json` and stop (no save) when:

- `inputs/broll/` has no decodable video (every ffprobe fails), or
- the usable clips cannot reach the requested coverage even with reuse and the shortfall leaves
  zero b-roll windows (e.g. all clips are shorter than `broll_min_seconds`).

```json
{ "inputId": "broll", "reason": "The b-roll clips could not be used — please add a few more clips of at least 2 seconds each.", "count": 2 }
```

A shortfall that still yields ≥ 1 b-roll window is NOT an ask: keep the beats, log the
`shortfall_note`, and finish. Tool errors (node missing, planner crash) are failures, not asks.

## Checks

`beats_guard.py` (above) is the check, and it is this recipe's own script, not a `b-qa-gate` check:
`saves/beat_list.json` parses, `beats` contains ≥ 1 `kind: "broll"` beat, every b-roll beat has
`broll.clip` pointing at an existing file in `inputs/broll/` with `0 ≤ in < out ≤ clip duration`,
windows lie within `[2, BED_DUR − 2]`, and no b-roll beat overlaps a graphics takeover from the edit
plan.
