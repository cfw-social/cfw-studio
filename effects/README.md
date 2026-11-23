# Effects

Visual treatments an agent can snap into a recipe. An **effect is a block of `kind: effect`**. It has the same shape as any other building block — declared inputs and outputs, instructions, and supporting scripts — and a recipe references it by id and variation.

This folder is both the catalog and the engine:

- Each `e-*` directory is one catalog entry (`effect.yaml`, `SKILL.md`, `PREVIEW.md`) an agent can open on its own.
- The shared Python package `fx` implements all of them. `python -m fx` and `pytest` run from this directory.

An effect here is a **template**: it teaches. It does not run for a brand by itself. A brand's own bot reads an effect, builds it into that brand's own recipe, and tries it. See [the design](../docs/DESIGN.md). The CFW-side tools that save those recipes are live, for a key made with the "Save its own recipes" permission. A folder here is checked-in source an agent can run locally.

Start a brand-new effect that is not part of `fx` from [`_template/`](_template/). To add a look to this engine, register it in `fx/effects/`, export it from `fx/effects/__init__.py`, add an `e-*` folder, and add a row to the table below.

## License

Everything in this repository, including this `effects/` library, is under the MIT License. [`LICENSE`](LICENSE) here is the same text as the root [`LICENSE`](../LICENSE). Copyright (c) 2026 CFW Social. `pyproject.toml` records it as `license = "MIT"`.

Dependencies below are installed from PyPI or downloaded separately. They keep their own licenses.

## Checked-in effects

Twenty-four subject-aware effects, plus `grid_collage` and the utilities `label`, `redact`, and `grade`. `fx_name` in `effect.yaml` is the name `python -m fx apply --effect` expects. Samples are 360×640 renders of the procedural mannequin. That makes 28 `fx` effects, plus one standalone effect below: 29 `e-*` folders.

