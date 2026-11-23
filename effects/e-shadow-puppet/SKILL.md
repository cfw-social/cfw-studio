# e-shadow-puppet

A flat silhouette on a solid colour, with a rim light, a cast shadow, and a wipe-in from the original.

This folder is the CFW Studio catalog entry (`kind: effect`, variation `default`). The implementation is the shared `fx` package, effect `shadow_puppet`, in [`../fx/effects/shadow_puppet.py`](../fx/effects/shadow_puppet.py). Run commands from `effects/` so `python -m fx` imports that package.

The `fx` package and this catalog entry are MIT licensed. See [the effects license note](../README.md#license).

## When to use

Use to turn the person into a paper-cut shadow on a flat field of colour.

## Steps

1. Read the inputs in `effect.yaml`. The required input is one video, `clip`. Optional `params` is a JSON object of the settings below. Optional `palette` is a preset name (`neutral-mono`, `navy-amber`), a path to palette JSON, or inline palette JSON.
2. From `effects/`, apply the effect with the shared package. `--start` and `--end` are seconds; frames outside that window pass through, and audio is kept.

```bash
python -m fx apply \
  --effect shadow_puppet \
  --in "$CLIP" \
  --out "$OUT" \
  --palette neutral-mono \
  --size 1080x1920
```

From the repository root, prefix the same command with `PYTHONPATH=effects`.

The procedural subject, with no downloaded models and no real footage, is `examples/assets/synthetic_mannequin.mp4` (path relative to `effects/`). The chroma key matches that clip:

```bash
python -m fx apply \
  --effect shadow_puppet \
  --in examples/assets/synthetic_mannequin.mp4 \
  --out /tmp/shadow_puppet.mp4 \
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
fx.apply_effect('shadow_puppet', "in.mp4", "out.mp4", palette="neutral-mono", params={})
```

## Defaults

```json
{
  "bg": "accent",
  "silhouette": "outline",
  "rim": "text",
  "rim_px": 4,
  "cast": true,
  "cast_dx": 40,
  "cast_dy": 10,
  "cast_alpha": 0.25,
  "gradient": 0.25,
  "intro": 0.25,
  "grain": 0.02,
  "harden": [
    0.35,
    0.6
  ]
}
```

## Checks

- The subject reads as a silhouette.
- The background is a solid palette colour.
- The output duration matches the source.
