# Scene plan (version 1)

The scene plan is the bot's list of scenes for a reel: which stretch of the voice bed gets a
text card, which gets a b-roll clip, and which shows the speaker. The bot writes it. This block
checks it and turns it into a beat list. The block never chooses a clip for you: to put b-roll
on certain words, write a `broll` scene there.

```text
 transcript words --+
 bot's scene plan --+--> validate-scene-plan.js --> plan.js --> beat_list.json
 b-roll cues -------+
```

## Shape

```json
{
  "version": 1,
  "bed_duration": 20.0,
  "scenes": [
    { "id": "hook", "kind": "graphic", "start": 0, "end": 4, "type": "hook",
      "eyebrow": "NOBODY TALKS ABOUT THIS", "ghost": "?",
      "headline": "THE TOOL THAT <span class=\"accent\">CHANGED</span> MY WORK" },
    { "id": "demo", "kind": "broll", "start": 4, "end": 9,
      "asset": "inputs/broll/demo.mp4", "in": 0, "cover": true },
    { "id": "cta", "kind": "graphic", "start_phrase": "comment", "headline": "COMMENT <span class=\"accent\">GUIDE</span>",
      "sub": "I will send it over" }
  ]
}
```

| Field | Scene kind | Required | Notes |
|---|---|---|---|
| `version` | top | yes | The number `1`. |
| `bed_duration` | top | no | Seconds. `plan.js` fills it from `--bed-dur` when absent. |
| `scenes` | top | yes | Sorted, gapless, not overlapping, covering 0 to the bed length (0.25 s slack). |
| `id` | any | no | A short name. It becomes the beat slug `beat<N>-<id>`. |
| `kind` | any | yes | `graphic`, `broll` or `avatar`. |
| `start`, `end` | any | yes, or phrases | Seconds. Or `start_phrase` and `end_phrase`: words from the transcript. `end_phrase` is the first word of the next scene. A scene with no `end` ends where the next one starts; the last ends at the bed length. |
| `headline` | graphic | yes | Plain text plus only `<span class="accent">...</span>` and `<br>`. At most 90 characters of text. Empty is an error. |
| `eyebrow` | graphic | no | At most 40 characters. |
| `ghost` | graphic | no | At most 4 characters. |
| `sub`, `type` | graphic | no | `type` defaults to `standard`. |
| other keys | graphic | no | Copied to the beat's `scene` unchanged, for the card builder (`lines`, `chips`, and so on). |
| `asset` | broll | yes | Must name a clip in the `--broll` cues file: its exact path, its file name, or its `label`. Nothing else is accepted. |
| `in` | broll | no | Where in the clip to start, in seconds. The window is as long as the scene. |
| `asset` | avatar | no | Passed through to the beat for the recipe. |
| `cover` | any | no | `true` on one scene sets `cover_at` to that scene's start plus half its length (at most 2 s). |

## What the validator refuses (exit 1)

1. A graphic scene with no headline text.
2. Markup in a headline other than the accent span and `<br>`.
3. A graphic scene shorter than 1 s or longer than 12 s (a warning above 8 s).
4. Scenes out of order, overlapping by more than 0.05 s, with a gap over 0.25 s, not starting at 0, or not reaching the end of the bed.
5. A `broll` scene with no `asset`, or `in` below 0.
6. A phrase that is not in the transcript.

## How `plan.js` uses it

- If the plan has `broll` scenes, they are the b-roll placements. `--order` is ignored.
- If it has none, `plan.js` places windows from the `--broll` list to meet `--coverage` (see README).
- Every remaining graphics window is filled from the `graphic` and `avatar` scenes that overlap it.
  A fragment shorter than `--min-card-secs` joins its neighbour. A window no scene covers is an error.
- `title_html` holds the headline as a restricted HTML fragment (text, `<span class="accent">`, `<br>` only); see README. Other scene values are plain text for the consumer to escape.
- Each graphics beat gets `scene: { eyebrow, ghost, title_html, sub, type, scene_id, source, brand, ... }` and a `slug`.
- `avatar` scenes become `kind: "avatar"` beats with `avatar.asset`, left to the recipe.

## b-roll cues file (`--broll`)

```json
[ { "clip": "inputs/broll/demo.mp4", "duration": 12.4, "label": "demo",
    "cues": [ { "start": 0.0, "end": 3.2, "text": "words spoken in the clip" } ] } ]
```

`clip` is a path relative to the work folder, and the file must exist inside the inputs folder
(`inputs` by default). `duration` and `label` are optional. `cues` are for the bot's own matching;
`plan.js` does not read them.
