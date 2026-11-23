# b-typing-ui

Two page templates for vertical (1080 by 1920) reel beats, and one safe filler script for each:

- **Typing card**: a chat-style card that types out a prompt, with an optional tag below it.
- **Hook card**: an eyebrow label, up to three big title lines and an optional subhead.

The fillers take their text from a JSON file, escape it, check colours and numbers, and write
the filled page into the work folder. Rendering is not done here (see `../b-hyperframes/`).

```text
 text.json --+
 colour -----+--> typing_fill.py / hook_fill.py --> page.html (work folder)
 duration ---+     escape, check, one pass            |  + gsap.min.js beside it
                                                      v
                                          render with b-hyperframes
```

## Interface

Run from the work folder. Each script has one template, found inside this block. There is no
`--template` option. Unknown options are exit 2.

| Entry point | Arguments | Reads | Writes | Exit codes |
|---|---|---|---|---|
| `scripts/typing_fill.py` | `--out PAGE` `--duration S` `--text-file TEXT.json` `--accent HEX` `[--bg HEX]` `[--fg HEX]` `[--prompt-size PX]` `[--speed N]` `[--variant full\|pip-safe]` `[--wrap standalone\|template]` `[--slot ID]` | the text file, the block's template | `--out` only | 0 written, 2 bad input, unsafe path, or a prompt that cannot finish typing, 3 the block's template is missing or changed |
| `scripts/hook_fill.py` | `--out PAGE` `--duration S` `--text-file TEXT.json` `--accent HEX` `[--bg HEX]` `[--fg HEX]` `[--wrap standalone\|template]` `[--slot ID]` | the text file, the block's template | `--out` only | 0 written, 2, 3 as above |

Text files (a JSON object; every value is text; unknown keys are refused):

| File for | Key | Required | Limit | Default |
|---|---|---|---|---|
| typing | `prompt` | yes | 4000 characters, line breaks kept | |
| typing | `label` | no | 60, one line | `AI chat` |
| typing | `card_label` | no | 60, one line | `The prompt` |
| typing | `bottom_tag` | no | 80, one line; empty hides it | empty |
| hook | `line1` | yes | 40, one line | |
| hook | `eyebrow` | no | 80, one line | empty |
| hook | `line2`, `line3` | no | 40, one line; empty hides the line | empty |
| hook | `subhead` | no | 120, one line; empty hides it | empty |

Other arguments:

