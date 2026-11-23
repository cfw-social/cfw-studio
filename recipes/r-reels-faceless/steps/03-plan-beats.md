# Plan the scenes

Read `_shared.md` first. Receive `prior/voice_bed.mp4`, `prior/transcripts.json`, optional
`inputs/broll/`, `inputs/cta/` and `brief.json`. Read the block's scene contract,
`"$BLOCKS_DIR/b-broll-sync/SCENE-PLAN.md"`. Produce `saves/scene_plan.json` and `saves/beat_list.json`.
No rendering or provider call happens here. The planner starts no other program, and it never decides
which clip goes with which words: you do, by writing `broll` scenes.

## Inputs to write

- `work/words.json`: the words, `[{text,start,end}]`. A step may start with a fresh `work/` (step 2 saves only
  `transcripts.json`), so rebuild it from the checked save:

```python
import json
words = json.load(open('prior/transcripts.json', encoding='utf-8'))['words']
json.dump(words, open('work/words.json', 'w', encoding='utf-8'), ensure_ascii=False)
```
- `work/brand.json`: the brief's brand (name and the resolved palette from `work/palette.json`) as a
  JSON object. It is copied into each card. Do not print it.
- `work/palette.json` and `work/cta.json`: make them again with the two commands in `_shared.md` if `work/` is fresh. Read them as data.
- The bed duration: probe `prior/voice_bed.mp4` with ffprobe JSON.

## Optional b-roll

An absent or empty b-roll input means an all-graphics reel. Probe every supplied clip; require decodable
video of at least 2 seconds. If clips were supplied but every one is unusable, write `needs_input.json`
for `broll` and stop. If only some fail, report the excluded clips and carry on only if the person said a
partial set is fine. Never fetch stock assets to replace them.

Every clip must be a real file inside `inputs/` (the planner refuses a path anywhere else, a path that
climbs out of the folder, and a link that points out). For usable clips with audible speech you may run
`b-audio` as in step 2 to get cues (`--hint-file` takes a text file of names and product words to help spelling). Write `work/broll_cues.json`:
`[{"clip": "inputs/broll/<file>", "duration": <seconds>, "label": "<short name>", "cues": [{"text","start","end"}]}]`.
With no b-roll, leave the file out and omit `--broll`.

## Author and validate the scene plan

Author `work/scene_plan.json`, one scene per 4 to 6 second idea, splitting longer thoughts. Use
`start_phrase` and `end_phrase` from verbatim transcript words (the validator matches across hyphens), or
`start` and `end` in seconds. Each `graphic` scene has:

| Field | Rule |
| --- | --- |
| `headline` | At most 90 characters of text, plus only `<span class="accent">...</span>` and `<br>`. No title-only cards. |
| `eyebrow` | At most 40 characters. |
| `ghost` | A thematic number or letter (up to 4 characters). Never a placeholder such as `CTA` or `TITLE`. |
| `type` | `hook`, `terminal`, `chips`, `flow`, `checklist`, `stat`, `cta`, `standard` or `typing`. |
| `sub` | Optional, up to 160 characters. |
| text limits | `card_fill.py` refuses longer text (exit 2, naming the field): `eyebrow` 40, `ghost` 4, `sub` 160, `stat` 10, `unit` 14, each `chips` entry 24, each `items` entry 60, each `flow` entry 28, each `lines` entry 60. |
| type fields | `lines` (terminal, 1 to 8 texts), `chips` (2 to 8), `items` (checklist, 2 to 6), `flow` (2 to 5), `stat` (up to 10 characters) and `unit` (up to 14 characters) for stat, `prompt`, `label`, `card_label`, `bottom_tag` (typing), or for `hook`: `line1`, `line2`, `line3`. |

The `hook` and `typing` cards come from `b-typing-ui`: they have no ghost glyph, the hook card has no hero (its big
title lines are the focus) and the typing card's chat card is its hero. A `typing` scene must be long enough for its
prompt to finish typing: typing starts at 0.5 s and the whole prompt must be on screen 0.6 s before the beat ends,
at `--speed` 1.0 (see "Other arguments" in `"$BLOCKS_DIR/b-typing-ui/README.md"`). Give a long prompt a longer scene,
or shorten the prompt; a beat that ends mid-prompt cuts the text off.

A `broll` scene sets `asset` to a clip listed in `work/broll_cues.json` (its path, file name or label)
and `in` (seconds into the clip). Pin every b-roll window you want: when the plan has `broll` scenes
they are the placements. With none, the planner spaces the clips evenly to meet the coverage setting.
Pick `cover: true` on the strongest mid-content scene, never an empty hook entrance. The final scene is
`type: cta`. Use the exact typed CTA ahead of the brief's defaults; move overflow beyond 90 characters to
`sub`. With no CTA use the script's closing line, and invent no handle.

Run these commands (each is an argument list; `<seconds>` is the bed duration):

```text
node "$BLOCKS_DIR/b-broll-sync/scripts/validate-scene-plan.js" work/scene_plan.json --bed-dur <seconds> --transcript work/words.json
```

Exit 1 lists what to fix; fix and run again. Copy the valid plan to `saves/scene_plan.json`, then:

```text
node "$BLOCKS_DIR/b-broll-sync/scripts/plan.js" --transcript work/words.json --bed-dur <seconds> --scene-plan saves/scene_plan.json --brand work/brand.json --broll work/broll_cues.json --order as-given --out saves/beat_list.json
```

Leave out `--broll` when there is no b-roll. `--order` takes `as-given` or `even` (`transcript-match` is
refused by the block). Add `--coverage`, `--clip-secs`, `--min-secs`, `--max-secs` and `--reuse` only from
the options in `_shared.md`, after checking their ranges (coverage 0 to 100; min above 0; min at most clip
at most max). A validator or planner failure stops the step; never switch to all graphics after a failure.

`beat_list.json` has a `warnings` list (also printed on stderr): a b-roll clip shorter than its scene, or
shorter than `--min-secs`. Read each warning, and report it with the result. The block is stricter about
the files: every file must be a regular file of at most 8 MB inside the run folder, text fields must be
text (a number or list in `eyebrow`, `ghost`, `sub`, `id` or `type` is refused), and number options are
plain decimals.

## Check the beat list

```text
python3 "$RECIPE_DIR/scripts/check_beats.py" --beats saves/beat_list.json --bed-duration <seconds>
```

It checks ordered indices, positive contiguous spans (under 0.1 s gap), the bed length within 0.2 s,
non-empty graphics copy, safe unique slugs, the last beat a graphics `cta`, and for every b-roll beat a
real clip inside `inputs/` with a window that covers the beat. It prints the achieved b-roll share: record
it, and do not claim the requested coverage was met if the clips cannot meet it. Scene fields live inside
`scene`, not on the beat. Record `beats_cover_bed`.
