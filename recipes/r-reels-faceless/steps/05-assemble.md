# Assemble

Read `_shared.md` first. Receive checked `prior/body_video.mp4`, `prior/voice_bed.mp4`,
`prior/transcripts.json`, `prior/beat_list.json`, optional `inputs/outro/`, the CTA and `brief.json`.
Produce `saves/assembled_video.mp4`: 1080x1920, 30 fps, H.264 yuv420p and AAC 48 kHz stereo, body plus
outro in length, mastered to -14 LUFS (1.5 tolerance). No generated shell script and no nested agent.

```text
body + voice -> + outro -> pad to a tenth of a second -> b-reel-premium (captions, grade, sound effects)
                                                              -> loudness master -> saves/assembled_video.mp4
```

## Preserve the voice and append the lit outro

Mux the body video and the sealed voice bed, mapping only `0:v` and `1:a`:

```python
args = ['-y', '-protocol_whitelist', 'file', '-i', 'prior/body_video.mp4', '-protocol_whitelist', 'file', '-i', 'prior/voice_bed.mp4', '-map', '0:v', '-map', '1:a',
        '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2', '-shortest', 'work/body.mp4']
```

Never cut, retime or renormalise the voice. Check the A/V duration after the mux.

Supplied outro: require one portrait clip of 1 to 8 seconds that decodes. Normalise it to 1080x1920,
30 fps, H.264 and AAC 48 kHz stereo with the command below. Its own audio (if any) plays only after the
narration. A bad supplied clip fails, never silently replaced.

```python
# outro_in = the supplied clip (inputs/outro/<file>) or work/outro.mp4 (the rendered card); span = its length in seconds
args = ['-y', '-protocol_whitelist', 'file', '-i', outro_in, '-protocol_whitelist', 'file', '-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo',
        '-vf', 'scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30,format=yuv420p',
        '-map', '0:v', '-map', '0:a?', '-map', '1:a', '-t', str(span), '-c:v', 'libx264', '-preset', 'medium', '-crf', '18',
        '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2', 'work/outro-n.mp4']
```

(For a supplied clip that has its own audio, drop `'-map', '1:a'` and the lavfi input so its sound is kept; for a
clip with none, and always for the rendered card, whose sound is silence, use the command as written: the silent
track is the only audio.)

Otherwise make a 2.5 second closing card with the same tools as step 4. Write `work/outro-beat.json` (the brand
name is the headline, the exact CTA text is `sub`, the ghost is a thematic character; the handle comes from
`work/cta.json`, and only if supplied):

```text
{"bed_duration": 2.5, "beats": [{"index": 0, "kind": "graphics", "slug": "outro", "start": 0, "end": 2.5,
  "scene": {"type": "cta", "title_html": "<brand name>", "sub": "<exact CTA text>", "ghost": "1"}}]}
```

Then fill it, copy the library beside it and render it:

```text
python3 "$RECIPE_DIR/scripts/card_fill.py" --beats work/outro-beat.json --index 0 --palette work/palette.json --cta work/cta.json --out work/outro/index.html
python3 "$BLOCKS_DIR/b-hyperframes/scripts/hf_render.py" --comp work/outro --out work/outro.mp4 --quiet
```

(copy `vendor/gsap.min.js` to `work/outro/gsap.min.js` first). Whole and lit from frame 1, never fade to black.
Normalise `work/outro.mp4` to `work/outro-n.mp4` with the command above (the rendered card has no sound, so its
sound is the silent track).

Copy the checked body and the outro to fixed `work/join/part-0000.mp4` and `part-0001.mp4`; write a relative
concat list `work/join/concat.txt` as in step 4, `-safe 1`. Re-encode, do not stream-copy incompatible
tracks. Keep the result as `work/assembled-raw.mp4`. Its duration plus the 0.4 s cover must fit 30 to 90 s.

