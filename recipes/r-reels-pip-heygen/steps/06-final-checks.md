# Final checks and captions

Prove the voice is continuous, bake the first-frame cover, run the checks of `b-qa-gate`, and write
the per-platform post captions. Nothing creative happens here. A failing check means the reel is
NOT delivered. Everything is local.

## You receive

- `prior/assembled_video.mp4` (the finished reel), `prior/beat_list.json` (`cover_at` and the beats),
  `prior/transcripts.json` (`words`), `inputs/cta/` (CTA copy when supplied), `brief.json`
  (`targets`, `brand`, `intent`).

## You must produce

- `saves/final_video.mp4`: 1080×1920, 30 fps, copied only after the delivery check passes: a 0.4 s freeze of the money shot at position 0, then
  the assembled reel; AAC 48 kHz stereo throughout; length = assembled + 0.4 s.
- `saves/cover.png`: the money-shot frame (1080×1920) taken at `cover_at`.
- `saves/captions.json`: post text per platform, one key per platform in `brief.json.targets` plus
  `default`:

```json
{ "default": {"caption": "...", "hashtags": ["..."]},
  "instagram": {"caption": "...", "hashtags": ["..."]},
  "tiktok":    {"caption": "...", "hashtags": ["..."]},
  "youtube":   {"title": "...", "description": "...", "hashtags": ["..."]},
  "linkedin":  {"caption": "..."} }
```

## How

The final video is built in `work/` and copied to `saves/` only after the delivery check passes.

```bash
mkdir -p work saves
RECIPE_DIR=${RECIPE_DIR:?set RECIPE_DIR to the absolute path of this recipe folder}
case "$RECIPE_DIR" in /*) ;; *) echo "RECIPE_DIR must be an absolute path"; exit 1 ;; esac
BLOCKS_DIR="$(cd "$RECIPE_DIR/../../blocks" && pwd)" || exit 1
IN=prior/assembled_video.mp4
DUR=$(ffprobe -v error -protocol_whitelist file -show_entries format=duration -of csv=p=0 "$IN")
python3 "$RECIPE_DIR/scripts/check_reel.py" voice --video "$IN" --beats prior/beat_list.json || exit 1
```

### 1. The cover freeze (mandatory)

Feeds use frame 1 as the poster. Prepend a 0.4 s freeze of the money shot. The join re-encodes;
a stream copy gives non-monotonic timestamps. The silent audio for the freeze is an `anullsrc`
input, not a filter.

```bash
COVER_AT=$(python3 -c "import json,sys; p=json.load(open('prior/beat_list.json')); print(p.get('cover_at') or round(float(sys.argv[1])*0.4, 2))" "$DUR")
ffmpeg -v error -y -protocol_whitelist file -ss "$COVER_AT" -i "$IN" -frames:v 1 saves/cover.png
ffmpeg -v error -y -protocol_whitelist file -loop 1 -t 0.4 -i saves/cover.png -f lavfi -t 0.4 -i "anullsrc=r=48000:cl=stereo" \
  -vf "scale=1080:1920,setsar=1,fps=30,format=yuv420p" -shortest -c:v libx264 -pix_fmt yuv420p -c:a aac -ar 48000 -ac 2 work/cover-freeze.mp4
cp "$IN" work/assembled.mp4
printf "file 'cover-freeze.mp4'\nfile 'assembled.mp4'\n" > work/concat-cover.txt
ffmpeg -v error -y -protocol_whitelist file -f concat -safe 1 -i work/concat-cover.txt -c:v libx264 -pix_fmt yuv420p -preset medium -crf 18 \
  -c:a aac -b:a 192k -ar 48000 -ac 2 -movflags +faststart work/final_video.mp4
python3 "$RECIPE_DIR/scripts/check_reel.py" duration --video work/final_video.mp4 --expect "$(python3 -c "print(float('$DUR')+0.4)")" --tol 0.2 || exit 1
python3 "$RECIPE_DIR/scripts/check_reel.py" frames --video work/final_video.mp4 || exit 1
```

Look at `saves/cover.png`: the speaker in the card over a content beat, not a title card and not a
fade. If it is not, move `cover_at` in the beat list (rerun this step) rather than shipping it.

### 2. The checks: `b-qa-gate`, and the delivery check that stops the step

`acceptance.json` lists the measured checks (reel floor: size, frame rate, length, loudness near
-14 LUFS, audio, frame 0; duration 20 to 62 s; canvas 1080×1920; no black sample) and the questions
that need a look. A check kind the block does not know is a FAIL, never a skip. The gate runs on
`work/final_video.mp4`; nothing is in `saves/` as the final video yet.

