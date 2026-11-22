# b-reel-premium

The polish pass for a finished 9:16 reel: word-timed kinetic captions, a light colour grade, and
sound effects (and optional music) mixed under the reel's own audio. Three reel recipes share it.

```text
plan.json --check_plan.py--> build_comp.py --> hf_render.py --format mov --> captions.mov (transparent)
                                                                                  |
reel.mp4 --(grade)---------------------------------------------> mux.py <---------'
                                                                    |
                                                                    '--> polished.mp4 --> qa.py --> frames + .gate/premium.json
```

The footage is graded by ffmpeg and never goes through the renderer. The renderer draws only the captions,
on a transparent background. They are laid over the graded footage afterwards, so the footage is graded and
the captions keep their exact brand colours.

The bot that runs the recipe writes `plan.json` itself from the reel's word transcript. Word timings from `b-audio` (`{text, start, end}`) map to the caption plan's words as `w` = `text`, `s` = `start`, `e` = `end`. This block
only checks the plan and carries it out. It never asks a model for anything and starts no agent.

## Order a reel follows

All paths are inside the work folder. `BH` is `../../blocks/b-hyperframes`, `BP` is `../../blocks/b-reel-premium`.

```text
1  python3 BH/scripts/hf_install.py                       once per work folder (installs inside it)
2  python3 BH/scripts/fetch_gsap.py --outdir vendor       writes vendor/gsap.min.js
3  python3 BP/scripts/check_plan.py --plan premium/plan.json --reel reel.mp4
4  python3 BP/scripts/build_comp.py --plan premium/plan.json --reel reel.mp4 --cap-top 1180 --outdir premium/comp
5  python3 BH/scripts/hf_render.py --comp premium/comp --out premium/captions.mov --format mov --quiet     (runs check_local.py first)
6  python3 BP/scripts/mux.py --reel reel.mp4 --captions-mov premium/captions.mov --plan premium/plan.json --out premium/polished.mp4
7  python3 BP/scripts/qa.py --reel-in reel.mp4 --reel-out premium/polished.mp4 --frames-dir premium/qa --grade GRADE_FROM_PLAN
```

Never render the composition any way except `hf_render.py`, and always with `--format mov` (a transparent video).
With captions off, skip steps 4 and 5 and pass `--no-captions` to `mux.py` instead of `--captions-mov`.

## Entry points

Run each from the order's work folder (or pass `--workdir`). Every path argument must resolve inside the
work folder; anything else is refused. Every script is run as `python3 <path> <arguments>`. All write
only inside the work folder.