```python
args = ['-y', '-f', 'concat', '-safe', '1', '-protocol_whitelist', 'file', '-i', 'work/join/concat.txt', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
        '-preset', 'medium', '-crf', '18', '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2',
        'work/assembled-raw.mp4']
```

Get the frame-aligned end time `T` (a multiple of 0.1 s) and pad both streams to it, so the caption pass
cannot outlast the picture:

```text
python3 "$RECIPE_DIR/scripts/frame_qa.py" av-target work/assembled-raw.mp4
```

```python
# T and A = T - 0.03 are validated finite numbers
fc = ('[0:v]tpad=stop_mode=clone:stop_duration=5,trim=duration=%g,setpts=PTS-STARTPTS[v];'
      '[0:a]apad,atrim=duration=%g,asetpts=PTS-STARTPTS[a]' % (T, A))
args = ['-y', '-protocol_whitelist', 'file', '-i', 'work/assembled-raw.mp4', '-filter_complex', fc, '-map', '[v]', '-map', '[a]',
        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2',
        'work/assembled-av.mp4']
```

The sound is cut to end 0.03 s before the picture (`A = T - 0.03` above), so no sound overhangs when the frame count is taken. This removes at most 30 ms from the end of the sound.
Then require `python3 "$RECIPE_DIR/scripts/frame_qa.py" av-span work/assembled-av.mp4` to pass. This is the check
that protects the caption pass from a black tail: it counts the frames the caption pass will render from the real file
length, with no allowance. It fails if the audio ends more than one AAC frame (21.3 ms) after
the picture: an AAC stream is built from whole 1024-sample frames, so an exact cut still ends up to one frame later,
but any longer overhang is real sound past the picture. If it fails, pad the picture or cut the sound again with the
command above; do not loosen the check.

## Captions, grade and sound effects with b-reel-premium

All paths stay inside the run folder. Write `work/premium/plan.json` yourself from the transcript words (no
other model, no nested agent). Read `"$BLOCKS_DIR/b-reel-premium/README.md"` for the plan format:

- `grade`: `clean-bright` (the default), `warm-amber` only when the person asks, or `off`. There is no
  other default.
