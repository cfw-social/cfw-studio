# e-chat-window

The clip plays inside a generic chat window with an avatar, a title, timed bubbles, and typing dots.

This folder is the CFW Studio catalog entry (`kind: effect`, variation `default`). The implementation is the shared `fx` package, effect `chat_window`, in [`../fx/effects/chat_window.py`](../fx/effects/chat_window.py). Run commands from `effects/` so `python -m fx` imports that package.

The `fx` package and this catalog entry are MIT licensed. See [the effects license note](../README.md#license).

## When to use

Use to stage the clip as a clip sent in a chat. The window is a generic drawing.

## Steps

1. Read the inputs in `effect.yaml`. The required input is one video, `clip`. Optional `params` is a JSON object of the settings below. Optional `palette` is a preset name (`neutral-mono`, `vasanth-personal`), a path to palette JSON, or inline palette JSON.
2. From `effects/`, apply the effect with the shared package. `--start` and `--end` are seconds; frames outside that window pass through, and audio is kept.

```bash
python -m fx apply \
  --effect chat_window \
  --in "$CLIP" \
  --out "$OUT" \
  --palette neutral-mono \
  --size 1080x1920 \
  --params '{"title": "Group chat", "messages": [{"text": "check this out", "at": 0.5, "mine": true}, {"text": "nice!", "at": 1.4}]}'
```

From the repository root, prefix the same command with `PYTHONPATH=effects`.

The procedural subject, with no downloaded models and no real footage, is `examples/assets/synthetic_mannequin.mp4` (path relative to `effects/`). The chroma key matches that clip:

```bash
python -m fx apply \
  --effect chat_window \
  --in examples/assets/synthetic_mannequin.mp4 \
  --out /tmp/chat_window.mp4 \
  --palette neutral-mono \
  --size 360x640 \
  --backend chroma \
  --seg '{"chroma_hue": 290, "chroma_tol": 22, "chroma_subject": "key"}' \
  --params '{"title": "Group chat", "messages": [{"text": "check this out", "at": 0.5, "mine": true}, {"text": "nice!", "at": 1.4}]}'
```

`ensemble`, `mediapipe`, and `u2net` need the weights from `../scripts/download_models.sh`. Those binaries stay out of git. `chroma` needs no weights.

3. Write the treated video to the `treated_clip` output.
4. Compare it with the sample in `PREVIEW.md`. Rebuild synthetic samples from `effects/` with `python examples/make_samples.py`.

Python API, with `effects/` on `PYTHONPATH`:

```python
import fx
fx.apply_effect('chat_window', "in.mp4", "out.mp4", palette="neutral-mono", params={'title': 'Group chat', 'messages': [{'text': 'check this out', 'at': 0.5, 'mine': True}, {'text': 'nice!', 'at': 1.4}]})
```

## Defaults

```json
{
  "title": "Chat",
  "messages": [
    {
      "text": "look at this!",
      "at": 0.4,
      "mine": true
    },
    {
      "text": "love it",
      "at": 1.6,
      "mine": false
    }
  ],
  "bg": "bg",
  "width": 0.86,
  "height": 0.78,
  "video_h": 0.5,
  "intro": 0.45,
  "typing": true
}
```

## Checks

- The clip sits inside the drawn window.
- Bubbles appear on the times in params.
- The output duration matches the source.