| Script | Arguments | Reads | Writes |
|---|---|---|---|
| `scripts/check_plan.py` | `--plan FILE` and one of `--duration SECONDS` or `--reel FILE`; optional `--captions on\|off`, `--sfx on\|off`, `--cover-tolerance S` (default 3.0: see below), `--any-script`, `--workdir DIR` | the plan; the reel's length through `ffprobe` | nothing. One line on stdout, or a list of problems on stderr |
| `scripts/build_comp.py` | `--plan FILE --reel FILE --cap-top N --outdir DIR`; optional `--gsap FILE` (default `vendor/gsap.min.js`, where `fetch_gsap.py --outdir vendor` puts it), `--duration S`, `--cover-tolerance S`, `--any-script`, `--workdir DIR` | the plan, the reel, the animation library file, an optional font file | in `--outdir`: `index.html`, `compositions/caption-overlay.html`, `gsap.min.js` (a copy; the library and font are also copied into `compositions/` because the caption page links to them from there), and `fonts/` when a font file is used. The reel is read for its length only; it is not copied. |
| `scripts/mux.py` | `--reel FILE --plan FILE --out FILE.mp4` and exactly one of `--captions-mov FILE` (the transparent caption render, same picture size as the reel, with an alpha channel) or `--no-captions`; optional `--sfx on\|off`, `--workdir DIR`, `--print-command` | the reel, the caption render, the plan, the sound files in this block, an optional music file | `--out` |
| `scripts/qa.py` | `--reel-in FILE --reel-out FILE --frames-dir DIR`; `--grade warm-amber\|clean-bright\|off` (required: the plan's grade; exit 2 without it); optional `--captions on\|off`, `--sfx on\|off`, `--max-shift N` (default 1.5), `--workdir DIR` | both reels | four PNG frames in `--frames-dir`; `.gate/premium.json` beside `--reel-out` |

`--cover-tolerance`: the check fails when the last caption ends more than this many seconds before the end of
the reel (default 3.0). A reel with an end card or a silent tail after the speech ends its captions early on
purpose, so such a recipe must pass `--cover-tolerance` at least as long as that tail, to both `check_plan.py`
and `build_comp.py`.

`--cap-top` is the top edge of the caption band in pixels, 0 to 1920. The band is 260 px tall, so it covers
`--cap-top` to `--cap-top + 260`. Starting points (check a rendered frame; these are not computed):

| Layout | `--cap-top` | Why |
|---|---|---|
| Full-frame speaker or footage, nothing in the lower half | 1180 | The band sits in the lower middle, clear of a face in the upper half |
| Picture-in-picture, a card in the lower half | 980 to 1020 | The band sits above the card's top edge. One recipe used 980 and it sat clear |
| Motion-graphics layout whose cards fill the centre down to about y=1330 | 1450 | Below the cards; the band ends at 1710, above the platform's bottom interface |
| Layout with an end card | as for the main layout | The captions stop before the end card; pass `--cover-tolerance` |

Rule of thumb: `--cap-top` = (top edge of the card or other graphic below the speech) minus 300 px, so the band
ends about 40 px above it. Keep `--cap-top` + 260 at or below about 1700 so the lowest line is not under the
platform's own buttons, and keep the band below any face.

`--print-command` on `mux.py` runs every check, prints the ffmpeg argument list as JSON, and runs nothing.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Done. |
| 1 | The plan or an input has problems, or ffmpeg failed. Every problem is listed on stderr, one per line. Nothing was written (`qa.py`: no stamp). |
| 2 | Bad arguments, or the plan file cannot be read as JSON. |
| 3 | `ffmpeg` or `ffprobe` is not installed. |

### The plan file

One JSON object. Colours are six hex digits, with or without one leading `#`.

```json
{
  "grade": "clean-bright",
  "brand": { "accent": "#F97316", "fg": "#F1F5F9", "font_file": "inputs/brand-font.ttf" },
  "caption_groups": [
    { "start": 0.0, "end": 1.0, "style": 0,
      "words": [ { "w": "HELLO", "s": 0.1, "e": 0.4, "em": false },
                 { "w": "THERE", "s": 0.5, "e": 0.9, "em": true } ] }
  ],
  "sfx": [ { "t": 0.5, "name": "pop", "gain": 0.4 } ],
  "music": { "file": "inputs/bed.mp3", "gain": 0.15 }
}
```

| Field | Rule |
|---|---|
| `grade` | Required. `warm-amber`, `clean-bright` or `off`. Anything else is an error; there is no default. |
| `brand.accent`, `brand.fg` | Required for captions. Six hex digits. |
| `brand.font_file` | Optional. A font file inside `<work folder>/inputs/`: `.ttf .otf .woff .woff2`, correct file header, at most 3 MB. See Fonts. |
| `caption_groups` | Required unless `--captions off`. Up to 400 groups, in time order, not overlapping. The last one must end within `--cover-tolerance` seconds of the end of the reel. |
| group `start`, `end` | Numbers, `0 <= start < end`, not after the end of the reel plus the tolerance. |
| group `style` | 0, 1 or 2. The entrance animation. |
| group `words` | 1 to 8 words, in time order. |
| word `w` | Plain text, 1 to 40 characters, no control characters. Latin script only unless `--any-script` (the caption font has no other scripts). Any other character is allowed; it is escaped, see Safety. |
| word `s`, `e` | Numbers, `s <= e`, `s` inside its group (0.05 s slack). |
| word `em` | `true` or `false`. At most one `true` per group. It pops in the accent colour. |
| `sfx` | Optional list, up to 12 cues, in time order. |
| cue `name` | One of the eight below. Nothing else is accepted. |
| cue `t` | Seconds, from 0 to the end of the reel. |
| cue `gain` | 0 to 0.6, default 0.5. Out of range is an error, not clamped. |
| `music.file` | Optional. A path inside `<work folder>/inputs/` to an `.mp3 .wav .m4a .aac .flac .ogg` file. Anywhere else is refused, including links that lead out. `mux.py` also probes it with ffprobe: it must really be a plain audio file (no video stream) in one of these formats: wav, mp3, m4a/aac, flac, ogg. A cover picture inside an mp3 is fine. Anything else is refused. |
| `music.gain` | 0 to 0.3, default 0.15. |

The eight sound effects: `whoosh-deep`, `whoosh-air`, `impact-sub`, `impact-punch`, `riser`, `click`,
`pop`, `swipe`. They live in `assets/sfx/` and nowhere else in this repository. They are supplied by the
owner of this repository and covered by the repository licence. `assets/sfx/SHA256SUMS` lists their hashes;
`mux.py` checks each file against it before use.

Captions only: use `"sfx": []` and `"grade": "off"`; `mux.py` still lays the captions over the reel.
No captions: run `check_plan.py --captions off`, skip `build_comp.py` and the render, and pass `--no-captions` to `mux.py`.

## What the three steps do

- **Captions.** `build_comp.py` fills two page templates in `templates/`. The result is a small
  HyperFrames composition: a transparent root page holding only the caption overlay. Render it with
  `b-hyperframes`' `hf_render.py --format mov` (the wrapper also runs its local-only check) to get a transparent
  video. Do not render it any other way. The caption tweens are written out one by one with plain numbers, not
  in a loop, so the renderer's lint reads every start time and reports no overlap warnings.
- **Grade and mix.** `mux.py` makes one ffmpeg run. The reel's picture gets the grade first, then the caption
  render is laid over it, so the footage is graded and the captions are not. The reel's audio is used as it is:
  no loudness change, and `amix` runs with `normalize=0`, so its level does not move. Effects are delayed to
  their times and mixed under it. Output is H.264 CRF 19, AAC 192k, 48 kHz, stereo.
  **The output is always exactly as long as the reel:** the same number of picture frames at the same frame rate
  (a reel whose frame rate cannot be read, is outside 1 to 120 frames a second, or does not fit its own length, or that holds no frames, is refused with exit 1 and nothing is written). A caption render that is longer or shorter, sound effects or music
  that run past the end, and audio a few milliseconds longer or shorter than the picture never lengthen or
  shorten it. The sound is cut or padded with silence to the picture's length.
- **Check.** `qa.py` confirms the output decodes, has exactly the reel's frame count and frame rate (it compares the same frame number in both files, never the same percentage of two lengths), and has
  video and audio, then saves four frames and writes the stamp. With `--grade off` it also compares the average
  colour of the reel and the output (see Colour). A person or a vision step must still look at the frames:
  captions readable, accent on the emphasis words, nothing covering a face or card, grade subtle, effects
  clearly under the voice.

## Colour

The footage never goes through the renderer. The renderer's browser-to-video round trip (RGB frame, then colour
conversion back to 4:2:0 video) shifts colours a little, and this block does not control it. So the renderer draws
only the captions, and the footage goes through one ffmpeg encode. Measured on a generated neutral gradient: the
footage chroma average moves by 0.0 levels of 255, and a whole-frame check with captions on moved by 0.2 to 0.55
levels (the caption pixels themselves). The colour check runs only when the plan's grade is `off`; with a grade,
the colour is meant to change. `qa.py` needs `--grade`, uses a default tolerance of 1.5 levels, and records the
grade and whether the check ran in `.gate/premium.json`. These numbers are from one generated clip at 1080x1920,
not from real reels. The alpha render's own pixel format is 12-bit 4:4:4, and the caption edges are subsampled
to 4:2:0 in the final encode, as in any 4:2:0 video.

