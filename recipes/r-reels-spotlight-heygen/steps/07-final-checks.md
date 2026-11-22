# Final checks and captions

Prove continuity, bake the first-frame cover, run the `b-qa-gate` checks, answer its looks, run the
delivery gate, and write the per-platform post captions. Nothing creative happens here; a failing gate means the
reel is NOT delivered.

## You receive

- `prior/assembled_video.mp4` — the finished reel at bed length (graded, captioned; with `cta_card`
  on, the full end card right after the last spoken word, over the bed's silent tail).
- `prior/edit_plan.json` — `cover_at`, `takeovers[]`, `duration`.
- `prior/beat_list.json` — only when b-roll was planned (b-roll windows for the continuity proof).
- `prior/transcripts.json` — `.words` (source for the post captions).
- `inputs/cta/cta.json` (or the typed `inputs/cta/cta.md`) — CTA text / brand name / handle when supplied; else `brief.json.brand`.
- `brief.json` — `targets` (platform list), `brand.slug`, intent.

## You must produce

- `saves/final_video.mp4` — 1080×1920 30 fps: a 0.4 s money-shot freeze at position 0 followed by
  the assembled reel; AAC 48 kHz stereo throughout; duration = bed + 0.4 s.
- `saves/cover.png` — the money-shot frame (1080×1920) extracted at `cover_at`.
- `saves/captions.json` — per-platform post text:

```json
{ "default": {"caption": "...", "hashtags": ["..."]},
  "instagram": {"caption": "...", "hashtags": ["..."]},
  "tiktok":    {"caption": "...", "hashtags": ["..."]},
  "youtube":   {"title": "...", "description": "...", "hashtags": ["..."]},
  "linkedin":  {"caption": "..."} }
```

One key per platform in `brief.json.targets` plus `default`. Plain Latin text,
no handle unless the brand has one.

## How

```bash
mkdir -p work saves || exit 1
OUT_RAW=prior/assembled_video.mp4
DUR=$(ffprobe -v error -protocol_whitelist file -show_entries format=duration -of csv=p=0 "$OUT_RAW") || exit 1
```

### 1. Verify — stream sanity + continuity proof

```bash
ffprobe -v error -protocol_whitelist file -show_entries format=duration,size -show_entries stream=codec_type,codec_name,width,height,r_frame_rate -of json "$OUT_RAW" || exit 1
ffmpeg -v error -protocol_whitelist file -i "$OUT_RAW" -f null - || exit 1
python3 "$RECIPE_DIR/scripts/final_gate.py" continuity "$OUT_RAW" || exit 1
```

### 2. First-frame cover (mandatory)

Feeds use frame 1 as the poster; the hook animates from black. Prepend a 0.4 s freeze of the
money shot at `cover_at`.

```bash
COVER_AT=$(python3 -c "import json; p=json.load(open('prior/edit_plan.json')); print(p.get('cover_at', $DUR*0.4))") || exit 1
ffmpeg -y -ss "$COVER_AT" -protocol_whitelist file -i "$OUT_RAW" -frames:v 1 -update 1 work/cover.png || exit 1
ffmpeg -y -loop 1 -t 0.4 -protocol_whitelist file -i work/cover.png -f lavfi -t 0.4 -i "anullsrc=r=48000:cl=stereo" \
  -vf "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30,format=yuv420p" \
  -shortest -c:v libx264 -pix_fmt yuv420p -c:a aac -ar 48000 -ac 2 work/cover-freeze.mp4 || exit 1
# the concat list holds plain relative names inside work/, so `-safe 1` applies and no path is quoted into it
cp "$OUT_RAW" work/main-reel.mp4 || exit 1
printf "file 'cover-freeze.mp4'\nfile 'main-reel.mp4'\n" > work/concat-cover.txt || exit 1
ffmpeg -y -f concat -safe 1 -protocol_whitelist file -i work/concat-cover.txt \
  -c:v libx264 -pix_fmt yuv420p -preset medium -crf 18 -c:a aac -b:a 192k -ar 48000 -ac 2 \
  -movflags +faststart work/final_video.mp4 || exit 1
COVER_DUR=$(ffprobe -v error -protocol_whitelist file -show_entries format=duration -of csv=p=0 work/final_video.mp4) || exit 1
python3 -c "import sys; raw=$DUR; cov=float('$COVER_DUR'); sys.exit(0 if abs(cov-(raw+0.4))<0.1 else 'cover duration mismatch %.2f vs %.2f' % (cov, raw+0.4)); " || exit 1
python3 -c "print('cover OK: %.2fs' % $COVER_DUR)" || exit 1
```

(`anullsrc` must be a lavfi input, not an `-af` filter; the concat must re-encode — `-c copy`
gives non-monotonic DTS.) The video is built in `work/` and copied to `saves/` only after the delivery
check passes (section 4). Frame 0 of `work/final_video.mp4` must not be black — look at
`work/cover.png`; it must show the speaker mid-content, not a card, not a fade.

### 3. QA gate (`b-qa-gate`)

The gate measures what it can and lists what only a look can judge. First write this run's copy of the
spec: it carries the measured bed length. Pass `--no-broll` when the order had no b-roll (it drops the
b-roll look and the b-roll window source).

```bash
mkdir -p work || exit 1
BED_DUR=$(ffprobe -v error -protocol_whitelist file -show_entries format=duration -of csv=p=0 "$OUT_RAW") || exit 1
GATE_ARGS=()
if [ ! -f prior/beat_list.json ]; then GATE_ARGS=(--no-broll); fi
python3 "$RECIPE_DIR/scripts/gate_spec.py" --spec "$RECIPE_DIR/acceptance.json" --bed-duration "$BED_DUR" --out work/acceptance.run.json "${GATE_ARGS[@]}" || exit 1
python3 "$BLOCKS_DIR/b-qa-gate/check.py" --kind reel --spec work/acceptance.run.json --input work/final_video.mp4 --out work/scorecard.json
GATE=$?
echo "gate exit: $GATE"
[ "$GATE" -eq 0 ] || [ "$GATE" -eq 4 ] || exit 1   # 0 passed, 4 passed with looks owed; anything else stops
```

| Exit | Do |
|---|---|
| 0 | Everything passed and no look is owed: go to section 4. |
| 4 | Mechanical checks passed; looks are owed. Answer them (below), then go to section 4. |
| 1 | A check failed: read the `FAIL` lines, fix the earlier step that made it, run again. Never edit the spec. |
| 2 | Your command was wrong; nothing was checked. |

**Answer the looks.** Each `LOOK` row in `work/scorecard.json` has a question; the gate saved seven
frames in `work/scorecard-frames/` (at 0, 5, 20, 40, 60, 80 and 95 %). Open the frames with your own
vision tool and answer each question yes or no. The gate's frames sit at fixed percentages and may
miss a b-roll window: also pull one frame from inside each b-roll beat (add 0.4 s to its time, for the
cover freeze) and look at it, for example
`ffmpeg -y -ss 8.9 -protocol_whitelist file -i work/final_video.mp4 -frames:v 1 -update 1 work/broll-look-1.png`. The questions are: captions legible in the lower band
and not on the face; Latin script only; takeover frames show an opaque card or b-roll clip; grade
subtle, skin natural; no black or empty frame; b-roll beats show the planned clip (only with b-roll);
the voice is audible under every takeover; frame 0 shows the speaker at `cover_at`, not black, not a
card, not a fade. Answer "no" if you did not really look or are unsure. A failed item means you stop
and report which: do not "fix" the picture here (that is a rerun of an earlier step).

Write `work/answers.json` **after you have looked**, one entry for every `LOOK` row id in the scorecard.
Each answer is the word `yes` or the word `no` that your own look gave, with a short note saying what you
saw. This file shape is only a format; nothing here is a pre-filled answer:

```json
{ "<the id of a LOOK row>": { "answer": "<yes or no, from looking at the frames>", "note": "<what you saw>" } }
```

When the file is written, record the answers:

```bash
python3 "$BLOCKS_DIR/b-qa-gate/check.py" --finalize work/scorecard.json --answers work/answers.json --out work/final-scorecard.json || exit 1
```

Exit 0 is a final PASS. Exit 1 is a final
FAIL: a "no", a missing answer, or a mechanical failure. A scorecard is a record, not proof: never
edit it by hand, and run the check again if the video changes.

### 4. Delivery gate (mechanical, hard)

It reads the final scorecard and the spec and checks them together with the file: finalized, verdict PASS, counts that match the rows (no FAIL row, no unanswered look), a PASS row for every check of the spec, and the recorded hash and size equal to the file's. Only when that passes is the video copied to `saves/`, and the saved copy is checked again. A failed gate therefore leaves nothing in `saves/`. A scorecard is a record, not proof: someone who edits it by hand can make it pass.

```bash
python3 "$RECIPE_DIR/scripts/final_gate.py" delivery work/final-scorecard.json work/acceptance.run.json work/final_video.mp4 \
  || { echo "DELIVERY BLOCKED — fix the render (rerun the failing step); do not deliver."; exit 1; }
cp work/final_video.mp4 saves/final_video.mp4 || exit 1
cp work/cover.png saves/cover.png || exit 1
# check the saved copy again: same hash and size as the scorecard records, same rules
python3 "$RECIPE_DIR/scripts/final_gate.py" delivery work/final-scorecard.json work/acceptance.run.json saves/final_video.mp4 \
  || { rm -f saves/final_video.mp4 saves/cover.png; echo "DELIVERY BLOCKED — the saved copy differs; removed it."; exit 1; }
```

### 5. Per-platform post captions

Write `saves/captions.json` yourself from `prior/transcripts.json` words, the brief's intent and
the CTA copy (`inputs/cta/` → `brief.json.brand`): a hook line in the speaker's own words,
one line of value, the CTA; 3–8 relevant hashtags for Instagram/TikTok, a ≤ 100-char title plus
description for YouTube, no hashtags and a fuller first line for LinkedIn. Include the brand handle
only if one exists. Latin script only. Validate: `python3 -c "import json;
c=json.load(open('saves/captions.json')); import sys; sys.exit(0 if 'default' in c else 'captions.json needs a default key')"`.

## If you cannot proceed

This step has no `canAsk`. Never write `needs_input.json`. A gate failure is a failure: the candidate stays in
`work/final_video.mp4` for inspection and nothing is left in `saves/`; exit non-zero and say which check failed and at
which timestamp so the right earlier step can be rerun.

## Checks

All of them are in section 3 and section 4, on `work/final_video.mp4` (and the delivery check again on the copy in `saves/`):

- `qa_gate` — the `b-qa-gate` reel floor: video and audio streams, 1080×1920, 30 fps, length above 0,
  loudness about −14 LUFS, and the frame-0 cover rule (a bright frame, not black or flat).
- `duration_window` — duration within 20–65 s. `canvas_1080x1920` — video stream exactly 1080×1920.
- `frame_not_black` — frames at 5/20/40/60/80/95 % have mean luma above 16/255.
- Looks (your vision pass, section 3): `captions_legible_not_on_face`, `latin_script_only`,
  `takeover_frames_not_blank`, `grade_is_subtle`, `no_black_empty_frames`, `broll_beats_correct`,
  `vo_continuous_bed`, `cover_is_moneyshot`.
- The delivery gate (section 4): the final scorecard is finalized, PASS, agrees with its rows and the spec, and is for this file.
