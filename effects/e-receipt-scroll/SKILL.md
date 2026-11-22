# e-receipt-scroll

A procedural paper receipt with torn zig-zag edges, mono type, and a barcode scrolls through the frame.

This folder is the CFW Studio catalog entry (`kind: effect`, variation `default`). The implementation is the shared `fx` package, effect `receipt_scroll`, in [`../fx/effects/receipt_scroll.py`](../fx/effects/receipt_scroll.py). Run commands from `effects/` so `python -m fx` imports that package.

The `fx` package and this catalog entry are MIT licensed. See [the effects license note](../README.md#license).

## When to use

Use for a printed receipt moving past the subject.

## Steps

1. Read the inputs in `effect.yaml`. The required input is one video, `clip`. Optional `params` is a JSON object of the settings below. Optional `palette` is a preset name (`neutral-mono`, `vasanth-personal`), a path to palette JSON, or inline palette JSON.
2. From `effects/`, apply the effect with the shared package. `--start` and `--end` are seconds; frames outside that window pass through, and audio is kept.

```bash
python -m fx apply \
  --effect receipt_scroll \
  --in "$CLIP" \
  --out "$OUT" \
  --palette neutral-mono \
  --size 1080x1920 \
  --params '{"title": "TODAY", "items": [["warm-up", "5 min"], ["drills", "10 min"], ["cool-down", "3 min"]], "total": ["TOTAL", "18 min"], "speed": 900}'
```

From the repository root, prefix the same command with `PYTHONPATH=effects`.

The procedural subject, with no downloaded models and no real footage, is `examples/assets/synthetic_mannequin.mp4` (path relative to `effects/`). The chroma key matches that clip:

```bash
python -m fx apply \
  --effect receipt_scroll \
  --in examples/assets/synthetic_mannequin.mp4 \
  --out /tmp/receipt_scroll.mp4 \
  --palette neutral-mono \
  --size 360x640 \
  --backend chroma \
  --seg '{"chroma_hue": 290, "chroma_tol": 22, "chroma_subject": "key"}' \
  --params '{"title": "TODAY", "items": [["warm-up", "5 min"], ["drills", "10 min"], ["cool-down", "3 min"]], "total": ["TOTAL", "18 min"], "speed": 900}'
```

`ensemble`, `mediapipe`, and `u2net` need the weights from `../scripts/download_models.sh`. Those binaries stay out of git. `chroma` needs no weights.

3. Write the treated video to the `treated_clip` output.
4. Compare it with the sample in `PREVIEW.md`. Rebuild synthetic samples from `effects/` with `python examples/make_samples.py`.

Python API, with `effects/` on `PYTHONPATH`:

```python
import fx
fx.apply_effect('receipt_scroll', "in.mp4", "out.mp4", palette="neutral-mono", params={'title': 'TODAY', 'items': [['warm-up', '5 min'], ['drills', '10 min'], ['cool-down', '3 min']], 'total': ['TOTAL', '18 min'], 'speed': 900})
```

## Defaults

```json
{
  "title": "RECEIPT",
  "items": [
    [
      "item one",
      "1.00"
    ],
    [
      "item two",
      "2.50"
    ],
    [
      "item three",
      "x3"
    ],
    [
      "extra",
      "free"
    ]
  ],
  "total": [
    "TOTAL",
    "6.50"
  ],
  "width": 0.62,
  "x": 0.5,
  "angle": -4.0,
  "speed": 520,
  "layer": "behind",
  "paper": "paper",
  "ink": "outline",
  "accent": "hot",
  "font": "mono",
  "size": 46
}
```

## Checks

- The receipt is a paper strip with torn ends and mono type.
- It moves upward through the frame.
- The output duration matches the source.
