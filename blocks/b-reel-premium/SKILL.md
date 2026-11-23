# b-reel-premium

Kinetic captions, colour grade and sound effects for a finished 9:16 reel, from one checked plan file.

Use after a reel is fully assembled. You write one plan file, check it, build a caption page, render it
with `b-hyperframes`, then mix. Work folder = current folder. Full details and the plan format: `README.md`.

1. Write `work/premium/plan.json` yourself from the reel's word transcript. No other model, no nested agent.
   Fields: `grade` (`warm-amber`, `clean-bright`, `off`), `brand.accent` and `brand.fg` (six hex digits),
   `caption_groups` (2 to 4 words each, up to 6 to keep a phrase whole, in time order, words as spoken, Latin
   script only, at most one `em` word per group, `style` cycling 0/1/2 so neighbours differ), `sfx` (4 to 10
   cues, none in the first second, names only from `whoosh-deep whoosh-air impact-sub impact-punch riser click pop swipe`,
   `gain` up to 0.6), optional `music` (a file inside `inputs/`).
2. Once per work folder: `python3 HF/scripts/hf_install.py`, then `python3 HF/scripts/fetch_gsap.py --outdir vendor` (writes `vendor/gsap.min.js`).
3. `python3 BLOCK/scripts/check_plan.py --plan work/premium/plan.json --reel REEL`. Fix every listed problem. Do not go on until it exits 0.
4. `python3 BLOCK/scripts/build_comp.py --plan PLAN --reel REEL --cap-top N --outdir work/premium/comp` (`--gsap` defaults to `vendor/gsap.min.js`).
   A brand font goes in as `brand.font_file` (inside `inputs/`); with none, captions use the generic sans-serif.
5. `python3 HF/scripts/hf_render.py --comp work/premium/comp --out work/premium/captions.mov --format mov --quiet` (a transparent video). It runs the local-only check first. Never render another way.
6. `python3 BLOCK/scripts/mux.py --reel REEL --captions-mov work/premium/captions.mov --plan PLAN --out work/premium/polished.mp4`. It grades the footage, then lays the captions on top, so they keep their exact colours.
7. `python3 BLOCK/scripts/qa.py --reel-in REEL --reel-out work/premium/polished.mp4 --frames-dir work/premium/qa --grade GRADE_FROM_PLAN`,
   then look at the four frames: captions legible and clear of faces and cards, accent on emphasis words, grade subtle.

Text limits: caption words must not hold `scheme://` addresses, `//host`, `javascript:`/`data:` addresses, `url(` or `@import`; write `example.com`, not `https://example.com`. Quotes, `<>`, `&`, emoji, `a/b`, `1:2`, `50%` and `me@example.com` are fine.

Rules: captions off means skip steps 4 and 5 and pass `--no-captions` to `mux.py`. A reel with an end card or silent tail needs `--cover-tolerance` at least as long as the tail (check_plan and build_comp). Pick `--cap-top` from the README table (about 1180 full-frame, 980 to 1020 with a card below). Never fall back to another grade or
another sound; fix the plan. Never paste caption text into a shell command or a page yourself. Never touch the reel's
loudness. `BLOCK` is `../../blocks/b-reel-premium` and `HF` is `../../blocks/b-hyperframes`, from a recipe folder.