- `--duration`: seconds, 0.5 to 300.
- `--accent`, `--bg`, `--fg`: exactly six hex digits, with or without `#`. Anything else is exit 2. `--bg` is the background of the card scene (default `0F172A`, a dark navy) and, in standalone mode, of the page. On the typing card the card, its header and the prompt box are shades of `--bg`. `--fg` is the text colour (default `F8FAFC`); the muted and dim text are shades between `--fg` and `--bg`.
- Contrast: the WCAG contrast ratio of `--fg` against the background (and, on the typing card, against the card and the prompt box) must be at least 3.0, and on the hook card so must the accent against the background (the big lines are accent-coloured). Below 3.0 is exit 2 with the pair and the ratio. Default pair: 17.4.
- `--prompt-size PX` (typing only): prompt text size, 24 to 72. The default is **44** for `full` and **38** for `pip-safe`. The prompt wraps inside the card (about 33 characters per line at 44 px). The box holds about 1300 px of text (`full`) or 640 px (`pip-safe`) and cuts anything longer off at its bottom edge; the typing still runs over the whole prompt, so the cut-off end is typed out of sight. The filler prints a note on stderr when its estimate says the prompt will not fit (about 20 lines at 44 px for `full`, about 10 lines at 38 px for `pip-safe`); shorten the prompt or lower `--prompt-size`.
- `--speed`: typing speed, 0.25 to 4 (default 1.0). Typing starts at 0.5 s and the whole prompt is on screen 0.6 s before the clip ends.
- **Typing time rule (typing only).** The card does not type at a fixed number of characters a second. It always finishes the whole prompt, so the speed depends on the prompt and the beat. Typing starts at 0.5 s. The typing window is `--duration` x 0.88 / `--speed` seconds long (at least 0.5 s), and it never ends later than 0.6 s before the clip ends: that last 0.6 s is the end pause with the whole prompt on screen. At the default speed of 1.0 a prompt of 100 characters in a 9 s beat is typed in about 7.4 s, about 13 characters a second. A **higher** `--speed` makes the window shorter and the typing faster; a lower one makes it slower. A long prompt in a short beat is therefore typed too fast to read. `typing_fill.py` refuses it with exit 2 and writes nothing when the typing would be faster than **30 characters a second** (this block's own limit, about six words a second). The message gives the minimum `--duration`, and names a lower `--speed` as a fix when that can help. Example: 300 characters need 10 s of typing, so the shortest beat is 12.0 s at speed 1.0. Fix it with a shorter prompt, a longer beat, or a lower `--speed`. Characters are counted as the page counts them, with line breaks included.
- `--variant pip-safe` (typing only): moves the card up so all content is in the top half of the frame, for recipes that put a speaker video below.
- `--wrap standalone` (default) writes a complete page. `--wrap template` keeps the `<template>` wrapper so the scene can be used as a sub-composition.
- `--slot ID` gives the scene its own composition id and prefixes its element ids and classes (`ID-ts-card`), so several scenes can share one page. ID is lower-case letters, digits and hyphens, starting with a letter, 24 characters at most.

Both scripts print one line on stdout, and a note on stderr if `gsap.min.js` is not yet beside the page.

## Where the caption band sits

Recipes that burn captions into the reel place a caption band 260 px tall. Its top edge is the `--cap-top` setting of `b-reel-premium`, about 1180 for a full-frame speaker, 1020 when a card sits at the bottom, and 1450 for a motion-graphics layout. Two places on these cards fall inside that band:

| Card | Key | Where it sits | When captions are on |
|---|---|---|---|
| hook | `subhead` | y 1060 to about 1170 (up to about 1230 on two lines) | leave empty |
| typing, `pip-safe` | `bottom_tag` | y 980 to about 1010 | leave empty |
| typing, `full` | `bottom_tag` | y about 1800 to 1840 | fine unless the band reaches below about 1760 (a `--cap-top` above 1500) |

The typing card's prompt box ends no lower than y about 1700 (`full`) or 1040 (`pip-safe`), so with the default sizes a long prompt can run into a band at 1180 or 1450: keep prompts short, or check a frame.

## Text limits

The render check in `b-hyperframes` (`check_local.py`) is a text scan. It refuses any page that contains an
address, even as plain text, and it also reads the page after undoing HTML entities and CSS escapes, so it
cannot tell a sentence from a link. The fillers therefore refuse the same text up front, with exit 2, naming
the key, and write nothing:

- a web address with a scheme: `http:`, `https:`, `ws:`, `wss:`, `ftp:` (even without the slashes), and any other `name://`
- a protocol-relative address: `//host`
- a script address: `javascript:`, `vbscript:`, or `data:` followed by a type such as `text/html`
- the CSS forms `url(`, `@import` and `image-set(`

Write `example.com`, not `https://example.com`. Plain `a/b`, `1:2`, `me@example.com`, `example.com/path`,
`C:\folder`, quotes, angle brackets, ampersands, emoji and `50% off (today)` are fine. The escaping described
below is still applied to everything that is accepted. A few programming words that the check also refuses
anywhere in a page (`WebSocket`, `innerHTML`, `XMLHttpRequest`, `document.write` and similar) are accepted:
one letter of each is written as an entity or `\u` escape, so the page shows the same text.

## How text is kept safe

- Characters refused with exit 2, naming the key: lone surrogates, control characters (NUL, bell, escape, delete and the C1 range), and text-direction controls (U+200E, U+200F, U+202A to U+202E, U+2066 to U+2069). Tab and line breaks are allowed only in `prompt`; in every other key they become one space. A `--slot` rename is done on the bare template before any text goes in, so text that contains `.ts-` or `#ts-` is left as written.

- Text enters a page in one way. Hook text and the typing labels go in as HTML text, escaped: `<`, `>`, `&`, quotes, braces, backslash, slash, colon, parentheses and `@` become entities. They display the same, and no value can look like an address, a `url()` or an import to the local-only check.
- The typed prompt is the one value in a script string. Letters, digits, spaces and `. , ; ! ? - _` stay; every other character is written as a `\uXXXX` escape. The string is the exact typed text, with no decoding step in the page. It is shown with `textContent`.
- Placeholders are filled in one pass from a fixed list. Text that looks like a placeholder is never filled again. A placeholder left over is an error.
- The tests fill both templates with hostile text (tags, quotes, `</script>`, event handlers, backslashes, line separators, addresses) and check that the page gets the same elements and the same script code as with harmless text.
- Colours must be six hex digits. Numbers must be finite and in range. The slot name is checked against a short pattern.
- Files are read and written only if their real path, links followed, is inside the work folder. The page is written to a fresh temporary file in the target folder and renamed into place. A target that is a link, a parent folder that is a link pointing outside, and an output that is the same file as the text file are all refused (exit 2). An unexpected error prints one fixed line and exits 1, with no stack trace. The templates come from this block, never from the command line.

## The animation library and where it must sit

The templates load `gsap.min.js` from beside the filled page. It is not in this repository. GSAP is
third-party code under GreenSock's standard licence (gsap.com/standard-license). The filler neither copies
nor fetches it. Get it once per work folder with the `b-hyperframes` block, then copy it next to each page:

```text
python3 "$BLOCKS_DIR/b-hyperframes/scripts/fetch_gsap.py" --outdir vendor     # writes vendor/gsap.min.js
cp vendor/gsap.min.js comp/gsap.min.js                                        # beside comp/index.html
python3 "$BLOCKS_DIR/b-typing-ui/scripts/typing_fill.py" --out comp/index.html ...
python3 "$BLOCKS_DIR/b-hyperframes/scripts/check_local.py" --comp comp        # prints LOCAL_ONLY: PASS
python3 "$BLOCKS_DIR/b-hyperframes/scripts/hf_render.py" --comp comp --out out.mp4 --quiet   # runs the check first
```

A page used as a composition's `index.html` is the standalone output. For a scene inside a larger
composition, use `--wrap template` (and `--slot`) and place it in that composition's page.

## Fonts

The pages name the fonts Inter, JetBrains Mono and Oswald. Each is declared once with
`@font-face { font-family: "Name"; src: local("Name"); }`. HyperFrames asks a font service on the network
for any named family that has no `@font-face`, and the local-only check refuses such a page; with the
declaration, nothing is requested. The `local()` source means the font must be installed on the machine
that renders. No font file is bundled (the fonts are under the SIL Open Font Licence). If a font is not
installed the renderer falls back to the generic family each rule lists (`sans-serif` or `monospace`), so the
text is still there but the letter shapes and widths differ from the named web font; check a render.

## Network use

None. The scripts use the Python standard library, call no network function, and start no other
program. The templates load nothing remote: the only external reference is `gsap.min.js` beside the
page. Each filler refuses a template that holds a remote address, an iframe, a link tag, an import,
or any script source other than `gsap.min.js`.

## Tools

Python 3.10 or newer; run with 3.15 only (standard library only). Node.js 22 or newer for the tests' script checks
(skipped, and reported as skipped, if Node is missing). The tests also need the `b-hyperframes` block beside this one. To render: the tools of `b-hyperframes`.
Fonts Inter, JetBrains Mono and Oswald installed locally (see Fonts).

## Used by

`r-reels-faceless`, `r-reels-pip`, `r-reels-spotlight` and the two HeyGen variants (`r-reels-pip-heygen`, `r-reels-spotlight-heygen`) (recipe templates live under `recipes/` and are added separately).
In the spotlight recipes the typing card is a takeover scene, made with `--wrap template` and `--slot`.

## Proof

A short summary of the limits below. Where this README does not say, it reads "not recorded".

| What | Status | Detail |
|---|---|---|
| Automated tests | 58 tests, as of 2026-11-22 | `python3 -m unittest discover -s blocks/b-typing-ui/test`, from the repository root. They do not render the pages. |
| Run on which operating systems | macOS (Apple silicon) only; Linux and Windows not run | Python 3.15.2, Node 25.9.0, ffmpeg 8.1 on one Apple-silicon Mac. |
| Run with a real provider account | no provider | No network, no key. |
| Used in a real start-to-finish recipe run | yes, in recipe template runs with stand-in media on macOS, 2026-11-22 | Part of the reel recipe template runs. The media was generated, not a real reel. |

## Tests

```text
python3 -m unittest discover -s blocks/b-typing-ui/test -v
```

No account, no private file, no network. They cover hostile-text escaping in both fillers, the typed
text coming back exactly, scripts that parse, bad colours, writes only inside the work folder, text
files outside it, a damaged block, and the local-only check on the templates and filled pages.

## Limits

- The default look of the typing card is a neutral "AI chat" card with an "AI" mark. It does not imitate any product. Change `label` and `card_label` as the brand needs, but do not put another company's name or logo on it.
- The renderer's validator prints contrast warnings for the typing card's dim text. They did not stop a render in the runs so far.
- The tests do not render the pages. They prove the pages are well formed and inert; they do not prove how they look in a render.
- Long text wraps or is cut by the card; the limits above keep it inside, but check a render.
