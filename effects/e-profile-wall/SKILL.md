# e-profile-wall

A grid of playing tiles with the live centre tile highlighted, plus a big count-up number.

This folder is the CFW Studio catalog entry (`kind: effect`, variation `default`). The implementation is the shared `fx` package, effect `profile_wall`, in [`../fx/effects/profile_wall.py`](../fx/effects/profile_wall.py). Run commands from `effects/` so `python -m fx` imports that package.

The `fx` package and this catalog entry are MIT licensed. See [the effects license note](../README.md#license).

## When to use

Use for a wall of tiles and a large counting number.

## Steps

1. Read the inputs in `effect.yaml`. The required input is one video, `clip`. Optional `params` is a JSON object of the settings below. Optional `palette` is a preset name (`neutral-mono`, `vasanth-personal`), a path to palette JSON, or inline palette JSON.
2. From `effects/`, apply the effect with the shared package. `--start` and `--end` are seconds; frames outside that window pass through, and audio is kept.

```bash
python -m fx apply \
  --effect profile_wall \
  --in "$CLIP" \
  --out "$OUT" \
  --palette neutral-mono \
  --size 1080x1920 \
  --params '{"count_to": 12500, "count_label": "views"}'
```

From the repository root, prefix the same command with `PYTHONPATH=effects`.

The procedural subject, with no downloaded models and no real footage, is `examples/assets/synthetic_mannequin.mp4` (path relative to `effects/`). The chroma key matches that clip:

```bash
python -m fx apply \
  --effect profile_wall \
  --in examples/assets/synthetic_mannequin.mp4 \
  --out /tmp/profile_wall.mp4 \
  --palette neutral-mono \
  --size 360x640 \
  --backend chroma \
  --seg '{"chroma_hue": 290, "chroma_tol": 22, "chroma_subject": "key"}' \
  --params '{"count_to": 12500, "count_label": "views"}'
```

`ensemble`, `mediapipe`, and `u2net` need the weights from `../scripts/download_models.sh`. Those binaries stay out of git. `chroma` needs no weights.

3. Write the treated video to the `treated_clip` output.
4. Compare it with the sample in `PREVIEW.md`. Rebuild synthetic samples from `effects/` with `python examples/make_samples.py`.

Python API, with `effects/` on `PYTHONPATH`:

```python
import fx
fx.apply_effect('profile_wall', "in.mp4", "out.mp4", palette="neutral-mono", params={'count_to': 12500, 'count_label': 'views'})
```

## Defaults

```json
{
  "clips": null,
  "cols": 3,
  "rows": 4,
  "gap": 14,
  "count_from": 0,
  "count_to": 17355,
  "count_label": "views",
  "count_dur": null,
  "highlight": "accent",
  "bg": "bg",
  "intro": 0.4,
  "font": "antonio",
  "self_delay": 6,
  "header": 0.24
}
```

## Checks

- Multiple tiles are on screen.
- The centre tile is outlined.
- The number increases over the clip.
- The output duration matches the source.
