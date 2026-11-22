# Composite the PIP reel

Lay the speaker on the background as a rounded, ringed card at the bottom centre, keep the sealed
voice bed as the audio, add ONE end card, then burn kinetic captions, a light grade and sound
effects under the voice in one pass with `b-reel-premium`, and append the outro if there is one.
Everything is local; the setup downloads are listed in the README. The code blocks below share shell
variables (`RING`, `TAKEOVER`, `CTA_DURATION`, `CAPTIONS` and others): run them in one shell session, in order,
or set the variable again before you use it.

## You receive

- `prior/voice_track.mp4`: the sealed bed (picture and the only voice). Never cut, re-time or
  normalise it. `prior/background.mp4`: silent background at bed length.
- `prior/transcripts.json` (`words`), `prior/beat_list.json` (a beat with `scene.type: "cta"` means
  the background already carries its call to action).
- `inputs/cta/` (`cta.json` or `cta.md`), `inputs/outro/` (one optional clip), `brief.json`.

## You must produce

- `saves/assembled_video.mp4`: 1080×1920, 30 fps, H.264 + AAC 48 kHz stereo: background, rounded
  ringed card, one end card, captions; as long as the bed plus the outro if any. No cover freeze yet.

## How

```bash
mkdir -p work saves
RECIPE_DIR=${RECIPE_DIR:?set RECIPE_DIR to the absolute path of this recipe folder}
case "$RECIPE_DIR" in /*) ;; *) echo "RECIPE_DIR must be an absolute path"; exit 1 ;; esac
BLOCKS_DIR="$(cd "$RECIPE_DIR/../../blocks" && pwd)" || exit 1
python3 "$RECIPE_DIR/scripts/options.py" || exit 1
opt () { python3 -c 'import json,sys; v=json.load(open("work/options.json")).get(sys.argv[1]); print("" if v is None else v)' "$1"; }
BED_DUR=$(ffprobe -v error -protocol_whitelist file -show_entries format=duration -of csv=p=0 prior/voice_track.mp4)
python3 -c "import json; json.dump(json.load(open('brief.json')).get('brand') or {}, open('work/brand.json','w'))"
ACCENT_HEX=$(python3 -c "import json;b=json.load(open('work/brand.json'));print((b.get('accent') or (b.get('palette') or {}).get('accent') or '#F97316').lstrip('#'))")
```

### 1. The card's mask and ring (standard-library Python)

Card 364×504, radius 40, 110 px above the bottom edge; the ring is the brand accent. `pip_card.py`
checks the colour, writes the rounded mask and the ring-and-shadow frame, and stops with one line
if it cannot (there is no square-card fallback). `pip_ring` `0` gives no ring and no frame.

```bash
RING=$(opt pip_ring); SHADOW=$(opt pip_shadow); FRAME_ARGS=()
python3 "$RECIPE_DIR/scripts/pip_card.py" --card 364x504 --radius 40 --ring "$RING" --shadow "$SHADOW" \
  --accent "$ACCENT_HEX" --mask work/pip-mask.png --frame work/pip-frame.png || exit 1
[ "$RING" -gt 0 ] && FRAME_ARGS=(--frame work/pip-frame.png)
```

### 2. The end card: one call to action, never invented

`cta_takeover.py` decides and says why (`reason`); say that line in your final message.

- `cta_card` is not `on`: no card.
- The background already has a `cta` beat: no card and no scrim.
- Copy: `inputs/cta/cta.json` `text`, then typed `inputs/cta/cta.md`, then `brand.cta`. No copy: no card.
  No handle: no handle line.
- Otherwise a translucent card covers the last `cta_duration` seconds. It is rendered with
  `--format mov` (ProRes with alpha) so the scrim stays translucent; an MP4 card is opaque.

