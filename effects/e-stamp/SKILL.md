# e-stamp

A rubber-stamp slam: bordered text hits with grunge ink and an impact shake.

This folder is the CFW Studio catalog entry (`kind: effect`, variation `default`). The implementation is the shared `fx` package, effect `stamp`, in [`../fx/effects/stamp.py`](../fx/effects/stamp.py). Run commands from `effects/` so `python -m fx` imports that package.

The `fx` package and this catalog entry are MIT licensed. See [the effects license note](../README.md#license).

## When to use

Use for a short phrase that stamps onto the frame.

## Steps

1. Read the inputs in `effect.yaml`. The required input is one video, `clip`. Optional `params` is a JSON object of the settings below. Optional `palette` is a preset name (`neutral-mono`, `navy-amber`), a path to palette JSON, or inline palette JSON.
2. From `effects/`, apply the effect with the shared package. `--start` and `--end` are seconds; frames outside that window pass through, and audio is kept.

```bash
python -m fx apply \
  --effect stamp \
  --in "$CLIP" \
  --out "$OUT" \
  --palette neutral-mono \
  --size 1080x1920 \
  --params '{"text": "DONE", "at": 0.5}'
```

From the repository root, prefix the same command with `PYTHONPATH=effects`.

The procedural subject, with no downloaded models and no real footage, is `examples/assets/synthetic_mannequin.mp4` (path relative to `effects/`). The chroma key matches that clip:

```bash
python -m fx apply \
  --effect stamp \
  --in examples/assets/synthetic_mannequin.mp4 \
  --out /tmp/stamp.mp4 \
  --palette neutral-mono \
  --size 360x640 \
  --backend chroma \
  --seg '{"chroma_hue": 290, "chroma_tol": 22, "chroma_subject": "key"}' \
  --params '{"text": "DONE", "at": 0.5}'
```

`ensemble`, `mediapipe`, and `u2net` need the weights from `../scripts/download_models.sh`. Those binaries stay out of git. `chroma` needs no weights.

3. Write the treated video to the `treated_clip` output.
4. Compare it with the sample in `PREVIEW.md`. Rebuild synthetic samples from `effects/` with `python examples/make_samples.py`.

Python API, with `effects/` on `PYTHONPATH`:

```python
import fx
fx.apply_effect('stamp', "in.mp4", "out.mp4", palette="neutral-mono", params={'text': 'DONE', 'at': 0.5})
```

## Defaults

```json
{
  "text": "NAILED IT",
  "at": 0.3,
  "color": "hot",
  "pos": [
    0.5,
    0.3
  ],
  "angle": -12.0,
  "width": 0.78,
  "border": 14,
  "from_scale": 3.2,
  "slam": 0.14,
  "shake": 26,
  "grunge": 0.45,
  "seed": 2,
  "font": "nunito"
}
```

## Checks

- The stamp text reaches full size after the hit.
- The frame shifts on impact with the default shake.
- The output duration matches the source.