## Text limits

Caption words may hold quotes, angle brackets, ampersands, emoji, slashes, colons, percent signs and
addresses such as `example.com` or `me@example.com`. They are escaped, so none of it can act as markup or code.
A word is refused, with the group and word named, if it holds a web address with a scheme (`https://...`,
`ftp:`, `ws:`), a protocol-relative address (`//host`), a script address (`javascript:`, `vbscript:`, `data:` with
content), or the CSS forms `url(`, `@import` and `image-set(`. The same forms are refused when written as HTML
entities or CSS or `\u` escapes. Why: the render check in `b-hyperframes` refuses any page that holds such an
address, so the caption would stop the render. Write `example.com`, not `https://example.com`. Both
`check_plan.py` and `build_comp.py` apply these rules; `build_comp.py` does not rely on the checker having run.

## Fonts

The renderer contacts a font host for any font family a page names without an `@font-face`, so
`b-hyperframes`' local-only check refuses such a page. This block therefore names no web font.
- Default: the generic `sans-serif` family, bold, upper case. It is the render machine's own system
  font, so the look differs from a named web font and differs a little between machines. Caption fitting adjusts to whatever font is used.
- With `brand.font_file`: the file is copied to `fonts/caption-font.<ext>` and declared once with
  `@font-face` and a local `url()`. The caption uses it, with `sans-serif` behind it. The font is
  third-party: the recipe README must name its licence. No font file is shipped here.