| Effect | `fx` name | Layer | What it does | Sample |
| --- | --- | --- | --- | --- |
| [e-vertigo](e-vertigo/) | `vertigo` | background | Dolly-zoom: the background zooms around a locked subject, with a radial streak and a vignette. | [vertigo.mp4](examples/samples/vertigo.mp4) |
| [e-paper-cut](e-paper-cut/) | `paper_cut` | background + cutout | Torn-edge paper sticker, drop shadow, procedural paper background. | [paper_cut.mp4](examples/samples/paper_cut.mp4) |
| [e-spotlight](e-spotlight/) | `spotlight` | background + foreground | Dimmed background, light pool, rim glow, beam, and sparkles. | [spotlight.mp4](examples/samples/spotlight.mp4) |
| [e-backdrop-words](e-backdrop-words/) | `backdrop_words` | behind subject | Giant timed words behind the subject, with a punch-in. | [backdrop_words.mp4](examples/samples/backdrop_words.mp4) |
| [e-scribble-outline](e-scribble-outline/) | `scribble_outline` | foreground | Boiling hand-drawn contour around the subject. | [scribble_outline.mp4](examples/samples/scribble_outline.mp4) |
| [e-countdown-behind](e-countdown-behind/) | `countdown_behind` | behind subject | Flip-clock or plain digits counting behind the subject. | [countdown_behind.mp4](examples/samples/countdown_behind.mp4) |
| [e-glass-card](e-glass-card/) | `glass_card` | foreground or behind | Frosted note card that slides in and out. | [glass_card.mp4](examples/samples/glass_card.mp4) |
| [e-orbit](e-orbit/) | `orbit` | behind + foreground | Clip cards on a tilted orbit, behind and in front of the subject. | [orbit.mp4](examples/samples/orbit.mp4) |
| [e-locked-on](e-locked-on/) | `locked_on` | foreground | Track, recentre, zoom, brackets, and a reticle. | [locked_on.mp4](examples/samples/locked_on.mp4) |
| [e-digital-zoom](e-digital-zoom/) | `digital_zoom` | full frame | Stepped camcorder zoom, pixelation, scanlines, generic REC UI. | [digital_zoom.mp4](examples/samples/digital_zoom.mp4) |
| [e-rabbit-hole](e-rabbit-hole/) | `rabbit_hole` | background | Recursive rotating frame tunnel; subject stays in front. | [rabbit_hole.mp4](examples/samples/rabbit_hole.mp4) |
| [e-chat-window](e-chat-window/) | `chat_window` | full frame | Clip inside a generic chat window with timed bubbles. | [chat_window.mp4](examples/samples/chat_window.mp4) |
| [e-shadow-puppet](e-shadow-puppet/) | `shadow_puppet` | full frame | Flat silhouette, rim light, and cast shadow. | [shadow_puppet.mp4](examples/samples/shadow_puppet.mp4) |
| [e-key-rain](e-key-rain/) | `key_rain` | behind + foreground | Falling keycaps, half behind the subject and half in front. | [key_rain.mp4](examples/samples/key_rain.mp4) |
| [e-receipt-scroll](e-receipt-scroll/) | `receipt_scroll` | behind or foreground | Procedural paper receipt scrolling through the frame. | [receipt_scroll.mp4](examples/samples/receipt_scroll.mp4) |
| [e-stamp](e-stamp/) | `stamp` | foreground | Rubber-stamp slam with grunge ink and impact shake. | [stamp.mp4](examples/samples/stamp.mp4) |
| [e-giant-captions](e-giant-captions/) | `giant_captions` | behind or foreground | Screen-filling stacked words, one per line. | [giant_captions.mp4](examples/samples/giant_captions.mp4) |
| [e-dot-mosaic](e-dot-mosaic/) | `dot_mosaic` | background | Halftone dots on the background or the whole frame. | [dot_mosaic.mp4](examples/samples/dot_mosaic.mp4) |
| [e-tier-list](e-tier-list/) | `tier_list` | full frame | Generic tier board; a snapshot card flies into a row. | [tier_list.mp4](examples/samples/tier_list.mp4) |
| [e-profile-wall](e-profile-wall/) | `profile_wall` | full frame | Grid of playing tiles plus a count-up number. | [profile_wall.mp4](examples/samples/profile_wall.mp4) |
| [e-colour-collage](e-colour-collage/) | `colour_collage` | background + behind | Solid poster; rotated word blocks slide in behind the cutout. | [colour_collage.mp4](examples/samples/colour_collage.mp4) |
| [e-phone-fan](e-phone-fan/) | `phone_fan` | behind subject | Generic phones fan out behind the subject. | [phone_fan.mp4](examples/samples/phone_fan.mp4) |
| [e-moody-grade](e-moody-grade/) | `moody_grade` | full frame | Desaturate, crush, shadow tint, oval vignette, and grain. | [moody_grade.mp4](examples/samples/moody_grade.mp4) |
| [e-pullback](e-pullback/) | `pullback` | full frame | Full frame shrinks into a generic phone feed. | [pullback.mp4](examples/samples/pullback.mp4) |
| [e-grid-collage](e-grid-collage/) | `grid_collage` | full frame | Every clip in a labelled grid. | [_grid.mp4](examples/samples/_grid.mp4) |
| [e-label](e-label/) | `label` | foreground | Pill chip that names the shot. | [label.mp4](examples/samples/label.mp4) |
| [e-redact](e-redact/) | `redact` | full frame | Blur, pixelate, or fill rectangular regions. | [redact.mp4](examples/samples/redact.mp4) |
| [e-grade](e-grade/) | `grade` | full frame | Light global contrast, saturation, warmth, and lift. | [grade.mp4](examples/samples/grade.mp4) |

`orbit`, `phone_fan`, `profile_wall`, and `grid_collage` take `clips` (paths or `{"src", "in", "dur"}`). With no clips they use delayed copies of the current clip. Chat, phone, feed, camera, and tier-board chrome are generic drawings.

### Standalone effects

These do not use the `fx` package. Each has its own script, declared in its `effect.yaml` with `engine: standalone`, and its own sample.

