# b-hyperframes

The one place that says how to install HyperFrames, how to write a composition for it, how to render safely, and how to fetch the animation library. Every reel recipe renders through this block and does not repeat any of it.

HyperFrames is a public npm package that turns an HTML page with a paused GSAP timeline into a video. This block pins it, wraps it, and puts a check in front of it.

```text
 recipe fills a page --> check_local.py --> lint --> validate --> render (1 worker) --> .mp4 / .mov
 (text is data,          refuses anything   \_______ hf_render.py runs all four, in this order _______/
  never markup)          that loads from
                         the network
```

## Interface

All paths are relative to the work folder, which is the current folder unless `--work` says otherwise. A path that leaves the work folder, or passes through a symbolic link, is a usage error (exit 2).

| Entry point | Arguments | Reads | Writes | Stdout | Exit codes |
|---|---|---|---|---|---|
| `scripts/hf_install.py` | `[--work DIR] [--cache DIR] [--skip-browser]` | this block's `runtime/package.json`, `runtime/package-lock.json`, `pins.json` | `WORK/hyperframes-runtime/` (packages and `.hf-trust.json`, the recorded checksums), `WORK/.hf-cache/` (npm cache, the pinned browser, temp files) | path of the runtime folder | 0 done, 1 install failed (also: a `.npmrc` exists in the runtime folder), 2 bad usage or a symbolic link in a folder it would write to, 3 node, npm, ffmpeg or ffprobe missing |
| `scripts/fetch_gsap.py` | `--outdir DIR [--work DIR] [--force]` | `pins.json`; the npm registry | `OUTDIR/gsap.min.js`, `OUTDIR/gsap.min.js.json` | path of `gsap.min.js` | 0 done, 1 verification or download failed, 2 bad usage, 3 pins file missing |
| `scripts/check_local.py` | `--comp DIR [--work DIR]` | every `.html .htm .css .js .mjs .cjs .svg .xml` file under `DIR`, and text files they reference | nothing | `LOCAL_ONLY: PASS (n files scanned)` or `LOCAL_ONLY: FAIL (n problems)`; problems on stderr as `file:line: reason` | 0 passed, 1 problems, 2 bad usage |
| `scripts/hf_render.py` | `--comp DIR --out FILE [--work DIR] [--fps 24\|25\|30\|50\|60] [--quality draft\|standard\|high] [--format mp4\|mov] [--cache DIR] [--timeout S] [--quiet] [--use-system-browser PATH]` | the composition folder; `WORK/hyperframes-runtime/`; the pinned browser | `FILE` (a new file, never inside the composition, runtime or cache folders), `WORK/.hf-cache/` | path of `FILE` | 0 rendered, 1 refused or failed, 2 bad usage or a symbolic link, 3 renderer or browser not installed, not the pinned version, or changed since install |

`fetch_gsap.py` requires `tarball_integrity` and `file_sha256` in any pins file given to `--pins`; a missing key is exit 2. Files are written through an exclusive temporary file and `os.replace`. Every folder a script creates, deletes or runs from must be inside the work folder with no symbolic link at any component below it, or the script exits 2.

Defaults: `--fps 30`, `--quality high`, `--format mp4`, `--timeout 1800`. `--out` must end in `.mp4` for `mp4` and `.mov` for `mov`. `--quiet` prints only the stage lines (`stage lint: ok (0.3s)`), warnings, errors and the final path; the full output, including one line per frame, goes to `WORK/.hf-cache/logs/<output name>.log`. Bots should always use `--quiet`. `--use-system-browser PATH` runs an installed Chrome instead of the pinned one. Opt-in only: that browser makes its own background connections (see Network use). `mov` gives a transparent video (ProRes with alpha, observed), for end cards laid over a clip.

`fetch_gsap.py` also takes `--registry` and `--pins`. They exist for the tests. `--registry` accepts only `https://registry.npmjs.org` or a `http://127.0.0.1` / `localhost` address.

Where things land:

```text
WORK/hyperframes-runtime/          the pinned package and its dependencies (node_modules inside)
WORK/.hf-cache/                    HOME for the renderer: npm cache, temp files, font cache, browser cache
WORK/vendor/gsap.min.js            what fetch_gsap.py writes when called with --outdir vendor
WORK/vendor/gsap.min.js.json       its version, source URL, checksums, licence line
```

Run order for a recipe:

