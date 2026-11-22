# Generate the avatar video

Make the talking-head video from the narration text with `b-heygen`, then hand it to the same steps as
the base recipe. This is provider work only: no compositing, no captions, no grade. The output becomes
`talking_head`, which step 1 seals.

**What leaves this machine.** The narration text, the avatar id and the voice id are sent to the provider
(`api.heygen.com`) together with the brand's key. The video is downloaded from the provider's file host.
Nothing else is uploaded. The render is **paid, once per run**: a rerun with the earlier render record
resumes the same render and is not charged again; without the record a new render is a new charge.
This step has not been run against a real account (see the README).

## You receive

- `inputs/script/`: the narration as plain text (`script.txt` or `script.md`) or `script.json` with
  `{"text": "..."}`. 50 to 150 words of plain prose: no stage directions, no markdown.
- `inputs/avatar_id/` and `inputs/voice_id/`: the provider's avatar id and voice id as text. When a
  folder is absent, `brief.json.brand.heygen.avatarId` / `voiceId` is used. This recipe ships no id and
  you never invent or reuse one. The avatar and the voice must be the brand's own, of a person who agreed
  to be shown and heard.
- `brief.json`: `brand` (its `palette.bg` becomes the plain background).
- The brand's provider key. You take it from the order's private input (your own provider connection)
  into the shell variable `BRAND_KEY`: a plain shell variable, **not exported**, assigned without echoing
  or printing it (no `export`, no `echo`, no `set -x`). It is never read from the brief, a file of this
  repository or any other file, never typed into the command text, never written to a file, never in a
  log or your reply. It reaches the provider script only as a per-command prefix on the one render command
  below (or through `--key-stdin`, piped from the variable with the shell's built-in `printf`).

## You must produce

- `saves/talking_head.mp4`: the avatar render as the provider returned it: 9:16 at 720p (720×1280),
  H.264 with the avatar's voice as audio, 20 to 60 s. Not re-encoded, not trimmed, not normalised.
- `saves/avatar_render.json`: the render record (`video_id`, `status`; no key). Keep it: it is what makes
  a rerun resume instead of paying twice.

## How

```bash
mkdir -p work saves
RECIPE_DIR=${RECIPE_DIR:?set RECIPE_DIR to the absolute path of this recipe folder}
case "$RECIPE_DIR" in /*) ;; *) echo "RECIPE_DIR must be an absolute path"; exit 1 ;; esac
BLOCKS_DIR="$(cd "$RECIPE_DIR/../../blocks" && pwd)" || exit 1
python3 "$RECIPE_DIR/scripts/heygen_inputs.py"; RC=$?
[ "$RC" -eq 0 ] || { [ "$RC" -eq 3 ] && exit 0; exit 1; }     # 3: needs_input.json was written, nothing was sent
AVATAR_ID=$(python3 "$RECIPE_DIR/scripts/heygen_inputs.py" --get avatar_id)
VOICE_ID=$(python3 "$RECIPE_DIR/scripts/heygen_inputs.py" --get voice_id)
BACKGROUND=$(python3 "$RECIPE_DIR/scripts/heygen_inputs.py" --get background)
```

`heygen_inputs.py` checks the script (50 to 150 words), checks both ids against `[A-Za-z0-9_-]`, up to
128 characters, writes the narration to `work/narration.txt` (so the text never passes through a shell
string) and the checked values to `work/heygen.json`. **One rule for asking.** A missing or invalid input
found here, before anything is paid, writes `needs_input.json` and the step stops: you ask the person.
After a render exists, a video of the wrong length is a failure, never an ask (see below).

### Render, once

The call is the one `b-heygen`'s README documents. The aspect ratio and resolution come from its fixed
lists: `9:16` and `720p`, because the speaker card of the next steps is 364×504 and is filled from a
portrait frame, which 720×1280 more than covers; 720p is the block's default, and higher resolutions can
depend on the provider plan. The
background is a plain solid colour (the brand's `palette.bg`, else `#0F172A`), not the block's default
green: the colour shows around the avatar inside the card, and step 1 looks for baked-in bars, which a
solid backdrop behind a person is not. The key is set for this one command only.

Fill the key variable first, without echo, as a plain (unexported) shell variable. `read -rs` works the same in
bash and zsh; paste the key from the order's private input, or have your own secret tool assign the variable
without printing it. Do not use `export`, `echo` or `set -x` on it:

```bash
read -rs BRAND_KEY          # nothing is shown; the key stays in this shell only
```

Then the one render command, with the key as a per-command prefix:

```bash
[ -f saves/avatar_render.json ] && [ ! -f work/avatar.mp4.render.json ] && cp saves/avatar_render.json work/avatar.mp4.render.json
HEYGEN_API_KEY="${BRAND_KEY:?HeyGen is not connected for this brand: no key}" \
  python3 "$BLOCKS_DIR/b-heygen/scripts/render.py" --script work/narration.txt \
  --avatar-id="$AVATAR_ID" --voice-id="$VOICE_ID" --out work/avatar.mp4 \
  --aspect-ratio 9:16 --resolution 720p --background "$BACKGROUND"
echo "render exit: $?"
```

The same command with the key piped instead of a prefix (the shell's built-in `printf` keeps it out of any
process list):

```text
printf '%s\n' "$BRAND_KEY" | python3 "$BLOCKS_DIR/b-heygen/scripts/render.py" --key-stdin --script work/narration.txt \
  --avatar-id="$AVATAR_ID" --voice-id="$VOICE_ID" --out work/avatar.mp4 --aspect-ratio 9:16 --resolution 720p --background "$BACKGROUND"
```

| Exit | Meaning | Do |
|---|---|---|
| 0 | `VIDEO_FILE: work/avatar.mp4` printed | go on |
| 3 | no key; nothing was sent | tell the person the provider is not connected; stop |
| 1 | the provider refused, the render failed, timed out, or the download failed | report the printed line and stop. Never run it again to "retry" a failed render without the person's say: a failed render is never resubmitted by the script, and deleting its record starts a new paid one |
| 2 | bad usage or a bad file (a record that is unreadable stops it with nothing sent) | fix the call; delete the record only if the person wants a new paid render |

A killed or timed-out run left `work/avatar.mp4.render.json`: run the same command again and it resumes
that render. Download soon after completion: the provider's link is short-lived.

### Save the record, then check

The render record is saved **first**, so a render that turns out wrong keeps its record and a rerun resumes
it instead of paying again. Then the video is checked.

```bash
cp work/avatar.mp4.render.json saves/avatar_render.json
python3 - <<'PY' || exit 1
import json, subprocess
p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height:format=duration",
                    "-of", "json", "work/avatar.mp4"], capture_output=True, text=True)
info = json.loads(p.stdout or "{}")
kinds = [s.get("codec_type") for s in info.get("streams", [])]
dur = float((info.get("format") or {}).get("duration") or 0)
assert "video" in kinds and "audio" in kinds, "the render has no picture or no audio: %s" % kinds
assert 20 <= dur <= 60, "the render is %.1f s; 20 to 60 s are needed" % dur
print("avatar render OK: %.1f s" % dur)
PY
cp work/avatar.mp4 saves/talking_head.mp4
```

If the check fails, the step fails: nothing is saved as `talking_head`, `saves/avatar_render.json` is kept,
and you tell the person the render was the wrong length. Do not trim the video and do not render again on
your own: a new script and a new render are a new charge, and only the person decides that.

## If you cannot proceed

This step may ask for `script`, `avatar_id` and `voice_id`, only before the render (`heygen_inputs.py`
writes the file). After that, a missing key, a failed render, a timeout or a wrong-length video is a
failure, not an ask: exit non-zero with one plain line and do not resubmit.

## Checks (declared in `manifest.json`)

- `avatar_has_audio`: `saves/talking_head.mp4` has an audio stream and a picture.
- `avatar_length`: 20 to 60 s.
