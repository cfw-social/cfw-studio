# e-spotlight

Dims and desaturates the background, pools light on the subject, and adds a coloured rim glow, an overhead beam, and sparkles.

This folder is the CFW Studio catalog entry (`kind: effect`, variation `default`). The implementation is the shared `fx` package, effect `spotlight`, in [`../fx/effects/spotlight.py`](../fx/effects/spotlight.py). Run commands from `effects/` so `python -m fx` imports that package.

The `fx` package and this catalog entry are MIT licensed. See [the effects license note](../README.md#license).

## When to use

Use when the subject should be the brightest thing in the frame.

## Steps

1. Read the inputs in `effect.yaml`. The required input is one video, `clip`. Optional `params` is a JSON object of the settings below. Optional `palette` is a preset name (`neutral-mono`, `vasanth-personal`), a path to palette JSON, or inline palette JSON.
2. From `effects/`, apply the effect with the shared package. `--start` and `--end` are seconds; frames outside that window pass through, and audio is kept.

```bash
python -m fx apply \
  --effect spotlight \
  --in "$CLIP" \
  --out "$OUT" \
  --palette neutral-mono \
  --size 1080x1920
```

From the repository root, prefix the same command with `PYTHONPATH=effects`.

The procedural subject, with no downloaded models and no real footage, is `examples/assets/synthetic_mannequin.mp4` (path relative to `effects/`). The chroma key matches that clip:

```bash
python -m fx apply \
  --effect spotlight \
  --in examples/assets/synthetic_mannequin.mp4 \
  --out /tmp/spotlight.mp4 \
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
fx.apply_effect('spotlight', "in.mp4", "out.mp4", palette="neutral-mono", params={})
```

## Defaults

```json
{
  "dim": 0.3,
  "desat": 0.55,
  "radius": 1.15,
  "glow": "glow",
  "glow_strength": 0.85,
  "glow_size": 34,
  "beam": true,
  "beam_strength": 0.35,
  "sparkles": 40,
  "sparkle_color": "text",
  "sparkle_size": 30,
  "ramp": 0.35,
  "lift": 1.06,
  "seed": 7
}
```

## Checks

- The background is dimmer than the subject.
- A coloured rim reads around the silhouette.
- The output duration matches the source.
