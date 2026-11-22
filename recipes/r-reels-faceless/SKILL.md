---
name: r-reels-faceless
description: Make a 9:16 faceless reel from a script, using a brand narration voice, animated illustrative graphics, optional supplied b-roll, kinetic captions, sound effects and a branded closing card.
when-to-use: Use for a narrated short with full-frame motion graphics and optional supplied b-roll. No talking head and no avatar.
version: 2026.11.7
kind: pipeline
visibility: catalog
providers: elevenlabs
produces:
  dish: Faceless Reel
  format: 9:16 vertical video
  duration: 30-90s
inputs: [script]
dependsOn: [b-audio, b-broll-sync, b-typing-ui, b-reel-premium, b-hyperframes, b-qa-gate]
---

# Faceless reel

This is a template. A brand's bot reads it, adapts it into its own recipe and runs that. The CFW Social
tools for saving a brand's own recipes are planned, not built. Today you can follow the steps by hand or
with your own agent. Read `README.md` for the tools, hosts and limits. Then read `steps/_shared.md` and the
step file for the step you are on.

```text
script -> brand voice bed -> local word timings -> scene and beat plan
                                                         |
                      animated graphics + optional b-roll <-+
                                   |
                         captions / sound effects / grade
                                   |
                      cover + checks + looks -> final video
```

The steps run in order:

1. `steps/01-voice-over.md`: one continuous narration bed (ElevenLabs).
2. `steps/02-transcribe.md`: word timings from a local speech-to-text tool (`b-audio`).
3. `steps/03-plan-beats.md`: scenes, copy and optional b-roll windows (`b-broll-sync`).
4. `steps/04-render-graphics.md`: one animated page per graphics beat, rendered with `b-hyperframes`
   (`card_fill.py`, `b-typing-ui`).
5. `steps/05-assemble.md`: voice, outro, captions, sound effects, grade, mix (`b-reel-premium`).
6. `steps/06-final-checks.md`: cover, the acceptance gate (`b-qa-gate`), per-platform captions.

The voice bed is one continuous narration. Every graphics beat has an illustrative hero that shows the
point, a readable headline, and ambient motion for its whole span. A still image with a zoom is not a
substitute. B-roll is optional; with none, every beat is animated graphics, with the same checks. The last
beat is a call-to-action card and a lit brand outro closes the reel. A 0.4 second freeze of the best frame
starts the video. Output: 1080x1920, 30 fps, H.264 yuv420p with AAC 48 kHz stereo, 30 to 90 seconds in all.

A file, a stamp or a PASS label proves nothing by itself. Run the checks and keep the measurements. The
recipe never approves, schedules or publishes a post. Checking these files makes no paid call and no upload.

Blocks used (paths from this folder): `../../blocks/b-audio/`, `../../blocks/b-broll-sync/`,
`../../blocks/b-typing-ui/`, `../../blocks/b-reel-premium/` (also holds the eight sound effects),
`../../blocks/b-hyperframes/` (install, animation library, local-only check, the one renderer) and
`../../blocks/b-qa-gate/`. The renderer version is pinned by `b-hyperframes`. Do not upgrade it without a
separately checked recipe version.

Quality rules and known gaps are in `LEARNINGS.md`.
