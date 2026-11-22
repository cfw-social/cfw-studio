# e-tier-list

A generic tier board under the clip; a snapshot card flies into one tier.

This folder is the CFW Studio catalog entry (`kind: effect`, variation `default`). The implementation is the shared `fx` package, effect `tier_list`, in [`../fx/effects/tier_list.py`](../fx/effects/tier_list.py). Run commands from `effects/` so `python -m fx` imports that package.

The `fx` package and this catalog entry are MIT licensed. See [the effects license note](../README.md#license).

## When to use

Use to drop the shot onto a plain tier board. The board is a generic drawing.

## Steps

1. Read the inputs in `effect.yaml`. The required input is one video, `clip`. Optional `params` is a JSON object of the settings below. Optional `palette` is a preset name (`neutral-mono`, `navy-amber`), a path to palette JSON, or inline palette JSON.
2. From `effects/`, apply the effect with the shared package. `--start` and `--end` are seconds; frames outside that window pass through, and audio is kept.

```bash
python -m fx apply \
  --effect tier_list \
  --in "$CLIP" \
  --out "$OUT" \
  --palette neutral-mono \
  --size 1080x1920 \
  --params '{"items": [{"label": "idea one", "tier": 1}, {"label": "idea two", "tier": 2}], "drop_at": 0.8}'
```

From the repository root, prefix the same command with `PYTHONPATH=effects`.

The procedural subject, with no downloaded models and no real footage, is `examples/assets/synthetic_mannequin.mp4` (path relative to `effects/`). The chroma key matches that clip:

```bash
python -m fx apply \
  --effect tier_list \
  --in examples/assets/synthetic_mannequin.mp4 \
  --out /tmp/tier_list.mp4 \
  --palette neutral-mono \
  --size 360x640 \
  --backend chroma \
  --seg '{"chroma_hue": 290, "chroma_tol": 22, "chroma_subject": "key"}' \
  --params '{"items": [{"label": "idea one", "tier": 1}, {"label": "idea two", "tier": 2}], "drop_at": 0.8}'
```

`ensemble`, `mediapipe`, and `u2net` need the weights from `../scripts/download_models.sh`. Those binaries stay out of git. `chroma` needs no weights.

3. Write the treated video to the `treated_clip` output.
4. Compare it with the sample in `PREVIEW.md`. Rebuild synthetic samples from `effects/` with `python examples/make_samples.py`.

Python API, with `effects/` on `PYTHONPATH`:

```python
import fx
fx.apply_effect('tier_list', "in.mp4", "out.mp4", palette="neutral-mono", params={'items': [{'label': 'idea one', 'tier': 1}, {'label': 'idea two', 'tier': 2}], 'drop_at': 0.8})
```

## Defaults

```json
{
  "tiers": [
    "S",
    "A",
    "B",
    "C"
  ],
  "colors": [
    "hot",
    "accent",
    "secondary",
    "text"
  ],
  "items": [
    {
      "label": "idea one",
      "tier": 0
    },
    {
      "label": "idea two",
      "tier": 2
    }
  ],
  "drop_tier": 0,
  "drop_at": 1.2,
  "video_h": 0.46,
  "board_bg": "bg",
  "fly": 0.45
}
```

## Checks

- Tier labels and rows are readable.
- A card moves into a tier during the clip.
- The output duration matches the source.
