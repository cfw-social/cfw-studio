# b-broll-sync

Check a bot-written scene plan against the transcript, then turn it into a gapless beat list of graphics cards and b-roll clips. Planner only; it renders nothing and never chooses clips for you.

Use when a reel recipe needs a beat list: stretches of the voice bed that show a text card, a
b-roll clip, or the speaker. Read `SCENE-PLAN.md` for the plan format.

You decide which clip goes with which words. Write `broll` scenes in the scene plan, with `asset`
set to a clip listed in your b-roll cues file. The block will not pick clips from transcript text.

## Steps

1. Write `work/scene_plan.json` (one `graphic` scene per card, each with a headline; `broll` scenes where you want clips).
2. Check it:
   `node "$BLOCKS_DIR"/b-broll-sync/scripts/validate-scene-plan.js work/scene_plan.json --bed-dur S --transcript work/words.json`
   Exit 1 lists what to fix. Fix and run again.
3. Build the beat list:
   `node "$BLOCKS_DIR"/b-broll-sync/scripts/plan.js --transcript work/words.json --bed-dur S --scene-plan work/scene_plan.json --brand work/brand.json --broll work/broll_cues.json --out work/beat_list.json`
   Leave out `--broll` when there is no b-roll.
4. Read `beat_list.json`: beats cover 0 to the bed length with no gap.

## Rules

- Run from the work folder. Every file you pass must be inside it. Clips must be files inside `inputs/`.
- `--order as-given` uses the first clips in listed order; `even` picks clips spread across the whole list. Any other value is an error.
- Exit 1: fix the plan or the data. Exit 2: fix the command or the path.
- No network, no keys.
