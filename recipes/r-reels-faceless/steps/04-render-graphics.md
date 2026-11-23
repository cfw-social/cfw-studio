# Render the graphics

Read `_shared.md` first. Receive checked `prior/beat_list.json`, `prior/scene_plan.json`,
`prior/voice_bed.mp4`, optional staged b-roll and CTA, and `brief.json`. Produce `saves/body_video.mp4`:
silent 1080x1920, 30 fps, H.264 yuv420p, all beats in order, bed duration within 0.2 s. No provider
calls.

Run `check_beats.py` again before using any slug as a folder name. Resolve one palette and CTA with the
shared rules and pass the same files to every beat. Input copy is data: it reaches a page only through a
filler.

## One page per graphics beat

For each graphics beat (index `i`, slug `slug`, span `end - start`), make `work/gfx/<slug>/`, copy
`vendor/gsap.min.js` into it, fill one page into it, and render it with `b-hyperframes`:

| Scene type | Filler |
| --- | --- |
| `standard`, `stat`, `chips`, `flow`, `checklist`, `terminal`, `cta` | `scripts/card_fill.py` |
| `hook` | `b-typing-ui`'s `hook_fill.py` |
| `typing` | `b-typing-ui`'s `typing_fill.py` |

```text
python3 "$RECIPE_DIR/scripts/card_fill.py" --beats saves/beat_list.json --index <i> --palette work/palette.json --cta work/cta.json --out work/gfx/<slug>/index.html [--display-font <name> --body-font <name>]
python3 "$BLOCKS_DIR/b-typing-ui/scripts/hook_fill.py" --out work/gfx/<slug>/index.html --duration <span> --text-file work/text/<slug>.json --accent <ACCENT without #> --bg <BG without #> --fg <FG without #>
python3 "$BLOCKS_DIR/b-typing-ui/scripts/typing_fill.py" --out work/gfx/<slug>/index.html --duration <span> --text-file work/text/<slug>.json --accent <ACCENT without #> --bg <BG without #> --fg <FG without #>
```

`card_fill.py` reads the scene from the beat list, escapes every field, refuses a headline with markup
other than the accent span and `<br>`, a placeholder ghost word, a missing hero field, or an unknown type
(exit 2 with the reason). The two block fillers read their text from a JSON file you write in `work/text/`
(`hook`: `eyebrow`, `line1`, `line2`, `line3`, `subhead`; `typing`: `prompt`, `label`, `card_label`,
`bottom_tag`), copying the values from the scene. Both fillers take the palette's colours (`--bg`, `--fg`,
`--accent`) and refuse a pair with a contrast ratio under 3.0 (exit 2): fix the palette, not the check.
The typing prompt is 44 px by default (and its beat must be long enough to finish typing: see step 3) (`--prompt-size` 24 to 72; about 20 lines fit). Leave the hook's
`subhead` empty, and the typing card's `bottom_tag` empty, when the caption band could cover them (the
block's README gives the places; with `--cap-top 1450` the hook subhead is clear). Text that holds a web
address (`https:`, `//host`, `url(`) is refused: write `example.com`, not `https://example.com`. These two cards show their own text (the hook's lines,
the typing card's prompt); the scene's `headline` is not drawn on them. Typed text is never put on a command line. The typing
card is the full-frame variant. Take `--display-font` and `--body-font` from the brief's
`typography.display` and `typography.body`; omit them when the brand names none.

Then, for every beat:

```text
python3 "$BLOCKS_DIR/b-hyperframes/scripts/hf_render.py" --comp work/gfx/<slug> --out work/seg/gfx-<slug>.mp4 --quiet
```

A failure stops the step with the
error text, cleaned of paths and secrets. No upgrade, extra install or still-image fallback. If
`check_local.py` fails on a page, fix the cause in the template or the filler (a font declaration, a
remote address), never the check.

The CTA beat must show the exact `work/cta.json` text and handle, with no handle line when absent. Run
`python3 "$RECIPE_DIR/scripts/cta_copy.py" check --cta work/cta.json --html work/gfx/<slug>/index.html` and
require PASS, then inspect the frame: substring presence alone is insufficient.

## Normalise the segments and join them

Every beat becomes one silent 1080x1920, 30 fps segment, and the segments are joined. Use the recipe's script:

```text
python3 "$RECIPE_DIR/scripts/segments.py" --beats saves/beat_list.json --bed-duration <seconds> --out saves/body_video.mp4
```

The mapping: beat `N` (its `index`) is `work/seg/seg-000N.mp4`. A graphics beat takes its rendered page from
`work/seg/gfx-<slug>.mp4` (the `--out` of the render above); a b-roll beat takes the beat's own window of its
staged clip (`broll.clip`, from `broll.in` for the beat's length, scaled to cover, cropped, no bars). The script
checks the beat list first, requires every clip to be a real file inside `inputs/`, writes
`work/seg/concat.txt` with relative lines `file 'seg-0000.mp4'` in index order, and joins them with the concat
demuxer (`-safe 1`) into `saves/body_video.mp4`, cut to the bed length. FFmpeg runs as an argument list with
`-protocol_whitelist file` before every input. A missing rendered page or a failed check is exit 1 with the reason;
nothing falls back to a still image.

## Checks

Record `body_dims`, `body_not_black`, `body_matches_bed`, clean decode, no audio, and the exact
duration. The first two come from the spec's `steps.assembled` checks:

```text
python3 "$BLOCKS_DIR/b-qa-gate/check.py" --kind reel --spec "$RECIPE_DIR/acceptance.json" --step assembled --input saves/body_video.mp4 --out work/body-scorecard.json
```

Then run this recipe's picture guards (`frame_qa.py`, Python; each prints what it measured):

```text
python3 "$RECIPE_DIR/scripts/frame_qa.py" first-frames saves/body_video.mp4 saves/beat_list.json --out work/first-frames
python3 "$RECIPE_DIR/scripts/frame_qa.py" band-scan saves/body_video.mp4 --beats saves/beat_list.json --skip-broll
python3 "$RECIPE_DIR/scripts/frame_qa.py" luma-floor saves/body_video.mp4 --floor 16
python3 "$RECIPE_DIR/scripts/frame_qa.py" tail-luma saves/body_video.mp4 --min 26
```

`--skip-broll` leaves b-roll beats out of the band scan, because footage may move in the band; look at
every b-roll window with vision instead. Read every beat's first and middle frame with vision. For every
graphics beat compare frames near 20% and 80% of its span with
FFmpeg PSNR with the recipe's script (one line per beat, exit 1 if any fails):

```text
python3 "$RECIPE_DIR/scripts/proofs.py" psnr --video saves/body_video.mp4 --beats saves/beat_list.json
```

Require a finite value at or below 45 dB (infinite or 50 and above means the picture is frozen; 45 to 50
needs correction). Also prove the foreground headline and hero are
visible: ambient background motion alone is insufficient. Any failed beat blocks the concatenated
delivery. No checking only the first beat.