```bash
BLOCKS_DIR="$RECIPE_DIR/../../blocks"                      # derived, never read from the order
python3 "$BLOCKS_DIR/b-hyperframes/scripts/hf_install.py"                  # once per work folder
python3 "$BLOCKS_DIR/b-hyperframes/scripts/fetch_gsap.py" --outdir vendor  # once per work folder
cp vendor/gsap.min.js comp/gsap.min.js                     # beside each composition's index.html
python3 "$BLOCKS_DIR/b-hyperframes/scripts/hf_render.py" --comp comp --out visuals.mp4 --quiet
```

`hf_render.py` runs the local-only check itself, every time, and renders nothing if it fails. There is no switch to skip it and no stamp that can go stale. Run `check_local.py` on its own only to see problems early.

## Tools and pinned versions

| Tool | Version | Pinned by |
|---|---|---|
| `hyperframes` (npm) | exactly 0.7.5 | `runtime/package.json`, `runtime/package-lock.json` (every package has an integrity hash), `pins.json` |
| `gsap` (npm) | exactly 3.14.2 | `pins.json`: tarball integrity and the SHA-256 of `dist/gsap.min.js` |
| Chrome headless shell | exactly 131.0.6778.85 (the build HyperFrames 0.7.5 expects) | `pins.json`; downloaded by `hf_install.py`; its SHA-256 is recorded at install and re-checked at every render |
| Node.js | 22 or newer (HyperFrames requires it). Observed: 25.9.0 | not pinned |
| ffmpeg, ffprobe | 6 or newer, on the path. Observed: 8.1 | not pinned |
| Python | 3.10 or newer; run with 3.15 only, standard library only | not pinned |

GSAP is third-party code under GreenSock's standard licence (gsap.com/standard-license). It is not included here and is never copied into this repository. HyperFrames is a third-party npm package and is not included either. Its licence: the `package.json` of the installed `hyperframes` 0.7.5 package has no `license` field, so none is stated there. Read the package's own licence terms before you use it.

`gsap.min.js` for 3.14.2: SHA-256 `c174bfce53a729418d57a8ad8625e7247c793a22fef8e2851e3cfa3de9cd8280`. It was observed twice, from the registry tarball and from a separate local copy of the same version, and the two agreed. Both runs were on one machine.

## Network use

Setup, every host this block causes a download from:

| When | Host | What | Observed size |
|---|---|---|---|
| `hf_install.py` | `registry.npmjs.org` | the package and its dependencies, from the lockfile. `npm ci --ignore-scripts`: no install script runs | 172 requests, about 150 MB in npm's cache, 171 packages and 450 MB on disk (macOS, Apple silicon). The lockfile also lists platform-specific optional packages for other systems that were not installed here |
| `hf_install.py` (default; skipped with `--skip-browser`) | `storage.googleapis.com` (`chrome-for-testing-public`) | the pinned Chrome headless shell 131.0.6778.85, by the same library call HyperFrames uses | 88,077,521 byte zip, about 172 MB unpacked (macOS, Apple silicon). Lands in `WORK/.hf-cache/.cache/hyperframes/chrome` |
| `fetch_gsap.py` | `registry.npmjs.org` | version record, then the tarball. No redirect is followed | 2,137 bytes and 1,696,880 bytes; the library file inside is 72,779 bytes |

Registry: the npm registry is `https://registry.npmjs.org/`, given on the command line, in the environment, and in the lockfile (every entry resolves there). npm's user and global config files are pointed at empty files the script creates, and the script refuses to install when the runtime folder holds a `.npmrc`. A file in the work folder cannot redirect the install. Download sizes for Linux and Windows: not determined.

Run time, `hf_render.py`, default (pinned headless browser):

- Observed: three renders and their lint and validate steps, with a sampler that listed every network socket of every process the wrapper started, about ten times a second. No connection to any address was seen. The same sampler, run on the same page with `--use-system-browser` pointing at the installed Google Chrome, saw 18 connections by Chrome processes to Google-owned and other addresses on ports 443, 80 and 5228. So the pinned browser makes none that the sampler could see, and the installed Chrome makes its own background connections, before and apart from the page.
- Not observed: DNS lookups as such; a connection shorter than the sampling interval; Linux and Windows.
- The log line `[non-blocking] Failed to load resource ... 404 (Not Found)` is the browser asking the renderer's own localhost server for `/favicon.ico`. Traced with a scratch render and a request log on that server. Seen with an installed Chrome; not seen with the pinned headless browser.
- The package gives no way to add browser flags, so background networking cannot be switched off from here. The package already passes `--disable-component-update`, `--disable-sync`, `--no-pings` and `--disable-domain-reliability`; it does not pass `--disable-background-networking`. That is why the default is the pinned headless browser and not whatever Chrome is installed.
- The page's own requests are blocked only by `check_local.py`. Nothing else blocks them: not a sandbox, not a firewall.
- If a page that passes the check still asks for something, the renderer would let it through. Earlier tests, with a logging proxy on the Node side, showed that the renderer contacts `fonts.googleapis.com` for any font family without `@font-face`, and downloads remote images and stylesheets named in the page. The check refuses those pages.
- Telemetry, the update check and background self-update are switched off with `HYPERFRAMES_NO_TELEMETRY`, `DO_NOT_TRACK`, `HYPERFRAMES_NO_UPDATE_CHECK`, `HYPERFRAMES_NO_AUTO_INSTALL`, read in the package's code.

