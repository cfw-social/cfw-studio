# e-backdrop-words

Giant words behind the subject, with a punch-in, a short settle, and a timed word list.

This folder is the CFW Studio catalog entry (`kind: effect`, variation `default`). The implementation is the shared `fx` package, effect `backdrop_words`, in [`../fx/effects/backdrop_words.py`](../fx/effects/backdrop_words.py). Run commands from `effects/` so `python -m fx` imports that package.

The `fx` package and this catalog entry are MIT licensed. See [the effects license note](../README.md#license).

## When to use

Use for one or more huge words that the person stands in front of.

## Steps

1. Read the inputs in `effect.yaml`. The required input is one video, `clip`. Optional `params` is a JSON object of the settings below. Optional `palette` is a preset name (`neutral-mono`, `vasanth-personal`), a path to palette JSON, or inline palette JSON.
2. From `effects/`, apply the effect with the shared package. `--start` and `--end` are seconds; frames outside that window pass through, and audio is kept.

```bash
python -m fx apply \
  --effect backdrop_words \
  --in "$CLIP" \
  --out "$OUT" \
  --palette neutral-mono \
  --size 1080x1920 \
  --params '{"words": [{"text": "FOCUS", "at": 0.1}, {"text": "REPEAT", "at": 1.2, "color": "secondary"}], "y": 0.45}'
```

From the repository root, prefix the same command with `PYTHONPATH=effects`.

The procedural subject, with no downloaded models and no real footage, is `examples/assets/synthetic_mannequin.mp4` (path relative to `effects/`). The chroma key matches that clip:

```bash
python -m fx apply \
  --effect backdrop_words \
  --in examples/assets/synthetic_mannequin.mp4 \
  --out /tmp/backdrop_words.mp4 \
  --palette neutral-mono \
  --size 360x640 \
  --backend chroma \
  --seg '{"chroma_hue": 290, "chroma_tol": 22, "chroma_subject": "key"}' \
  --params '{"words": [{"text": "FOCUS", "at": 0.1}, {"text": "REPEAT", "at": 1.2, "color": "secondary"}], "y": 0.45}'
```

`ensemble`, `mediapipe`, and `u2net` need the weights from `../scripts/download_models.sh`. Those binaries stay out of git. `chroma` needs no weights.

3. Write the treated video to the `treated_clip` output.
4. Compare it with the sample in `PREVIEW.md`. Rebuild synthetic samples from `effects/` with `python examples/make_samples.py`.

Python API, with `effects/` on `PYTHONPATH`:

```python
import fx
fx.apply_effect('backdrop_words', "in.mp4", "out.mp4", palette="neutral-mono", params={'words': [{'text': 'FOCUS', 'at': 0.1}, {'text': 'REPEAT', 'at': 1.2, 'color': 'secondary'}], 'y': 0.45})
```

## Defaults

```json
{
  "words": null,
  "text": "BACKDROP",
  "font": "antonio",
  "color": "accent",
  "outline": "outline",
  "outline_px": 0,
  "y": 0.36,
  "width": 0.96,
  "max_h": 0.42,
  "punch": 0.3,
  "punch_from": 1.8,
  "drift": 0.06,
  "angle": 0.0,
  "shadow": 0.45,
  "opacity": 1.0,
  "shake": 6
}
```

## Checks

- The words pass behind the subject.
- Timed words change across the clip.
- The output duration matches the source.