| Effect | Layer | What it does | Sample |
| --- | --- | --- | --- |
| [e-camera-motion](e-camera-motion/) | full frame | One-command camera moves with ffmpeg: push in, pull out, pans, slow drift, tilt, orbit, sway, or a floating card. | [camera_motion.mp4](examples/samples/camera_motion.mp4) |

The compositing order inside `fx` is:

```text
background  ->  behind-subject graphics  ->  subject (segmentation matte)  ->  foreground graphics
```

## Layout

```text
effects/
  README.md            this catalog
  LICENSE              MIT License text
  pyproject.toml       package fx-effects, import name fx
  requirements.txt
  fx/                  package: core, seg, compose, anim, text, palette, vio, audio, recipe, effects/
  presets/             palette JSON
  examples/            recipe, API sample, make_synthetic_clip.py, make_samples.py
    assets/synthetic_mannequin.mp4
    samples/*.mp4      one render per effect, plus samples/_grid.mp4
  scripts/download_models.sh
  tests/               pytest (no models required)
  docs/preview/        two blurred stills
  models/              download location only (.gitkeep; binaries are gitignored)
  e-*/                 one Studio effect entry per fx effect
  _template/           scaffold for a future effect
```

## Run and test

Needs Python 3.10 to 3.14 and `ffmpeg` / `ffprobe` on `PATH`. Python 3.15 does not work yet: `onnxruntime` has no build for it, so the install fails. From this directory:

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"    # or: pip install -r requirements.txt && pip install pytest
pytest
python -m fx list
```

From the repository root, with the same dependencies installed, `pytest` uses the root `pytest.ini` (`pythonpath = effects`). Either way the suite is `tests/test_smoke.py` (every effect on a synthetic frame, plus one short chroma-key recipe) and `tests/test_catalog.py` (every effect has an `e-*` entry, and private media links are absent).

Do not commit `.venv/`, `cache/`, or files downloaded into `models/`.

Apply one effect to your own clip (frames outside `--start` / `--end` pass through, audio is kept):

```bash
python -m fx apply --effect spotlight --in clip.mp4 --out out.mp4 --start 1.0 --end 4.0 \
    --params '{"sparkles": 40, "dim": 0.25}' --palette neutral-mono --size 1080x1920
```

The committed subject is procedural. Segment it with chroma (no model files):

```bash
python -m fx apply --effect spotlight \
    --in examples/assets/synthetic_mannequin.mp4 --out /tmp/spotlight.mp4 \
    --palette neutral-mono --size 360x640 --backend chroma \
    --seg '{"chroma_hue": 290, "chroma_tol": 22, "chroma_subject": "key"}'
```

Each `e-*/SKILL.md` has the same shape for that effect. Rebuild every sample with `python examples/make_samples.py`. Chain effects with `python -m fx recipe examples/recipe_example.json`. Check a matte with `python -m fx masks --in clip.mp4 --out mask_check.mp4`.

Optional segmentation weights (Apache-2.0, not committed):

```bash
./scripts/download_models.sh
```

Fonts named in effects (`nunito`, `nunito-bold`, `fraunces`, `antonio`, `caveat`) are Google Fonts (SIL OFL) looked up in `FX_FONT_DIR`, `./fonts`, or the system font folders. Any `.ttf` path also works. The fonts are not bundled.

## Recipe format

`python -m fx recipe` reads JSON. Paths are relative to the recipe file. Effect times are relative to the segment. Effects run in list order.

```jsonc
{
  "out": "reel.mp4", "size": [1080, 1920], "fps": 30,
  "palette": "neutral-mono",
  "seg": {"backend": "ensemble", "temporal_sigma": 1.2},
  "segments": [
    {"src": "clip.mp4",
     "in": 2.0, "dur": 4.0, "speed": 1.0,
     "center": [0.5, 0.6], "zoom": [1.2, 1.3],
     "redact_src": [[0, 0, 1, 0.2]],
     "mask_src": "clip_unblurred.mp4",
     "effects": [
       {"name": "backdrop_words", "start": 0.0, "end": null,
        "params": {"words": [{"text": "BALANCE", "at": 0.1}, {"text": "PATIENCE", "at": 2.0, "color": "secondary"}]}},
       {"name": "label", "params": {"text": "BACKDROP WORDS", "index": 4}}
     ]}
  ],
  "audio": {"music": "bed.mp3", "music_gain_db": -3, "voice": null,
            "sfx": [{"path": "hit.mp3", "at": 4.0, "gain_db": -8}]}
}
```

A worked file with placeholder paths is [`examples/recipe_example.json`](examples/recipe_example.json). [`examples/python_api.py`](examples/python_api.py) shows the per-frame API. [`examples/apply_examples.sh`](examples/apply_examples.sh) is a one-effect-per-command sketch.

```python
import fx
fx.apply_effect("paper_cut", "in.mp4", "out.mp4", start=0, end=3, params={"layers": 2}, palette="neutral-mono")
fx.run_recipe("recipe.json")
```

Register a new effect with `@fx.register("name", defaults={...})` on `fn(ctx, params) -> float32 frame`. `ctx` has `frame, src, mask, t, dur, u, i, fps, palette, state, W, H`. Helpers live in `fx.compose`, `fx.anim`, and `fx.text`.

## Palettes

Presets in `presets/` are JSON: `swatches` (name to hex) and `roles` (role to swatch or hex). Effects ask for `bg, outline, text, paper, accent, punch, glow, secondary, note, hot, split`. A colour param also accepts a swatch name or `#hex`.

