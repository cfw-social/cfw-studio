# e-colour-collage

A solid colour poster with rotated word blocks that slide in behind the cut-out subject.

This folder is the CFW Studio catalog entry (`kind: effect`, variation `default`). The implementation is the shared `fx` package, effect `colour_collage`, in [`../fx/effects/colour_collage.py`](../fx/effects/colour_collage.py). Run commands from `effects/` so `python -m fx` imports that package.

The `fx` package and this catalog entry are MIT licensed. See [the effects license note](../README.md#license).

## When to use

Use for a flat poster of big words with the person cut out on top.

## Steps

1. Read the inputs in `effect.yaml`. The required input is one video, `clip`. Optional `params` is a JSON object of the settings below. Optional `palette` is a preset name (`neutral-mono`, `vasanth-personal`), a path to palette JSON, or inline palette JSON.
2. From `effects/`, apply the effect with the shared package. `--start` and `--end` are seconds; frames outside that window pass through, and audio is kept.

```bash
python -m fx apply \
  --effect colour_collage \
  --in "$CLIP" \
  --out "$OUT" \
  --palette neutral-mono \
  --size 1080x1920 \
  --params '{"blocks": [{"text": "PLAN", "color": "accent", "pos": [0.32, 0.2], "angle": -6}, {"text": "DO", "color": "hot", "pos": [0.68, 0.35], "angle": 5}, {"text": "REVIEW", "color": "bg", "pos": [0.42, 0.8], "angle": -3}]}'
```

From the repository root, prefix the same command with `PYTHONPATH=effects`.

The procedural subject, with no downloaded models and no real footage, is `examples/assets/synthetic_mannequin.mp4` (path relative to `effects/`). The chroma key matches that clip:

```bash
python -m fx apply \
  --effect colour_collage \
  --in examples/assets/synthetic_mannequin.mp4 \
  --out /tmp/colour_collage.mp4 \
  --palette neutral-mono \
  --size 360x640 \
  --backend chroma \
  --seg '{"chroma_hue": 290, "chroma_tol": 22, "chroma_subject": "key"}' \
  --params '{"blocks": [{"text": "PLAN", "color": "accent", "pos": [0.32, 0.2], "angle": -6}, {"text": "DO", "color": "hot", "pos": [0.68, 0.35], "angle": 5}, {"text": "REVIEW", "color": "bg", "pos": [0.42, 0.8], "angle": -3}]}'
```

`ensemble`, `mediapipe`, and `u2net` need the weights from `../scripts/download_models.sh`. Those binaries stay out of git. `chroma` needs no weights.

3. Write the treated video to the `treated_clip` output.
4. Compare it with the sample in `PREVIEW.md`. Rebuild synthetic samples from `effects/` with `python examples/make_samples.py`.

Python API, with `effects/` on `PYTHONPATH`:

```python
import fx
fx.apply_effect('colour_collage', "in.mp4", "out.mp4", palette="neutral-mono", params={'blocks': [{'text': 'PLAN', 'color': 'accent', 'pos': [0.32, 0.2], 'angle': -6}, {'text': 'DO', 'color': 'hot', 'pos': [0.68, 0.35], 'angle': 5}, {'text': 'REVIEW', 'color': 'bg', 'pos': [0.42, 0.8], 'angle': -3}]})
```

## Defaults

```json
{
  "bg": "secondary",
  "blocks": [
    {
      "text": "BIG",
      "color": "accent",
      "pos": [
        0.32,
        0.2
      ],
      "angle": -6
    },
    {
      "text": "BOLD",
      "color": "hot",
      "pos": [
        0.66,
        0.36
      ],
      "angle": 5
    },
    {
      "text": "BLOCKS",
      "color": "bg",
      "pos": [
        0.4,
        0.78
      ],
      "angle": -3
    }
  ],
  "text_color": "text",
  "font": "antonio",
  "block_h": 0.13,
  "stagger": 0.25,
  "slide": 0.35,
  "keep_bg": false
}
```

## Checks

- The blocks pass behind the subject.
- Each block is rotated and carries a word.
- The output duration matches the source.
