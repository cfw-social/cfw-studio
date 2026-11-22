# Generate the avatar video

Turn the narration script into the talking-head video with the brand's HeyGen avatar, using the
`b-heygen` block (`../../blocks/b-heygen/`). This is provider work only: no compositing, no captions,
no grade happens here. The output becomes the `talking_head` every later step builds on, so it must be a
clean, decodable 20–60 s portrait clip with the avatar's voice as its audio.

## Read this first: what this step does and does not do

- **The script text is uploaded.** It is sent to HeyGen, together with the avatar id and the voice id, over
  https. Do not use a script you may not share with that provider.
- **The avatar and the voice must be the brand's own**, and of a person who agreed to be used this way.
  This recipe ships no avatar id, no voice id and no name. Never invent or reuse one: ask the person.
- **One paid render per run.** The render is paid at HeyGen. `render.py` writes a record
  (`work/avatar.mp4.render.json`, no key in it) right after it submits. Run the same command again with the
  same `--out` and it **resumes** that render instead of paying a second time. This step copies the record
  to `saves/avatar_render.json` as soon as the render command returns, whether it worked or not, and
  restores it before a rerun, because `work/` is discarded when a step ends. Delete the record only if the
  person asks for a new, separately paid render. A failed render is never resubmitted by the script.
- **The key is never typed into a command, a file or a message.** It is the brand's own HeyGen key and
  comes to you as a private input of the order (a secret prompt or a private pipe), never as text you copy
  into a command. Take it into an **unexported** shell variable without echoing it, and pass it only as a
  per-command prefix on the one render command (section 2). Never write it to a file, never print it, never
  turn on shell tracing, and never put it in your reply or in a `reason` text. With no key the script
  exits 3 and sends nothing: tell the person HeyGen is not connected and stop.
- **Higher resolutions may depend on the provider plan.** That is all this recipe says about plans.
- **Not proven with a real account.** `b-heygen` was only run against a local fake server. Nobody has run
  this step against HeyGen. Check the first paid render yourself, and the shapes against HeyGen's live
  pages.

## You receive

- `inputs/script/script.txt` (or `script.md`) — the narration, plain prose with no stage directions or
  markdown, 50 to 150 words (150 words a minute is 20 to 60 s).
- `inputs/avatar_id/avatar_id.txt` and `inputs/voice_id/voice_id.txt` — one line each; or `brief.json`
  `brand.heygen.avatarId` and `brand.heygen.voiceId`. Supplied by the person.
- The HeyGen key, as a private input (see above).
- `saves/avatar_render.json` — only on a rerun: the render record of an earlier run.
- `brief.json` — `brand` and the usual options.

## You must produce

- `saves/talking_head.mp4` — the avatar render, 9:16 portrait, H.264 + AAC, 20–60 s, audio present.
  Not re-encoded, not trimmed, not loudnormed (step 01 does that). It is saved only after the checks below.
- `saves/avatar_render.json` — the render record (`video_id`, `status`; no key), saved right after the render
  command returns, even when it failed.

## How

Two kinds of problem, two different endings. **Before the render** a missing or invalid input is a question
for the person: `needs_input.json` is written and the step stops (section 1). **After the render** a video
that is the wrong length or not usable is a failure: the record is already saved, and you report it (section 3).

### 1. Check the inputs (nothing is sent or paid yet)

```bash
mkdir -p work saves || exit 1
python3 "$RECIPE_DIR/scripts/heygen_inputs.py" > work/heygen-inputs.txt || exit 1   # on a problem it writes needs_input.json
read -r AVATAR_ID VOICE_ID SCRIPT_FILE < work/heygen-inputs.txt || exit 1
```

It prints the two ids and the script path to the file, or writes `needs_input.json` with one plain reason
and exits 1: stop there and let the person answer. It checks the ids (1 to 128 letters, digits, `-`, `_`) and
the script length; it reads no key.

### 2. Render with HeyGen (`b-heygen`) — never pay twice