## Safety

- Caption text is data, never markup. It reaches the page only inside one JSON array in which every
  character except ASCII letters, digits and spaces is written as a `\uXXXX` escape. It cannot close a
  script tag, open a tag, break a quote, or look like a web address. The page shows it with `textContent`.
- Colours must be six hex digits; the band top and the length are checked numbers. Placeholders are filled
  in one pass from a fixed list. An unknown or left-over placeholder is an error.
- After filling, `build_comp.py` scans both pages for remote addresses, script loads other than
  `gsap.min.js`, frames, `fetch`, sockets and `@import`, and refuses to write if it finds any.
- ffmpeg and ffprobe are started with argument lists. No shell is used and no script is written.
- Every file and folder the scripts create is written safely: a target that is already a symbolic link
  is refused, a folder in the path that is a link is refused (the work folder itself may be one), the data
  goes to a temporary file made in the target folder and is moved into place with `os.replace`, and the final
  real path is checked to be inside the work folder. Temporary files are removed on every failure path.
  ffmpeg writes to a fresh temporary name, never to the final name. An output that is also an input is refused.
  If a run stops part-way, files already moved into place stay; each one is complete.
- Every ffmpeg and ffprobe input is opened with `-protocol_whitelist file`, so a path can only name a local file.
- An unexpected error prints one fixed line, never a traceback, and exits 1.
- `mux.py` probes its inputs with ffprobe before mixing: `--reel` must hold a video stream and audio, `--captions-mov` must be a video with an alpha channel and the reel's picture size, music must be a plain audio file in a named format. Each input is then opened with its real format named to ffmpeg (mp4 and mov video; wav, mp3, m4a or aac, flac, ogg audio). A file in any other format, such as a playlist or a concat text file, is refused with exit 1; ffmpeg never guesses.
- `build_comp.py` checks every target path first (links, folders in the way, inputs equal to outputs) and writes nothing if any check fails.
- Sound names must be one of the eight. Music must be inside `inputs/`. Output must be inside the work folder.
- Nothing contacts a network. Nothing reads keys or other folders.

## Tools

| Tool | Version | Used by |
|---|---|---|
| Python | 3.10 or newer; run with 3.15 only | all scripts (standard library only) |
| ffmpeg and ffprobe | tested with 8.1; the filters used are long-standing | `mux.py`, `qa.py`, length checks |
| HyperFrames (npm `hyperframes`) | 0.7.5, installed and run by `b-hyperframes`, not here | the caption render |
| GSAP (npm `gsap`) | 3.14.2, fetched by `b-hyperframes/scripts/fetch_gsap.py` | the page timeline. Not included. |
| Node.js | tests only, tested with 25.9.0 | page checks in the tests |

