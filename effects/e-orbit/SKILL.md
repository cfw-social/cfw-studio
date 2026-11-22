# e-orbit

Clip cards orbit the subject on a tilted ellipse, depth-sorted so the far half passes behind and the near half in front.

This folder is the CFW Studio catalog entry (`kind: effect`, variation `default`). The implementation is the shared `fx` package, effect `orbit`, in [`../fx/effects/orbit.py`](../fx/effects/orbit.py). Run commands from `effects/` so `python -m fx` imports that package.

The `fx` package and this catalog entry are MIT licensed. See [the effects license note](../README.md#license).

## When to use

Use when several small clips should circle the person.

## Steps

1. Read the inputs in `effect.yaml`. The required input is one video, `clip`. Optional `params` is a JSON object of the settings below. Optional `palette` is a preset name (`neutral-mono`, `vasanth-personal`), a path to palette JSON, or inline palette JSON.
2. From `effects/`, apply the effect with the shared package. `--start` and `--end` are seconds; frames outside that window pass through, and audio is kept.

```bash
python -m fx apply \
  --effect orbit \
  --in "$CLIP" \
  --out "$OUT" \
  --palette neutral-mono \
  --size 1080x1920
```

From the repository root, prefix the same command with `PYTHONPATH=effects`.

The procedural subject, with no downloaded models and no real footage, is `examples/assets/synthetic_mannequin.mp4` (path relative to `effects/`). The chroma key matches that clip:

```bash
python -m fx apply \
  --effect orbit \
  --in examples/assets/synthetic_mannequin.mp4 \
  --out /tmp/orbit.mp4 \
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
fx.apply_effect('orbit', "in.mp4", "out.mp4", palette="neutral-mono", params={})
```

## Defaults

```json
{
  "clips": null,
  "count": 5,
  "card_w": 0.3,
  "aspect": 1.6,
  "radius_x": 0.42,
  "radius_y": 0.07,
  "y": 0.45,
  "speed": 0.35,
  "tilt": 8.0,
  "min_scale": 0.55,
  "border": "text",
  "radius": 26,
  "intro": 0.5,
  "self_delay": 12
}
```

`clips` in `params` is a list of paths or `{src, in, dur}` objects. Omit `clips` and the effect uses delayed copies of `clip`.

## Checks

- Cards move on a loop around the subject.
- Far cards pass behind the subject and near cards pass in front.
- The output duration matches the source.
