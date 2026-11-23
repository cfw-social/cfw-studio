# e-camera-motion

Adds a camera move to a video clip with one ffmpeg command: push in, pull out, pans, slow drift, ken-burns, tilt, orbit, sway, or a clip floating as a card. Pure ffmpeg. No browser, no GPU, no models, no account, no network.

This is an effect **template**. It teaches. A brand's bot reads it, adapts it, and runs it in its own recipe. It does not run for a brand from here. The CFW Social side that saves a brand's recipes is planned, not built. MIT licence, like the rest of this repository.

It is a standalone effect: it does not use the shared `fx` package.

## What you need

| Tool | Version | Notes |
|---|---|---|
| Python | 3.10 or newer (run with 3.15.2) | standard library only |
| ffmpeg and ffprobe | 6 or newer (run with 8.1) | needs the `libx264` encoder and the `perspective`, `geq`, `gblur` filters. A transparent card also needs `prores_ks` (.mov) or `libvpx-vp9` (.webm). |

## Interface

Run from the work folder. The input and the output must both resolve inside it. The script path below is relative to the repository root (the folder that holds `effects/`); from the work folder, give the path that reaches the same file. An existing output file is replaced; `--out` may not be the input file.

```text
python3 effects/e-camera-motion/scripts/camera_motion.py INPUT --motion NAME --out OUTPUT [options]
```

| Argument | Applies to | Default | Check |
|---|---|---|---|
| `INPUT` | all | required | a video file inside the work folder |
| `--out FILE` | all | required (not with `--print-filter`) | inside the work folder; not the input; `.mp4`, `.mov` or `.mkv`; a transparent card needs `.mov` or `.webm` |
| `--motion`, `-m` | all | `push-in` | one of the names in `--list` |
| `--amount` | zoom motions | per motion, about 0.10 to 0.20 | 0 to 0.5 |
| `--drift-x`, `--drift-y` | zoom motions without a pan | per motion | -0.5 to 0.5 |
| `--intensity` | warp and card motions | 1.0 | 0 to 1.5 |
| `--background`, `--bg` | card motions | `0x101018` | `0xRRGGBB`, `#RRGGBB` or `transparent` only |
| `--canvas` | card motions | `1920x1080` | `WxH`, each 16 to 4096 |
| `--card-scale` | card motions | 0.76 | 0.1 to 1 |
| `--corner-radius` | card motions | 0.05 | 0 to 0.5 |
| `--shadow` / `--no-shadow` | card motions | shadow on | flag |
| `--crf` | all | 18 | 0 to 51 |
| `--preset` | all | `medium` | an x264 preset name |
| `--print-filter` | all | off | prints the ffmpeg filter, renders nothing |
| `--list` | none | off | lists the motions |

An option that does not apply to the chosen motion is an error, not ignored.

| Item | Value |
|---|---|
| Input | one video, any aspect ratio. Each side 2 to 16384 pixels, duration over 0 and under 10 hours; otherwise exit 1. A frame rate outside 1 to 240 is treated as 30. |
| Output | one video at `--out`: H.264 yuv420p with the audio copied unchanged. Zoom and warp motions keep the input size. Card motions use the canvas size. A transparent `.mov` is ProRes 4444 with audio copied. A transparent `.webm` is VP9 and has no audio. |
| stdout | the last line is `OUTPUT_FILE: <path>` |
| Exit 0 | done |
| Exit 1 | the clip could not be read, or ffmpeg failed (a partial output is removed) |
| Exit 2 | bad arguments, an option outside its range, or a path outside the work folder; nothing was written |
| Exit 3 | ffmpeg or ffprobe is not installed |

## Motions

| Kind | Motions |
|---|---|
| Zoom (scale and crop) | `push-in` (alias `focus`), `pull-out`, `pan-left`, `pan-right`, `pan-up`, `pan-down`, `ken-burns`, `drift` |
| Warp (fake 3D lean, gap-free) | `tilt-back`, `tilt-forward`, `orbit`, `sway` |
| Card (clip floats on a canvas) | `card-orbit`, `card-swoop`, `card-focus`, `card-glide` |

## How it stays safe

- ffmpeg and ffprobe run with argument lists, never a shell string.
- Every number, colour and name is checked against a fixed range or pattern before it is written into a filter. A colour is rewritten as `0xRRGGBB`, so it cannot carry filter text.
- Input and output must resolve inside the current folder, including through symlinks. Nothing is written beside the input unless you name it. ffmpeg may read only local files (`-protocol_whitelist file`).

## Network use

None, at setup or at run time. Nothing is downloaded.

## Proof

A short summary of the limits below. Where this README does not say, it reads "not recorded".

| What | Status | Detail |
|---|---|---|
| Automated tests | 60 tests, as of 2026-11-22 | From `effects/`: `uvx --quiet --with-requirements requirements.txt --with pyyaml pytest tests/test_camera_motion.py -q`. They render every motion on a tiny clip. The whole effects suite (all effects) is 96 tests. |
| Run on which operating systems | macOS (Apple silicon) only; Linux and Windows not run | ffmpeg 8.1 on one Apple-silicon Mac. |
| Run with a real provider account | no provider | No network, no account. |
| Used in a real start-to-finish recipe run | not yet used by a recipe template | One sample is included (`../examples/samples/camera_motion.mp4`). |

## Tests

They make a tiny clip with ffmpeg and render every motion. They need no account and no private file. From `effects/`:

```bash
uvx --quiet --with-requirements requirements.txt --with pyyaml pytest tests/test_camera_motion.py tests/test_catalog.py -q
```

(`tests/test_camera_motion.py` alone needs only `pytest` and ffmpeg. The catalog test imports the shared `fx` package, which is why the requirements are installed.)

## Limits and known gaps

- The warp and card motions are 2D perspective approximations. They read well on flat footage. They are not a true 3D orbit with depth, parallax, lighting and reflections.
- Not stacked on footage that already moves a lot; over-doing `--amount` softens the image and over-doing `--intensity` looks rubbery.
- Re-encodes the video, so the output is a new generation of the file. Audio is copied, not re-encoded.
- Run on macOS with ffmpeg 8.1 only. Not run on Windows or Linux, and not run with an ffmpeg build lacking `libx264`.
- One sample is included (`../examples/samples/camera_motion.mp4`, see `PREVIEW.md`). The other motions are exercised by the tests, not shown as video here.
