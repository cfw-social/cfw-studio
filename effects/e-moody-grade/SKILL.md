# e-moody-grade

Desaturates, crushes the shadows, tints them, and adds an oval vignette, grain, and an optional subject colour pop.

This folder is the CFW Studio catalog entry (`kind: effect`, variation `default`). The implementation is the shared `fx` package, effect `moody_grade`, in [`../fx/effects/moody_grade.py`](../fx/effects/moody_grade.py). Run commands from `effects/` so `python -m fx` imports that package.

The `fx` package and this catalog entry are MIT licensed. See [the effects license note](../README.md#license).

## When to use

Use for a heavy, dim grade. For a light global correction, use grade.

## Steps

1. Read the inputs in `effect.yaml`. The required input is one video, `clip`. Optional `params` is a JSON object of the settings below. Optional `palette` is a preset name (`neutral-mono`, `navy-amber`), a path to palette JSON, or inline palette JSON.
2. From `effects/`, apply the effect with the shared package. `--start` and `--end` are seconds; frames outside that window pass through, and audio is kept.

```bash
python -m fx apply \
  --effect moody_grade \
  --in "$CLIP" \
  --out "$OUT" \
  --palette neutral-mono \
  --size 1080x1920
```

From the repository root, prefix the same command with `PYTHONPATH=effects`.

The procedural subject, with no downloaded models and no real footage, is `examples/assets/synthetic_mannequin.mp4` (path relative to `effects/`). The chroma key matches that clip:

```bash
python -m fx apply \
  --effect moody_grade \
  --in examples/assets/synthetic_mannequin.mp4 \
  --out /tmp/moody_grade.mp4 \
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
fx.apply_effect('moody_grade', "in.mp4", "out.mp4", palette="neutral-mono", params={})
```

## Defaults

```json
{
  "desat": 0.7,
  "vignette": 0.55,
  "crush": 0.06,
  "contrast": 1.12,
  "shadows": "bg",
  "tint": 0.12,
  "grain": 0.035,
  "ramp": 0.4,
  "subject_pop": 0.25
}
```

## Checks

- Saturation is lower than the source.
- The corners are darker than the centre.
- The output duration matches the source.