GSAP is third-party code under GreenSock's standard licence (gsap.com/standard-license). It is not
included here: `b-hyperframes` fetches the pinned version, and `build_comp.py` reads it from `vendor/gsap.min.js` unless you pass `--gsap`.

## Network use

None. No script here opens a connection. The pages load only local files. Installing HyperFrames and
fetching the animation library belong to `b-hyperframes`, which declares its own use.

## Proof

A short summary of the limits below. Where this README does not say, it reads "not recorded".

| What | Status | Detail |
|---|---|---|
| Automated tests | 87 tests, as of 2026-11-22 | `python3 -m unittest discover -s blocks/b-reel-premium/test`, from the repository root. |
| Run on which operating systems | macOS (Apple silicon) only; Linux and Windows not run | Python 3.15.2, Node 25.9.0, ffmpeg 8.1 on one Apple-silicon Mac. |
| Run with a real provider account | no provider | No network, no key. |
| Used in a real start-to-finish recipe run | yes, in recipe template runs with stand-in media on macOS, 2026-11-22 | Part of the reel recipe template runs. The media was generated, not a real reel. |

## Tests

No account, no private file, no network. From the repository root:

```text
python3 -m unittest discover -s blocks/b-reel-premium/test -v
```

Tests that need `ffmpeg` or `node` are reported as skipped, by name, when the tool is missing.
They cover hostile caption text, bad colours, unknown sound names, times out of order, a music path
outside `inputs/`, a real mix from generated audio, remote-address scans of the filled pages, `b-hyperframes`' `check_local.py` on hostile and normal fills (it must print PASS), and the sound files' hashes.

## Used by

`r-reels-faceless`, `r-reels-pip`, `r-reels-spotlight` and the two HeyGen variants (`r-reels-pip-heygen`, `r-reels-spotlight-heygen`) (recipe templates live under `recipes/` and are added separately). The reel recipes call these scripts instead of carrying their own plan check or mix script.

## Limits and not proven

- One real render was run by hand (not part of the tests): a 3 s 1080x1920 generated clip, filled
  caption page, `hf_render.py --format mov` to `captions.mov`, then `mux.py` and `qa.py`, with the generic font. The caption
  frame showed the words, the accent pop and the glow. No render with a `brand.font_file`, on a real reel, or with
  long captions has been looked at. Check a rendered frame before trusting a recipe.
- The automated mix tests use tiny 160x284 clips.
- Operating systems: tested on macOS only (Chrome as the render browser). The scripts use no shell and no OS-specific call, but no run on Windows or Linux is recorded.
- The caption layout is built for 1080x1920. The caption band and fit are not adjusted for other sizes.
- A mono reel is upmixed to stereo by ffmpeg and measures about 3 dB lower. Use stereo reels.
- Music shorter than the reel simply ends; longer music is cut at the reel's end. There is no fade or ducking.
- The caption render is a transparent mov (ProRes with alpha). A 3 s clip made 14 MB; expect roughly 5 MB per second, so a 60 s reel makes a file near 300 MB in the work folder. It can be deleted after `mux.py`.
- The transparent caption video is large and slow to make: about 160 MB and about a minute and a half for a 33-second reel in one run on this machine. It is a temporary file in the work folder and can be deleted after the mix.
- The renderer's own lint may still print warnings for a caption page (overlapping tweens at group boundaries, contrast notes, a file-size note). They did not stop a render in the runs so far.
- The renderer's contrast check still prints about 20 contrast warnings on the transparent page; they compare the caption text with the page's own background, not with the footage. Judge legibility on the rendered frame.
- The caption pop uses an animated CSS variable. That works in the pinned HyperFrames render; other renderers are untested.
- The colour check in `qa.py` compares whole-frame averages. It cannot see a local colour change inside the caption pixels.
- The checks cannot judge caption quality (phrase breaks, wording). The bot must.

## Terms used by CFW Social

None are needed here. The plan format above is the whole contract.