- `brand`: `accent` and `fg` as six hex digits (the palette's `ACCENT` and `CAP_FG`). A brand font file
  goes in as `brand.font_file` (inside `inputs/`); with none, captions use the generic sans-serif.
- `caption_groups`: every group holds 2 to 4 words. The only exception is the last group, which may hold one
  word, and only when it cannot join the group before it: that is, only after a group of 4 words. Break a group at a sentence end or a pause of 150 ms or more only
  when both sides keep at least 2 words; never leave a word alone, let it join the neighbour. (The plan checker
  in the block accepts 1 to 8 words, so run `check_captions.py` below as well.) In time order, not
  overlapping, each word with its exact transcript
  time (`s`, `e`), at most one `em` word per group, `style` cycling 0, 1, 2 so neighbours differ, Latin
  script only, the words as spoken. Cover all the narration; no captions over the silent outro. The last
  group ends within the cover tolerance (4 s) of the end of the reel.
- `sfx`: 4 to 10 cues, none in the first second, names only from `whoosh-deep whoosh-air impact-sub
  impact-punch riser click pop swipe`, `gain` 0 to 0.6, in time order. The sounds live in the block; never
  download a replacement.
- `captions=off` and `sfx=off` are allowed only when the person set them: use `"sfx": []`, run
  `check_plan.py` with `--captions off`, skip the build and render, and pass `--no-captions` to `mux.py` instead of `--captions-mov`.
  Never turn captions off because a render failed.

```text
python3 "$RECIPE_DIR/scripts/check_captions.py" --plan work/premium/plan.json
python3 "$BLOCKS_DIR/b-reel-premium/scripts/check_plan.py" --plan work/premium/plan.json --reel work/assembled-av.mp4 --cover-tolerance 4
python3 "$BLOCKS_DIR/b-reel-premium/scripts/build_comp.py" --plan work/premium/plan.json --reel work/assembled-av.mp4 --cap-top 1450 --cover-tolerance 4 --outdir work/premium/comp
python3 "$BLOCKS_DIR/b-hyperframes/scripts/hf_render.py" --comp work/premium/comp --out work/premium/captions.mov --format mov --quiet
python3 "$BLOCKS_DIR/b-reel-premium/scripts/mux.py" --reel work/assembled-av.mp4 --captions-mov work/premium/captions.mov --plan work/premium/plan.json --out work/premium/polished.mp4
python3 "$BLOCKS_DIR/b-reel-premium/scripts/qa.py" --reel-in work/assembled-av.mp4 --reel-out work/premium/polished.mp4 --frames-dir work/premium/qa --grade <the plan's grade>
```

`check_plan.py` must exit 0 before you go on: fix every listed problem. The closing card is a silent tail
with no speech, so `--cover-tolerance` (the most seconds the last caption may end before the end of the
reel) must be at least as long as that tail plus any pause after the last word: 4 covers the 2.5 s card.
Pass it to both `check_plan.py` and `build_comp.py`. `--cap-top 1450` keeps the caption band below the
card content (which ends near y=1330). The renderer draws only the captions, as a transparent `mov`;
the footage never goes through it. `mux.py` grades the footage with ffmpeg, lays the captions over it
and mixes the effects under the reel's own sound without changing its level, so the caption colours stay
exact and the footage colour does not drift. `qa.py` confirms the output decodes, keeps the reel's length
and has video and audio, saves four frames and (with `--grade off`) runs its own colour guard: look at
the frames (captions legible and clear of cards, accent on emphasis words, grade subtle, effects under
the voice).

## Master the loudness once

The effects slightly change the mix, so master the polished reel once, two passes, no one-pass fallback:

```text
python3 "$RECIPE_DIR/scripts/master_loudness.py" --in work/premium/polished.mp4 --out saves/assembled_video.mp4
```

## Continuity proof

Clean-decode and probe the exact streams and duration of `saves/assembled_video.mp4`, and measure its
loudness. For every beat window require a finite mean volume above -40 dB with the recipe's script (offset 0 here, because
the 0.4 s cover is not in front yet); spot-listen to prove the narration stays intelligible under the effects
(effects alone are not voice proof). Then:

```text
python3 "$RECIPE_DIR/scripts/proofs.py" volume --video saves/assembled_video.mp4 --beats saves/beat_list.json
python3 "$RECIPE_DIR/scripts/frame_qa.py" band-scan saves/assembled_video.mp4 --beats saves/beat_list.json --skip-broll
python3 "$RECIPE_DIR/scripts/frame_qa.py" first-frames saves/assembled_video.mp4 saves/beat_list.json --outro <bed duration> --out work/first-frames-assembled
python3 "$RECIPE_DIR/scripts/frame_qa.py" av-span saves/assembled_video.mp4 --after-captions
python3 "$RECIPE_DIR/scripts/frame_qa.py" tail-luma saves/assembled_video.mp4 --min 26
```

Notes on those guards. `--after-captions` is used only here and in step 6, once the captions are rendered: it skips the
black-tail frame count (no caption pass follows, so a file a few milliseconds past a whole number of frames would be
flagged for a frame that is never rendered). It does not relax the sound check: a real overhang still fails. The loudness master cuts the sound to the picture and re-encodes it as AAC, which ends up to one AAC frame (21.3 ms)
after the picture; the sound check allows that and nothing more. The master itself fails (exit 1) if the sound is more
than 0.1 s longer than the picture, so real sound is never cut silently. `tail-luma --min 26`: a dark brand canvas is lifted only
to luma 24, so a lit closing card measures in the high 20s to 30s; 26 still catches a black or faded end (the
gate's own not-black floor is 16).


Read the first, middle and outro frames; confirm the
actual captions, CTA, fonts and effects. A stamp alone proves nothing. Record `vo_continuous_bed`,
`brand_outro_at_end` and every other actual measurement. No `canAsk` and no silent premium-off fallback.