Included: `navy-amber` (default example palette) and `neutral-mono`. Flat caption palettes (`{"primary": "#..", "punch": "#..", "outline": "#.."}`) are accepted. Set `FX_PALETTE` to change the default.

## Segmentation

- `mediapipe` — selfie multiclass model. Fast on CPU, finds small or distant people.
- `u2net` — U²-Net human segmentation (ONNX). Cleaner edges on medium and close subjects.
- `ensemble` (default) — average of both, re-ramped.
- `chroma` — colour key, no model. The synthetic mannequin uses `chroma_subject: "key"`, `chroma_hue` around 290, and `chroma_tol` around 22.

Analysis is at 540 px wide, then small-island removal, hole closing, a PNG mask cache (`cache/masks`, or `FX_MASK_CACHE`), a temporal gaussian, and a guided-filter refine at output size. People under about 5% of frame height, fast motion blur, clothing that matches the floor, and held objects are the weak spots. Use `python -m fx masks`, a tighter `zoom`, or another backend when a matte looks wrong.

## Preview stills

These two blurred stills are the only overview images in the tree. They are still images. Per-effect motion previews are the synthetic samples linked above.

![Blurred still of an effects test reel](docs/preview/fx_test_reel.jpg)

Blurred still from a 28-second effects pass: vertigo, paper cut, spotlight, backdrop words, scribble outline, countdown behind, and glass card.

![Blurred still of a narrated reel with effects applied](docs/preview/stone_grinder_fx_reel.jpg)

Blurred still from a 28-second narrated reel (`docs/preview/stone_grinder_fx_reel.jpg`): digital zoom, spotlight, backdrop words, glass card, and moody grade. Wall and banner text in the source was softened before this still was saved.

## Dependency licenses

| Component | License |
| --- | --- |
| numpy | BSD-3-Clause |
| Pillow | MIT-CMU (HPND) |
| OpenCV (+ contrib) | Apache-2.0 |
| MediaPipe and the selfie multiclass model | Apache-2.0 |
| ONNX Runtime | MIT |
| U²-Net human-seg weights (rembg release) | Apache-2.0 |
| Google Fonts used by name (Nunito, Fraunces, Antonio, Caveat) | SIL OFL 1.1 — not bundled |
| ffmpeg (external binary, not bundled) | LGPL/GPL depending on the build |

## Untracked local files

Model binaries, mask caches, virtualenvs, credentials, and real footage stay out of git. The committed media are `examples/assets/synthetic_mannequin.mp4`, `examples/samples/*.mp4`, and the two JPEGs in `docs/preview/`.
