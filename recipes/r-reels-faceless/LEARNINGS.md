# Faceless reel: quality notes

Short rules that came out of earlier runs. They describe the method. They are not a promise that any host
or recipe version has been proven.

- One continuous voice bed, no cuts or retiming. Normalise the voice once to -14 LUFS and master the final
  mix once after the sound effects, then measure the delivered file.
- Write the scene copy before planning. One beat at a time. No blank graphics, no bare titles, no still
  image with a zoom. Every graphics beat has a readable illustrative hero and ambient motion for its whole
  span.
- The first frame of a card shows its headline and hero, moving in without an opacity fade (`card_fill.py`
  does this). Ghost glyphs are thematic numbers or letters, never placeholders. Use SVG or CSS icons.
- A brand's palette and fonts come from that brand's own data. An explicit call to action wins. With no
  handle, show no handle. Near-black canvases must still pass the brightness check.
- Local assets, GSAP and fonts only, and every named font declared with a local `@font-face`; the render
  wrapper refuses a page that is not local. Text goes into a page only through a filler. No raw input in a
  script or a shell.
- Render every composition with `b-hyperframes` (one worker, `--quiet`), and scan every frame of the bottom
  caption band.
- The caption band near y=1450 stays clear of cards that end near y=1330. Keep word timing, phrase breaks,
  emphasis spacing and Latin transliteration.
- The default grade is clean-bright. Warm-amber is a choice, because it can tint a light neutral brand.
  The footage is graded by ffmpeg and never goes through the renderer, so the captions keep their exact
  colours and the footage colour does not drift. Look at brand colours.
- Make the picture end at least as late as the audio. Otherwise the caption pass can run past the picture
  and leave black at the end. The outro is lit from its first frame.
- Put 0.4 seconds of the strongest checked frame first. Keep the total, including cover and outro, between
  30 and 90 seconds. Check every beat with motion, frame and vision evidence.
- Use argument lists and path joins, not shell strings or Unix-only commands.
- Choose the one installed local speech-to-text tool through `b-audio`, with an explicit model path. No
  silent download, no silent fallback, no made-up timestamps.
- The bot pins every b-roll window it wants by writing `broll` scenes. The planner never chooses clips from
  the transcript. The optional `overlay_beats` option is not supported and must fail before any paid call.
- Tests here use made-up media and JSON. They do not prove a run on Windows or Linux, and they do not prove
  a real paid narration or a real speech-to-text run.
