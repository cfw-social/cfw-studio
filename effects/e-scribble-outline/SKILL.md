# e-scribble-outline

A hand-drawn contour that boils around the subject, draws on, and can use a second sketch line plus glow.

This folder is the CFW Studio catalog entry (`kind: effect`, variation `default`). The implementation is the shared `fx` package, effect `scribble_outline`, in [`../fx/effects/scribble_outline.py`](../fx/effects/scribble_outline.py). Run commands from `effects/` so `python -m fx` imports that package.

The `fx` package and this catalog entry are MIT licensed. See [the effects license note](../README.md#license).

## When to use

Use for an ink outline that keeps moving slightly, like a drawn circle around a person.

## Steps

1. Read the inputs in `effect.yaml`. The required input is one video, `clip`. Optional `params` is a JSON object of the settings below. Optional `palette` is a preset name (`neutral-mono`, `navy-amber`), a path to palette JSON, or inline palette JSON.
2. From `effects/`, apply the effect with the shared package. `--start` and `--end` are seconds; frames outside that window pass through, and audio is kept.

```bash
python -m fx apply \
  --effect scribble_outline \
  --in "$CLIP" \
  --out "$OUT" \
  --palette neutral-mono \
  --size 1080x1920
```

From the repository root, prefix the same command with `PYTHONPATH=effects`.

The procedural subject, with no downloaded models and no real footage, is `examples/assets/synthetic_mannequin.mp4` (path relative to `effects/`). The chroma key matches that clip:

```bash
python -m fx apply \
  --effect scribble_outline \
  --in examples/assets/synthetic_mannequin.mp4 \
  --out /tmp/scribble_outline.mp4 \
  --palette neutral-mono \
  --size 360x640 \
  --backend chroma \
  --seg '{"chroma_hue": 290, "chroma_tol": 22, "chroma_subject": "key"}'
```

`ensemble`, `mediapipe`, and `u2net` need the weights from `../scripts/download_models.sh`. Those binaries stay out of git. `chroma` needs no weights.

3. Write the treated video to the `treated_clip` output.
4. Compare it with the sample in `PREVIEW.md`. Rebuild synthetic samples from `effects/` with `python examples/make_samples.py`.

Python API, with `effects/` on `PYTHONPATH`:

```python
import fx
fx.apply_effect('scribble_outline', "in.mp4", "out.mp4", palette="neutral-mono", params={})
```

## Defaults

```json
{
  "color": "accent",
  "color2": "text",
  "thickness": 7,
  "offset": 16,
  "jitter": 5.0,
  "boil": 3,
  "passes": 2,
  "step": 16,
  "draw_on": 0.5,
  "min_area": 0.004,
  "glow": 0.5,
  "seed": 11,
  "max_shapes": 4
}
```

## Checks

- The outline follows the silhouette.
- The line stays uneven and shifts slightly over time.
- The output duration matches the source.