```bash
mkdir -p work/cta
python3 "$RECIPE_DIR/scripts/cta_takeover.py" --brief brief.json --beats prior/beat_list.json \
  --cta inputs/cta/cta.json --cta-card "$(opt cta_card)" --decision work/cta-decision.json \
  --card-text work/cta/text.json || exit 1
TAKEOVER=$(python3 -c 'import json; print("on" if json.load(open("work/cta-decision.json"))["takeover"] else "off")')
CTA_DURATION=$(opt cta_duration); CTA_ARGS=(); CTA_START=""
if [ "$TAKEOVER" = on ]; then
  python3 "$RECIPE_DIR/scripts/fill_page.py" --card cta --out work/cta/index.html --duration "$CTA_DURATION" \
    --text-file work/cta/text.json --accent "$ACCENT_HEX" || exit 1
  cp vendor/gsap.min.js work/cta/gsap.min.js
  python3 "$BLOCKS_DIR/b-hyperframes/scripts/hf_render.py" --comp work/cta --out work/cta-card.mov --format mov --fps 30 --quality high --quiet < /dev/null || exit 1
  ffprobe -v error -protocol_whitelist file -select_streams v:0 -show_entries stream=pix_fmt -of csv=p=0 work/cta-card.mov | grep -Eq 'yuva|rgba|argb|bgra|abgr|gbrap' \
    || { echo "the end card has no alpha channel"; exit 1; }
  CTA_START=$(python3 -c "print(max(0.0, round(${BED_DUR} - ${CTA_DURATION}, 3)))")
  CTA_ARGS=(--cta-mov work/cta-card.mov --cta-start "$CTA_START" --cta-dur "$CTA_DURATION")
  python3 -c 'import json,sys; json.dump({"cta_start": float(sys.argv[1])}, open("work/cta-window.json","w"))' "$CTA_START"
else
  rm -f work/cta-window.json
fi
```

`vendor/gsap.min.js` comes from step 4's `fetch_gsap.py`; if this work folder is new, run
`hf_install.py` and `fetch_gsap.py --outdir vendor` from step 4 first. Everything in the shell
variables above is a number, a fixed word or a colour the scripts checked.

### 3. Composite: card, ring, end card, voice

`composite_pip.py` runs one ffmpeg command from an argument list. The card is filled (scale to
cover, then a top-biased crop), never fitted, so no bars show and the head is whole. The bed's audio
is copied, not re-encoded; the picture is held on its last frame if short, and the output is cut
at the bed length.

```bash
python3 "$RECIPE_DIR/scripts/composite_pip.py" --background prior/background.mp4 --voice prior/voice_track.mp4 \
  --mask work/pip-mask.png "${FRAME_ARGS[@]}" --pad $(( RING + SHADOW )) --card 364x504 --margin 110 \
  --bed-dur "$BED_DUR" "${CTA_ARGS[@]}" --out work/composed.mp4 || exit 1
python3 "$RECIPE_DIR/scripts/check_reel.py" duration --video work/composed.mp4 --expect "$BED_DUR"
```

### 4. Captions, grade and sound effects: `b-reel-premium`, once

Read `"$BLOCKS_DIR/b-reel-premium/README.md"` for the plan format. You write `work/premium/plan.json`
yourself from the words; no other model is asked.

```bash
mkdir -p work/premium
python3 "$RECIPE_DIR/scripts/clamp_captions.py" words prior/transcripts.json work/words.json || exit 1
```

`clamp_captions.py` drops words that start inside the end-card window (`work/cta-window.json`), so
no caption sits on the end card; with no end card it only copies the words. Now write the plan:

- `grade`: the `grade` option. `brand.accent` is the brand accent with `#`; `brand.fg` the
  foreground colour (six hex digits).
- `caption_groups`: 2 to 4 words each (up to 6 to keep a phrase whole), in time order, words as
  spoken, Latin script, at most one `em` word per group, `style` 0, 1, 2 cycling so neighbours
  differ. Times come from `work/words.json`; never change a word's time. None may start after the
  end-card window opens.
- `sfx`: 4 to 10 cues, none in the first second, names only from `whoosh-deep whoosh-air
  impact-sub impact-punch riser click pop swipe`, gain up to 0.6. `sfx` off: `"sfx": []`.

Keep phrases whole. A caption must not end on a preposition, article or auxiliary, and a one- or
two-word fragment from mid-clause joins its neighbour. A caption never spans a sentence end: the words
carry their punctuation, and a group with a word ending in `.`, `!`, `?` or an ellipsis before its last word is
split there by the repair and refused by `--check`. `caption_phrases.py` repairs a plan in place and checks it:

```bash
CAPTIONS=$(opt captions); SFX=$(opt sfx); CAP_TOP=980
python3 "$RECIPE_DIR/scripts/clamp_captions.py" plan work/premium/plan.json || exit 1
[ "$CAPTIONS" = off ] || python3 "$RECIPE_DIR/scripts/caption_phrases.py" work/premium/plan.json || exit 1
TOL=3; [ "$TAKEOVER" = on ] && TOL=$(python3 -c "print(${CTA_DURATION} + 3)")
python3 "$BLOCKS_DIR/b-reel-premium/scripts/check_plan.py" --plan work/premium/plan.json --reel work/composed.mp4 \
  --captions "$CAPTIONS" --sfx "$SFX" --cover-tolerance "$TOL" || exit 1
```

`CAP_TOP=980` puts the 260 px caption band at y 980 to 1240: above the card's ring (top at y≈1276)
and below the graphics (above y≈1040). It is the value `b-reel-premium`'s table gives for a card in the lower half (980 to 1020). Look at a frame and move it if a card's text meets it. The
caption band never enters the card's zone.

