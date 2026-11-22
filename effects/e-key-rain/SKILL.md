# e-key-rain

Keycaps fall with gravity, spin, and bounce, about half behind the subject and half in front.

This folder is the CFW Studio catalog entry (`kind: effect`, variation `default`). The implementation is the shared `fx` package, effect `key_rain`, in [`../fx/effects/key_rain.py`](../fx/effects/key_rain.py). Run commands from `effects/` so `python -m fx` imports that package.

The `fx` package and this catalog entry are MIT licensed. See [the effects license note](../README.md#license).

## When to use

Use for a shower of keyboard keys around the person.

## Steps

1. Read the inputs in `effect.yaml`. The required input is one video, `clip`. Optional `params` is a JSON object of the settings below. Optional `palette` is a preset name (`neutral-mono`, `vasanth-personal`), a path to palette JSON, or inline palette JSON.
2. From `effects/`, apply the effect with the shared package. `--start` and `--end` are seconds; frames outside that window pass through, and audio is kept.

```bash
python -m fx apply \
  --effect key_rain \
  --in "$CLIP" \
  --out "$OUT" \
  --palette neutral-mono \
  --size 1080x1920 \
  --params '{"letters": "SAMPLE", "count": 18, "spawn": 1.0}'
```

From the repository root, prefix the same command with `PYTHONPATH=effects`.

The procedural subject, with no downloaded models and no real footage, is `examples/assets/synthetic_mannequin.mp4` (path relative to `effects/`). The chroma key matches that clip:

```bash
python -m fx apply \
  --effect key_rain \
  --in examples/assets/synthetic_mannequin.mp4 \
  --out /tmp/key_rain.mp4 \
  --palette neutral-mono \
  --size 360x640 \
  --backend chroma \
  --seg '{"chroma_hue": 290, "chroma_tol": 22, "chroma_subject": "key"}' \
  --params '{"letters": "SAMPLE", "count": 18, "spawn": 1.0}'
```

`ensemble`, `mediapipe`, and `u2net` need the weights from `../scripts/download_models.sh`. Those binaries stay out of git. `chroma` needs no weights.

3. Write the treated video to the `treated_clip` output.
4. Compare it with the sample in `PREVIEW.md`. Rebuild synthetic samples from `effects/` with `python examples/make_samples.py`.

Python API, with `effects/` on `PYTHONPATH`:

```python
import fx
fx.apply_effect('key_rain', "in.mp4", "out.mp4", palette="neutral-mono", params={'letters': 'SAMPLE', 'count': 18, 'spawn': 1.0})
```

## Defaults

```json
{
  "letters": "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
  "count": 26,
  "size": 150,
  "gravity": 2600,
  "spawn": 1.6,
  "floor": 0.93,
  "bounce": 0.35,
  "behind_ratio": 0.5,
  "cap": "text",
  "side": "secondary",
  "legend": "outline",
  "accent_every": 5,
  "accent": "accent",
  "seed": 5
}
```

## Checks

- Caps fall and meet a floor line.
- Some caps are hidden by the subject and some draw on top.
- The output duration matches the source.
