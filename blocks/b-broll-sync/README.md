# b-broll-sync

Checks a reel's scene plan and turns it into a gapless beat list: stretches of the voice bed that
show a text card, a b-roll clip, or the speaker. It plans only. It renders nothing, and it never
decides which clip goes with which words. The bot does that by writing `broll` scenes in the plan.

```text
 words.json ------+
 scene_plan.json -+--> validate-scene-plan.js (exit 0/1) --> plan.js --> beat_list.json
 broll_cues.json -+
 inputs/broll/*.mp4  (clips must live here)
```

## Interface

Run both from the work folder. Every file you pass must resolve inside it.

| Entry point | Arguments | Reads | Writes | Exit codes |
|---|---|---|---|---|
| `scripts/validate-scene-plan.js` | `PLAN.json` `[--bed-dur S]` `[--transcript WORDS.json]` | the two named files | nothing (messages on stderr) | 0 valid, 1 invalid plan, 2 usage, unreadable file or path outside the work folder |
| `scripts/plan.js` | `--transcript WORDS.json` `--out BEATS.json` and the options below | the files named | `--out` only | 0 written, 1 plan or data invalid, 2 usage, unknown ordering, or unsafe path |

`plan.js` options:

| Option | Default | Meaning |
|---|---|---|
| `--transcript` | required | Words `[{text,start,end}]` (`word` also accepted). |
| `--out` | `beat_list.json` | Where to write. Must resolve inside the work folder. |
| `--bed-dur` | last word's end | Length of the voice bed, in seconds. |
| `--scene-plan` | none | The plan file. Without it every card is blank and the run fails (below). |
| `--broll` | none | Cues file `[{clip,duration?,label?,cues?}]`. No file means no b-roll. |
| `--inputs-dir` | `inputs` | Every clip must be a real file inside this folder. |
| `--brand` | `{}` | A JSON object copied into each graphics beat as `scene.brand`. |
| `--coverage` | 30 | Percent of the bed that should be b-roll, when the plan has no `broll` scenes. 0 to 100. |
| `--clip-secs`, `--min-secs`, `--max-secs` | 5, 4, 6 | Window length, and its limits. |
| `--order` | `as-given` | `as-given` or `even`. See "Orderings". Anything else is exit 2. |
| `--reuse` | `false` | `true` lets clips repeat to meet coverage. |
| `--min-card-secs` | 1.0 | A card shorter than this joins its neighbour. |
| `--allow-empty-copy` | off | Write blank cards instead of failing. The bot must then write the copy before any render. |

Any other option is exit 2.

Formats are in [SCENE-PLAN.md](SCENE-PLAN.md). The output `beat_list.json` is
`{bed_duration, achieved_broll_pct, cover_at, shortfall_note, params, beats[]}`. Each beat is
`{index, start, end, kind: "graphics"|"broll"|"avatar", ...}`: graphics beats carry `scene` and a `slug`;
b-roll beats carry `broll: {clip, in, out, match_score, match_reason}`.

## What the files must hold

- Every input file must be a regular file of at most 8 MB, inside the work folder. A named pipe, device or folder is exit 2 and is never opened. The keys `__proto__`, `constructor` and `prototype` are dropped at every depth when a file is read.
- Number options are plain decimals only (`12`, `12.5`, `.5`). `0x10`, `1e2` and spaces are exit 2.
- Transcript words must be objects with a text (`text` or `word`, a string) and real numbers `start` and `end`, with `end` not before `start`, no negative start, and starts that never go back. Anything else is exit 1 with the word's number.
- Text fields must be strings when present, with a cap: `id` 60, `type` 30, `eyebrow` 40, `ghost` 4, `sub` 200, `headline` 90 of text, `asset` 300. A number, object, list or null in one of them is exit 1 ("must be text"), in both scripts. Any other scene key, and every `--brand` and cue value, may hold only text of at most 500 characters, numbers, true or false, lists and objects, nested at most 6 deep.

## `title_html`