```bash
python3 "$BLOCKS_DIR/b-qa-gate/check.py" --kind reel --spec "$RECIPE_DIR/acceptance.json" \
  --input work/final_video.mp4 --out work/scorecard.json
GATE=$?; echo "gate exit: $GATE"
[ "$GATE" -eq 0 ] || [ "$GATE" -eq 4 ] || { echo "the gate failed (exit $GATE): do not deliver"; exit 1; }
```

| Exit | Do |
|---|---|
| 1 | A check failed. The step stops (above). Fix the cause in the earlier step and rerun it. |
| 2 | Your command was wrong. The step stops. Fix it. |
| 4 | Mechanical checks passed; looks are owed. Open each PNG in `work/scorecard-frames/` and answer every `LOOK` row from what you see, then finalize. |
| 0 | No look is owed. Finalize with an empty answers file. |

Write `work/answers.json` with one entry per `LOOK` row id, the answer `"yes"` or `"no"`, and a short note
saying what you saw. The answers come from looking at the frames; nothing here pre-fills them, and you
answer `"no"` when you did not look or are unsure:

```json
{ "<check id>": { "answer": "yes", "note": "what I saw in the frame" } }
```

Never edit the scorecard by hand. Then finalize, and run the delivery check. It exits non-zero, and the
step stops, unless the scorecard is finalized with the verdict PASS and records exactly this video file:

```bash
python3 "$BLOCKS_DIR/b-qa-gate/check.py" --finalize work/scorecard.json --answers work/answers.json --out work/final-scorecard.json \
  || { echo "finalize failed: a look was answered no, a look has no answer, or a check failed: do not deliver"; exit 1; }
python3 "$RECIPE_DIR/scripts/check_delivery.py" --video work/final_video.mp4 --scorecard work/final-scorecard.json \
  --spec "$RECIPE_DIR/acceptance.json" || exit 1
cp work/final_video.mp4 saves/final_video.mp4
python3 "$RECIPE_DIR/scripts/check_delivery.py" --video saves/final_video.mp4 --scorecard work/final-scorecard.json \
  --spec "$RECIPE_DIR/acceptance.json" || { rm -f saves/final_video.mp4; exit 1; }
```

The second delivery check proves the file in `saves/` is the file that passed. A "no" on a look means stop
and report which look and which earlier step to rerun; do not touch the picture here. The looks, which are the
`LOOK` rows of the scorecard and the keys of `answers.json` (the same ids and questions as in `acceptance.json`):

| Look id | Question |
|---|---|
| `bg_has_content` | The background behind and around the speaker card is not black: real footage or a card is visible in every sample frame. |
| `face_whole_in_pip` | The complete face shows in the speaker card, forehead to chin, not cropped at the top or bottom and not stretched. |
| `pip_on_screen_with_margin` | The speaker card is fully on screen with a clear gap below it (a 110 px margin) and a ring in the brand colour. |
| `content_above_pip_only` | Cards and captions occupy the upper zone only; nothing invades the bottom band where the speaker card sits. |
| `bg_fills_full_width` | The background fills the full frame width: no side bars, no top or bottom bands, no distortion. |
| `captions_legible_not_over_pip` | Captions are legible, the emphasis words are in the brand accent, and no caption overlaps the speaker card. |
| `latin_script_only` | All captions and card text use Latin script only. |
| `broll_beats_correct` | Where the plan placed a b-roll clip, that clip is on screen; where it did not, a card is. |
| `cover_is_moneyshot` | Frame 0 shows the speaker card over a content beat (the planned money shot): not black, not a title card, not a fade. |

### 3. Post captions

Write `saves/captions.json` yourself from the words, the brief's `intent` and the CTA copy: a hook
line in the speaker's own words, one line of value, the call to action; 3 to 8 hashtags for
Instagram and TikTok; for YouTube a title of at most 100 characters plus a description; for
LinkedIn no hashtags and a fuller first line. Include the brand handle only if one exists. Latin
script only. Then:

```bash
python3 -c "import json; c=json.load(open('saves/captions.json')); assert 'default' in c and all(t in c for t in json.load(open('brief.json')).get('targets', []))"
```

## If you cannot proceed

No `canAsk`; never write `needs_input.json`. A gate failure is a failure: leave
`work/final_video.mp4` and the scorecards in place for inspection, put nothing in `saves/final_video.mp4`,
exit non-zero and say which check failed and at which time, so the right earlier step can be rerun.

## Checks (declared in `manifest.json`)

- `qa_gate`, `duration_window`, `canvas_1080x1920`, `frame_not_black`: rows of the final scorecard, and
  `check_delivery.py` passes for the saved file.
- The nine looks above, answered through `--finalize`.