The format is fixed here, from `b-heygen`'s own lists: **aspect ratio `9:16`**, **resolution `1080p`**
(a 1080×1920 portrait file; higher resolutions may depend on the provider plan, and if HeyGen refuses, stop
and tell the person rather than switching to another size), and a **plain solid background `#0F172A`** (the
default dark navy of the brand palette). Nothing is keyed out: step 01 scales the picture to fill the frame,
so the avatar plays full-frame on that colour.

First restore the record from an earlier run, if there is one. Then take the key from the private input into
an unexported variable without echo (the second line reads it from the standard input of your shell, which the
person or the harness fills; nothing is shown), and run the one render command with the key as a
per-command prefix. The record is copied back whether the render worked or not.

```bash
if [ -f saves/avatar_render.json ]; then cp saves/avatar_render.json work/avatar.mp4.render.json || exit 1; fi
IFS= read -rs BRAND_KEY
HEYGEN_API_KEY="${BRAND_KEY:?missing}" python3 "$BLOCKS_DIR/b-heygen/scripts/render.py" --script "$SCRIPT_FILE" --avatar-id "$AVATAR_ID" --voice-id "$VOICE_ID" --out work/avatar.mp4 --aspect-ratio 9:16 --resolution 1080p --background "#0F172A"
RC=$?
unset BRAND_KEY
if [ -f work/avatar.mp4.render.json ]; then cp work/avatar.mp4.render.json saves/avatar_render.json || exit 1; fi
if [ "$RC" -ne 0 ]; then exit "$RC"; fi
```

Or, to keep the key out of every environment, pipe it on standard input: replace the prefix line with
`printf '%s\n' "$BRAND_KEY" | python3 "$BLOCKS_DIR/b-heygen/scripts/render.py" ... --key-stdin` (`printf` is a
shell built-in, so the key is not in any argument list). Never write the key as a literal in a command.

It polls every 30 s for up to 30 minutes (`--poll-seconds`, `--max-wait`); run it in the background if your
engine can. It prints one line `VIDEO_FILE: work/avatar.mp4` when done.

| Exit | Meaning | Do |
|---|---|---|
| 0 | done | go to section 3 |
| 1 | HeyGen error, failed render, timeout or a bad download | the record is saved. Report the printed line and stop. Do not delete the record and resubmit. A timeout can be resumed by running the commands again |
| 2 | bad input, or a render record that cannot be read | fix the input; if the record is unreadable the person decides whether to delete it (a new paid render) |
| 3 | no key | tell the person HeyGen is not connected; nothing was sent |

### 3. Verify and save

```bash
python3 "$RECIPE_DIR/scripts/check_avatar.py" work/avatar.mp4 || exit 1
cp work/avatar.mp4 saves/talking_head.mp4 || exit 1
```

`check_avatar.py` fails with one plain line when the file is not a decodable video, has no audio stream, is
not portrait, or is outside 20–60 s. This is a **failure**, not an ask: the render is already done and its
record is in `saves/avatar_render.json`. Report it and stop. A different script means a new, separately paid
render, which only the person decides.

## If you cannot proceed

- Before the render (missing or invalid script, avatar id or voice id): `heygen_inputs.py` has written
  `needs_input.json` with one plain reason. Stop; the person answers; run the step again.
- No key: exit 3, nothing sent. Tell the person HeyGen is not connected and stop. Do not write
  `needs_input.json` for a key.
- After the render: a failed render, a timeout or a wrong-length video is a failure with the record saved,
  never an ask.
- Never fall back to another provider or to a pre-made clip: for a clip you already have, use
  `r-reels-spotlight`.

## Checks

Before the render, the script is checked against the gate's `script_timed_20_60s` rule (50 to 150 words at
150 words a minute, which `heygen_inputs.py` enforces). After it, the `generate_avatar` checks run on the
saved video: 1080×1920, 20–60 s, an audio stream, not black. Exit 0 means pass.

```bash
python3 "$BLOCKS_DIR/b-qa-gate/check.py" --kind reel --spec "$RECIPE_DIR/acceptance.json" \
  --step generate_avatar --input saves/talking_head.mp4 --out work/check-avatar.json || exit 1
```