HyperFrames has other commands that use the network or download models (`transcribe`, `tts`, `remove-background`, `publish`, `cloud`, `skills`, `auth`). This block never calls them. Speech to text belongs to `b-audio`.

## The renderer runs with the browser sandbox and site isolation off

The renderer has to run the page's own script, because the animation is a script, so scripts cannot be turned off. HyperFrames 0.7.5 starts its browser with the browser's own sandbox switched off (`--no-sandbox`) and with site isolation switched off (`--disable-features=...IsolateOrigins,site-per-process`). These flags are fixed in the package; this block cannot change them. A page script therefore runs in a browser without those two protections, as the same user, on the machine that renders.

What this block does:

- `check_local.py` refuses a page before any browser starts. It looks at the text of the page twice, the second time after undoing HTML entities and CSS escapes. It refuses: network addresses in the forms it knows (`http`, `https`, `ws`, `wss`, `ftp`), protocol-relative addresses, `data:` addresses that are not a small image or font, `javascript:` addresses, `image-set(`, CSS escapes inside `url()`, `@import` and `src`, embedding elements (`iframe`, `object`, `embed`, `base`), `srcdoc`, `meta http-equiv`, connection hints, every address-carrying attribute it knows (`src`, `href`, `srcset`, `imagesrcset`, `poster`, `data`, `action`, ...), a named font with no local `@font-face`, any reference that is absolute, missing, leaves the work folder or crosses a symbolic link, and these script features: `fetch`, `XMLHttpRequest`, `WebSocket`, `EventSource`, `sendBeacon`, `import`, `importScripts`, workers, `eval`, the `Function` constructor, computed access on the global object, markup built from strings (`innerHTML` and relatives; `innerHTML = ""` is allowed), link attributes set at run time, `new Image`, creating loadable elements, navigation. The pinned GSAP file is skipped, and only when its SHA-256 equals the pin. Any other script is scanned.
- `hf_render.py` runs that check, then lint, validate and render with one worker. The child process gets a short environment: `PATH`, locale, a few Windows system variables, and the variables this block sets. It gets no keys, tokens, proxy settings or browser-path overrides from the caller. `HOME`, the temp folder and the font cache point inside the work folder. The pinned browser comes from `WORK/.hf-cache`.
- Before rendering it re-checks the SHA-256 of the package's entry files (`package.json` and the scripts directly in `dist/`) and of the pinned browser against the record made at install. A change is exit 3. This catches a change after install. It does not stop someone who can write the work folder from rewriting the record too.

What remains (known limits):

- The check is a text scan, not a sandbox. It stops mistakes, and data-only injection of the forms it knows. A hand-written hostile page with script can get past it. Three such pages are kept in `test/test_check_local.py` as KNOWN LIMITS, and they pass the check: `var f=self.fetch; f('ht'+'tp://...')` (an aliased call with a split string), `im['sr'+'c']=...` (a computed property name), and `setAttribute(a, ...)` with the attribute name in a variable.
- The check does not see inside binary media (video, images, audio, fonts).
- Whether a page script can reach files or services on the render machine through the browser: not determined.
- Requests made by the browser were sampled at the socket level only (see Network use).

So: render untrusted pages only on a machine or in a container with no network. If the text in a page comes from anyone you do not trust (order text, brand text, a transcript), put it in as data, never markup, and still render with no network. The check is the second line of defence, not the first.

## Recipes that use it

`r-reels-faceless`, `r-reels-pip`, `r-reels-spotlight` and the two HeyGen variants (`r-reels-pip-heygen`, `r-reels-spotlight-heygen`) install HyperFrames, fetch the animation library and render through this block (`hf_install.py`, `fetch_gsap.py`, `hf_render.py`). The pip recipes also use `--format mov` for the end card. `r-inspired-reel` renders through it as well, and `b-reel-premium` renders its caption pages with `hf_render.py --format mov` (recipe templates live under `recipes/` and are added separately).

