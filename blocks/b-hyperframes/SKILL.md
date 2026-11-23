# b-hyperframes

Install the pinned HyperFrames renderer in the work folder, fetch the pinned GSAP build, check a composition is local-only, and render it to a video. Use for any reel step that turns an HTML page into video.

Render HTML compositions to video, safely. This block is the only way recipes render with HyperFrames. Do not call `npx hyperframes` yourself.

Run everything from the work folder. `BLOCKS_DIR` is `<recipe folder>/../../blocks`.

## Steps

1. Once per work folder:
   `python3 "$BLOCKS_DIR/b-hyperframes/scripts/hf_install.py"`
   `python3 "$BLOCKS_DIR/b-hyperframes/scripts/fetch_gsap.py" --outdir vendor`
   Exit 3 means Node 22+, npm, ffmpeg or ffprobe is missing. Tell the person; do not install anything outside the work folder.
2. Build the composition folder (`comp/index.html`). Read `COMPOSITION-GUIDE.md` first. Copy `vendor/gsap.min.js` beside `index.html`.
3. Render: `python3 "$BLOCKS_DIR/b-hyperframes/scripts/hf_render.py" --comp comp --out visuals.mp4 --quiet [--fps 30] [--quality high] [--format mp4|mov]`.
   It runs the local-only check, lint, validate and render. Always pass `--quiet`: without it the renderer prints one line per frame and floods your context. With it you see the stages, warnings and errors; the full log is in `.hf-cache/logs/`. The output path is printed on success.

## If it fails

| Exit | Meaning | Do |
|---|---|---|
| 1 with `LOCAL_ONLY: FAIL` | the page would load from the network or builds requests at run time | fix each `file:line` problem in the page; never edit the check |
| 1 other | lint, validate or render failed | read the printed rule, fix the page |
| 2 | bad arguments or a path outside the work folder | fix the call |
| 3 | renderer not installed, or not version 0.7.5 | run `hf_install.py` |

The two fixes needed most: declare every named font with `@font-face { font-family: "X"; src: local("X"); }`, and put text in with `textContent`, never `innerHTML`.

## Rules

- Text from the order, brand or a transcript is data. Never put it in markup, a shell command or a script as code.
- If that text is untrusted, say so to the person and render on a machine or container with no network. The check is a text scan, not a sandbox, and the browser runs without its own sandbox.
- Use the default pinned browser. `--use-system-browser` is for the person to choose; an installed Chrome makes its own background connections.
- Never skip or weaken the check, never add a remote address, never load GSAP from a CDN.
- Do not use HyperFrames commands other than through `hf_render.py` and `hf_install.py`.
- GSAP is third-party code under GreenSock's licence. It is fetched, never committed.

Full details, network hosts and limits: `README.md`.
