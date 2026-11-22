# Assemble

Marry the rendered picture back to the sealed voice bed, burn kinetic captions, grade and add sound
effects under the voice with the `b-reel-premium` block, and finish with the branded CTA end card as
a **tail takeover** of the bed. Nothing is appended. Total duration = bed duration.

## You receive

- `prior/voice_track.mp4` — the sealed bed; its audio is the ONLY voice source. Never cut, re-time
  or loudnorm it.
- `prior/rendered_scenes.mp4` — silent picture: bed + graphics takeovers (+ b-roll takeovers).
- `prior/edit_plan.json` — `grade`, `brand`, `sfx[]`, `caption_groups[]`, `takeovers[]`.
- `prior/transcripts.json` — `.words` for the end-card timing.
- `inputs/cta/cta.json` — `{"text","brandName","handle"}` when the owner supplied a CTA (a typed
  answer arrives as `inputs/cta/cta.md`: plain text, read by `scripts/cta_copy.py`); dir absent →
  the brand block of `brief.json` (`brand.name`, `brand.handle`, `brand.cta` if present).
- `brief.json` — `options.captions` (on), `options.sfx` (on), `options.cta_card` (on),
  `options.cta_duration` (3), `options.music` (none).

## You must produce

- `saves/assembled_video.mp4` — 1080×1920 30 fps, H.264 + AAC 48 kHz stereo, exactly the bed's
  duration: graded picture, captions burned, SFX under the voice, end card over the last
  `cta_duration` seconds but never before the last spoken word ends. No cover frame yet; that is
  the final step.

## How

```bash
mkdir -p work/premium saves || exit 1
cp prior/edit_plan.json work/plan.json || exit 1
python3 -c "import json; json.dump(json.load(open('prior/transcripts.json'))['words'], open('work/words.json','w'))" || exit 1
opt () { python3 -c "import json,sys; print(json.load(open('brief.json')).get('options',{}).get(sys.argv[1],sys.argv[2]))" "$1" "$2"; }
CTA_CARD=$(opt cta_card on); CTA_DURATION=$(opt cta_duration 3.0)
BED_DUR=$(ffprobe -v error -protocol_whitelist file -show_entries format=duration -of csv=p=0 prior/voice_track.mp4) || exit 1
# Renderer setup, once per work folder (see _shared.md): skip what is already here.
[ -d hyperframes-runtime ] || python3 "$BLOCKS_DIR/b-hyperframes/scripts/hf_install.py" || exit 1
[ -s vendor/gsap.min.js ] || python3 "$BLOCKS_DIR/b-hyperframes/scripts/fetch_gsap.py" --outdir vendor || exit 1
```

### 1. Put the voice bed under the picture

`b-reel-premium` reads one reel that already has its audio, and grades and mixes from that. Make it
by joining the silent rendered picture with the bed's audio, copying both streams as they are. The
audio is not touched.

```bash
ffmpeg -y -protocol_whitelist file -i prior/rendered_scenes.mp4 -protocol_whitelist file -i prior/voice_track.mp4 -map 0:v -map 1:a -c copy -movflags +faststart work/reel.mp4 || exit 1
```

### 2. The premium plan, then kinetic captions, grade and sound effects

`premium_plan.py` carves the block's plan (grade, caption colours, caption groups, sound-effect cues,
and a music file if the brief names one inside `inputs/`) out of the edit plan, and prints
`CAPTIONS SFX GRADE`: the first two (`on` or `off`) from the brief's options, then the plan's grade.
Then, in the order the block documents. The footage never goes through the renderer here: the renderer
draws only the captions, as a transparent video, and `mux.py` lays them over the graded footage.

