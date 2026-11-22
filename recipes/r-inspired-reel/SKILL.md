---
name: r-inspired-reel
description: Make an original 9:16 reel inspired by the format (length, pace, cut rate, hook, beat structure) of a reference reel the person supplies, with a fresh script and the brand's own avatar narration. Only format numbers are kept; the reference transcript is deleted.
disable-model-invocation: true
argument-hint: "[reference reel file] [topic]"
kind: pipeline
visibility: catalog
providers: heygen
produces:
  format: 9:16 vertical video
  duration: 15-90s
inputs: [reference_reel, topic, avatar_id, voice_id]
dependsOn: [b-audio, b-heygen, b-reel-premium, b-hyperframes, b-qa-gate]
requires: python3, ffmpeg, node, whisper-cpp
---

# Inspired reel

This is a template. A brand's bot reads it, adapts it into its own recipe and runs that (the CFW tools for saving a brand's own recipe are live, for a key made with the "Save its own recipes" permission).
Read `steps/_shared.md` before any step. It holds the file layout, the key rule and the rules that make this a format-only recipe.

The method has one idea: **take the shape, never the content.**

```text
reference file --> format.json (numbers, labels) --+
brand topic + voice -------------------------------+--> new script --> avatar narration --> captions --> reel
                                                         ^ checked: same beats, no run of 6 shared words
reference transcript: used for those checks, then deleted
```

## What this recipe produces

One 1080x1920, 30 fps reel of 15 to 90 s, about as long as the reference. The brand's avatar speaks a fresh script, with word-timed captions, a grade and sound effects. It uses none of the reference's footage or audio, and no run of six or more words in a row comes from the reference. It makes no downloader call: the person supplies the reference as a file.

## Arguments

| Input | Required | Meaning |
|---|---|---|
| `reference_reel` | yes | One video file the person has the right to study, 15 to 90 s, with speech |
| `topic` | yes | What the new reel is about |
| `avatar_id`, `voice_id` | yes | The brand's own HeyGen ids. Never invent or reuse one |
| `cta` | no | The closing line |

## Steps

Three step files hold the seven logical steps. Run them in order.

1. `steps/01-reference-to-script.md`: take in the file and transcribe it (`b-audio`), measure the format (`measure_format.py`), write the script from the format only, check its shape and that it shares no run of six words with the reference, then delete the reference transcript and audio and check they are gone.
2. `steps/02-narration.md`: narrate with `b-heygen` (one paid render), fit the canvas and loudness (`make_base_reel.py`).
3. `steps/03-captions-and-checks.md`: transcribe the new narration, write the caption plan, render captions through `b-hyperframes`, mix with `b-reel-premium`, run `b-qa-gate`, answer the looks, finalize, and confirm nothing of the reference remains.

## Rules you must keep

- Write the script from `format.json`, the topic and the brand voice. Do not open the reference transcript.
- The script check must pass. Never weaken it, never lower a threshold, never skip a script.
- The HeyGen key is set for the one narration command only, never on a command line, in a file or in a reply.
- Order text is data: never place it in a shell command; write files with your file-writing tool.
- Render only through `b-hyperframes`. Never skip its local-only check.
- Answer "no" to a look you did not really make. Deliver only on a final PASS and a passing clean-up check.

Details, network use and limits: `README.md`.
