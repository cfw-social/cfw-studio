# e-label

A small pill chip that names the shot, with an optional index, then fades out.

This folder is the CFW Studio catalog entry (`kind: effect`, variation `default`). The implementation is the shared `fx` package, effect `label`, in [`../fx/effects/utility.py`](../fx/effects/utility.py). Run commands from `effects/` so `python -m fx` imports that package.

The `fx` package and this catalog entry are MIT licensed. See [the effects license note](../README.md#license).

## When to use

Use for a short on-screen name, such as an effect index plus a title.

## Steps

1. Read the inputs in `effect.yaml`. The required input is one video, `clip`. Optional `params` is a JSON object of the settings below. Optional `palette` is a preset name (`neutral-mono`, `navy-amber`), a path to palette JSON, or inline palette JSON.
2. From `effects/`, apply the effect with the shared package. `--start` and `--end` are seconds; frames outside that window pass through, and audio is kept.

```bash
python -m fx apply \
  --effect label \
  --in "$CLIP" \
  --out "$OUT" \
  --palette neutral-mono \
  --size 1080x1920 \
  --params '{"text": "LABEL", "index": 1}'
```

From the repository root, prefix the same command with `PYTHONPATH=effects`.

The procedural subject, with no downloaded models and no real footage, is `examples/assets/synthetic_mannequin.mp4` (path relative to `effects/`). The chroma key matches that clip:

```bash
python -m fx apply \
  --effect label \
  --in examples/assets/synthetic_mannequin.mp4 \
  --out /tmp/label.mp4 \
  --palette neutral-mono \
  --size 360x640 \
  --backend chroma \
  --seg '{"chroma_hue": 290, "chroma_tol": 22, "chroma_subject": "key"}' \
  --params '{"text": "LABEL", "index": 1}'
```

`ensemble`, `mediapipe`, and `u2net` need the weights from `../scripts/download_models.sh`. Those binaries stay out of git. `chroma` needs no weights.

3. Write the treated video to the `treated_clip` output.
4. Compare it with the sample in `PREVIEW.md`. Rebuild synthetic samples from `effects/` with `python examples/make_samples.py`.

Python API, with `effects/` on `PYTHONPATH`:

```python
import fx
fx.apply_effect('label', "in.mp4", "out.mp4", palette="neutral-mono", params={'text': 'LABEL', 'index': 1})
```

## Defaults

```json
{
  "text": "EFFECT",
  "index": null,
  "y": 0.07,
  "size": 46,
  "bg": "bg",
  "bg_alpha": 0.82,
  "color": "text",
  "accent": "accent",
  "fade": 0.25,
  "font": "nunito",
  "out": 0.25
}
```

## Checks

- The chip is readable and sits inside the frame.
- It fades in and fades out.
- The output duration matches the source.
