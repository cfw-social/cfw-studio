# e-giant-captions

Screen-filling stacked words, one per line, with colours cycling through the palette.

This folder is the CFW Studio catalog entry (`kind: effect`, variation `default`). The implementation is the shared `fx` package, effect `giant_captions`, in [`../fx/effects/giant_captions.py`](../fx/effects/giant_captions.py). Run commands from `effects/` so `python -m fx` imports that package.

The `fx` package and this catalog entry are MIT licensed. See [the effects license note](../README.md#license).

## When to use

Use when a few words should fill the vertical frame.

## Steps

1. Read the inputs in `effect.yaml`. The required input is one video, `clip`. Optional `params` is a JSON object of the settings below. Optional `palette` is a preset name (`neutral-mono`, `vasanth-personal`), a path to palette JSON, or inline palette JSON.
2. From `effects/`, apply the effect with the shared package. `--start` and `--end` are seconds; frames outside that window pass through, and audio is kept.

```bash
python -m fx apply \
  --effect giant_captions \
  --in "$CLIP" \
  --out "$OUT" \
  --palette neutral-mono \
  --size 1080x1920 \
  --params '{"text": "SAY IT BIG"}'
```

From the repository root, prefix the same command with `PYTHONPATH=effects`.

The procedural subject, with no downloaded models and no real footage, is `examples/assets/synthetic_mannequin.mp4` (path relative to `effects/`). The chroma key matches that clip:

```bash
python -m fx apply \
  --effect giant_captions \
  --in examples/assets/synthetic_mannequin.mp4 \
  --out /tmp/giant_captions.mp4 \
  --palette neutral-mono \
  --size 360x640 \
  --backend chroma \
  --seg '{"chroma_hue": 290, "chroma_tol": 22, "chroma_subject": "key"}' \
  --params '{"text": "SAY IT BIG"}'
```

`ensemble`, `mediapipe`, and `u2net` need the weights from `../scripts/download_models.sh`. Those binaries stay out of git. `chroma` needs no weights.

3. Write the treated video to the `treated_clip` output.
4. Compare it with the sample in `PREVIEW.md`. Rebuild synthetic samples from `effects/` with `python examples/make_samples.py`.

Python API, with `effects/` on `PYTHONPATH`:

```python
import fx
fx.apply_effect('giant_captions', "in.mp4", "out.mp4", palette="neutral-mono", params={'text': 'SAY IT BIG'})
```

## Defaults

```json
{
  "text": "MAKE IT BIG AND BOLD",
  "words": null,
  "per_word": null,
  "lines": 3,
  "font": "antonio",
  "colors": [
    "text",
    "accent",
    "secondary"
  ],
  "outline": "outline",
  "outline_px": 8,
  "top": 0.12,
  "bottom": 0.62,
  "layer": "behind",
  "pop": 0.18,
  "keep": true
}
```

## Checks

- Words span most of the frame width.
- Each word sits on its own line.
- The output duration matches the source.
