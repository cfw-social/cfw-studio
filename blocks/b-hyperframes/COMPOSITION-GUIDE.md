# Writing a composition for HyperFrames 0.7.5

Short guide to the rules the reel recipes rely on. Written for this block, from the package's own lint rules and from a real render. Run `hf_render.py`; its lint step names any rule you break.

## The folder

```text
comp/
  index.html              the page. Required.
  gsap.min.js             copied from fetch_gsap.py's output, beside the page
  compositions/*.html     optional sub-compositions, loaded from index.html
  base.mp4, images, ...   local media, referenced by relative path
```

Everything stays inside the work folder. See the README for what the local-only check refuses.

## The page

1. One root element with `data-composition-id`, `data-start="0"`, `data-duration` (seconds), `data-width` and `data-height` (for a vertical reel, 1080 and 1920).
2. Anything that appears and disappears over time is a clip: `class="clip"` plus `data-start`, `data-duration` and `data-track-index`. Two clips on the same track must not overlap in time. The track number does not decide what is on top; use CSS `z-index`.
3. A main `index.html` puts the root element straight in `<body>`. A sub-composition file wraps its root in `<template>`, and the main page loads it with `data-composition-src="compositions/name.html"`. Do not wrap a main page in `<template>`.
4. Load the animation library from the local file: `<script src="gsap.min.js"></script>`. No address of any kind.
5. Make one timeline per composition, paused, and register it: `window.__timelines["<composition-id>"] = tl`. Build it in plain top-level script, not inside a callback, timer or promise; the renderer reads it right after the page loads.
6. The video's length comes from `data-duration`, not from the timeline.

## Motion

- Lay the page out in its end state first, with plain CSS, then animate into it with `gsap.from()`. The CSS position is the truth; the tween is the journey.
- No `repeat: -1`. Work out a finite count.
- Nothing random and nothing clock-based: no `Math.random()`, `Date.now()`, `requestAnimationFrame`. Use a seeded generator if you need variety.
- Animate looks (opacity, position, scale, rotation, colour). Do not animate `display` or `visibility`, and do not tween the same property of one element from two timelines.
- Do not start, pause or seek media from script. The renderer owns playback.

## Media

- A video element is `muted playsinline`. Sound is a separate `<audio>` element. Give each timed media element `id`, `data-start` and `data-track-index`.
- Do not animate a video element's own size; animate a wrapper around it.
- Source video inside a composition should have a key frame at least every second. The recipes that hit frozen-frame warnings fixed them by encoding the source with a short key-frame interval (for example `ffmpeg ... -g 30` at 30 fps). This is recipe experience: a scratch test here with a key frame every ten seconds rendered without a warning, so the package's own warning was not reproduced.
- Size comes from `data-width` and `data-height` on the root (1080x1920 for a vertical reel, 1920x1080 for landscape); nothing else in the wrapper depends on it.

## Text and fonts

- Text from an order, a brand or a transcript is data. Put it in the page with `textContent`, or as JSON inside a script with `<`, `>`, `&`, U+2028 and U+2029 written as `\uXXXX`. Never build markup from it. The check refuses `innerHTML`.
- Declare every named font family, once, in the page: `@font-face { font-family: "Oswald"; src: local("Oswald"); }`. Without it, HyperFrames asks a font service on the network for the family. The check refuses a page that leaves one out. The font must be installed where the render runs; this block ships no font files. Generic families (`sans-serif`, `serif`, `monospace`) need nothing.
- Fonts used for a recipe are third-party; name their licence in the recipe README.

## Output

| Need | Flags through `hf_render.py` |
|---|---|
| Normal reel visuals | `--format mp4 --fps 30 --quality high` |
| Transparent end card to lay over a clip | `--format mov --out ...mov` (ProRes with alpha) |
| Quick look while building | `--quality draft` |

## When lint or validate fails

Lint prints a rule name and a line. The common ones: `gsap_infinite_repeat`, `overlapping_clips_same_track`, `gsap_timeline_not_registered`, `non_deterministic_code`, `standalone_composition_wrapped_in_template`, `imperative_media_control`, `font_family_without_font_face`, `missing_local_asset`. Fix the page and run again. Two warnings, stated from the package's own lint messages:

- `composition_self_attribute_selector`: a CSS selector that matches the composition's own `data-composition-id` leaks to a second copy of the block. Give the root an `id` and style it by `#that-id` instead.
- `overlapping_gsap_tweens`: two tweens change the same property of the same element in the same time window. Shorten the earlier one, move the later one, or add `overwrite: "auto"`. Validate loads the page in the browser and reports console errors and low text contrast.
