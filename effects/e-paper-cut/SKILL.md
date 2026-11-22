# e-paper-cut

Paper-sticker cutout: a torn white edge, an optional second colour border, a drop shadow, and a procedural paper background.

This folder is the CFW Studio catalog entry (`kind: effect`, variation `default`). The implementation is the shared `fx` package, effect `paper_cut`, in [`../fx/effects/paper_cut.py`](../fx/effects/paper_cut.py). Run commands from `effects/` so `python -m fx` imports that package.

The `fx` package and this catalog entry are MIT licensed. See [the effects license note](../README.md#license).

## When to use

Use when the subject should read as a sticker stuck on paper.

## Steps

1. Read the inputs in `effect.yaml`. The required input is one video, `clip`. Optional `params` is a JSON object of the settings below. Optional `palette` is a preset name (`neutral-mono`, `navy-amber`), a path to palette JSON, or inline palette JSON.
2. From `effects/`, apply the effect with the shared package. `--start` and `--end` are seconds; frames outside that window pass through, and audio is kept.

```bash
python -m fx apply \
  --effect paper_cut \
  --in "$CLIP" \
  --out "$OUT" \
  --palette neutral-mono \
  --size 1080x1920
```

From the repository root, prefix the same command with `PYTHONPATH=effects`.

The procedural subject, with no downloaded models and no real footage, is `examples/assets/synthetic_mannequin.mp4` (path relative to `effects/`). The chroma key matches that clip:

```bash
python -m fx apply \
  --effect paper_cut \
  --in examples/assets/synthetic_mannequin.mp4 \
  --out /tmp/paper_cut.mp4 \
  --palette neutral-mono \
  --size 360x640 \
  --backend chroma \
  --seg '{"chroma_hue": 290, "chroma_tol": 22, "chroma_subject": "key"}'
```

`ensemble`, `mediapipe`, and `u2net` need the weights from `../scripts/download_models.sh`. Those binaries stay out of git. `chroma` needs no weights.

3. Write the treated video to the `treated_clip` output.
4. Compare it with the sample in `PREVIEW.md`. Rebuild synthetic samples from `effects/` with `python examples/make_samples.py`.

Python API, with `effects/` on `PYTHONPATH`:

```python
import fx
fx.apply_effect('paper_cut', "in.mp4", "out.mp4", palette="neutral-mono", params={})
```

## Defaults

```json
{
  "border": 26,
  "rough": 12,
  "rough_scale": 34,
  "paper": "paper",
  "bg": "texture",
  "bg_color": "secondary",
  "shadow": 0.5,
  "shadow_dx": 14,
  "shadow_dy": 22,
  "pop": 0.4,
  "angle": -2.0,
  "seed": 3,
  "layers": 1
}
```

## Checks

- A torn light border follows the subject.
- A drop shadow sits off the cutout.
- The output duration matches the source.
