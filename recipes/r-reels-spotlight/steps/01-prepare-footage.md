# Prepare footage

Build the **speaker bed**: the one continuous, never-cut voice track every later step rides on.
Everything downstream (captions, takeovers, b-roll, end card) is timed against this file, so its
duration is the master reel length.

## You receive

- `inputs/talking_head/` — exactly one video file (any orientation, 20–60 s). Pick it with
  `AVATAR=$(ls inputs/talking_head/* | head -1)`. It is already on local disk; never composite
  from a remote URL.
- `brief.json` — read `options.avatar_layout` (`fill` default, or `letterbox`).

No prior saves: this is the first computer step.

## You must produce

- `saves/voice_track.mp4` — 1080×1920, 30 fps, H.264 yuv420p, AAC 48 kHz stereo, loudnormed
  **once** (`I=-14:TP=-1.5:LRA=11`: the −14 LUFS the final QA gate checks; no later step
  re-normalises), leading dead air trimmed, audio otherwise untouched.

## How

Work in `work/` (the first block makes `work/` and `saves/`).

### 1. Probe the source — the duration is the master reel length

```bash
mkdir -p work saves || exit 1
AVATAR=$(ls inputs/talking_head/* | head -1)
ffprobe -v error -protocol_whitelist file -show_entries format=duration -of csv=p=0 "$AVATAR" || exit 1
SILENCE_LOG0=$(ffmpeg -hide_banner -protocol_whitelist file -i "$AVATAR" -af "silencedetect=noise=-35dB:d=0.5" -f null - 2>&1) || exit 1
printf '%s\n' "$SILENCE_LOG0" | grep -E "silence_(start|end)" || echo "narration continuous"
```

### 2. Detect & crop a baked-in bar pair (BEFORE anything else)

Re-used avatar or studio renders often carry a 16:9 picture baked between two flat bars (white,
cream or mint) at the top and bottom, or a 9:16 picture between two side bars. The
`scripts/bars.py` helper samples three frames and prints `crop=W:H:X:Y,` only for a **matched pair** —
top+bottom (or left+right) bars of about the same size and the same flat colour that leave a
picture within 5 % of 16:9 or 9:16. Anything else (a speaker on a plain backdrop, a one-sided
margin) prints nothing and nothing is cropped, so the head is never cut. It measures frames the
way ffmpeg shows them (rotation applied), so a rotated phone clip is read on the right axes.
A flat seam of 6 rows or fewer (another flat colour) right beside a bar counts as part
of that bar, so no grey line is left at the picture's edge; a band of 7 rows or more is kept.

```bash
CROP=$(python3 "$RECIPE_DIR/scripts/bars.py" "$AVATAR") || exit 1
echo "[spotlight] bar crop: '${CROP:-none}'"
AVATAR_CLEAN="$AVATAR"
```

### 3. Build the bed — full length, scale-to-cover, loudnormed ONCE

```bash
ffmpeg -y -protocol_whitelist file -i "$AVATAR_CLEAN" \
  -vf "${CROP}scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30" \
  -af "loudnorm=I=-14:TP=-1.5:LRA=11" \
  -c:v libx264 -g 30 -keyint_min 30 -pix_fmt yuv420p -c:a aac -ar 48000 -ac 2 work/base.mp4 || exit 1
DUR=$(ffprobe -v error -protocol_whitelist file -show_entries format=duration -of csv=p=0 work/base.mp4) || exit 1
```

`avatar_layout: letterbox` → first get the padding colour, checked to be exactly six hex digits (the brand
background in `brief.json`, else the default navy): `PAD=$(python3 "$RECIPE_DIR/scripts/pad_color.py") || exit 1`.
Then replace the `-vf` with `${CROP}scale=1080:-2,pad=1080:1920:0:(1920-ih)/2:color=$PAD,setsar=1,fps=30`. A key frame every second (`-g 30`) keeps the renderer's seeks exact (it warns about a sparse bed otherwise). **Do not slice the bed** — one unbroken audio track. Loudnorm
happens here and never again in any later step.

### 4. Trim leading dead air only (mandatory, guarded)

