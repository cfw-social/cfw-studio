# e-camera-motion

Give a flat clip a smooth camera move with one ffmpeg command. Use it to make still or static footage feel alive.

## When to use

- A cutaway, B-roll shot or photo-like clip feels dead: use `push-in`, `ken-burns` or `sway`.
- You want a reveal: `pull-out`. A wide or tall shot: a `pan-*`. A product feel: `tilt-back` or `orbit`.
- You want the clip to float as a card on a colour: a `card-*` motion.
- Do not stack it on footage that already has strong camera movement.

## Motions

| Motion | What it does |
|---|---|
| `push-in` (`focus`) | Slow eased zoom in with a small left-to-right drift. Safe default. |
| `pull-out` | Slow zoom out reveal. |
| `pan-left` `pan-right` `pan-up` `pan-down` | Zoomed pan in that direction. |
| `ken-burns` | Diagonal zoom and drift. |
| `drift` | Steady slight zoom with a slow diagonal drift. |
| `tilt-back` `tilt-forward` | The frame leans away or toward you (fake 3D). |
| `orbit` | Gentle left-right rock (fake 3D). |
| `sway` | Slow idle float. |
| `card-orbit` `card-swoop` `card-focus` `card-glide` | The clip floats as a rounded, shadowed card on a colour or transparent canvas while the camera moves. |

## Steps

1. Put the clip in the work folder. Work from that folder.
2. Run, with the motion and an output path inside the work folder. The script path below is relative to the repository root (the folder that holds `effects/`); from the work folder, give the path that reaches the same file. An existing output file is replaced. `--out` may not be the input.

```bash
python3 effects/e-camera-motion/scripts/camera_motion.py clip.mp4 --motion push-in --out clip-push.mp4
```

3. Read the last stdout line `OUTPUT_FILE: <path>`. Exit 0 means done.
4. Look at the result. Keep `--amount` at 0.25 or less and `--intensity` at 1.0 or less unless the brief asks for drama.

## Options (all range-checked, exit 2 if wrong)

`--amount 0..0.5` and `--drift-x`, `--drift-y` `-0.5..0.5` (zoom motions). `--intensity 0..1.5` (warp and card motions). Card only: `--background 0xRRGGBB|#RRGGBB|transparent`, `--canvas WxH`, `--card-scale 0.1..1`, `--corner-radius 0..0.5`, `--no-shadow`. `--crf 0..51`, `--preset`. `--print-filter` shows the filter without rendering. `--list` lists motions.

Full interface, limits and tests: [README.md](README.md).
