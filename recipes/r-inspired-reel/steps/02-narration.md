# Narrate the script with the brand's avatar

Turn the checked script into a narrated avatar video with `b-heygen`, then fit it to the reel canvas. One paid render. Read `_shared.md` first.

## You receive

- `prior/format.json` and `prior/script.md` from step 1.
- `inputs/avatar_id/avatar_id.md` and `inputs/voice_id/voice_id.md`: the brand's own HeyGen ids. The template ships none; never invent or reuse one.
- `brief.json`: the brand's palette when known. The bot may set `BG` to a six-digit hex colour (with or without `#`) for the avatar's solid background. Default `#14181F`. There is no green screen and no keying: the background is the reel's background.
- The brand's HeyGen key, supplied with the order's private input. See "Provider key" in `_shared.md`: the bot reads it into an unexported shell variable `ORDER_KEY` without echoing it, and it appears only as a per-command prefix on the one render command. It is never typed into command text, written to a file or echoed.
- Optionally `saves/render_record.json` from an earlier attempt in this folder (see below).

## You must produce

- `saves/base_reel.mp4`: the avatar narration at 1080x1920, 30 fps, about -14 LUFS, AAC stereo 48 kHz.
- `saves/render_record.json`: HeyGen's render record (a video id and status, no key), so a rerun never pays twice.

## People and likeness

The script text is uploaded to HeyGen; its retention policy was not checked. HeyGen renders the brand's avatar and voice. Use only an avatar and voice of a person who agreed, supplied by the brand. This template does not build a likeness from the reference reel or from anyone else.

## How

```bash
set -eu   # every command in this step stops the step if it fails
mkdir -p work saves
case "${RECIPE_DIR:-}:${BLOCKS_DIR:-}" in /*:/*) ;; *) echo "RECIPE_DIR and BLOCKS_DIR must be set to absolute paths"; exit 1 ;; esac
RS="$RECIPE_DIR/scripts"
HG="$BLOCKS_DIR/b-heygen/scripts/render.py"
[ -f "$HG" ] || { echo "the b-heygen render.py is missing under BLOCKS_DIR"; exit 1; }
[ -f "$RS/make_base_reel.py" ] || { echo "the recipe scripts are missing under RECIPE_DIR"; exit 1; }
for f in prior/format.json prior/script.md inputs/avatar_id/avatar_id.md inputs/voice_id/voice_id.md; do
  [ -s "$f" ] || { echo "$f is missing or empty"; exit 1; }
done
command -v ffmpeg >/dev/null 2>&1 && command -v ffprobe >/dev/null 2>&1 || { echo "ffmpeg and ffprobe are needed"; exit 1; }
python3 "$RS/check_script_shape.py" --format prior/format.json --script prior/script.md --narration-out work/narration.txt
AVATAR_ID="$(tr -d '[:space:]' < inputs/avatar_id/avatar_id.md)"
VOICE_ID="$(tr -d '[:space:]' < inputs/voice_id/voice_id.md)"
BG="${BG:-#14181F}"
```

The shape check runs again so a changed script is checked again, and it writes `work/narration.txt`: the paragraphs joined into one line of plain text.

### 0. Fill the key variable

The key never appears in command text. The bot's tool supplies it on standard input of this shell, one line from the order's private input. It is read silently into an unexported shell variable, then used only as a prefix on the one render command below (or piped with `--key-stdin`). Do not echo it, do not export it, do not turn on shell tracing, do not write it to a file.

```bash
IFS= read -rs ORDER_KEY
```

The same shell must run this block and the next one. If your tool runs each block in a fresh shell, put the `read` line at the start of the narrate block instead. A shell variable that is not exported is not inherited by the programs the shell starts, which is what you want; only the one render command receives the key, through its own `HEYGEN_API_KEY=` prefix. The other way is `--key-stdin`: replace the prefix with `printf '%s\n' "$ORDER_KEY" | python3 "$HG" --key-stdin ...` (`printf` is a shell built-in, so the key is not in any process's arguments).

### 1. Narrate (one paid render, never repeated)

`b-heygen` creates the video once, polls until it is done, and downloads it. The key is set for this one command only. Ids are checked by the block (letters, digits, `-`, `_`). The first line of output names the failure when there is one.

```bash
# a record from an earlier attempt is put back first, so a rerun resumes that render instead of paying again
[ ! -s saves/render_record.json ] || [ -e work/avatar.mp4.render.json ] || cp saves/render_record.json work/avatar.mp4.render.json
RC=0
HEYGEN_API_KEY="${ORDER_KEY:-}" python3 "$HG" --script work/narration.txt --avatar-id "$AVATAR_ID" --voice-id "$VOICE_ID" \
  --out work/avatar.mp4 --aspect-ratio 9:16 --resolution 1080p --background "$BG" > work/heygen.log 2>&1 || RC=$?
# keep the render record right away, whether the call worked or not
[ ! -s work/avatar.mp4.render.json ] || cp work/avatar.mp4.render.json saves/render_record.json
tail -2 work/heygen.log
[ "$RC" -eq 0 ] || exit 1
```

Exit 3 means no key: tell the person HeyGen is not connected, and stop. Exit 1 on a failed render or a timeout: report it and stop. A rerun with the same `--out` resumes the first render and is not charged again; the block records the render in `work/avatar.mp4.render.json`, and the command above saves that record to `saves/render_record.json` the moment the call returns and puts it back before the next try. Keep `saves/render_record.json` with the order; a rerun in a fresh folder needs it restored first. Delete that file only when the person wants a new, separately charged render (for example with `--speed` changed because the narration came out too long or too short).

### 2. Fit the canvas and the loudness

```bash
python3 "$RS/make_base_reel.py" --avatar work/avatar.mp4 --out saves/base_reel.mp4 --pad-color "$BG"
ffprobe -v error -protocol_whitelist file -show_entries format=duration -of csv=p=0 saves/base_reel.mp4
```

The printed length matters: the final gate needs it within 15 percent of `duration_s` in `prior/format.json`. If it is outside, say so now. The usual fix is a new narration at a different `--speed` (a new paid render, so ask first).

Done when `saves/base_reel.mp4` exists. Check it has a picture and a sound track and is not silent; `make_base_reel.py` refuses a silent one.
