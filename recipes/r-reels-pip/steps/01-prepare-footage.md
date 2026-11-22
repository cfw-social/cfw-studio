# Prepare footage

Build the **voice bed**: the one continuous, never-cut talking-head track every later step rides
on. Its length is the reel's length; its audio is the only audio in the reel. The video is read
and written on this machine only.

## You receive

- `inputs/talking_head/`: exactly one video file (any orientation, 20 to 60 s). When the folder is
  absent, the clip may arrive as `prior/talking_head.mp4`.
- `brief.json`: nothing used here.

## You must produce

- `saves/voice_track.mp4`: the talking head at its **source** size (a matched pair of baked-in
  bars cropped away, see 2), 30 fps, H.264 yuv420p, AAC 48 kHz stereo, loudness-normalised once to
  about -14 LUFS (`I=-14:TP=-1.5:LRA=11`). No scaling to the canvas here; the card is sized in
  step 5.

## How

```bash
mkdir -p work saves
RECIPE_DIR=${RECIPE_DIR:?set RECIPE_DIR to the absolute path of this recipe folder}
case "$RECIPE_DIR" in /*) ;; *) echo "RECIPE_DIR must be an absolute path"; exit 1 ;; esac
BLOCKS_DIR="$(cd "$RECIPE_DIR/../../blocks" && pwd)" || exit 1
```

### 1. Probe the source

```bash
TH=$(find inputs/talking_head -maxdepth 1 -type f ! -name '.*' 2>/dev/null | sort | head -1); [ -n "$TH" ] || TH=prior/talking_head.mp4
BED_DUR=$(ffprobe -v error -protocol_whitelist file -show_entries format=duration -of csv=p=0 "$TH")
ffprobe -v error -protocol_whitelist file -select_streams a:0 -show_entries stream=codec_type -of csv=p=0 "$TH" | grep -q audio || {
  echo '{ "inputId": "talking_head", "reason": "The talking-head video has no sound. Please upload a 20 to 60 second clip with the speaker voice.", "count": 1 }' > needs_input.json
  echo "talking head has no audio: asked the person (needs_input.json)"; exit 0; }
echo "[pip] source length ${BED_DUR}s"
python3 "$RECIPE_DIR/scripts/check_reel.py" range --video "$TH" --min 15 --max 75 || {
  echo '{ "inputId": "talking_head", "reason": "The talking-head video is shorter than 15 or longer than 75 seconds. Please upload a 20 to 60 second clip with the speaker voice.", "count": 1 }' > needs_input.json
  echo "talking head length out of range: asked the person (needs_input.json)"; exit 0; }
```

### 2. Find a baked-in bar pair (before anything else)

Clips from an avatar tool or a studio render often carry a 16:9 picture between two flat bars.
`scripts/bars.py` samples three frames and prints `crop=W:H:X:Y,` only for a **matched pair**: top
and bottom (or left and right) bars of about the same size and flat colour that leave a picture
within 5 % of 16:9 or 9:16. Anything else (a speaker on a plain backdrop, a one-sided margin)
prints nothing, so a head is never cut. It reads frames as ffmpeg shows them, rotation applied.

```bash
CROP=$(python3 "$RECIPE_DIR/scripts/bars.py" "$TH") || exit 1
echo "[pip] bar crop: '${CROP:-none}'"
```

### 3. Seal the bed: loudness once

```bash
ffmpeg -v error -y -protocol_whitelist file -i "$TH" \
  -vf "${CROP}fps=30,setsar=1,format=yuv420p" \
  -af "loudnorm=I=-14:TP=-1.5:LRA=11" \
  -c:v libx264 -preset medium -crf 18 -c:a aac -b:a 192k -ar 48000 -ac 2 \
  -movflags +faststart saves/voice_track.mp4
python3 "$BLOCKS_DIR/b-qa-gate/check.py" --kind reel --spec "$RECIPE_DIR/acceptance.json" --step voicebed \
  --input saves/voice_track.mp4 --out work/scorecard-bed.json
```

`CROP` is empty or a fixed `crop=...,` string made by `bars.py`; it is not order text. The gate
check must exit 0 (loudness within 1.5 LU of -14, real speech level). Exit 1 means the bed is wrong:
read the failing row, fix the cause, run again. The bed is now sealed: no later step cuts, re-times
or normalises it.

## If you cannot proceed

This step may ask for **`talking_head` only**. The commands above write `needs_input.json` and stop (no
save) when the file is not a decodable video, has no audio, or is shorter than 15 s or longer than 75 s:

```json
{ "inputId": "talking_head", "reason": "The talking-head video could not be used. Please upload a 20 to 60 second clip with the speaker's voice.", "count": 1 }
```

A missing ffmpeg or ffprobe is a failure, not an ask.

## Checks (declared in `manifest.json`)

- `bed_has_audio`: `saves/voice_track.mp4` has one audio stream (AAC 48 kHz stereo).
- `bed_not_black`: a frame at 1 s has mean luma above 16 of 255.
- `bed_loudness`: the `voicebed` gate row passes.
