# e-grid-collage

Tiles many clips in one grid with per-tile labels and a title.

This folder is the CFW Studio catalog entry (`kind: effect`, variation `default`). The implementation is the shared `fx` package, effect `grid_collage`, in [`../fx/effects/grid_collage.py`](../fx/effects/grid_collage.py). Run commands from `effects/` so `python -m fx` imports that package.

The `fx` package and this catalog entry are MIT licensed. See [the effects license note](../README.md#license).

## When to use

Use to show a set of clips at once, including a contact sheet of effect samples.

## Steps

1. Read the inputs in `effect.yaml`. The required input is one video, `clip`. Optional `params` is a JSON object of the settings below. Optional `palette` is a preset name (`neutral-mono`, `vasanth-personal`), a path to palette JSON, or inline palette JSON.
2. From `effects/`, apply the effect with the shared package. `--start` and `--end` are seconds; frames outside that window pass through, and audio is kept.

```bash
python -m fx apply \
  --effect grid_collage \
  --in "$CLIP" \
  --out "$OUT" \
  --palette neutral-mono \
  --size 1080x1920 \
  --params '{"cols": 5, "rows": 6, "title": "fx samples"}'
```

From the repository root, prefix the same command with `PYTHONPATH=effects`.

The procedural subject, with no downloaded models and no real footage, is `examples/assets/synthetic_mannequin.mp4` (path relative to `effects/`). The chroma key matches that clip:

```bash
python -m fx apply \
  --effect grid_collage \
  --in examples/assets/synthetic_mannequin.mp4 \
  --out /tmp/grid_collage.mp4 \
  --palette neutral-mono \
  --size 360x640 \
  --backend chroma \
  --seg '{"chroma_hue": 290, "chroma_tol": 22, "chroma_subject": "key"}' \
  --params '{"cols": 5, "rows": 6, "title": "fx samples"}'
```

`ensemble`, `mediapipe`, and `u2net` need the weights from `../scripts/download_models.sh`. Those binaries stay out of git. `chroma` needs no weights.

3. Write the treated video to the `treated_clip` output.
4. Compare it with the sample in `PREVIEW.md`. Rebuild synthetic samples from `effects/` with `python examples/make_samples.py`.

Python API, with `effects/` on `PYTHONPATH`:

```python
import fx
fx.apply_effect('grid_collage', "in.mp4", "out.mp4", palette="neutral-mono", params={'cols': 5, 'rows': 6, 'title': 'fx samples'})
```

## Defaults

```json
{
  "clips": null,
  "cols": 4,
  "rows": 6,
  "gap": 10,
  "bg": "bg",
  "labels": null,
  "intro": 0.6,
  "title": null,
  "include_self": false,
  "radius": 12
}
```

`clips` in `params` is a list of paths or `{src, in, dur}` objects. Omit `clips` and the effect uses delayed copies of `clip`.

The committed contact sheet `examples/samples/_grid.mp4` is what `examples/make_samples.py` writes after the other samples exist. Re-run that script from `effects/` to rebuild it. A one-clip `apply` call only shows copies of that single clip.

## Checks

- Tiles cascade in.
- Labels match the clips passed in params.
- The output duration matches the source segment.
