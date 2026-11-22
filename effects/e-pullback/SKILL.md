# e-pullback

The full-frame clip shrinks into a generic phone with a neutral short-video feed, and can swipe to a next post.

This folder is the CFW Studio catalog entry (`kind: effect`, variation `default`). The implementation is the shared `fx` package, effect `pullback`, in [`../fx/effects/pullback.py`](../fx/effects/pullback.py). Run commands from `effects/` so `python -m fx` imports that package.

The `fx` package and this catalog entry are MIT licensed. See [the effects license note](../README.md#license).

## When to use

Use to end a shot inside a plain phone feed. The UI is a generic drawing.

## Steps

1. Read the inputs in `effect.yaml`. The required input is one video, `clip`. Optional `params` is a JSON object of the settings below. Optional `palette` is a preset name (`neutral-mono`, `navy-amber`), a path to palette JSON, or inline palette JSON.
2. From `effects/`, apply the effect with the shared package. `--start` and `--end` are seconds; frames outside that window pass through, and audio is kept.

```bash
python -m fx apply \
  --effect pullback \
  --in "$CLIP" \
  --out "$OUT" \
  --palette neutral-mono \
  --size 1080x1920 \
  --params '{"at": 0.2, "dur": 0.7, "caption": "your caption here"}'
```

From the repository root, prefix the same command with `PYTHONPATH=effects`.

The procedural subject, with no downloaded models and no real footage, is `examples/assets/synthetic_mannequin.mp4` (path relative to `effects/`). The chroma key matches that clip:

```bash
python -m fx apply \
  --effect pullback \
  --in examples/assets/synthetic_mannequin.mp4 \
  --out /tmp/pullback.mp4 \
  --palette neutral-mono \
  --size 360x640 \
  --backend chroma \
  --seg '{"chroma_hue": 290, "chroma_tol": 22, "chroma_subject": "key"}' \
  --params '{"at": 0.2, "dur": 0.7, "caption": "your caption here"}'
```

`ensemble`, `mediapipe`, and `u2net` need the weights from `../scripts/download_models.sh`. Those binaries stay out of git. `chroma` needs no weights.

3. Write the treated video to the `treated_clip` output.
4. Compare it with the sample in `PREVIEW.md`. Rebuild synthetic samples from `effects/` with `python examples/make_samples.py`.

Python API, with `effects/` on `PYTHONPATH`:

```python
import fx
fx.apply_effect('pullback', "in.mp4", "out.mp4", palette="neutral-mono", params={'at': 0.2, 'dur': 0.7, 'caption': 'your caption here'})
```

## Defaults

```json
{
  "at": 0.3,
  "dur": 0.7,
  "phone_w": 0.62,
  "bg": "secondary",
  "handle": "@yourhandle",
  "caption": "your caption here",
  "scroll_at": null,
  "ui": true
}
```

## Checks

- The picture ends inside a drawn phone.
- A caption line is readable.
- The output duration matches the source.