```bash
python3 "$RECIPE_DIR/scripts/premium_plan.py" --edit-plan prior/edit_plan.json --brief brief.json --out work/premium/plan.json \
  > work/premium/flags.txt || exit 1
read -r CAPTIONS SFX GRADE < work/premium/flags.txt || exit 1
PREMIUM="$BLOCKS_DIR/b-reel-premium/scripts"
python3 "$PREMIUM/check_plan.py" --plan work/premium/plan.json --reel work/reel.mp4 --cover-tolerance 4.5 \
  --captions "$CAPTIONS" --sfx "$SFX" || exit 1
if [ "$CAPTIONS" = "on" ]; then
  python3 "$PREMIUM/build_comp.py" --plan work/premium/plan.json --reel work/reel.mp4 --cap-top 1180 \
    --outdir work/premium/comp --cover-tolerance 4.5 || exit 1
  python3 "$BLOCKS_DIR/b-hyperframes/scripts/hf_render.py" --comp work/premium/comp --out work/premium/captions.mov \
    --format mov --quiet > work/premium/render.log 2>&1 \
    || { echo "captions: render failed: $(tail -n 5 work/premium/render.log | tr '\n' ' ')" >&2; exit 1; }
  python3 "$PREMIUM/mux.py" --reel work/reel.mp4 --captions-mov work/premium/captions.mov --plan work/premium/plan.json \
    --out work/premium/polished.mp4 --sfx "$SFX" || exit 1
else
  python3 "$PREMIUM/mux.py" --reel work/reel.mp4 --no-captions --plan work/premium/plan.json \
    --out work/premium/polished.mp4 --sfx "$SFX" || exit 1
fi
python3 "$PREMIUM/qa.py" --reel-in work/reel.mp4 --reel-out work/premium/polished.mp4 --frames-dir work/premium/qa \
  --captions "$CAPTIONS" --sfx "$SFX" --grade "$GRADE" || exit 1
```

Notes on what the block does:

- Captions are burned exactly once, on the fully composited picture, so they sit on top of
  takeovers and b-roll. Never feed `polished.mp4` back in (double burn), and never burn captions
  with raw `ffmpeg drawtext`.
- `mux.py` grades the footage first and then lays the captions over it, so the captions keep their exact
  brand colours. It mixes the effects under the reel's own audio with `amix=normalize=0`: **never
  loudnorm here**; the voice stays at exactly the level sealed in step 01. The eight sound effects are
  read from the block's `assets/sfx/`; sound names outside the fixed eight, or a gain above 0.6, fail
  `check_plan.py`. With `sfx: off` no effect is mixed. With `captions: off` no caption page is built.
- `options.music`, when set, is a file inside `inputs/`; the block refuses any other path. Its level
  is the block's (gain 0.15, up to 0.3); there is no fade or ducking.
- The caption band top is y=1180, the block's value for a full-frame speaker with nothing in the lower
  half (takeover cards keep their content in the top ~55 %). The brand accent goes on the emphasis
  word. The caption font is the machine's generic sans-serif unless a brand font file is supplied (see
  the block's README).
- Look at the four frames `qa.py` saved in `work/premium/qa/`: captions legible and clear of the
  face, accent on emphasis words, grade subtle.

### 3. CTA end card — tail takeover, per-brand copy

**No CTA text at all → no end card.** The copy is `inputs/cta/cta.json` `text`, else the typed
answer in `inputs/cta/cta.md` (or `cta.txt`), else `brief.json` `brand.cta`. With none, the step
logs the skip and never writes generic copy such as "Follow <brand> for more". **No handle → no
handle line.** Never invent a handle or reuse another brand's.

**The card never covers speech.** It starts at `max(bed − cta_duration, last word end)`, where the
last word end is the latest `end` in `work/words.json` or `e` in the plan's `caption_groups`. The
card covers the rest of the bed and is rendered at that length. The silent tail from *Prepare
footage* always leaves room, so when less than 1.0 s of bed is left after the last word the step
fails (exit 1) with the reason instead of shipping a reel with no end card.

The copy is resolved to `work/cta.json` and read by the card script as data; it is never put in a
shell command or evaluated, and it enters the card page escaped.