## What a recipe must do to pass the check

Found by running the check on the ten page templates in the three reel editions and the typing and caption blocks. Eight failed on undeclared fonts (point 1), two on `innerHTML` (point 2), and two on unfilled placeholders (point 3; one of them also names a sub-composition file that was not there).

1. Declare every named font family. HyperFrames asks a font service on the network for any family that has no `@font-face`, even one installed on the machine. Add, for each family: `@font-face { font-family: "Oswald"; src: local("Oswald"); }`. The font must be installed on the machine. This block ships no font files.
2. Put text into the page with `textContent` or DOM calls, not `innerHTML`.
3. Fill every `{{PLACEHOLDER}}` before rendering. An unfilled one in a file reference fails the check.
4. Keep all files inside the work folder and refer to them by relative paths.

See [COMPOSITION-GUIDE.md](COMPOSITION-GUIDE.md) for the page rules.

## Size

Nothing in the wrapper assumes a size or aspect ratio: the size comes from `data-width` and `data-height` on the composition root, and the wrapper only passes fps, quality and format. The minimal example rendered at 1920x1080 through the wrapper gave an H.264 file of 1920x1080, 30 frames.

## Proof

A short summary of the limits below. Where this README does not say, it reads "not recorded".

| What | Status | Detail |
|---|---|---|
| Automated tests | 56 tests, as of 2026-11-22 | `cd blocks/b-hyperframes && python3 -m unittest discover -s test -t test`. No real render needed. |
| Run on which operating systems | macOS (Apple silicon) only; Linux and Windows not run | Python 3.15.2, Node 25.9.0, ffmpeg 8.1 on one Apple-silicon Mac. |
| Run with a real provider account | no provider | No account. Setup downloads from the npm registry and a browser host. |
| Used in a real start-to-finish recipe run | yes, in recipe template runs with stand-in media on macOS, 2026-11-22 | Fresh install with the pinned headless browser. |

## Tests

No paid account, no private file, no internet and no real render needed:

```bash
cd blocks/b-hyperframes
python3 -m unittest discover -s test -t test -v
```

The tests cover: the check (one case per rule, the disguised-address pages, the three known limits), the fetch verification against a local stand-in registry (including a pins file with a missing key), the wrappers against stand-in `node` and `npm` programs (symbolic-link folders, a changed entry file, a planted `.npmrc`, output equal to an input), and the shipped lockfile and pins.

## Sample

`examples/minimal/index.html` is a one-second composition. Observed on macOS, Apple silicon, Node 25.9.0, ffmpeg 8.1:

```bash
mkdir work && cd work
python3 ../blocks/b-hyperframes/scripts/hf_install.py
python3 ../blocks/b-hyperframes/scripts/fetch_gsap.py --outdir vendor
mkdir comp && cp ../blocks/b-hyperframes/examples/minimal/index.html comp/ && cp vendor/gsap.min.js comp/
python3 ../blocks/b-hyperframes/scripts/hf_render.py --comp comp --out out/minimal.mp4 --quality draft --quiet
```

Result of the run: an H.264 file, 360 by 640, 30 frames, 1.0 s, about 8 KB. A `--format mov` run gave a ProRes file with an alpha channel. The video itself is not stored in this repository.

## Limits and what is not proven

- Proven on one machine only: macOS, Apple silicon. Linux and native Windows: not proven. The code uses `HOME` and `USERPROFILE` and `shutil.which`, which should work on all three, but no run is recorded.
- The install on Linux or Windows would fetch different optional packages. Not observed.
- One tiny composition was rendered through the wrapper. No reel recipe has been run through this block.
- `--format mov` was run once. Other formats of HyperFrames (webm, gif, png sequence) are not exposed here.
- Rendering uses one worker, so it is slower than the package's default.
- `hyperframes validate` runs the page in a browser. It runs only after the check has passed.
- The browser cache and the font cache live in `WORK/.hf-cache`. Each new work folder downloads the pinned browser again (about 88 MB).
- The npm lockfile was produced with npm 11.12.1.
- A page that uses a feature the check refuses must be changed; there is no override.
- The downloaded headless browser zip has no checksum pinned in this repository. I found no published checksum for it in the package or at the download source, so none is verified. It is trusted over https on the first install; its SHA-256 is recorded then, and every render re-checks it against that first recording.
- `--use-system-browser PATH` runs whatever program the caller names. It accepts any existing file.
