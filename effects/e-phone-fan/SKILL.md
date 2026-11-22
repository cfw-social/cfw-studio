# e-phone-fan

Generic phones fan out from behind the subject, each screen playing a clip.

This folder is the CFW Studio catalog entry (`kind: effect`, variation `default`). The implementation is the shared `fx` package, effect `phone_fan`, in [`../fx/effects/phone_fan.py`](../fx/effects/phone_fan.py). Run commands from `effects/` so `python -m fx` imports that package.

The `fx` package and this catalog entry are MIT licensed. See [the effects license note](../README.md#license).

## When to use

Use for a hand of plain phones behind the person. The phones are generic drawings.

## Steps

1. Read the inputs in `effect.yaml`. The required input is one video, `clip`. Optional `params` is a JSON object of the settings below. Optional `palette` is a preset name (`neutral-mono`, `vasanth-personal`), a path to palette JSON, or inline palette JSON.
2. From `effects/`, apply the effect with the shared package. `--start` and `--end` are seconds; frames outside that window pass through, and audio is kept.

```bash
python -m fx apply \
  --effect phone_fan \
  --in "$CLIP" \
  --out "$OUT" \
  --palette neutral-mono \
  --size 1080x1920
```

From the repository root, prefix the same command with `PYTHONPATH=effects`.

The procedural subject, with no downloaded models and no real footage, is `examples/assets/synthetic_mannequin.mp4` (path relative to `effects/`). The chroma key matches that clip:

```bash
python -m fx apply \
  --effect phone_fan \
  --in examples/assets/synthetic_mannequin.mp4 \
  --out /tmp/phone_fan.mp4 \
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
fx.apply_effect('phone_fan', "in.mp4", "out.mp4", palette="neutral-mono", params={})
```

## Defaults

```json
{
  "clips": null,
  "count": 5,
  "spread": 95.0,
  "phone_w": 0.34,
  "pivot_y": 0.95,
  "lift": 0.18,
  "intro": 0.6,
  "stagger": 0.06,
  "self_delay": 10,
  "y": 0.5
}
```

`clips` in `params` is a list of paths or `{src, in, dur}` objects. Omit `clips` and the effect uses delayed copies of `clip`.

## Checks

- Phones rotate out from a low pivot.
- They stay behind the subject.
- The output duration matches the source.