```bash
python3 "$RECIPE_DIR/scripts/cta_copy.py" resolve --inputs inputs/cta --brief brief.json --out work/cta.json \
  || exit 1   # an unreadable cta file / brief.json stops the step, it does not skip the card
if [ "$CTA_CARD" = "on" ] && ! python3 "$RECIPE_DIR/scripts/cta_copy.py" has-text work/cta.json; then
  echo "[spotlight] end card skipped: the order has no CTA copy; no generic copy is invented" >&2
  CTA_CARD=off
fi
CTA_START=""
if [ "$CTA_CARD" = "on" ]; then
  CTA_START=$(python3 - "$BED_DUR" "$CTA_DURATION" <<'PY' || exit 1
import json, sys
bed, want = float(sys.argv[1]), float(sys.argv[2])
ends = [float(w["end"]) for w in json.load(open("work/words.json")) if isinstance(w, dict) and "end" in w]
for g in json.load(open("work/plan.json")).get("caption_groups") or []:
    ends += [float(w["e"]) for w in g.get("words") or [] if isinstance(w, dict) and "e" in w]
if not ends:
    sys.exit("end card: no word timings in work/words.json or the plan caption groups")
print("%.3f" % max(bed - want, max(ends)))
PY
  ) || exit 1
  CTA_DURATION=$(python3 -c "import sys; print('%.3f' % max(0.0, float(sys.argv[1]) - float(sys.argv[2])))" "$BED_DUR" "$CTA_START") || exit 1
  python3 -c "import sys; sys.exit(0 if float(sys.argv[1]) >= 1.0 else 'end card: only %ss of bed after the last spoken word (needs 1.0s); the end-card tail from prepare_footage is missing' % sys.argv[1])" "$CTA_DURATION" || exit 1
fi
if [ "$CTA_CARD" = "on" ]; then
  python3 "$RECIPE_DIR/scripts/cta-card.py" work/plan.json work/cta.json work/cta-card.json \
    --project work/cta-card --gsap vendor/gsap.min.js --duration "$CTA_DURATION" || exit 1   # omits the handle layer when empty
  # The card must animate, so there is no still ffmpeg card: a failed render stops the step.
  python3 "$BLOCKS_DIR/b-hyperframes/scripts/hf_render.py" --comp work/cta-card --out work/cta-card.mp4 --fps 30 --quality high --quiet \
    > work/cta-render.log 2>&1 && [ -f work/cta-card.mp4 ] \
    || { echo "end card: render of work/cta-card failed; no still fallback card: $(tail -n 5 work/cta-render.log | tr '\n' ' ')" >&2; exit 1; }
  ffmpeg -y -protocol_whitelist file -i work/premium/polished.mp4 -itsoffset "$CTA_START" -protocol_whitelist file -i work/cta-card.mp4 \
    -filter_complex "[0:v][1:v]overlay=enable='between(t,${CTA_START},${BED_DUR})':eof_action=pass[v]" \
    -map "[v]" -map 0:a -c:v libx264 -pix_fmt yuv420p -c:a copy -movflags +faststart work/assembled.mp4 || exit 1
else
  cp work/premium/polished.mp4 work/assembled.mp4 || exit 1
fi
```

### 4. Save

```bash
cp work/assembled.mp4 saves/assembled_video.mp4 || exit 1
python3 -c "
import subprocess, sys
d = lambda f: float(subprocess.run(['ffprobe','-v','error','-protocol_whitelist','file','-show_entries','format=duration','-of','csv=p=0',f], capture_output=True, text=True).stdout)
a, b = d('saves/assembled_video.mp4'), d('prior/voice_track.mp4')
if abs(a - b) >= 0.15:
    sys.exit('duration drifted %.2f vs bed %.2f' % (a, b))
print('assembled OK %.2fs' % a)" || exit 1
```

## If you cannot proceed

This step has no `canAsk` (`cta` defaults to the brand). Never write `needs_input.json`. A failed
premium pass, a `LOCAL_ONLY: FAIL` or a failed end-card render is a failure: exit non-zero with one
plain line. There is no still ffmpeg end card to fall back to.

## Checks

`vo_continuous_bed`: for every takeover window in the edit plan (and every b-roll beat when
present), `volumedetect` on `saves/assembled_video.mp4` reports a real (non −inf) `mean_volume`: the
voice is audible under every cutaway and the duration equals the bed's. It is the same continuity
proof as step 07 section 1, run on this file:

```bash
python3 "$RECIPE_DIR/scripts/final_gate.py" continuity saves/assembled_video.mp4 || exit 1
```
