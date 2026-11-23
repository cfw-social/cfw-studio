# e-glass-card

A frosted-glass note card (blurred fill, tint, rim, shadow, accent bar) that slides in and out.

This folder is the CFW Studio catalog entry (`kind: effect`, variation `default`). The implementation is the shared `fx` package, effect `glass_card`, in [`../fx/effects/glass_card.py`](../fx/effects/glass_card.py). Run commands from `effects/` so `python -m fx` imports that package.

The `fx` package and this catalog entry are MIT licensed. See [the effects license note](../README.md#license).

## When to use

Use for a short title and body on a glass card over the shot, or behind the subject.

## Steps

1. Read the inputs in `effect.yaml`. The required input is one video, `clip`. Optional `params` is a JSON object of the settings below. Optional `palette` is a preset name (`neutral-mono`, `navy-amber`), a path to palette JSON, or inline palette JSON.
2. From `effects/`, apply the effect with the shared package. `--start` and `--end` are seconds; frames outside that window pass through, and audio is kept.

```bash
python -m fx apply \
  --effect glass_card \
  --in "$CLIP" \
  --out "$OUT" \
  --palette neutral-mono \
  --size 1080x1920 \
  --params '{"title": "One tip", "body": "Keep one idea per card."}'
```

From the repository root, prefix the same command with `PYTHONPATH=effects`.

The procedural subject, with no downloaded models and no real footage, is `examples/assets/synthetic_mannequin.mp4` (path relative to `effects/`). The chroma key matches that clip:

```bash
python -m fx apply \
  --effect glass_card \
  --in examples/assets/synthetic_mannequin.mp4 \
  --out /tmp/glass_card.mp4 \
  --palette neutral-mono \
  --size 360x640 \
  --backend chroma \
  --seg '{"chroma_hue": 290, "chroma_tol": 22, "chroma_subject": "key"}' \
  --params '{"title": "One tip", "body": "Keep one idea per card."}'
```

`ensemble`, `mediapipe`, and `u2net` need the weights from `../scripts/download_models.sh`. Those binaries stay out of git. `chroma` needs no weights.

3. Write the treated video to the `treated_clip` output.
4. Compare it with the sample in `PREVIEW.md`. Rebuild synthetic samples from `effects/` with `python examples/make_samples.py`.

Python API, with `effects/` on `PYTHONPATH`:

```python
import fx
fx.apply_effect('glass_card', "in.mp4", "out.mp4", palette="neutral-mono", params={'title': 'One tip', 'body': 'Keep one idea per card.'})
```

## Defaults

```json
{
  "title": "Try this",
  "body": "",
  "pos": [
    0.07,
    0.66
  ],
  "width": 0.62,
  "radius": 40,
  "blur": 24,
  "tint": "text",
  "tint_alpha": 0.2,
  "border_alpha": 0.6,
  "shadow": 0.4,
  "accent": "accent",
  "text_color": "text",
  "text_outline": "outline",
  "title_font": "nunito",
  "body_font": "nunito-bold",
  "title_size": 76,
  "body_size": 54,
  "wrap": 22,
  "padding": 40,
  "slide_from": "left",
  "slide": 0.45,
  "slide_out": 0.3,
  "layer": "front",
  "grain": 0.02
}
```

## Checks

- The card has a blurred fill, a rim, and a readable title.
- The slide-in finishes inside the clip.
- The output duration matches the source.
