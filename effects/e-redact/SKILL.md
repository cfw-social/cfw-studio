# e-redact

Hides rectangles with blur, pixelation, or a flat fill. Rects are frame fractions [x, y, w, h].

This folder is the CFW Studio catalog entry (`kind: effect`, variation `default`). The implementation is the shared `fx` package, effect `redact`, in [`../fx/effects/utility.py`](../fx/effects/utility.py). Run commands from `effects/` so `python -m fx` imports that package.

The `fx` package and this catalog entry are MIT licensed. See [the effects license note](../README.md#license).

## When to use

Use to cover signs, names, or screens before a shot is shared.

## Steps

1. Read the inputs in `effect.yaml`. The required input is one video, `clip`. Optional `params` is a JSON object of the settings below. Optional `palette` is a preset name (`neutral-mono`, `vasanth-personal`), a path to palette JSON, or inline palette JSON.
2. From `effects/`, apply the effect with the shared package. `--start` and `--end` are seconds; frames outside that window pass through, and audio is kept.

```bash
python -m fx apply \
  --effect redact \
  --in "$CLIP" \
  --out "$OUT" \
  --palette neutral-mono \
  --size 1080x1920 \
  --params '{"rects": [[0.6, 0.12, 0.35, 0.12]], "mode": "pixelate"}'
```

From the repository root, prefix the same command with `PYTHONPATH=effects`.

The procedural subject, with no downloaded models and no real footage, is `examples/assets/synthetic_mannequin.mp4` (path relative to `effects/`). The chroma key matches that clip:

```bash
python -m fx apply \
  --effect redact \
  --in examples/assets/synthetic_mannequin.mp4 \
  --out /tmp/redact.mp4 \
  --palette neutral-mono \
  --size 360x640 \
  --backend chroma \
  --seg '{"chroma_hue": 290, "chroma_tol": 22, "chroma_subject": "key"}' \
  --params '{"rects": [[0.6, 0.12, 0.35, 0.12]], "mode": "pixelate"}'
```

`ensemble`, `mediapipe`, and `u2net` need the weights from `../scripts/download_models.sh`. Those binaries stay out of git. `chroma` needs no weights.

3. Write the treated video to the `treated_clip` output.
4. Compare it with the sample in `PREVIEW.md`. Rebuild synthetic samples from `effects/` with `python examples/make_samples.py`.

Python API, with `effects/` on `PYTHONPATH`:

```python
import fx
fx.apply_effect('redact', "in.mp4", "out.mp4", palette="neutral-mono", params={'rects': [[0.6, 0.12, 0.35, 0.12]], 'mode': 'pixelate'})
```

## Defaults

```json
{
  "rects": [],
  "mode": "blur",
  "color": "bg",
  "strength": 28
}
```

Set `rects` to `[[x, y, w, h], ...]` in fractions of the frame. `mode` is `blur`, `pixelate`, or `fill`. An empty list leaves the frame unchanged.

## Checks

- Each rect in params is covered by the chosen mode.
- Regions outside those rects match the source.
- The output duration matches the source.