`title_html` on a graphics beat is a **restricted HTML fragment**, already safe to insert as HTML. The validator allows only plain text, `<span class="accent">`, `</span>` and `<br>`; every other `<` or `>` is refused, and the spans must be balanced. An `&` is not changed, so an entity the author wrote (`&lt;`) is shown as text. Text that must be shown literally should be written with entities in the plan. All other `scene` values (`eyebrow`, `ghost`, `sub`, and pass-through keys such as `lines`) are plain text, not HTML: a consumer must escape them before putting them in a page.

## Warnings

`beat_list.json` has a `warnings` list (empty when there is nothing to report), and each entry is also printed on stderr. It holds the scene-plan validator's warnings and these:

- A plan `broll` scene whose clip is shorter than the scene (counting from `in`): the beat is shortened, and the next card is stretched back to cover the rest.
- A clip shorter than `--min-secs` when `plan.js` places it: its window is only as long as the clip.

A bed too short for even one window sets `shortfall_note`, and no b-roll is placed.

## Orderings

- Both place the windows at even spacing across the bed and stay within `--coverage`. They differ only in which clips fill the windows when there are more clips than windows:
  - `as-given` (default) uses the first clips, in the order the cues file lists them.
  - `even` picks clips evenly across the whole list (for 5 clips and 2 windows: clips 2 and 4 of the list, counting from 1), so a long list is represented end to end.
- With as many windows as clips, or `--reuse true`, both cycle through the list in order and give the same result.
- The two orderings are `as-given` and `even`. Any other value is exit 2.
- If you need exact clip order and timing, write `broll` scenes in the plan; `--order` is then ignored.

## Clip paths

`--out` is written to a new temporary file in its folder and renamed into place. A target that is a link, a parent folder that is a link pointing outside the work folder, and an output that is the same file as any input are refused (exit 2). An unexpected error prints one fixed line and exits 1, with no stack trace.

A clip is accepted only if its real location, with symbolic links followed, is a file inside
`--inputs-dir`, and that folder is inside the work folder. An absolute path elsewhere, a path that
climbs out with `..`, and a link that points outside are all refused (exit 2) before anything is
written. A plan's `asset` must name a clip that is in the cues file, by exact path, file name or
`label`. A file that is merely present on disk is not enough (exit 1).

## What it needs

Node.js 22 or newer expected; the tests were run on Node 25.9 (22 is untested). No packages. No network. It reads no key and no environment setting, and it
starts no other program.

## Used by

`r-reels-faceless`, `r-reels-pip`, `r-reels-spotlight` and the two HeyGen variants (`r-reels-pip-heygen`, `r-reels-spotlight-heygen`) (recipe templates live under `recipes/` and are added separately). In the spotlight recipes the validator always runs and the planner only when b-roll is supplied.

## Proof

A short summary of the limits below. Where this README does not say, it reads "not recorded".

| What | Status | Detail |
|---|---|---|
| Automated tests | 45 tests, as of 2026-11-22 | `node --test blocks/b-broll-sync/test/broll-sync.test.js`, from the repository root, on Node 25.9. |
| Run on which operating systems | macOS (Apple silicon) only; Linux and Windows not run | Python 3.15.2, Node 25.9.0, ffmpeg 8.1 on one Apple-silicon Mac. |
| Run with a real provider account | no provider | No network, no key. |
| Used in a real start-to-finish recipe run | yes, in recipe template runs with stand-in media on macOS, 2026-11-22 | Part of the reel recipe template runs. The media was generated, not a real reel. |

## Tests

```text
node --test blocks/b-broll-sync/test/broll-sync.test.js
```

Run from the repository root, on Node 25.9 (22 or newer expected, untested). One test needs `mkfifo`; it is reported as skipped if that is missing.

They need no account and no private file. They cover valid plans, gaps and overlaps, a clip outside
the inputs folder, a climbing path, a link that points out, an unknown ordering, an output path
outside the work folder, and a search of the block's own files for any agent command line.

## Limits

- It does not read the clips or decode video. `duration` in the cues file is taken as given.
- `as-given` and `even` do not look at what is said, so they pick clips by position only. Matching clips to words is the bot's work.
- Checking a path at one moment does not stop another process changing it afterwards. Run it in a folder that nothing else writes to.