The renderer draws only the captions, as a transparent `.mov`; the footage is graded and mixed by
`mux.py` and never goes through the renderer. With captions off there is nothing to render.

```bash
GRADE=$(opt grade)
if [ "$CAPTIONS" = on ]; then
  python3 "$BLOCKS_DIR/b-reel-premium/scripts/build_comp.py" --plan work/premium/plan.json --reel work/composed.mp4 \
    --cap-top "$CAP_TOP" --outdir work/premium/comp --cover-tolerance "$TOL" || exit 1
  python3 "$BLOCKS_DIR/b-hyperframes/scripts/hf_render.py" --comp work/premium/comp --out work/premium/captions.mov \
    --format mov --fps 30 --quality high --quiet < /dev/null || exit 1
  CAPTION_ARGS=(--captions-mov work/premium/captions.mov)
else
  CAPTION_ARGS=(--no-captions)
fi
python3 "$BLOCKS_DIR/b-reel-premium/scripts/mux.py" --reel work/composed.mp4 "${CAPTION_ARGS[@]}" \
  --plan work/premium/plan.json --sfx "$SFX" --out work/polished.mp4 || exit 1
python3 "$BLOCKS_DIR/b-reel-premium/scripts/qa.py" --reel-in work/composed.mp4 --reel-out work/polished.mp4 \
  --frames-dir work/premium/qa --captions "$CAPTIONS" --sfx "$SFX" --grade "$GRADE" || exit 1
[ "$CAPTIONS" = off ] || python3 "$RECIPE_DIR/scripts/caption_phrases.py" --check work/premium/plan.json || exit 1
```

`CAPTION_ARGS`, `FRAME_ARGS` and `CTA_ARGS` are arrays (they work the same in bash and zsh): quote them as `"${NAME[@]}"`. `--cover-tolerance` must cover the end-card tail
(`TOL` above), for `check_plan.py` and `build_comp.py` both. `qa.py --grade` is the plan's grade; with
`off` it also checks that the colour did not shift.

Look at the four frames `qa.py` saved: captions readable and clear of the card, accent on the
emphasis words, grade subtle, no text on the end card. Never hand-burn captions with a drawing
filter, and never loudness-normalise here: the mix is `amix` with `normalize=0`.

### 5. Optional outro (the only thing ever appended), then save

The outro is a portrait clip of the person's own. It is scaled to cover, given the bed's audio
format, and joined after the polished reel, so the captions, grade and effects do not touch it. That is
intended, not a gap.

```bash
OUTRO=$(find inputs/outro -maxdepth 1 -type f ! -name '.*' 2>/dev/null | sort | head -1)
if [ -n "$OUTRO" ]; then
  ffmpeg -v error -y -protocol_whitelist file -i "$OUTRO" -vf "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30,format=yuv420p" \
    -af "aresample=48000" -c:v libx264 -preset medium -crf 19 -c:a aac -b:a 192k -ar 48000 -ac 2 work/outro-norm.mp4
  printf "file 'polished.mp4'\nfile 'outro-norm.mp4'\n" > work/outro_concat.txt
  ffmpeg -v error -y -protocol_whitelist file -f concat -safe 1 -i work/outro_concat.txt -c:v libx264 -pix_fmt yuv420p -crf 19 -c:a aac -b:a 192k -ar 48000 -ac 2 -movflags +faststart saves/assembled_video.mp4
  EXPECT=$(python3 -c "import subprocess,sys; d=lambda f: float(subprocess.run(['ffprobe','-v','error','-protocol_whitelist','file','-show_entries','format=duration','-of','csv=p=0',f],capture_output=True,text=True).stdout); print(d('work/polished.mp4')+d('work/outro-norm.mp4'))")
else
  cp work/polished.mp4 saves/assembled_video.mp4; EXPECT="$BED_DUR"
fi
python3 "$RECIPE_DIR/scripts/check_reel.py" duration --video saves/assembled_video.mp4 --expect "$EXPECT"
python3 "$RECIPE_DIR/scripts/check_reel.py" voice --video saves/assembled_video.mp4 --beats prior/beat_list.json
```

## If you cannot proceed

No `canAsk`; never write `needs_input.json`. A card that cannot be built, a failed end-card render,
an end card with no alpha, or a premium pass that did not run is a failure: exit non-zero with one
plain line.

## Checks (declared in `manifest.json`)

- `vo_continuous_bed`: `check_reel.py voice` passes and the length equals the bed (plus the outro).
- `pip_zone_clear`: in sampled frames the ringed card sits bottom-centre, the face is whole, and no
  caption text is below y≈1240.