Strip the silent buffer before the first word, but ONLY if the first detected silence genuinely
starts within the first 1.0 s — an internal pause mid-content must never be trimmed.

```bash
SILENCE_LOG=$(ffmpeg -hide_banner -protocol_whitelist file -i work/base.mp4 \
  -af "silencedetect=noise=-40dB:d=0.4" -f null - 2>&1) || exit 1
SILENCE_EVENTS=$(printf '%s\n' "$SILENCE_LOG" | grep "silence_" || true)   # no silence at all is fine
SILENCE_START_0=$(echo "$SILENCE_EVENTS" | grep silence_start | head -1 \
  | grep -oE 'silence_start: [0-9.]+' | grep -oE '[0-9.]+$' || echo "999")
SILENCE_END_0=$(echo "$SILENCE_EVENTS" | grep silence_end | head -1 \
  | grep -oE 'silence_end: [0-9.]+' | grep -oE '[0-9.]+$' || echo "0")
TRIM_START=$(python3 -c "
s_start = float('$SILENCE_START_0'); s_end = float('$SILENCE_END_0')
print(max(0, s_end - 0.05) if (s_start < 1.0 and s_end > 0.3) else 0)
") || exit 1
if python3 -c "exit(0 if float('$TRIM_START') > 0.3 else 1)"; then
  ffmpeg -y -ss "$TRIM_START" -protocol_whitelist file -i work/base.mp4 -c copy work/base-trimmed.mp4 \
    && mv work/base-trimmed.mp4 work/base.mp4 || exit 1
  echo "[spotlight] trimmed ${TRIM_START}s of leading silence"
fi
```

### 4b. Give the end card a silent tail

The end card never covers speech, so the bed needs room after the last spoken word.
When the speech runs to the end of the clip (or nearly), hold the last frame with silence until
`cta_duration` + 0.5 s follows the speech end (a tail of at most 3.5 s). The speech end is
where the final silence starts (`silencedetect` −40 dB, 0.3 s); with no trailing silence it is
the clip end. `cta_card: off` adds no tail, and neither does an order with no CTA copy (no `inputs/cta/` text and no
`brand.cta`): step 06 skips the card then, so the tail would be dead air. A clip that already ends in enough silence is
left as it is. The tail is part of the sealed bed: captions, takeovers, checks and the reel all
time against it, and the end card then shows in full right after the last word.

```bash
opt () { python3 -c "import json,sys; print(json.load(open('brief.json')).get('options',{}).get(sys.argv[1],sys.argv[2]))" "$1" "$2"; }
python3 "$RECIPE_DIR/scripts/end_card_tail.py" work/base.mp4 "$(opt cta_card on)" "$(opt cta_duration 3.0)" || exit 1
```

### 5. Seal and save

```bash
cp work/base.mp4 saves/voice_track.mp4 || exit 1
ffprobe -v error -protocol_whitelist file -select_streams v:0 -show_entries stream=width,height -of csv=p=0 saves/voice_track.mp4 || exit 1   # 1080,1920
ffprobe -v error -protocol_whitelist file -show_entries format=duration -of csv=p=0 saves/voice_track.mp4 || exit 1                             # 20–64 s (with the end-card tail)
```

From here on `voice_track.mp4` is sealed: no later step may cut, re-time or re-normalise it.

## If you cannot proceed

This step may not ask for inputs: `talking_head` is a required start input and the runner only
starts the run once it is present. If the file is not a decodable video (ffprobe fails), exit
non-zero with a one-line owner-readable message — that is a failure, not an ask. Do not write
`needs_input.json`.

## Checks

Run the two bed checks with `b-qa-gate`. Exit 0 means both passed; anything else, fix the bed and run
again. They are `bed_dims` (the frame is exactly 1080x1920) and `bed_not_black` (mean luma of the
full frame at 10/30/50/70/90 % is above 16/255: the bed is a real picture, not padding only).

```bash
python3 "$BLOCKS_DIR/b-qa-gate/check.py" --kind reel --spec "$RECIPE_DIR/acceptance.json" \
  --step speakerbed --input saves/voice_track.mp4 --out work/check-speakerbed.json || exit 1
```
