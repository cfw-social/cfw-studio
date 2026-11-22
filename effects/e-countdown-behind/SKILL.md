# e-countdown-behind

A timer behind the subject: flip-clock tiles that flip each tick, or big outlined digits.

This folder is the CFW Studio catalog entry (`kind: effect`, variation `default`). The implementation is the shared `fx` package, effect `countdown_behind`, in [`../fx/effects/countdown_behind.py`](../fx/effects/countdown_behind.py). Run commands from `effects/` so `python -m fx` imports that package.

The `fx` package and this catalog entry are MIT licensed. See [the effects license note](../README.md#license).

## When to use

Use for a large countdown the person stands in front of.

## Steps

1. Read the inputs in `effect.yaml`. The required input is one video, `clip`. Optional `params` is a JSON object of the settings below. Optional `palette` is a preset name (`neutral-mono`, `navy-amber`), a path to palette JSON, or inline palette JSON.
2. From `effects/`, apply the effect with the shared package. `--start` and `--end` are seconds; frames outside that window pass through, and audio is kept.

```bash
python -m fx apply \
  --effect countdown_behind \
  --in "$CLIP" \
  --out "$OUT" \
  --palette neutral-mono \
  --size 1080x1920 \
  --params '{"start_value": 3, "end_value": 0, "y": 0.3}'
```

From the repository root, prefix the same command with `PYTHONPATH=effects`.

The procedural subject, with no downloaded models and no real footage, is `examples/assets/synthetic_mannequin.mp4` (path relative to `effects/`). The chroma key matches that clip:

```bash
python -m fx apply \
  --effect countdown_behind \
  --in examples/assets/synthetic_mannequin.mp4 \
  --out /tmp/countdown_behind.mp4 \
  --palette neutral-mono \
  --size 360x640 \
  --backend chroma \
  --seg '{"chroma_hue": 290, "chroma_tol": 22, "chroma_subject": "key"}' \
  --params '{"start_value": 3, "end_value": 0, "y": 0.3}'
```

`ensemble`, `mediapipe`, and `u2net` need the weights from `../scripts/download_models.sh`. Those binaries stay out of git. `chroma` needs no weights.

3. Write the treated video to the `treated_clip` output.
4. Compare it with the sample in `PREVIEW.md`. Rebuild synthetic samples from `effects/` with `python examples/make_samples.py`.

Python API, with `effects/` on `PYTHONPATH`:

```python
import fx
fx.apply_effect('countdown_behind', "in.mp4", "out.mp4", palette="neutral-mono", params={'start_value': 3, 'end_value': 0, 'y': 0.3})
```

## Defaults

```json
{
  "start_value": 3,
  "end_value": 0,
  "per_tick": null,
  "format": "mm:ss",
  "style": "tiles",
  "font": "antonio",
  "color": "accent",
  "outline": "outline",
  "outline_px": 10,
  "y": 0.34,
  "width": 0.86,
  "tick_punch": 0.2,
  "flip": 0.22,
  "tile_color": "bg",
  "tile_alpha": 0.92,
  "text_color": "text",
  "line_color": "hot",
  "shadow": 0.4,
  "final_color": "hot"
}
```

## Checks

- The digits pass behind the subject.
- The shown value changes over the clip.
- The output duration matches the source.
